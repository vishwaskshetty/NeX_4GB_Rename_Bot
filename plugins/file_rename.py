import os
import sys
import time
import math
import html
import shutil
import asyncio
import traceback
import inspect
import gc
import random
import re
import mimetypes
import warnings
import humanize
import pytz
from datetime import datetime
from PIL import Image
import logging

logger = logging.getLogger(__name__)
log = logger

warnings.filterwarnings("ignore", message=".*reply_to_message_id.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pyrogram")

from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply,
    InputMediaPhoto,
    CallbackQuery,
    ReplyParameters
)
from pyrogram.file_id import FileId
try:
    from pyrogram import StopTransmission
except ImportError:
    from pyrogram.errors import StopTransmission

from helper.fast_transfer import (
    fast_download,
    fast_upload,
    zero_disk_turbo_pipe,
    send_input_file_big,
    _TRANSFER_SEMAPHORE,
    _cleanup_memory
)
from helper.tg_virtual_disk import (
    TelegramVirtualDisk,
    get_virtual_disk_channel,
    stage_to_virtual_disk,
    fetch_from_virtual_disk,
    delete_from_virtual_disk,
    stream_virtual_disk_slice
)

from helper.utils import (
    progress_for_pyrogram,
    convert,
    humanbytes,
    CANCEL_REQUESTS,
    USER_STATE,
    to_small_caps,
    safe_reply_params,
    edit_message_content,
    sanitize_secrets,
    is_duplicate_update,
    prepare_crisp_thumbnail,
    get_private_mode_markup
)
from helper.ffmpeg_utils import (
    inject_metadata,
    generate_sample_video,
    generate_screenshots,
    get_video_duration_and_dims,
    apply_video_watermark
)
from helper.database import db, TIER_LIMITS
from config import Config, Txt, parse_channel_id
from bot import app_4gb

# Global concurrency queue lock - Max 10 heavy operations at once
RENAME_SEMAPHORE = asyncio.Semaphore(10)

# 2-Task Concurrency Semaphore for heavy 4 GB multitasking (imported from helper.fast_transfer)
_TRANSFER_WAITING_TASKS: list[str] = []

# Per-user active task tracking & pre-rename extras cache
ACTIVE_USER_TASKS = {}
USER_QUEUE = {}
PENDING_MEDIA_EXTRAS = {}
ACTIVE_WORK_DIRS = set()
USER_FILE_CONTEXT = {}
USER_RENAME_CACHE = {}


def get_optimal_work_dir(user_id: int, file_size: int = 0, is_remux_needed: bool = False) -> str:
    """
    Routes small files (<= 1.8GB) to high-speed RAM-disk /dev/shm if sufficient free space (> 2.0x file size).
    Routes all large files (1.8GB - 4.0GB) directly to fast NVMe SSD (downloads/...) with 64MB buffer
    so /dev/shm never exhausts memory mid-transfer.
    """
    ts = int(time.time())
    pid = os.getpid()
    sub = f"{user_id}_{ts}_{pid}"
    max_shm_size = int(1.8 * 1024 * 1024 * 1024)  # 1.8 GB max for RAM-disk
    if os.name != 'nt' and os.path.exists('/dev/shm') and (file_size <= max_shm_size or file_size == 0):
        try:
            shm_usage = shutil.disk_usage('/dev/shm')
            multiplier = 2.2 if is_remux_needed else 2.0
            needed = int(file_size * multiplier) if file_size > 0 else (100 * 1024 * 1024)
            if shm_usage.free > needed:
                path = f"/dev/shm/nex_tasks/{sub}"
                os.makedirs(path, exist_ok=True)
                return path
        except Exception:
            pass
    fallback = f"downloads/{sub}"
    os.makedirs(fallback, exist_ok=True)
    return fallback


def is_active_task_path(target_path: str) -> bool:
    """Checks whether a given file or directory is part of an ongoing rename task."""
    try:
        abs_target = os.path.abspath(target_path)
        for active_dir in list(ACTIVE_WORK_DIRS):
            if abs_target == active_dir or abs_target.startswith(active_dir + os.sep):
                return True
    except Exception:
        pass
    return False


def get_full_mime_type(f: str) -> str:
    mime, _ = mimetypes.guess_type(f)
    return mime or "application/octet-stream"


def apply_cleaner(filename: str, clean_words: str, replace_words: str) -> str:
    base_name, ext = os.path.splitext(filename)

    # 1. Apply replacement words (old:new)
    if replace_words:
        for pair in replace_words.split(","):
            pair = pair.strip()
            if ":" in pair:
                old, new = pair.split(":", 1)
                old = old.strip()
                new = new.strip()
                if old:
                    base_name = base_name.replace(old, new)

    # 2. Apply clean words (removal)
    if clean_words:
        for word in clean_words.split(","):
            word = word.strip()
            if word:
                base_name = base_name.replace(word, "")

    # Clean up redundant whitespace and underscores
    base_name = re.sub(r'[\s_]+', ' ', base_name).strip()
    if not base_name:
        base_name = "Cleaned_File"
    return f"{base_name}{ext}"


def apply_prefix_suffix(filename: str, prefix: str, suffix: str) -> str:
    base_name, ext = os.path.splitext(filename)
    base_name = base_name.strip()
    if prefix and suffix:
        return f"{prefix.strip()} {base_name} {suffix.strip()}{ext}"
    elif prefix:
        return f"{prefix.strip()} {base_name}{ext}"
    elif suffix:
        return f"{base_name} {suffix.strip()}{ext}"
    return filename


@Client.on_message(filters.private & (filters.document | filters.audio | filters.video) & filters.incoming & ~filters.bot & ~filters.via_bot)
async def rename_start(client, message):
    if not message.from_user or message.from_user.is_bot:
        return
    user_id = message.from_user.id
    if Config.PRIVATE_MODE and user_id not in Config.ADMIN:
        await message.reply_text(
            Txt.PRIVATE_MODE_TXT,
            reply_markup=get_private_mode_markup(),
            quote=True
        )
        return
    if message.chat and await is_duplicate_update(f"media_{message.chat.id}_{message.id}"):
        return
    file = message.document or message.video or message.audio
    filename = file.file_name if file.file_name else "Unknown_File"
    file_id = file.file_id
    file_size = file.file_size
    filesize = humanize.naturalsize(file_size)
    
    try:
        dcid = FileId.decode(file_id).dc_id
    except Exception:
        dcid = "Unknown"

    _, ext = os.path.splitext(filename)
    file_extension = ext.replace(".", "") if ext else "unknown"
    mime_type = get_full_mime_type(filename)
    user_id = message.from_user.id
    try:
        asyncio.create_task(db.update_user_info(message.from_user))
    except Exception:
        pass

    username = message.from_user.username or "No Username"
    user_mention = message.from_user.mention
    user_link = f"<a href='tg://openmessage?user_id={user_id}'>Click Here</a>"
    curr = datetime.now(pytz.timezone("Asia/Kolkata"))
    date = curr.strftime('%d %B, %Y')
    time_str = curr.strftime('%I:%M:%S %p')

    # Backup to files channel if configured
    if Config.FILES_CHANNEL and Config.FILES_CHANNEL != 0:
        try:
            caption = (
                f"<b>NeX 4GB Rename Bot - New File Received</b>\n\n"
                f"<b>Title :</b> <code>{filename}</code>\n"
                f"<b>Size :</b> <code>{filesize}</code>\n\n"
                f"<b>User Name :</b> @{username}\n"
                f"<b>User Link :</b> {user_link}\n"
                f"<b>User Mention :</b> {user_mention}\n"
                f"<b>User ID :</b> <code>{user_id}</code>\n\n"
                f"<b>Date :</b> <code>{date}</code>\n"
                f"<b>Time :</b> <code>{time_str}</code>\n\n"
                f"⚡ <b>Powered by :</b> @Nex_bots"
            )
            await client.send_cached_media(chat_id=int(Config.FILES_CHANNEL), file_id=file_id, caption=caption)
        except Exception:
            pass

    # Check 3-Tier Limits (Max File Size & Daily Bandwidth)
    prem_info = await db.get_premium_info(user_id)
    user_tier = prem_info.get("tier", 0)
    tier_limits = TIER_LIMITS.get(user_tier, TIER_LIMITS[0])
    max_size = tier_limits["max_file_size"]
    daily_limit = tier_limits["daily_bytes"]

    # Cache active media file context for user
    USER_FILE_CONTEXT[user_id] = {
        "file_msg_id": message.id,
        "chat_id": message.chat.id,
        "filename": filename,
        "file_size": file_size,
        "file_id": file_id
    }

    # 2GB+ File Cap for Free Users
    if file_size > (2 * 1024 * 1024 * 1024) and user_tier == 0 and user_id not in Config.ADMIN:
        has_trial = await db.has_claimed_trial(user_id)
        bot_settings = await db.get_bot_settings()
        row = [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans")]
        if not has_trial and bot_settings.get("trial_enabled", True):
            row.insert(0, InlineKeyboardButton("🎁 Claim 3-Day Free 4GB Trial", callback_data="claim_trial_cb"))
        return await message.reply_text(
            f"⚠️ <b>2GB Free Tier Limit!</b>\n\n"
            f"📦 <b>Your File:</b> <code>{humanbytes(file_size)}</code>\n"
            f"🆓 <b>Free Limit:</b> <code>2.00 GB max per file</code>\n"
            f"💎 <b>Premium Limit:</b> <code>4.00 GB max per file</code>\n\n"
            f"<i>Upgrade to Premium to rename files up to 4GB!</i>",
            reply_markup=InlineKeyboardMarkup([
                row,
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ]),
            quote=True
        )

    if file_size > max_size and user_id not in Config.ADMIN:
        await message.reply_text(
            f"⭐ <b>File Size Limit Exceeded!</b>\n\n"
            f"Your plan (<b>{prem_info['plan_name']}</b>) allows files up to <b>{humanbytes(max_size)}</b>.\n"
            f"Upgrade to Premium for full 4GB files!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans")],
                [InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")]
            ]),
            quote=True
        )
        return

    # Check daily bandwidth
    user_usage = await db.get_user_usage(user_id)
    daily_used = user_usage.get("daily_bytes", 0)
    if (daily_used + file_size) > daily_limit and user_id not in Config.ADMIN:
        await message.reply_text(
            f"⚠️ <b>Daily Bandwidth Limit Exceeded!</b>\n\n"
            f"Plan: <b>{prem_info['plan_name']}</b>\n"
            f"Used Today: <b>{humanbytes(daily_used)}</b> / <b>{humanbytes(daily_limit)}</b>\n\n"
            f"Upgrade your plan for higher daily limits or unlimited transfers!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans")],
                [InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")]
            ]),
            quote=True
        )
        return

    # Check 4GB Secondary Client
    client_4gb = getattr(client, "app_4gb", None) or app_4gb
    if file_size > (2 * 1024 * 1024 * 1024) and not client_4gb:
        await message.reply_text(
            "🚫 <b>Files larger than 2GB require 4GB Premium Mode!</b>\n\n"
            "<i>Telegram restricts standard bot tokens to 2GB uploads.\n"
            "To enable 4GB uploads, configure <code>STRING_SESSION</code> with a Telegram Premium account.\n"
            "Need help? Contact @NexCRSupportbot.</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")]]),
            quote=True
        )
        return

    is_video = bool(
        message.video
        or (message.document and message.document.mime_type and message.document.mime_type.startswith("video/"))
        or (filename.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.m4v')))
    )

    media_info_text = (
        "<b>◈ NᴇX Mᴇᴅɪᴀ Iɴꜰᴏ 🗂️</b>\n"
        "\n"
        f"▸ <b>Fɪʟᴇɴᴀᴍᴇ :</b> <code>{filename}</code>\n"
        f"▸ <b>Sɪᴢᴇ :</b> <code>{filesize}</code>\n"
        f"▸ <b>Tʏᴘᴇ :</b> <code>.{file_extension}</code> ({mime_type})\n"
        f"▸ <b>DC ID :</b> <code>{dcid}</code>\n"
        "\n"
        "<i>Select an action below:</i>"
    )

    if is_video:
        buttons = [
            [
                InlineKeyboardButton("✏️ Rᴇɴᴀᴍᴇ Fɪʟᴇ", callback_data=f"rename_{message.id}"),
                InlineKeyboardButton("⚡ Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ", callback_data=f"auto_rename_{message.id}")
            ],
            [
                InlineKeyboardButton("🎧 Eᴅɪᴛ Tʀᴀᴄᴋꜱ (Aᴜᴅɪᴏ / Sᴜʙ)", callback_data=f"inspect_tracks_{message.id}")
            ],
            [
                InlineKeyboardButton("🎬 Sᴀᴍᴘʟᴇ Vɪᴅᴇᴏ", callback_data=f"extract_sample_only_{message.id}"),
                InlineKeyboardButton("📸 Sᴄʀᴇᴇɴꜱʜᴏᴛꜱ", callback_data=f"extract_ss_only_{message.id}")
            ],
            [
                InlineKeyboardButton("🎵 Aᴜᴅɪᴏ / Sᴜʙꜱ", callback_data=f"extract_streams_{message.id}"),
                InlineKeyboardButton("🔄 MKV ⇄ MP4", callback_data=f"remux_action_{message.id}")
            ],
            [
                InlineKeyboardButton("💧 Wᴀᴛᴇʀᴍᴀʀᴋ", callback_data=f"watermark_action_{message.id}"),
                InlineKeyboardButton("⚙️ Sᴇᴛᴛɪɴɢꜱ", callback_data="open_settings")
            ],
            [
                InlineKeyboardButton("✖️ Cᴀɴᴄᴇʟ", callback_data="close")
            ]
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("✏️ Rᴇɴᴀᴍᴇ Fɪʟᴇ", callback_data=f"rename_{message.id}"),
                InlineKeyboardButton("⚡ Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ", callback_data=f"auto_rename_{message.id}")
            ],
            [
                InlineKeyboardButton("⚙️ Sᴇᴛᴛɪɴɢꜱ", callback_data="open_settings"),
                InlineKeyboardButton("✖️ Cᴀɴᴄᴇʟ", callback_data="close")
            ]
        ]

    reply_kwargs = safe_reply_params(message.id)
    await message.reply_text(
        text=media_info_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        **reply_kwargs
    )


@Client.on_callback_query(filters.regex(r'^auto_rename(?:_(\d+))?$'))
async def auto_rename_handler(client, update: CallbackQuery):
    user_id = update.from_user.id
    target_id = (
        (update.matches[0].group(1) if update.matches and update.matches[0].groups() and update.matches[0].group(1) else None)
        or update.message.reply_to_message_id
        or getattr(update.message.reply_to_message, "id", None)
        or USER_FILE_CONTEXT.get(user_id, {}).get("file_msg_id")
    )
    reply_msg = None
    if target_id:
        try:
            reply_msg = await client.get_messages(update.message.chat.id, int(target_id))
        except Exception:
            pass
    if not reply_msg or not (reply_msg.document or reply_msg.video or reply_msg.audio):
        reply_msg = update.message.reply_to_message

    if not reply_msg or not (reply_msg.document or reply_msg.video or reply_msg.audio):
        return await update.message.edit("❌ Original file message not found! Please send your file again.")

    file = reply_msg.document or reply_msg.video or reply_msg.audio
    orig_filename = file.file_name or "file.mkv"
    clean_words = await db.get_clean_words(user_id)
    replace_words = await db.get_replace_words(user_id)
    cleaned_name = apply_cleaner(orig_filename, clean_words, replace_words)

    prefix = await db.get_prefix(user_id)
    suffix = await db.get_suffix(user_id)
    final_name = apply_prefix_suffix(cleaned_name, prefix, suffix)

    upload_mode = await db.get_upload_mode(user_id)
    if upload_mode in ["Document", "Video", "Audio"]:
        await route_to_extras_or_execute(client, update, final_name, upload_mode.lower(), reply_msg)
        return

    buttons = [[InlineKeyboardButton("📁 Document", callback_data=f"upload_document_{reply_msg.id}")]]
    if reply_msg.video or (reply_msg.document and final_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))):
        buttons.append([InlineKeyboardButton("🎥 Video", callback_data=f"upload_video_{reply_msg.id}")])
    elif reply_msg.audio or (reply_msg.document and final_name.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg'))):
        buttons.append([InlineKeyboardButton("🎵 Audio", callback_data=f"upload_audio_{reply_msg.id}")])

    await update.message.edit_text(
        text=f"⚡ <b>Auto Cleaned & Formatted Name:</b>\n`{final_name}`\n\n<b>Select Output Format:</b>",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex(r'^rename(?:_(\d+))?$'))
async def rename_handler(client, update: CallbackQuery):
    user_id = update.from_user.id
    file_msg_id = (
        (update.matches[0].group(1) if update.matches and update.matches[0].groups() and update.matches[0].group(1) else None)
        or update.message.reply_to_message_id
        or getattr(update.message.reply_to_message, "id", None)
        or USER_FILE_CONTEXT.get(user_id, {}).get("file_msg_id")
    )
    USER_RENAME_CACHE[user_id] = {
        "file_msg_id": file_msg_id,
        "chat_id": update.message.chat.id
    }
    chat_id = update.message.chat.id
    try:
        await update.message.delete()
    except Exception:
        pass

    reply_kwargs = safe_reply_params(file_msg_id)
    await client.send_message(
        chat_id=chat_id,
        text=(
            "<b>◈ ᴘʟᴇᴀꜱᴇ ᴇɴᴛᴇʀ ɴᴇᴡ ꜰɪʟᴇ ɴᴀᴍᴇ...</b>\n\n"
            "<i>(You can omit the extension; the original extension will be preserved automatically.)</i>"
        ),
        reply_markup=ForceReply(True),
        **reply_kwargs
    )


# ==================== STANDALONE SAMPLE & SCREENSHOTS ONLY ====================

@Client.on_callback_query(filters.regex(r"^extract_sample_only(?:_(\d+))?$"))
async def extract_sample_only_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    target_id = (
        (query.matches[0].group(1) if query.matches and query.matches[0].groups() and query.matches[0].group(1) else None)
        or USER_FILE_CONTEXT.get(user_id, {}).get("file_msg_id")
    )
    file_msg = None
    if target_id:
        try:
            file_msg = await client.get_messages(query.message.chat.id, int(target_id))
        except Exception:
            pass
    if not file_msg:
        file_msg = query.message.reply_to_message

    if not file_msg or not (file_msg.video or file_msg.document):
        return await query.answer("❌ Media message could not be retrieved!", show_alert=True)

    file = file_msg.video or file_msg.document
    filename = file.file_name or "video.mp4"
    file_size = file.file_size or 0

    user_tier = (await db.get_premium_info(user_id)).get("tier", 0)
    bot_settings = await db.get_bot_settings()
    max_active = bot_settings.get("prem_concurrency", 4) if (user_tier > 0 or user_id in Config.ADMIN) else bot_settings.get("free_concurrency", 1)
    if ACTIVE_USER_TASKS.get(user_id, 0) >= max_active:
        return await query.answer(f"⚠️ You already have {max_active} active task(s)! Please wait for them to finish.", show_alert=True)

    ACTIVE_USER_TASKS[user_id] = ACTIVE_USER_TASKS.get(user_id, 0) + 1
    ms = await edit_message_content(query.message, "<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴀᴍᴘʟᴇ ᴄʟɪᴘ... 📥</b>")
    if not ms:
        ms = await query.message.reply_text("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴀᴍᴘʟᴇ ᴄʟɪᴘ... 📥</b>")

    work_dir = get_optimal_work_dir(user_id, file_size)
    ACTIVE_WORK_DIRS.add(os.path.abspath(work_dir))
    input_path = os.path.join(work_dir, filename)
    base_name, _ = os.path.splitext(filename)
    sample_path = os.path.join(work_dir, f"sample_{base_name}.mp4")

    try:
        start_time = time.time()
        dl_ok = False
        try:
            dl_res = await fast_download(
                client=client,
                message_or_file=file_msg,
                file_path=input_path,
                progress=progress_for_pyrogram,
                progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴀᴍᴘʟᴇ... 📥</b>", ms, start_time, client, user_tier)
            )
            dl_ok = bool(dl_res and os.path.exists(input_path) and os.path.getsize(input_path) > 0)
        except Exception:
            dl_ok = False

        if not dl_ok:
            await client.download_media(
                message=file_msg,
                file_name=input_path,
                progress=progress_for_pyrogram,
                progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴀᴍᴘʟᴇ (ꜰᴀʟʟʙᴀᴄᴋ)... 📥</b>", ms, start_time, client, user_tier)
            )

        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
            await ms.edit("❌ Download failed. Please try again.")
            return

        await ms.edit("<b>◈ ɢᴇɴᴇʀᴀᴛɪɴɢ 30ꜱ ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ... 🎬</b>")
        duration, width, height = await get_video_duration_and_dims(input_path)
        ok = await generate_sample_video(input_path, sample_path, total_duration=duration or 300, sample_sec=30, start_mode="auto")
        if not ok or not os.path.exists(sample_path):
            await ms.edit("❌ Failed to generate sample video.")
            return

        up_start = time.time()
        await ms.edit("<b>◈ ᴜᴘʟᴏᴀᴅɪɴɢ ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ... 🚀</b>")
        s_dur, s_w, s_h = await get_video_duration_and_dims(sample_path)
        await client.send_video(
            chat_id=user_id,
            video=sample_path,
            caption=f"🎬 <b>Sample Video (30s)</b>\n📁 <code>{filename}</code>\n\n⚡ @Nex_bots",
            duration=s_dur or 30,
            width=s_w or 1280,
            height=s_h or 720,
            supports_streaming=True,
            progress=progress_for_pyrogram,
            progress_args=("<b>◈ ᴜᴘʟᴏᴀᴅɪɴɢ ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ... 🚀</b>", ms, up_start, client, user_tier)
        )
        try:
            await ms.delete()
        except Exception:
            pass
        # Auto-delete original incoming/forwarded file message to prevent chat clutter
        try:
            if 'file_msg' in locals() and file_msg:
                await file_msg.delete()
        except Exception:
            pass
        try:
            await db.increment_stat(user_id, "total_samples_generated", 1)
        except Exception:
            pass
    except Exception as e:
        await ms.edit(f"❌ <b>Error:</b> <code>{e}</code>")
    finally:
        ACTIVE_USER_TASKS[user_id] = max(0, ACTIVE_USER_TASKS.get(user_id, 1) - 1)
        ACTIVE_WORK_DIRS.discard(os.path.abspath(work_dir))
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)


@Client.on_callback_query(filters.regex(r"^extract_ss_only(?:_(\d+))?$"))
async def extract_ss_only_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    target_id = (
        (query.matches[0].group(1) if query.matches and query.matches[0].groups() and query.matches[0].group(1) else None)
        or USER_FILE_CONTEXT.get(user_id, {}).get("file_msg_id")
    )
    file_msg = None
    if target_id:
        try:
            file_msg = await client.get_messages(query.message.chat.id, int(target_id))
        except Exception:
            pass
    if not file_msg:
        file_msg = query.message.reply_to_message

    if not file_msg or not (file_msg.video or file_msg.document):
        return await query.answer("❌ Media message could not be retrieved!", show_alert=True)

    file = file_msg.video or file_msg.document
    filename = file.file_name or "video.mp4"
    file_size = file.file_size or 0

    user_tier = (await db.get_premium_info(user_id)).get("tier", 0)
    bot_settings = await db.get_bot_settings()
    max_active = bot_settings.get("prem_concurrency", 4) if (user_tier > 0 or user_id in Config.ADMIN) else bot_settings.get("free_concurrency", 1)
    if ACTIVE_USER_TASKS.get(user_id, 0) >= max_active:
        return await query.answer(f"⚠️ You already have {max_active} active task(s)! Please wait for them to finish.", show_alert=True)

    ACTIVE_USER_TASKS[user_id] = ACTIVE_USER_TASKS.get(user_id, 0) + 1
    ms = await edit_message_content(query.message, "<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 📥</b>")
    if not ms:
        ms = await query.message.reply_text("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 📥</b>")

    work_dir = get_optimal_work_dir(user_id, file_size)
    ACTIVE_WORK_DIRS.add(os.path.abspath(work_dir))
    input_path = os.path.join(work_dir, filename)
    ss_dir = os.path.join(work_dir, "screenshots")

    try:
        start_time = time.time()
        dl_ok = False
        try:
            dl_res = await fast_download(
                client=client,
                message_or_file=file_msg,
                file_path=input_path,
                progress=progress_for_pyrogram,
                progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 📥</b>", ms, start_time, client, user_tier)
            )
            dl_ok = bool(dl_res and os.path.exists(input_path) and os.path.getsize(input_path) > 0)
        except Exception:
            dl_ok = False

        if not dl_ok:
            await client.download_media(
                message=file_msg,
                file_name=input_path,
                progress=progress_for_pyrogram,
                progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰᴏʀ ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ (ꜰᴀʟʟʙᴀᴄᴋ)... 📥</b>", ms, start_time, client, user_tier)
            )

        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
            await ms.edit("❌ Download failed. Please try again.")
            return

        await ms.edit("<b>◈ ᴇxᴛʀᴀᴄᴛɪɴɢ 5 ʜᴅ ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 📸</b>")
        duration, _, _ = await get_video_duration_and_dims(input_path)
        shots = await generate_screenshots(input_path, ss_dir, total_duration=duration or 300, count=5)
        if not shots:
            await ms.edit("❌ Failed to generate screenshots.")
            return

        await ms.edit("<b>◈ ᴜᴘʟᴏᴀᴅɪɴɢ ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 🚀</b>")
        media_group = []
        for i, shot in enumerate(shots):
            caption = f"📸 <b>HD Screenshots (5 Frames)</b>\n📁 <code>{filename}</code>\n\n⚡ @Nex_bots" if i == 0 else ""
            media_group.append(InputMediaPhoto(shot, caption=caption))

        await client.send_media_group(chat_id=user_id, media=media_group)
        try:
            await ms.delete()
        except Exception:
            pass
        # Auto-delete original incoming/forwarded file message to prevent chat clutter
        try:
            if 'file_msg' in locals() and file_msg:
                await file_msg.delete()
        except Exception:
            pass
        try:
            await db.increment_stat(user_id, "total_screenshots_generated", len(shots))
        except Exception:
            pass
    except Exception as e:
        await ms.edit(f"❌ <b>Error:</b> <code>{e}</code>")
    finally:
        ACTIVE_USER_TASKS[user_id] = max(0, ACTIVE_USER_TASKS.get(user_id, 1) - 1)
        ACTIVE_WORK_DIRS.discard(os.path.abspath(work_dir))
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)


@Client.on_callback_query(filters.regex(r"^extract_streams(?:_(\d+))?$"))
async def extract_streams_cb(client, query: CallbackQuery):
    await query.answer("Opening Stream Inspector... 🎵")
    t_id = query.matches[0].group(1) if query.matches and query.matches[0].groups() and query.matches[0].group(1) else ""
    cb_target = f"inspect_tracks_{t_id}" if t_id else "inspect_tracks"
    await query.message.reply_text(
        "<b>◈ Sᴛʀᴇᴀᴍ Iɴꜱᴘᴇᴄᴛᴏʀ 🎵</b>\n"
        "\n"
        "▸ Tap <b>🎧 Interactive Track Manager</b> to toggle audio/sub tracks,\n"
        "or reply to the video file with:\n"
        "• <code>/streams</code> : View all audio & subtitle tracks\n"
        "• <code>/streams strip_subs</code> : Remove all subtitles\n"
        "• <code>/streams audio 1</code> : Keep only audio stream 1",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎧 Interactive Track Manager", callback_data=cb_target)],
            [InlineKeyboardButton("❌ Cʟᴏꜱᴇ", callback_data="close")]
        ])
    )


@Client.on_callback_query(filters.regex(r"^remux_action(?:_(\d+))?$"))
async def remux_action_cb(client, query: CallbackQuery):
    await query.answer("Opening Container Remuxer... 🔄")
    await query.message.reply_text(
        "<b>◈ Lᴏꜱꜱʟᴇꜱꜱ Rᴇᴍᴜxᴇʀ 🔄</b>\n"
        "\n"
        "▸ Reply to the video file with:\n"
        "• <code>/remux</code> : Convert MKV ⇄ MP4 losslessly\n"
        "(Lossless conversion in seconds with zero re-encoding!)",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cʟᴏꜱᴇ", callback_data="close")]])
    )


@Client.on_callback_query(filters.regex(r"^watermark_action(?:_(\d+))?$"))
async def watermark_action_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    prem_info = await db.get_premium_info(user_id)
    is_prem = (prem_info.get("tier", 0) >= 1) or (user_id in Config.ADMIN)

    if not is_prem:
        return await query.answer(
            "💎 Video Watermark is a Premium Feature!\n\nUpgrade via /plan to burn custom text or logo watermarks onto your videos.",
            show_alert=True
        )

    from plugins.extra_features import build_watermark_view
    text, markup = await build_watermark_view(user_id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer("Watermark Settings Opened! 💧")


@Client.on_message(filters.private & (filters.reply | filters.create(lambda _, __, m: bool(m.from_user and m.from_user.id in USER_STATE))), group=2)
async def refunc(client, message):
    if Config.PRIVATE_MODE and message.from_user and message.from_user.id not in Config.ADMIN:
        return
    if message.chat and await is_duplicate_update(f"reply_{message.chat.id}_{message.id}"):
        return

    # CRITICAL: Never trap commands (/start, /admin, /cancel, etc.)
    text_val = (message.text or message.caption or "").strip()
    if text_val.startswith("/"):
        if message.from_user:
            USER_STATE.pop(message.from_user.id, None)
        return await message.continue_propagation()

    user_id = message.from_user.id
    user_state = USER_STATE.get(user_id)
    reply_message = message.reply_to_message

    # 1. Check if user was setting Watermark Text
    if user_state == "waiting_wm_text":
        USER_STATE.pop(user_id, None)
        if reply_message:
            try:
                await reply_message.delete()
            except Exception:
                pass
        if not message.text:
            return await message.reply_text(
                "❌ <b>Please send text for your watermark tag.</b>\n\n⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_user_input")]])
            )
        wm_text = message.text.strip()
        await db.set_watermark(user_id, text=wm_text, type="text", enabled=True)
        try:
            await message.delete()
        except Exception:
            pass
        from plugins.extra_features import build_watermark_view
        t, m = await build_watermark_view(user_id)
        return await client.send_message(
            chat_id=user_id,
            text=f"✅ <b>Wᴀᴛᴇʀᴍᴀʀᴋ Tᴇxᴛ Sᴀᴠᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n▸ <b>Tᴀɢ :</b> <code>{wm_text}</code>\n▸ <b>Sᴛᴀᴛᴜꜱ :</b> Eɴᴀʙʟᴇᴅ 🟢\n\n⚡ @Nex_bots",
            reply_markup=m
        )

    # 2. Check if user was setting Watermark Logo
    if user_state == "waiting_wm_logo":
        USER_STATE.pop(user_id, None)
        if reply_message:
            try:
                await reply_message.delete()
            except Exception:
                pass
        photo = message.photo or (message.document if message.document and message.document.mime_type and message.document.mime_type.startswith("image/") else None)
        if not photo:
            return await message.reply_text(
                "❌ <b>Please send a photo or image file for your watermark logo.</b>\n\n"
                "<i>Action cancelled. You can try again from Watermark Settings.</i>\n\n⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💧 Watermark Settings", callback_data="cb_watermark")]])
            )
        file_id = photo.file_id
        await db.set_watermark(user_id, image_id=file_id, type="image", enabled=True)
        try:
            await message.delete()
        except Exception:
            pass
        from plugins.extra_features import build_watermark_view
        t, m = await build_watermark_view(user_id)
        return await client.send_message(
            chat_id=user_id,
            text="✅ <b>Wᴀᴛᴇʀᴍᴀʀᴋ Lᴏɢᴏ Sᴀᴠᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n▸ <b>Tʏᴘᴇ :</b> Iᴍᴀɢᴇ Lᴏɢᴏ 🖼️\n▸ <b>Sᴛᴀᴛᴜꜱ :</b> Eɴᴀʙʟᴇᴅ 🟢\n\n⚡ @Nex_bots",
            reply_markup=m
        )

    # 3. Check if user was setting Bottom Caption
    if user_state == "waiting_bottom_caption":
        USER_STATE.pop(user_id, None)
        if reply_message:
            try:
                await reply_message.delete()
            except Exception:
                pass
        if not message.text:
            return await message.reply_text(
                "❌ <b>Please send text for your bottom caption.</b>\n\n⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_user_input")]])
            )
        b_caption = message.text.strip()
        await db.set_bottom_caption(user_id, bottom_caption=b_caption)
        try:
            await message.delete()
        except Exception:
            pass
        from plugins.extra_features import build_settings_panel
        t, m = await build_settings_panel(user_id)
        return await client.send_message(
            chat_id=user_id,
            text=f"✅ <b>Bᴏᴛᴛᴏᴍ Cᴀᴘᴛɪᴏɴ Sᴀᴠᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n▸ <b>Fᴏᴏᴛᴇʀ :</b>\n<code>{b_caption}</code>\n\n⚡ @Nex_bots",
            reply_markup=m
        )

    # 4. Check if user was setting Prefix
    if user_state == "waiting_prefix":
        USER_STATE.pop(user_id, None)
        if reply_message:
            try:
                await reply_message.delete()
            except Exception:
                pass
        if not message.text:
            return await message.reply_text("❌ Please send text for your prefix.")
        prefix = message.text.strip()
        await db.set_prefix(user_id, prefix)
        try:
            await message.delete()
        except Exception:
            pass
        from plugins.extra_features import build_settings_panel
        t, m = await build_settings_panel(user_id)
        return await client.send_message(
            chat_id=user_id,
            text=f"✅ <b>Prefix Saved Successfully!</b>\n\n🔤 <b>Prefix:</b> <code>{prefix}</code>\n\n⚡ @Nex_bots",
            reply_markup=m
        )

    # 5. Check if user was setting Suffix
    if user_state == "waiting_suffix":
        USER_STATE.pop(user_id, None)
        if reply_message:
            try:
                await reply_message.delete()
            except Exception:
                pass
        if not message.text:
            return await message.reply_text("❌ Please send text for your suffix.")
        suffix = message.text.strip()
        await db.set_suffix(user_id, suffix)
        try:
            await message.delete()
        except Exception:
            pass
        from plugins.extra_features import build_settings_panel
        t, m = await build_settings_panel(user_id)
        return await client.send_message(
            chat_id=user_id,
            text=f"✅ <b>Suffix Saved Successfully!</b>\n\n🔡 <b>Suffix:</b> <code>{suffix}</code>\n\n⚡ @Nex_bots",
            reply_markup=m
        )

    # 6. Check if user was setting Custom Caption
    if user_state == "waiting_caption":
        USER_STATE.pop(user_id, None)
        if reply_message:
            try:
                await reply_message.delete()
            except Exception:
                pass
        if not message.text:
            return await message.reply_text("❌ Please send text for your custom caption.")
        caption = message.text.strip()
        await db.set_caption(user_id, caption)
        try:
            await message.delete()
        except Exception:
            pass
        from plugins.extra_features import build_settings_panel
        t, m = await build_settings_panel(user_id)
        return await client.send_message(
            chat_id=user_id,
            text="✅ <b>Custom Caption Saved Successfully!</b>\n\n⚡ @Nex_bots",
            reply_markup=m
        )

    # 7. Check if user was setting Thumbnail
    if user_state == "waiting_thumb":
        USER_STATE.pop(user_id, None)
        if reply_message:
            try:
                await reply_message.delete()
            except Exception:
                pass
        photo = message.photo or (message.document if message.document and message.document.mime_type and message.document.mime_type.startswith("image/") else None)
        if not photo:
            return await message.reply_text(
                "❌ <b>Please send a photo for your thumbnail.</b>\n\n⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_user_input")]])
            )
        await db.set_thumbnail(user_id, file_id=photo.file_id)
        try:
            await message.delete()
        except Exception:
            pass
        from plugins.extra_features import build_settings_panel
        t, m = await build_settings_panel(user_id)
        return await client.send_message(
            chat_id=user_id,
            text="✅ <b>Custom Thumbnail Saved Successfully!</b>\n\n⚡ @Nex_bots",
            reply_markup=m
        )

    # 8. Check if user was replying to Track Rename prompt
    if user_state == "waiting_track_rename" or (reply_message and "track-edited file" in ((reply_message.text or "") + (reply_message.caption or "")).lower()):
        from plugins.track_manager import handle_track_rename_reply
        return await handle_track_rename_reply(client, message)

    if not reply_message:
        return

    if not (reply_message.reply_markup and isinstance(reply_message.reply_markup, ForceReply)):
        return

        new_name = message.text.strip()
        try:
            await message.delete()
        except Exception:
            pass

        file_msg = None
        file_msg_id = (
            getattr(reply_message, "reply_to_message_id", None)
            or getattr(reply_message.reply_to_message, "id", None)
            or USER_RENAME_CACHE.get(user_id, {}).get("file_msg_id")
            or USER_FILE_CONTEXT.get(user_id, {}).get("file_msg_id")
        )

        if file_msg_id:
            try:
                file_msg = await client.get_messages(message.chat.id, file_msg_id)
            except Exception:
                pass

        if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
            if reply_message.reply_to_message and (
                reply_message.reply_to_message.document
                or reply_message.reply_to_message.video
                or reply_message.reply_to_message.audio
            ):
                file_msg = reply_message.reply_to_message

        if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
            return await message.reply_text("❌ Original media not found! Please send your file again.")

        file = file_msg.document or file_msg.video or file_msg.audio
        orig_name = file.file_name or "file.mkv"
        _, orig_ext = os.path.splitext(orig_name)

        if "." not in new_name:
            new_name = new_name + (orig_ext if orig_ext else ".mkv")

        # Apply prefix & suffix
        prefix = await db.get_prefix(user_id)
        suffix = await db.get_suffix(user_id)
        final_name = apply_prefix_suffix(new_name, prefix, suffix)

        try:
            await reply_message.delete()
        except Exception:
            pass

        upload_mode = await db.get_upload_mode(user_id)
        if upload_mode in ["Document", "Video", "Audio"]:
            prompt_msg = await client.send_message(
                chat_id=message.chat.id,
                text=f"<b>◈ Pʀᴏᴄᴇꜱꜱɪɴɢ Dᴇꜰᴀᴜʟᴛ Mᴏᴅᴇ ({upload_mode}) ⚡</b>\n\n▸ <b>Fɪʟᴇ Nᴀᴍᴇ :</b> <code>{final_name}</code>",
                **safe_reply_params(file_msg.id)
            )
            class MockCallback:
                def __init__(self, msg, user):
                    self.message = msg
                    self.from_user = user
                    self.data = f"upload_{upload_mode.lower()}_{file_msg.id}"
            mock_cb = MockCallback(prompt_msg, message.from_user)
            await route_to_extras_or_execute(client, mock_cb, final_name, upload_mode.lower(), file_msg)
            return

        buttons = [[InlineKeyboardButton("📁 Dᴏᴄᴜᴍᴇɴᴛ", callback_data=f"upload_document_{file_msg.id}")]]
        if file_msg.video or (file_msg.document and final_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))):
            buttons[0].append(InlineKeyboardButton("🎥 Vɪᴅᴇᴏ", callback_data=f"upload_video_{file_msg.id}"))
        elif file_msg.audio or (file_msg.document and final_name.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg'))):
            buttons[0].append(InlineKeyboardButton("🎵 Aᴜᴅɪᴏ", callback_data=f"upload_audio_{file_msg.id}"))

        await client.send_message(
            chat_id=message.chat.id,
            text=f"<b>◈ Sᴇʟᴇᴄᴛ Oᴜᴛᴘᴜᴛ Tʏᴘᴇ</b>\n\n▸ <b>Fɪʟᴇ Nᴀᴍᴇ :</b> <code>{final_name}</code>",
            reply_markup=InlineKeyboardMarkup(buttons),
            **safe_reply_params(file_msg.id)
        )


@Client.on_callback_query(filters.regex(r"^upload_(document|video|audio)(?:_(\d+))?$"))
async def upload_callback_router(client, update: CallbackQuery):
    upload_type = update.matches[0].group(1).lower()
    encoded_msg_id = update.matches[0].group(2)
    user_id = update.from_user.id

    # Extract filename from message text
    match = re.search(r'`([^`]+)`', update.message.text or "")
    if match:
        new_filename = match.group(1).strip()
    elif ":-" in (update.message.text or ""):
        new_filename = update.message.text.split(":-", 1)[1].strip()
    else:
        new_filename = "NeX_Renamed_File"

    file_msg = None
    target_id = (
        (int(encoded_msg_id) if encoded_msg_id else None)
        or update.message.reply_to_message_id
        or getattr(update.message.reply_to_message, "id", None)
        or USER_RENAME_CACHE.get(user_id, {}).get("file_msg_id")
        or USER_FILE_CONTEXT.get(user_id, {}).get("file_msg_id")
    )

    if target_id:
        try:
            file_msg = await client.get_messages(update.message.chat.id, target_id)
        except Exception:
            pass

    if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
        if update.message.reply_to_message and (
            update.message.reply_to_message.document
            or update.message.reply_to_message.video
            or update.message.reply_to_message.audio
        ):
            file_msg = update.message.reply_to_message

    if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
        return await update.message.edit("❌ Original media message could not be retrieved! Please send your file again.")

    await route_to_extras_or_execute(client, update, new_filename, upload_type, file_msg)


async def route_to_extras_or_execute(client, update, new_filename: str, upload_type: str, file_msg):
    user_id = update.from_user.id
    is_video = (upload_type == "video") or new_filename.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))

    if is_video:
        sample_settings = await db.get_sample_settings(user_id)
        sample_dur = sample_settings.get("duration", 0)
        ss_count = await db.get_screenshots(user_id)

        # If BOTH are disabled (0), do NOT prompt! Immediately start pipeline
        if sample_dur == 0 and ss_count == 0:
            return await execute_rename_pipeline(client, update, new_filename, upload_type, file_msg, extras={"sample": False, "ss": False})

        # Cache pending media extras request
        task_key = f"{user_id}_{file_msg.id}"
        PENDING_MEDIA_EXTRAS[task_key] = {
            "filename": new_filename,
            "upload_type": upload_type,
            "file_msg": file_msg,
            "sample_dur": sample_dur,
            "ss_count": ss_count
        }

        buttons = []
        if sample_dur > 0 and ss_count > 0:
            buttons.append([InlineKeyboardButton("🎬 Sample + 📸 Screenshots", callback_data=f"ext_both_{file_msg.id}")])

        row2 = []
        if sample_dur > 0:
            row2.append(InlineKeyboardButton(f"🎬 Sample Only ({sample_dur}s)", callback_data=f"ext_sample_{file_msg.id}"))
        if ss_count > 0:
            row2.append(InlineKeyboardButton(f"📸 Shots Only ({ss_count})", callback_data=f"ext_ss_{file_msg.id}"))
        if row2:
            buttons.append(row2)

        buttons.append([InlineKeyboardButton("⏩ Sᴋɪᴘ Exᴛʀᴀꜱ (Rᴇɴᴀᴍᴇ Oɴʟʏ)", callback_data=f"ext_skip_{file_msg.id}")])
        buttons.append([
            InlineKeyboardButton("🔕 Dɪꜱᴀʙʟᴇ ɪɴ Sᴇᴛᴛɪɴɢꜱ", callback_data=f"ext_disable_{file_msg.id}"),
            InlineKeyboardButton("❌ Cᴀɴᴄᴇʟ", callback_data="close")
        ])

        prompt_text = (
            "<b>◈ Mᴇᴅɪᴀ Exᴛʀᴀꜱ Cᴏɴꜰɪʀᴍᴀᴛɪᴏɴ 🎬</b>\n"
            "\n"
            f"▸ <b>Tᴀʀɢᴇᴛ Fɪʟᴇ :</b> <code>{new_filename}</code>\n"
            f"▸ <b>🎬 Sᴀᴍᴘʟᴇ Vɪᴅᴇᴏ :</b> <code>{sample_dur}s</code>\n"
            f"▸ <b>📸 Sᴄʀᴇᴇɴꜱʜᴏᴛꜱ :</b> <code>{ss_count} frames</code>\n\n"
            "<i>Do you want to generate Sample Video or Screenshots for this file?</i>\n\n"
            "⚡ @Nex_bots"
        )
        msg = update.message if hasattr(update, 'message') else update
        try:
            if hasattr(update, 'edit_message_text'):
                await update.edit_message_text(prompt_text, reply_markup=InlineKeyboardMarkup(buttons))
            elif hasattr(msg, 'edit'):
                await msg.edit(prompt_text, reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await msg.reply_text(prompt_text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await client.send_message(user_id, prompt_text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Non-video files proceed directly
    await execute_rename_pipeline(client, update, new_filename, upload_type, file_msg, extras={"sample": False, "ss": False})


@Client.on_callback_query(filters.regex(r"^ext_(both|sample|ss|skip|disable)_(\d+)$"))
async def extras_decision_callback(client, query: CallbackQuery):
    choice = query.matches[0].group(1)
    file_msg_id = int(query.matches[0].group(2))
    user_id = query.from_user.id
    task_key = f"{user_id}_{file_msg_id}"

    data = PENDING_MEDIA_EXTRAS.get(task_key)
    if not data:
        return await query.answer("❌ Session expired! Please resend the file.", show_alert=True)

    new_filename = data["filename"]
    upload_type = data["upload_type"]
    file_msg = data["file_msg"]

    if choice == "disable":
        await db.set_sample_duration(user_id, 0)
        await db.set_screenshots(user_id, 0)
        await query.answer("🔕 Sample and Screenshots permanently disabled in your settings!", show_alert=True)
        extras = {"sample": False, "ss": False}
    elif choice == "both":
        await query.answer("🎬 Sample + Screenshots will be generated!")
        extras = {"sample": True, "ss": True}
    elif choice == "sample":
        await query.answer("🎬 Sample video will be generated!")
        extras = {"sample": True, "ss": False}
    elif choice == "ss":
        await query.answer("📸 Screenshots will be generated!")
        extras = {"sample": False, "ss": True}
    else:  # skip
        await query.answer("⏩ Skipping extras. Rename starting...")
        extras = {"sample": False, "ss": False}

    await execute_rename_pipeline(client, query, new_filename, upload_type, file_msg, extras=extras)


async def execute_rename_pipeline(
    client,
    update=None,
    new_filename: str = "",
    upload_type: str = "document",
    file_msg=None,
    extras: dict = None,
    ms=None,
    status_msg=None,
    sts_msg=None,
    user_id: int = None,
    **kwargs
):
    status_target = status_msg or sts_msg or ms or update or kwargs.get("status")
    ms = getattr(status_target, "message", status_target)
    is_pipeline_success = False

    # Resolve user_id cleanly
    if not user_id:
        if hasattr(status_target, "from_user") and status_target.from_user and not getattr(status_target.from_user, "is_bot", False):
            user_id = status_target.from_user.id
        elif file_msg and hasattr(file_msg, "chat") and file_msg.chat:
            user_id = file_msg.chat.id
        elif file_msg and hasattr(file_msg, "from_user") and file_msg.from_user:
            user_id = file_msg.from_user.id
        elif hasattr(ms, "chat") and ms.chat:
            user_id = ms.chat.id
        elif hasattr(update, "from_user") and update.from_user:
            user_id = update.from_user.id
        else:
            user_id = 0

    task_key = f"exec_{user_id}_{file_msg.id if file_msg else 'none'}_{new_filename}"
    if await is_duplicate_update(task_key, ttl=10.0):
        print(f"⚠️ Duplicate execution prevented for task {task_key}")
        return

    # Verify Concurrency & Queue Limit (Free = 1 conc / 3 queue, Premium = 4 conc / 15 queue)
    prem_info = await db.get_premium_info(user_id)
    user_tier = prem_info.get("tier", 0)
    effective_tier = 3 if user_id in Config.ADMIN else user_tier
    if user_id in Config.ADMIN:
        max_concurrent = 10
        max_queue = 50
    elif user_tier == 0:
        max_concurrent = 1
        max_queue = 3
    else:
        max_concurrent = 4
        max_queue = 15

    if ACTIVE_USER_TASKS.get(user_id, 0) >= max_queue:
        return await ms.edit(
            f"⚠️ <b>Processing Queue Full!</b>\n\n"
            f"Your plan (<b>{prem_info['plan_name']}</b>) allows up to <b>{max_queue}</b> tasks in queue.\n"
            f"Please wait for your active task(s) to finish or upgrade via <code>/plan</code>!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 View Plans", callback_data="open_plans")],
                [InlineKeyboardButton("❌ Close", callback_data="close")]
            ])
        )

    # Verify 3-Tier Limits before entering semaphore
    file = file_msg.document or file_msg.video or file_msg.audio
    file_size = getattr(file, "file_size", 0) if file else 0
    tier_limits = TIER_LIMITS.get(user_tier, TIER_LIMITS[0])
    max_size = tier_limits["max_file_size"]
    daily_limit = tier_limits["daily_bytes"]

    if file_size > max_size and user_id not in Config.ADMIN:
        return await ms.edit(
            f"⭐ <b>File Size Limit Exceeded!</b>\n\n"
            f"Your plan allows files up to <b>{humanbytes(max_size)}</b>.\n"
            f"Upgrade to Premium for full 4GB files!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans")],
                [InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")]
            ])
        )

    user_usage = await db.get_user_usage(user_id)
    daily_used = user_usage.get("daily_bytes", 0)
    if (daily_used + file_size) > daily_limit and user_id not in Config.ADMIN:
        return await ms.edit(
            f"⚠️ <b>Daily Bandwidth Limit Exceeded!</b>\n\n"
            f"Used today: <b>{humanbytes(daily_used)}</b> / <b>{humanbytes(daily_limit)}</b>\n"
            f"Upgrade your plan for higher daily limits or unlimited transfers!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans")],
                [InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")]
            ])
        )

    ACTIVE_USER_TASKS[user_id] = ACTIVE_USER_TASKS.get(user_id, 0) + 1

    try:
        # Ensure queue concurrency limit
        await ms.edit("⏳ <b>Adding to processing queue... Please wait.</b>")
        
        async with RENAME_SEMAPHORE:
            clean_name = re.sub(r'[\\/*?:"<>|]', '_', str(new_filename)).strip()
            if not clean_name:
                clean_name = "renamed_file.mkv"
            new_filename = clean_name

            # Check user settings and remux requirements upfront
            metadata_bool = await db.get_metadata_bool(user_id)
            metadata_code = await db.get_metadata_code(user_id) or "Telegram : @Nex_bots"
            is_video = (upload_type == "video") or new_filename.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))
            is_prem = (user_tier >= 1) or (user_id in Config.ADMIN)
            wm_info = await db.get_watermark(user_id)
            wm_enabled = bool(is_video and is_prem and wm_info.get("enabled"))

            # Zero-Disk Turbo Pipe is MANDATORY DEFAULT for all renames unless explicitly requested remux
            # Custom thumbnails, custom captions, and bottom captions attach natively in MTProto without disk remuxing!
            strip_audio = bool(extras.get("strip_audio")) if isinstance(extras, dict) else False
            strip_sub = bool(extras.get("strip_sub")) if isinstance(extras, dict) else False
            convert_container = bool(extras.get("convert_container") or extras.get("remux")) if isinstance(extras, dict) else False
            is_remux_needed = bool(wm_enabled or strip_audio or strip_sub or convert_container)

            # 0. Telegram Virtual Disk Instant 0.05s Staging
            vdisk_ch = get_virtual_disk_channel(client)
            staged_msg = None
            if vdisk_ch and vdisk_ch != 0:
                try:
                    staged_msg = await stage_to_virtual_disk(client, file_msg, vdisk_ch)
                    if staged_msg:
                        print(f"✅ [VDisk] Media staged to Virtual Disk {vdisk_ch} (msg_id: {staged_msg.id})")
                except Exception as stage_err:
                    print(f"⚠️ [VDisk] Staging failed: {stage_err}")

            # High-Speed RAM-disk allocation (/dev/shm) if on Linux with > 1.3x file size (or > 2.2x if remuxing) free; fallback to SSD
            work_dir = get_optimal_work_dir(user_id, file_size, is_remux_needed=is_remux_needed)
            os.makedirs(work_dir, exist_ok=True)
            abs_work_dir = os.path.abspath(work_dir)
            ACTIVE_WORK_DIRS.add(abs_work_dir)
            final_file_path = os.path.join(work_dir, new_filename)
            download_path = os.path.join(work_dir, f"dl_{new_filename}") if is_remux_needed else final_file_path
            file_path = download_path
            ph_path = None
            sample_path = None
            ss_dir = None
            task_id = f"task_{user_id}_{int(time.time())}_{os.getpid()}"

            try:
                await db.add_active_task(
                    task_id=task_id,
                    user_id=user_id,
                    file_name=new_filename,
                    file_size=file_size,
                    task_type="rename",
                    extra={
                        "upload_type": upload_type,
                        "work_dir": work_dir,
                        "chat_id": file_msg.chat.id,
                        "source_message_id": file_msg.id,
                        "staged_msg_id": staged_msg.id if staged_msg else None,
                        "vdisk_ch": vdisk_ch if vdisk_ch else None,
                        "status_message_id": ms.id,
                        "new_name": new_filename,
                        "extras": extras or {}
                    }
                )
            except Exception:
                pass

            cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Cancel", callback_data=f"cancel_process_{task_id}")]])

            # Determine Premium 4GB Routing & Uploader Client
            user_dump = await db.get_dump_channel(user_id)
            bridge_channel = parse_channel_id(user_dump or vdisk_ch or Config.DUMP_CHANNEL or Config.FILES_CHANNEL or Config.LOG_CHANNEL)
            is_4gb = file_size > (1.95 * 1024 * 1024 * 1024)
            client_4gb = getattr(client, "app_4gb", None) or app_4gb
            is_prem_active = bool(client_4gb and (getattr(client, "app_4gb_started", False) or getattr(client_4gb, "is_connected", False) or getattr(client_4gb, "storage", None)))
            # Route ALL files through Premium app_4gb client whenever active for unthrottled Telegram speed
            uploader = client_4gb if is_prem_active else client
            upload_mode_tag = "<b>◈ 4ɢʙ ᴘʀᴇᴍɪᴜᴍ ᴜᴘʟᴏᴀᴅɪɴɢ... 🚀</b>" if is_prem_active else "<b>◈ ᴜᴘʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 🚀</b>"

            # Ensure critical peers are resolved and cached in Pyrogram to avoid PeerIdInvalid
            if is_prem_active and client_4gb:
                if bridge_channel and bridge_channel != 0:
                    try:
                        await client_4gb.get_chat(bridge_channel)
                    except Exception as pe_err:
                        log.warning(f"app_4gb get_chat bridge_channel note: {pe_err}")
                if user_id:
                    try:
                        await client_4gb.get_chat(user_id)
                    except Exception:
                        pass

            if bridge_channel and bridge_channel != 0:
                try:
                    await client.get_chat(bridge_channel)
                except Exception:
                    pass
            if user_id:
                try:
                    await client.get_chat(user_id)
                except Exception:
                    pass

            async def _prepare_thumb():
                c_thumb = await db.get_thumbnail(user_id)
                media = file_msg.document or file_msg.video or file_msg.audio
                target_file_id = None
                if c_thumb:
                    target_file_id = c_thumb
                elif hasattr(media, 'thumbs') and media.thumbs:
                    # Pick highest resolution thumbnail from original media [-1]
                    target_file_id = media.thumbs[-1].file_id

                if target_file_id:
                    try:
                        raw_thumb_dest = os.path.join(work_dir, "raw_thumb.jpg")
                        t_path = await client.download_media(target_file_id, file_name=raw_thumb_dest)
                        if t_path and os.path.exists(t_path) and os.path.getsize(t_path) > 0:
                            crisp_dest = os.path.join(work_dir, "thumb.jpg")
                            return prepare_crisp_thumbnail(t_path, crisp_dest)
                    except Exception as e:
                        print(f"Thumbnail processing error: {e}")
                return None

            async def _fetch_dims(f_path):
                if is_video and os.path.exists(f_path):
                    return await get_video_duration_and_dims(f_path)
                return (0, 0, 0)

            duration, width, height = 0, 0, 0
            if is_video:
                if hasattr(file_msg, "video") and file_msg.video:
                    duration = getattr(file_msg.video, "duration", 0) or 0
                    width = getattr(file_msg.video, "width", 0) or 0
                    height = getattr(file_msg.video, "height", 0) or 0
                elif hasattr(staged_msg, "video") and staged_msg and staged_msg.video:
                    duration = getattr(staged_msg.video, "duration", 0) or 0
                    width = getattr(staged_msg.video, "width", 0) or 0
                    height = getattr(staged_msg.video, "height", 0) or 0
                elif hasattr(file_msg, "document") and file_msg.document and hasattr(file_msg.document, "attributes"):
                    for attr in file_msg.document.attributes:
                        if hasattr(attr, "duration"):
                            duration = getattr(attr, "duration", 0) or duration
                            width = getattr(attr, "w", 0) or width
                            height = getattr(attr, "h", 0) or height

            ph_path = await _prepare_thumb()

            # 2-Task Concurrency Semaphore for heavy 4 GB multitasking (2 concurrent files saturate full pipe)
            task_queue_key = f"{user_id}_{ms.id}"
            transfer_sem_held = False
            if _TRANSFER_SEMAPHORE.locked():
                _TRANSFER_WAITING_TASKS.append(task_queue_key)
                try:
                    await ms.edit(
                        "⏳ <b>Qᴜᴇᴜᴇᴅ ꜰᴏʀ Tᴜʀʙᴏ Sᴛʀᴇᴀᴍɪɴɢ... ⚡</b>\n\n"
                        "▸ <i>Yᴏᴜʀ ꜰɪʟᴇ ᴡɪʟʟ ꜱᴛᴀʀᴛ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴀꜱ ꜱᴏᴏɴ ᴀꜱ ᴀɴ ᴀᴄᴛɪᴠᴇ ꜱʟᴏᴛ ꜰʀᴇᴇꜱ ᴜᴘ!</i>\n"
                        "<i>(Running 2 high-speed tasks simultaneously to saturate full network pipe)</i>",
                        reply_markup=cancel_btn
                    )
                except Exception:
                    pass

            await _TRANSFER_SEMAPHORE.acquire()
            transfer_sem_held = True
            if task_queue_key in _TRANSFER_WAITING_TASKS:
                try:
                    _TRANSFER_WAITING_TASKS.remove(task_queue_key)
                except ValueError:
                    pass

            if ms.id in CANCEL_REQUESTS or user_id in CANCEL_REQUESTS:
                _TRANSFER_SEMAPHORE.release()
                transfer_sem_held = False
                return await ms.edit("❌ <b>Operation Aborted!</b>\n\n⚡ @Nex_bots")

            uploaded_file = None
            use_zero_disk = False
            upload_start = time.time()
            actual_file_size = file_size

            # Attempt single-pass Zero-Disk RAM Turbo Pipe if no remuxing needed
            target_media_msg = staged_msg or file_msg
            if not is_remux_needed and target_media_msg is not None:
                try:
                    turbo_header = "⚡ <b>ᴢᴇʀᴏ-ᴅɪꜱᴋ ᴛᴜʀʙᴏ ꜱᴛʀᴇᴀᴍɪɴɢ... 🚀</b>"
                    await ms.edit(
                        f"{turbo_header}\n\n<i>Direct 24-Worker Dual-Client RAM Pipe active (40-80+ MB/s)...</i>",
                        reply_markup=cancel_btn
                    )
                    upload_start = time.time()
                    uploaded_file = await zero_disk_turbo_pipe(
                        client=client,
                        uploader=uploader,
                        staged_msg=target_media_msg,
                        new_filename=new_filename,
                        progress=progress_for_pyrogram,
                        progress_args=("⚡ ᴢᴇʀᴏ-ᴅɪꜱᴋ ᴛᴜʀʙᴏ ꜱᴛʀᴇᴀᴍɪɴɢ... 🚀", ms, upload_start, client, effective_tier),
                        is_prem=is_prem or (effective_tier >= 1) or is_4gb or is_prem_active
                    )
                    if uploaded_file:
                        use_zero_disk = True
                        actual_file_size = file_size
                except StopTransmission:
                    raise
                except Exception as pipe_err:
                    err_trace = traceback.format_exc()
                    print(f"⚠️ [ZERO-DISK ERROR] zero_disk_turbo_pipe failed: {pipe_err}\n{err_trace}")
                    log.error(f"zero_disk_turbo_pipe failed ({type(pipe_err).__name__}: {pipe_err}): {err_trace}")
                    use_zero_disk = False
                    uploaded_file = None
                    try:
                        await ms.edit(
                            "<b>◈ Zero-disk skipped. Switching to high-speed disk pipeline... 📥</b>",
                            reply_markup=cancel_btn
                        )
                    except Exception:
                        pass

            # Fallback to high-speed disk pipeline if remuxing needed or zero-disk pipe skipped/failed
            if not use_zero_disk:
                try:
                    await ms.edit(
                        "<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>\n\n<i>Connecting to high-speed MTProto server...</i>",
                        reply_markup=cancel_btn
                    )
                except Exception:
                    pass

                start_time = time.time()
                try:
                    # Prefer Premium app_4gb client with staged virtual disk message for unthrottled download
                    dl_client = client_4gb if (is_prem_active and staged_msg) else client
                    dl_msg = staged_msg if (is_prem_active and staged_msg) else file_msg
                    dl_tag = "<b>◈ 4ɢʙ ᴘʀᴇᴍɪᴜᴍ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ... 📥</b>" if dl_client == client_4gb else "<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>"
                    path = await fast_download(
                        client=dl_client,
                        message_or_file=dl_msg,
                        file_path=file_path,
                        progress=progress_for_pyrogram,
                        progress_args=(dl_tag, ms, start_time, client, effective_tier)
                    )
                except StopTransmission:
                    raise
                except Exception as down_err:
                    print(f"⚠️ fast_download error: {down_err}. Retrying fast_download with fallback...")
                    traceback.print_exc()
                    path = await fast_download(
                        client=client,
                        message_or_file=file_msg,
                        file_path=file_path,
                        progress=progress_for_pyrogram,
                        progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>", ms, start_time, client, effective_tier)
                    )

                if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                    return await ms.edit("❌ <b>Download Failed: Empty or missing file received.</b>")

                if ms.id in CANCEL_REQUESTS or f"{ms.chat.id}_{ms.id}" in CANCEL_REQUESTS or (ms.chat and ms.chat.id in CANCEL_REQUESTS) or user_id in CANCEL_REQUESTS:
                    return await ms.edit("❌ <b>Operation Aborted!</b>\n\n⚡ @Nex_bots")

                actual_file_size = os.path.getsize(file_path)

                if not is_remux_needed:
                    if download_path != final_file_path and os.path.exists(download_path):
                        os.rename(download_path, final_file_path)
                    file_path = final_file_path
                    actual_file_size = os.path.getsize(file_path)
                else:
                    if metadata_bool:
                        await ms.edit("<b>◈ ᴀᴘᴘʟʏɪɴɢ ᴄᴜꜱᴛᴏᴍ ᴍᴇᴛᴀᴅᴀᴛᴀ... 🏷️</b>")
                        meta_file = os.path.join(work_dir, f"meta_{new_filename}")
                        success = await inject_metadata(file_path, meta_file, metadata_code)
                        if success and os.path.exists(meta_file) and os.path.getsize(meta_file) > 0:
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except Exception:
                                    pass
                            os.replace(meta_file, final_file_path)
                            file_path = final_file_path
                            actual_file_size = os.path.getsize(file_path)
                            try:
                                await db.increment_stat(user_id, "total_metadata_applied", 1)
                            except Exception:
                                pass

                    if wm_enabled:
                        wm_type = wm_info.get("type", "text")
                        wm_img_path = None
                        can_apply = False

                        if wm_type == "image" and wm_info.get("image_id"):
                            try:
                                await ms.edit("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴡᴀᴛᴇʀᴍᴀʀᴋ ʟᴏɢᴏ... 🖼️</b>")
                                logo_target = os.path.join(work_dir, "wm_logo.png")
                                dl_logo = await client.download_media(wm_info.get("image_id"), file_name=logo_target)
                                if dl_logo and os.path.exists(dl_logo):
                                    wm_img_path = dl_logo
                                    can_apply = True
                            except Exception as err:
                                print(f"Failed to download watermark logo: {err}")
                        elif wm_info.get("text"):
                            can_apply = True

                        if can_apply:
                            await ms.edit("<b>◈ ᴀᴘᴘʟʏɪɴɢ ᴠɪᴅᴇᴏ ᴡᴀᴛᴇʀᴍᴀʀᴋ... 💧</b>")
                            wm_file = os.path.join(work_dir, f"wm_{new_filename}")
                            wm_ok = await apply_video_watermark(
                                input_path=file_path,
                                output_path=wm_file,
                                text=wm_info.get("text", ""),
                                wm_type=wm_type,
                                image_path=wm_img_path,
                                position=wm_info.get("position", "top_right"),
                                size=wm_info.get("size", 28),
                                opacity=wm_info.get("opacity", 0.85),
                                color=wm_info.get("color", "white")
                            )
                            if wm_ok and os.path.exists(wm_file) and os.path.getsize(wm_file) > 0:
                                if os.path.exists(file_path) and file_path != wm_file:
                                    try:
                                        os.remove(file_path)
                                    except Exception:
                                        pass
                                os.replace(wm_file, final_file_path)
                                file_path = final_file_path
                                actual_file_size = os.path.getsize(file_path)
                                try:
                                    await db.increment_stat(user_id, "total_watermarks_applied", 1)
                                except Exception:
                                    pass

                    if file_path != final_file_path and os.path.exists(file_path):
                        os.replace(file_path, final_file_path)
                        file_path = final_file_path

                # Re-fetch dims from local file if available
                (f_dur, f_w, f_h) = await _fetch_dims(file_path)
                if f_dur or f_w or f_h:
                    duration, width, height = f_dur, f_w, f_h

                await ms.edit(upload_mode_tag)
                upload_start = time.time()
                try:
                    uploaded_file = await fast_upload(
                        client=uploader,
                        file_path=file_path,
                        progress=progress_for_pyrogram,
                        progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier),
                        is_prem=is_prem or (effective_tier >= 1) or is_4gb or is_prem_active
                    )
                except StopTransmission:
                    raise
                except Exception as up_err:
                    print(f"⚠️ fast_upload failed ({up_err}). Falling back to standard Pyrogram send...")
                    traceback.print_exc()
                    uploaded_file = None

            # 5. Format Clean Caption (Clean filename on top, custom caption, and bottom caption / footer)
            c_caption = await db.get_caption(user_id)
            b_caption = await db.get_bottom_caption(user_id)
            if c_caption:
                try:
                    if "{filename}" in c_caption:
                        caption = c_caption.format(
                            filename=new_filename,
                            filesize=humanbytes(actual_file_size),
                            duration=convert(duration)
                        )
                    else:
                        caption = f"<b>{new_filename}</b>\n\n{c_caption}"
                except Exception:
                    caption = f"<b>{new_filename}</b>\n\n{c_caption}"
                if b_caption and b_caption.strip() not in caption:
                    caption = f"{caption}\n\n{b_caption.strip()}"
            elif b_caption and b_caption.strip():
                caption = f"<b>{new_filename}</b>\n\n{b_caption.strip()}"
            else:
                caption = f"<b>{new_filename}</b>"

            # Check Bot Content Protection status
            protect_content = await db.get_protect_content()

            upload_payload = uploaded_file if uploaded_file else file_path
            upload_progress = None if uploaded_file else progress_for_pyrogram
            upload_progress_args = None if uploaded_file else (upload_mode_tag, ms, upload_start, client, effective_tier)

            user_sent_msgs = []
            sent_msg = None

            try:
                # Premium Upload Flow (files of ANY size routed through app_4gb whenever active)
                if (is_prem_active or (is_4gb and client_4gb)):
                    if bridge_channel and bridge_channel != 0:
                        try:
                            if uploaded_file:
                                bridge_msg = await send_input_file_big(
                                    uploader_client=uploader,
                                    target_chat_id=bridge_channel,
                                    input_file_big=uploaded_file,
                                    thumb_path=ph_path,
                                    media_msg=staged_msg or file_msg,
                                    new_filename=new_filename,
                                    caption=caption,
                                    upload_type=upload_type,
                                    protect_content=False,
                                    duration=duration,
                                    width=width,
                                    height=height
                                )
                            elif upload_type == "document":
                                bridge_msg = await uploader.send_document(
                                    chat_id=bridge_channel,
                                    document=upload_payload,
                                    file_name=new_filename,
                                    thumb=ph_path,
                                    caption=caption,
                                    progress=upload_progress,
                                    progress_args=upload_progress_args
                                )
                            elif upload_type == "video":
                                bridge_msg = await uploader.send_video(
                                    chat_id=bridge_channel,
                                    video=upload_payload,
                                    file_name=new_filename,
                                    caption=caption,
                                    thumb=ph_path,
                                    duration=duration,
                                    width=width,
                                    height=height,
                                    supports_streaming=True,
                                    progress=upload_progress,
                                    progress_args=upload_progress_args
                                )
                            elif upload_type == "audio":
                                bridge_msg = await uploader.send_audio(
                                    chat_id=bridge_channel,
                                    audio=upload_payload,
                                    file_name=new_filename,
                                    caption=caption,
                                    thumb=ph_path,
                                    duration=duration,
                                    progress=upload_progress,
                                    progress_args=upload_progress_args
                                )

                            if bridge_msg and hasattr(bridge_msg, "id"):
                                sent_msg = await client.copy_message(
                                    chat_id=user_id,
                                    from_chat_id=bridge_channel,
                                    message_id=bridge_msg.id,
                                    caption=caption,
                                    protect_content=protect_content
                                )
                        except Exception as bridge_err:
                            print(f"Bridge copy delivery failed ({bridge_err}). Trying fallback direct delivery...")
                            sent_msg = None

                    if not sent_msg:
                        if uploaded_file:
                            sent_msg = await send_input_file_big(
                                uploader_client=uploader,
                                target_chat_id=user_id,
                                input_file_big=uploaded_file,
                                thumb_path=ph_path,
                                media_msg=staged_msg or file_msg,
                                new_filename=new_filename,
                                caption=caption,
                                upload_type=upload_type,
                                protect_content=protect_content,
                                duration=duration,
                                width=width,
                                height=height
                            )
                        elif upload_type == "document":
                            sent_msg = await uploader.send_document(
                                chat_id=user_id,
                                document=upload_payload,
                                file_name=new_filename,
                                thumb=ph_path,
                                caption=caption,
                                protect_content=protect_content,
                                progress=upload_progress,
                                progress_args=upload_progress_args
                            )
                        elif upload_type == "video":
                            sent_msg = await uploader.send_video(
                                chat_id=user_id,
                                video=upload_payload,
                                file_name=new_filename,
                                caption=caption,
                                thumb=ph_path,
                                duration=duration,
                                width=width,
                                height=height,
                                supports_streaming=True,
                                protect_content=protect_content,
                                progress=upload_progress,
                                progress_args=upload_progress_args
                            )
                        elif upload_type == "audio":
                            sent_msg = await uploader.send_audio(
                                chat_id=user_id,
                                audio=upload_payload,
                                file_name=new_filename,
                                caption=caption,
                                thumb=ph_path,
                                duration=duration,
                                protect_content=protect_content,
                                progress=upload_progress,
                                progress_args=upload_progress_args
                            )

                else:
                    # Standard Upload Flow (<= 1.95GB)
                    if uploaded_file:
                        sent_msg = await send_input_file_big(
                            uploader_client=client,
                            target_chat_id=user_id,
                            input_file_big=uploaded_file,
                            thumb_path=ph_path,
                            media_msg=staged_msg or file_msg,
                            new_filename=new_filename,
                            caption=caption,
                            upload_type=upload_type,
                            protect_content=protect_content,
                            duration=duration,
                            width=width,
                            height=height
                        )
                    elif upload_type == "document":
                        sent_msg = await client.send_document(
                            chat_id=user_id,
                            document=upload_payload,
                            file_name=new_filename,
                            thumb=ph_path,
                            caption=caption,
                            protect_content=protect_content,
                            progress=upload_progress,
                            progress_args=upload_progress_args
                        )
                    elif upload_type == "video":
                        sent_msg = await client.send_video(
                            chat_id=user_id,
                            video=upload_payload,
                            file_name=new_filename,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                            protect_content=protect_content,
                            progress=upload_progress,
                            progress_args=upload_progress_args
                        )
                    elif upload_type == "audio":
                        sent_msg = await client.send_audio(
                            chat_id=user_id,
                            audio=upload_payload,
                            file_name=new_filename,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            protect_content=protect_content,
                            progress=upload_progress,
                            progress_args=upload_progress_args
                        )

                # Automatic Zero-Crash Fallback: if zero-disk delivery didn't deliver a message, fallback to disk pipeline
                if (not sent_msg or not hasattr(sent_msg, "id")) and uploaded_file and not os.path.exists(file_path):
                    print("⚠️ Zero-disk delivery produced no message. Initiating automatic zero-crash fallback to multi-session disk transfer...", flush=True)
                    try:
                        await ms.edit("<b>◈ Zero-disk skipped. Switching to high-speed disk pipeline... 📥</b>", reply_markup=cancel_btn)
                    except Exception:
                        pass
                    file_path = await fast_download(
                        client=client,
                        message_or_file=file_msg,
                        file_path=file_path,
                        progress=progress_for_pyrogram,
                        progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>", ms, time.time(), client, effective_tier)
                    )
                    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                        return await ms.edit("❌ <b>Download Failed: Empty or missing file received.</b>\n\n⚡ @Nex_bots")

                    actual_file_size = os.path.getsize(file_path)
                    upload_start = time.time()
                    try:
                        await ms.edit(f"{upload_mode_tag}\n\n<i>Uploading file to Telegram servers...</i>", reply_markup=cancel_btn)
                    except Exception:
                        pass

                    if actual_file_size > (1.95 * 1024 * 1024 * 1024):
                        bridge_target = bridge_channel if (bridge_channel and bridge_channel != 0) else parse_channel_id(Config.FILES_CHANNEL or -1003792044224)
                        b_msg = None
                        if upload_type == "video":
                            b_msg = await uploader.send_video(chat_id=bridge_target, video=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, width=width, height=height, supports_streaming=True, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                        elif upload_type == "audio":
                            b_msg = await uploader.send_audio(chat_id=bridge_target, audio=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                        else:
                            b_msg = await uploader.send_document(chat_id=bridge_target, document=file_path, file_name=new_filename, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                        if b_msg and hasattr(b_msg, "id"):
                            sent_msg = await client.copy_message(chat_id=user_id, from_chat_id=bridge_target, message_id=b_msg.id, caption=caption, protect_content=protect_content)
                    else:
                        target_uploader = uploader if (is_prem_active and bridge_channel) else client
                        target_chat = bridge_channel if (is_prem_active and bridge_channel) else user_id
                        try:
                            if upload_type == "video":
                                d_msg = await target_uploader.send_video(chat_id=target_chat, video=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, width=width, height=height, supports_streaming=True, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                            elif upload_type == "audio":
                                d_msg = await target_uploader.send_audio(chat_id=target_chat, audio=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                            else:
                                d_msg = await target_uploader.send_document(chat_id=target_chat, document=file_path, file_name=new_filename, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                            if target_chat == user_id:
                                sent_msg = d_msg
                            elif d_msg and hasattr(d_msg, "id"):
                                sent_msg = await client.copy_message(chat_id=user_id, from_chat_id=target_chat, message_id=d_msg.id, caption=caption, protect_content=protect_content)
                        except Exception as fallback_err:
                            print(f"Fallback uploader send failed ({fallback_err}). Retrying with main bot client...", flush=True)
                            if upload_type == "video":
                                sent_msg = await client.send_video(chat_id=user_id, video=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, width=width, height=height, supports_streaming=True, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                            elif upload_type == "audio":
                                sent_msg = await client.send_audio(chat_id=user_id, audio=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))
                            else:
                                sent_msg = await client.send_document(chat_id=user_id, document=file_path, file_name=new_filename, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier))

                # Strict Verification: sent_msg MUST be a valid message delivered to the user
                if not sent_msg or not hasattr(sent_msg, "id"):
                    return await ms.edit("❌ <b>Delivery Failed: Renamed file could not be delivered to your chat. Please contact support.</b>\n\n⚡ @Nex_bots")

                is_pipeline_success = True

                # Release the turbo transfer semaphore as early as possible so queued tasks can start!
                if transfer_sem_held:
                    _TRANSFER_SEMAPHORE.release()
                    transfer_sem_held = False

                user_sent_msgs.append(sent_msg.id)

                # Send 15-Minute Copyright Auto-Delete notice as a SEPARATE reply message
                warn_text = "⏳ **Note:** This file will be automatically deleted in **15 minutes** due to copyright protection. Please forward it to your **Saved Messages**!"
                try:
                    warn_msg = await client.send_message(
                        chat_id=user_id,
                        text=warn_text,
                        reply_parameters=ReplyParameters(message_id=sent_msg.id)
                    )
                    user_sent_msgs.append(warn_msg.id)
                except Exception:
                    pass

                # Track usage statistics
                try:
                    await db.add_usage(user_id, actual_file_size)
                except Exception as e:
                    print(f"Usage tracking error: {e}")

                # Automatic File Channel / Dump Channel Forwarding for ALL successful renames
                dump_target = parse_channel_id(Config.DUMP_CHANNEL or Config.FILES_CHANNEL or -1003792044224)
                already_in_dump = is_4gb and ('bridge_msg' in locals()) and bridge_msg and (bridge_channel == dump_target)
                if already_in_dump:
                    try:
                        user_mention = getattr(status_target.from_user, "mention", f"User {user_id}") if hasattr(status_target, "from_user") and status_target.from_user else f"<code>{user_id}</code>"
                        orig_name = getattr(file_msg, "name", None) or getattr(file_msg, "file_name", None) or (file_msg.document and file_msg.document.file_name) or (file_msg.video and file_msg.video.file_name) or new_filename
                        dump_caption = f"{caption}\n\n👤 <b>Uꜱᴇʀ :</b> {user_mention} (<code>{user_id}</code>)\n📂 <b>Oʀɪɢɪɴᴀʟ :</b> <code>{orig_name}</code>"
                        await client.edit_message_caption(chat_id=dump_target, message_id=bridge_msg.id, caption=dump_caption)
                    except Exception as e:
                        print(f"Dump channel caption update error: {e}")
                elif dump_target and dump_target != 0 and dump_target != user_id:
                    try:
                        user_mention = getattr(status_target.from_user, "mention", f"User {user_id}") if hasattr(status_target, "from_user") and status_target.from_user else f"<code>{user_id}</code>"
                        orig_name = getattr(file_msg, "name", None) or getattr(file_msg, "file_name", None) or (file_msg.document and file_msg.document.file_name) or (file_msg.video and file_msg.video.file_name) or new_filename
                        dump_caption = f"{caption}\n\n👤 <b>Uꜱᴇʀ :</b> {user_mention} (<code>{user_id}</code>)\n📂 <b>Oʀɪɢɪɴᴀʟ :</b> <code>{orig_name}</code>"
                        await sent_msg.copy(chat_id=dump_target, caption=dump_caption)
                    except Exception as e:
                        print(f"Dump channel backup error: {e}")

            except StopTransmission:
                return await ms.edit("❌ <b>Upload Cancelled by User!</b>\n\n⚡ @Nex_bots")
            except Exception as e:
                err_trace = traceback.format_exc()
                print(f"❌ [UPLOAD ERROR] {type(e).__name__}: {e}\n{err_trace}", flush=True)
                return await ms.edit(f"❌ <b>Upload Failed:</b> <code>{type(e).__name__}: {str(e)[:250]}</code>\n\n⚡ @Nex_bots")

            # Record usage for 4GB uploads if not tracked inside standard block
            if is_4gb:
                try:
                    await db.add_usage(user_id, actual_file_size)
                except Exception:
                    pass

            # 7. Sample Video & Screenshots Generation
            sample_settings = await db.get_sample_settings(user_id)
            sample_duration = sample_settings.get("duration", 0)
            should_sample = extras.get("sample", sample_duration > 0) if extras is not None else (sample_duration > 0)
            screenshots_count = await db.get_screenshots(user_id)
            should_ss = extras.get("ss", screenshots_count > 0) if extras is not None else (screenshots_count > 0)

            media_source_path = None
            temp_slice_created = False
            if (should_sample or should_ss) and is_video:
                if os.path.exists(file_path):
                    media_source_path = file_path
                elif staged_msg is not None:
                    try:
                        slice_target = os.path.join(work_dir, f"slice_{new_filename}")
                        media_source_path = await stream_virtual_disk_slice(client, staged_msg, slice_target, max_bytes=35 * 1024 * 1024)
                        if media_source_path and os.path.exists(media_source_path):
                            temp_slice_created = True
                    except Exception as s_err:
                        print(f"Slice stream error: {s_err}")

            if should_sample and sample_duration > 0 and is_video and media_source_path:
                try:
                    await ms.edit("<b>◈ ɢᴇɴᴇʀᴀᴛɪɴɢ ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ... 🎬</b>")
                    sample_path = os.path.join(work_dir, f"sample_{new_filename}")
                    sample_ok = await generate_sample_video(
                        input_path=media_source_path,
                        output_path=sample_path,
                        total_duration=duration or 300,
                        sample_sec=sample_duration,
                        start_mode=sample_settings.get("start_mode", "auto")
                    )
                    if sample_ok:
                        try:
                            await db.increment_stat(user_id, "total_samples_generated", 1)
                        except Exception:
                            pass
                        sample_cap = f"🎬 <b>ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ ({sample_duration}ꜱ)</b>\n\n🏷 <code>{new_filename}</code>"
                        sample_dur, s_w, s_h = await get_video_duration_and_dims(sample_path)
                        s_msg = await client.send_video(
                            chat_id=user_id,
                            video=sample_path,
                            file_name=f"sample_{new_filename}",
                            caption=sample_cap,
                            thumb=None,
                            duration=sample_dur or sample_duration,
                            width=s_w or width,
                            height=s_h or height,
                            supports_streaming=True,
                            protect_content=protect_content
                        )
                        user_sent_msgs.append(s_msg.id)
                except Exception as e:
                    print(f"Sample video error: {e}")

            if should_ss and screenshots_count > 0 and is_video and media_source_path:
                try:
                    await ms.edit(f"<b>◈ ɢᴇɴᴇʀᴀᴛɪɴɢ {screenshots_count} ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 📸</b>")
                    ss_dir = os.path.join(work_dir, "screenshots")
                    ss_list = await generate_screenshots(media_source_path, ss_dir, duration or 300, screenshots_count)
                    if ss_list:
                        try:
                            await db.increment_stat(user_id, "total_screenshots_generated", 1)
                        except Exception:
                            pass
                        media_group = []
                        for idx, sp in enumerate(ss_list):
                            cap = f"📸 Screenshot {idx+1}/{len(ss_list)} - {new_filename}" if idx == 0 else ""
                            media_group.append(InputMediaPhoto(media=sp, caption=cap))
                        ss_msgs = await client.send_media_group(chat_id=user_id, media=media_group, protect_content=protect_content)
                        user_sent_msgs.extend([m.id for m in ss_msgs])
                except Exception as e:
                    print(f"Screenshots error: {e}")

            if temp_slice_created and media_source_path and os.path.exists(media_source_path):
                try:
                    os.remove(media_source_path)
                except Exception:
                    pass

            # Safe cleanup of temporary staged message from Virtual Disk
            if staged_msg and vdisk_ch:
                try:
                    await delete_from_virtual_disk(client, staged_msg.id, vdisk_ch)
                    staged_msg = None
                except Exception:
                    pass

            # Log activity to real-time tracker
            try:
                user_fn = "User"
                if hasattr(status_target, 'from_user') and status_target.from_user:
                    user_fn = getattr(status_target.from_user, "first_name", "User")
                elif file_msg and hasattr(file_msg, 'from_user') and file_msg.from_user:
                    user_fn = getattr(file_msg.from_user, "first_name", "User")
                await db.log_activity(
                    user_id=user_id,
                    name=user_fn,
                    action="File Renamed",
                    details=f"{new_filename} ({humanbytes(actual_file_size)})"
                )
            except Exception:
                pass

            # Atomically increment real-time persistent stats (total files, total bandwidth, today's counts)
            try:
                await db.increment_rename_stats(user_id, actual_file_size)
            except Exception as stat_err:
                print(f"Error incrementing rename stats: {stat_err}")

            # Auto-delete original incoming/forwarded media message as soon as rename finishes
            try:
                if 'file_msg' in locals() and file_msg and getattr(file_msg, "id", None) not in user_sent_msgs:
                    await file_msg.delete()
            except Exception:
                pass

            # 8.1 Spawn 15-Minute Copyright Auto-Delete Task (User Private Chat Only)
            if user_sent_msgs:
                async def _auto_delete_copyright_media(c_id, msg_ids):
                    await asyncio.sleep(900)  # 15 minutes = 900 seconds
                    try:
                        await client.delete_messages(chat_id=c_id, message_ids=msg_ids)
                    except Exception:
                        pass
                asyncio.create_task(_auto_delete_copyright_media(user_id, user_sent_msgs))

    except Exception as e:
        err_trace = traceback.format_exc()
        print(f"❌ [PIPELINE ERROR] {type(e).__name__}: {e}\n{err_trace}", flush=True)
        log_ch = parse_channel_id(Config.LOG_CHANNEL or -1003792044224)
        if log_ch and log_ch != 0:
            try:
                alert_text = (
                    f"⚠️ <b>Pipeline Error Alert</b>\n\n"
                    f"👤 <b>User:</b> <code>{user_id}</code>\n"
                    f"📁 <b>File:</b> <code>{new_filename}</code>\n"
                    f"❌ <b>Error:</b> <code>{type(e).__name__}: {str(e)[:250]}</code>\n\n"
                    f"⚡ @Nex_bots"
                )
                await client.send_message(log_ch, alert_text)
            except Exception:
                pass
        return await ms.edit(f"❌ <b>Rename Failed:</b> <code>{type(e).__name__}: {str(e)[:250]}</code>\n\n⚡ @Nex_bots")

    finally:
        ACTIVE_USER_TASKS[user_id] = max(0, ACTIVE_USER_TASKS.get(user_id, 1) - 1)
        if 'transfer_sem_held' in locals() and transfer_sem_held:
            try:
                _TRANSFER_SEMAPHORE.release()
                transfer_sem_held = False
            except Exception:
                pass
        if 'task_queue_key' in locals() and task_queue_key in _TRANSFER_WAITING_TASKS:
            try:
                _TRANSFER_WAITING_TASKS.remove(task_queue_key)
            except Exception:
                pass
        # 9. Strict Cleanup of Temporary Files, Concurrency Counter & Persistent Task
        try:
            if 'task_id' in locals():
                await db.remove_active_task(task_id)
        except Exception:
            pass
        try:
            if 'staged_msg' in locals() and staged_msg and 'vdisk_ch' in locals() and vdisk_ch:
                await delete_from_virtual_disk(client, staged_msg.id, vdisk_ch)
        except Exception:
            pass
        try:
            if 'abs_work_dir' in locals():
                ACTIVE_WORK_DIRS.discard(abs_work_dir)
        except Exception:
            pass
        CANCEL_REQUESTS.discard(ms.id)
        CANCEL_REQUESTS.discard(user_id)
        if ms.chat:
            CANCEL_REQUESTS.discard(ms.chat.id)
            CANCEL_REQUESTS.discard(f"{ms.chat.id}_{ms.id}")
        if is_pipeline_success:
            try:
                await ms.delete()
            except Exception:
                pass
            # Auto-delete original incoming/forwarded file message to prevent chat clutter ONLY on success
            try:
                if 'file_msg' in locals() and file_msg and getattr(file_msg, "id", None) not in user_sent_msgs:
                    await file_msg.delete()
            except Exception:
                pass
        else:
            print(f"⚠️ [TASK FAILED/INCOMPLETE] Preserved status message {ms.id} and media for user {user_id}", flush=True)
        if 'work_dir' in locals() and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)


@Client.on_message(filters.private & filters.command(["reset_task", "cleartask", "unfreeze"]))
async def reset_task_cmd(client, message):
    user_id = message.from_user.id
    ACTIVE_USER_TASKS[user_id] = 0
    USER_FILE_CONTEXT.pop(user_id, None)
    USER_RENAME_CACHE.pop(user_id, None)
    await db.reset_user_tasks(user_id)
    _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)
    await message.reply_text(
        "✅ <b>Your active task queue and cache have been completely cleared!</b>\n\n"
        "You can now send files again smoothly. 🚀\n\n"
        "⚡ @Nex_bots",
        **safe_reply_params(message.id)
    )


async def resume_interrupted_tasks(client):
    """
    Automatic Task Resumption after cloud handoff or server restart.
    Automatically retrieves interrupted tasks from MongoDB and resumes execution without user re-sending.
    """
    try:
        pending_tasks = await db.get_active_tasks(max_age_seconds=21600)
        if not pending_tasks:
            return

        print(f"🔄 [Recovery] Found {len(pending_tasks)} active/interrupted tasks from previous run.")
        for task in pending_tasks:
            task_id = str(task.get("_id"))
            try:
                user_id = task.get("user_id")
                file_name = task.get("file_name", "file.mkv")
                extra = task.get("extra", {}) or {}
                chat_id = extra.get("chat_id") or user_id
                src_msg_id = extra.get("source_message_id")
                status_msg_id = extra.get("status_message_id")
                upload_type = extra.get("upload_type", "document")
                task_extras = extra.get("extras", {})

                if not src_msg_id:
                    await db.remove_active_task(task_id)
                    continue

                try:
                    file_msg = await client.get_messages(chat_id, int(src_msg_id))
                except Exception as e:
                    print(f"⚠️ [Recovery] Failed to fetch source message {src_msg_id} in {chat_id}: {e}")
                    file_msg = None

                if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
                    staged_id = extra.get("staged_msg_id")
                    vdisk_target = extra.get("vdisk_ch") or get_virtual_disk_channel(client)
                    if staged_id and vdisk_target:
                        try:
                            file_msg = await fetch_from_virtual_disk(client, int(staged_id), vdisk_target)
                            if file_msg and (file_msg.document or file_msg.video or file_msg.audio):
                                print(f"✅ [Recovery] Successfully retrieved staged media {staged_id} from Virtual Disk {vdisk_target}")
                        except Exception as v_err:
                            print(f"⚠️ [Recovery] Failed to fetch from Virtual Disk: {v_err}")

                if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
                    try:
                        await client.send_message(
                            chat_id=chat_id,
                            text=f"⚠️ <b>NeX Cloud Handoff:</b>\n\nCould not recover interrupted task for <code>{file_name}</code>. Please send your file again.",
                            reply_parameters=ReplyParameters(message_id=int(src_msg_id)) if src_msg_id else None
                        )
                    except Exception:
                        pass
                    await db.remove_active_task(task_id)
                    continue

                ms = None
                if status_msg_id:
                    try:
                        ms = await client.get_messages(chat_id, int(status_msg_id))
                    except Exception:
                        ms = None

                if not ms or not getattr(ms, "text", None):
                    try:
                        ms = await client.send_message(
                            chat_id=chat_id,
                            text=f"🔄 <b>NeX Cloud Handoff Resuming...</b>\n\nResuming <code>{file_name}</code> automatically ⚡",
                            reply_parameters=ReplyParameters(message_id=file_msg.id)
                        )
                    except Exception:
                        pass

                if not ms:
                    await db.remove_active_task(task_id)
                    continue

                print(f"🚀 [Recovery] Resuming task {task_id} for user {user_id} ({file_name})...")
                await db.remove_active_task(task_id)
                asyncio.create_task(
                    execute_rename_pipeline(
                        client=client,
                        update=ms,
                        new_filename=file_name,
                        upload_type=upload_type,
                        file_msg=file_msg,
                        extras=task_extras,
                        ms=ms,
                        status_msg=ms,
                        user_id=int(user_id) if user_id else None
                    )
                )
                await asyncio.sleep(2)
            except Exception as task_err:
                print(f"⚠️ [Recovery] Error resuming task {task_id}: {task_err}")
                try:
                    await db.remove_active_task(task_id)
                except Exception:
                    pass

        await db.cleanup_stale_tasks(max_age_seconds=21600)
    except Exception as e:
        print(f"⚠️ [Recovery] Error in resume_interrupted_tasks: {e}")
