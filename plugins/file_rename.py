import os
import time
import re
import shutil
import asyncio
import mimetypes
import warnings
import humanize
import pytz
from datetime import datetime
from PIL import Image

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

from helper.fast_telethon_pyro import fast_download

from helper.utils import (
    progress_for_pyrogram,
    convert,
    humanbytes,
    CANCEL_REQUESTS,
    USER_STATE,
    to_small_caps,
    safe_reply_params,
    edit_message_content,
    sanitize_secrets
)
from helper.ffmpeg_utils import (
    inject_metadata,
    generate_sample_video,
    generate_screenshots,
    get_video_duration_and_dims,
    apply_video_watermark
)
from helper.database import db, TIER_LIMITS
from config import Config
from bot import app_4gb

# Global concurrency queue lock - Max 10 heavy operations at once
RENAME_SEMAPHORE = asyncio.Semaphore(10)

# Per-user active task tracking & pre-rename extras cache
ACTIVE_USER_TASKS = {}
USER_QUEUE = {}
PENDING_MEDIA_EXTRAS = {}
ACTIVE_WORK_DIRS = set()
USER_FILE_CONTEXT = {}
USER_RENAME_CACHE = {}


def get_optimal_work_dir(user_id: int, file_size: int = 0) -> str:
    """
    Returns a high-speed RAM-disk path (/dev/shm/nex_tasks/...) if running on Linux
    and /dev/shm has sufficient free space (> 2.2 * file_size).
    Otherwise falls back to SSD 'downloads/...'.
    """
    ts = int(time.time())
    pid = os.getpid()
    sub = f"{user_id}_{ts}_{pid}"
    if os.name != 'nt' and os.path.exists('/dev/shm'):
        try:
            shm_usage = shutil.disk_usage('/dev/shm')
            needed = int(file_size * 2.2) if file_size > 0 else (100 * 1024 * 1024)
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


@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def rename_start(client, message):
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
        "───────────────\n"
        f"▸ <b>Fɪʟᴇɴᴀᴍᴇ :</b> <code>{filename}</code>\n"
        f"▸ <b>Sɪᴢᴇ :</b> <code>{filesize}</code>\n"
        f"▸ <b>Tʏᴘᴇ :</b> <code>.{file_extension}</code> ({mime_type})\n"
        f"▸ <b>DC ID :</b> <code>{dcid}</code>\n"
        "───────────────\n"
        "<i>Select an action below:</i>"
    )

    if is_video:
        buttons = [
            [
                InlineKeyboardButton("✏️ Rᴇɴᴀᴍᴇ Fɪʟᴇ", callback_data=f"rename_{message.id}"),
                InlineKeyboardButton("⚡ Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ", callback_data=f"auto_rename_{message.id}")
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


@Client.on_callback_query(filters.regex(r"^extract_streams(?:_(\d+))?$"))
async def extract_streams_cb(client, query: CallbackQuery):
    await query.answer("Opening Stream Inspector... 🎵")
    await query.message.reply_text(
        "<b>◈ Sᴛʀᴇᴀᴍ Iɴꜱᴘᴇᴄᴛᴏʀ 🎵</b>\n"
        "───────────────\n"
        "▸ Reply to the video file with:\n"
        "• <code>/streams</code> : View all audio & subtitle tracks\n"
        "• <code>/streams strip_subs</code> : Remove all subtitles\n"
        "• <code>/streams audio 1</code> : Keep only audio stream 1",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cʟᴏꜱᴇ", callback_data="close")]])
    )


@Client.on_callback_query(filters.regex(r"^remux_action(?:_(\d+))?$"))
async def remux_action_cb(client, query: CallbackQuery):
    await query.answer("Opening Container Remuxer... 🔄")
    await query.message.reply_text(
        "<b>◈ Lᴏꜱꜱʟᴇꜱꜱ Rᴇᴍᴜxᴇʀ 🔄</b>\n"
        "───────────────\n"
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


@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if reply_message and reply_message.reply_markup and isinstance(reply_message.reply_markup, ForceReply):
        user_id = message.from_user.id
        user_state = USER_STATE.get(user_id)
        reply_prompt = (reply_message.text or "") + (reply_message.caption or "")

        # Check if user was replying to a Watermark Text prompt
        if user_state == "waiting_wm_text" or "watermark text" in reply_prompt.lower():
            USER_STATE.pop(user_id, None)
            try:
                await reply_message.delete()
            except Exception:
                pass
            if not message.text:
                return await message.reply_text("❌ Please send text for your watermark tag.")
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
                text=f"✅ <b>Wᴀᴛᴇʀᴍᴀʀᴋ Tᴇxᴛ Sᴀᴠᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n───────────────\n▸ <b>Tᴀɢ :</b> <code>{wm_text}</code>\n▸ <b>Sᴛᴀᴛᴜꜱ :</b> Eɴᴀʙʟᴇᴅ 🟢\n\n⚡ @Nex_bots",
                reply_markup=m
            )

        # Check if user was replying to a Watermark Logo prompt
        if user_state == "waiting_wm_logo" or "watermark logo" in reply_prompt.lower() or "logo photo" in reply_prompt.lower():
            USER_STATE.pop(user_id, None)
            try:
                await reply_message.delete()
            except Exception:
                pass
            photo = message.photo or (message.document if message.document and message.document.mime_type and message.document.mime_type.startswith("image/") else None)
            if not photo:
                return await message.reply_text("❌ Please reply with a photo or image file for your watermark logo.")
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
                text="✅ <b>Wᴀᴛᴇʀᴍᴀʀᴋ Lᴏɢᴏ Sᴀᴠᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n───────────────\n▸ <b>Tʏᴘᴇ :</b> Iᴍᴀɢᴇ Lᴏɢᴏ 🖼️\n▸ <b>Sᴛᴀᴛᴜꜱ :</b> Eɴᴀʙʟᴇᴅ 🟢\n\n⚡ @Nex_bots",
                reply_markup=m
            )

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
                text=f"<b>◈ Pʀᴏᴄᴇꜱꜱɪɴɢ Dᴇꜰᴀᴜʟᴛ Mᴏᴅᴇ ({upload_mode}) ⚡</b>\n───────────────\n▸ <b>Fɪʟᴇ Nᴀᴍᴇ :</b> <code>{final_name}</code>",
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
            text=f"<b>◈ Sᴇʟᴇᴄᴛ Oᴜᴛᴘᴜᴛ Tʏᴘᴇ</b>\n───────────────\n▸ <b>Fɪʟᴇ Nᴀᴍᴇ :</b> <code>{final_name}</code>",
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
            "───────────────\n"
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


async def execute_rename_pipeline(client, update, new_filename: str, upload_type: str, file_msg, extras: dict = None):
    user_id = update.from_user.id
    ms = update.message if hasattr(update, 'message') else update

    # 0. Check Drain Mode (Server 24/7 Cloud Handoff Window)
    try:
        from bot import is_in_drain_mode
        if is_in_drain_mode():
            return await ms.edit(
                "🔄 <b>Server is performing a 30-second high-speed cloud handoff...</b>\n\n"
                "To ensure 100% transfer integrity, new tasks are briefly paused.\n"
                "Please wait ~30-60 seconds and try again! ⚡",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close")]])
            )
    except Exception:
        pass

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

            # High-Speed RAM-disk allocation (/dev/shm) if on Linux with > 2.2x file size free; fallback to SSD
            work_dir = get_optimal_work_dir(user_id, file_size)
            os.makedirs(work_dir, exist_ok=True)
            abs_work_dir = os.path.abspath(work_dir)
            ACTIVE_WORK_DIRS.add(abs_work_dir)
            file_path = os.path.join(work_dir, new_filename)
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
                        "status_message_id": ms.id,
                        "new_name": new_filename,
                        "extras": extras or {}
                    }
                )
            except Exception:
                pass

            cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Cancel", callback_data=f"cancel_process_{task_id}")]])
            try:
                await ms.edit(
                    "<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>\n\n<i>Connecting to high-speed MTProto server...</i>",
                    reply_markup=cancel_btn
                )
            except Exception:
                pass

            # 1. Download media via parallel MTProto chunk streaming with safe fallback
            start_time = time.time()
            try:
                path = await fast_download(
                    client=client,
                    message_or_file=file_msg,
                    file_path=file_path,
                    progress=progress_for_pyrogram,
                    progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>", ms, start_time, client, effective_tier)
                )
            except StopTransmission:
                raise
            except Exception as down_err:
                print(f"⚠️ fast_download failed ({down_err}). Falling back to standard download_media...")
                path = await client.download_media(
                    file_msg,
                    file_name=file_path,
                    progress=progress_for_pyrogram,
                    progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>", ms, start_time, client, effective_tier)
                )

            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                return await ms.edit("❌ <b>Download Failed: Empty or missing file received.</b>")

            if ms.id in CANCEL_REQUESTS or f"{ms.chat.id}_{ms.id}" in CANCEL_REQUESTS or (ms.chat and ms.chat.id in CANCEL_REQUESTS) or user_id in CANCEL_REQUESTS:
                return await ms.edit("❌ <b>Operation Aborted!</b>\n\n⚡ @Nex_bots")

            actual_file_size = os.path.getsize(file_path)

            # 2. Apply Custom Metadata via FFmpeg if enabled (In-place overwrite with clean filename!)
            metadata_bool = await db.get_metadata_bool(user_id)
            metadata_code = await db.get_metadata_code(user_id) or "Telegram : @Nex_bots"

            if metadata_bool:
                await ms.edit("<b>◈ ᴀᴘᴘʟʏɪɴɢ ᴄᴜꜱᴛᴏᴍ ᴍᴇᴛᴀᴅᴀᴛᴀ... 🏷️</b>")
                meta_file = os.path.join(work_dir, f"meta_{new_filename}")
                success = await inject_metadata(file_path, meta_file, metadata_code)
                if success and os.path.exists(meta_file) and os.path.getsize(meta_file) > 0:
                    clean_target = os.path.join(work_dir, new_filename)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                    os.replace(meta_file, clean_target)
                    file_path = clean_target
                    actual_file_size = os.path.getsize(file_path)
                    try:
                        await db.increment_stat(user_id, "total_metadata_applied", 1)
                    except Exception:
                        pass

            # 3. Extract accurate duration, width, and height using ffprobe & hachoir
            duration, width, height = await get_video_duration_and_dims(file_path)

            # 3.1 Apply Video Watermark if enabled & user is premium (In-place overwrite with clean filename!)
            is_video = (upload_type == "video") or new_filename.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))
            is_prem = (user_tier >= 1) or (user_id in Config.ADMIN)
            wm_info = await db.get_watermark(user_id)

            if is_video and is_prem and wm_info.get("enabled"):
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
                        clean_target = os.path.join(work_dir, new_filename)
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                        os.replace(wm_file, clean_target)
                        file_path = clean_target
                        actual_file_size = os.path.getsize(file_path)
                        duration, width, height = await get_video_duration_and_dims(file_path)
                        try:
                            await db.increment_stat(user_id, "total_watermarks_applied", 1)
                        except Exception:
                            pass

            # 4. Process Custom Thumbnail with Aspect Ratio Preservation
            c_thumb = await db.get_thumbnail(user_id)
            media = file_msg.document or file_msg.video or file_msg.audio

            if c_thumb or (hasattr(media, 'thumbs') and media.thumbs):
                try:
                    thumb_dest = os.path.join(work_dir, "thumb.jpg")
                    if c_thumb:
                        ph_path = await client.download_media(c_thumb, file_name=thumb_dest)
                    else:
                        ph_path = await client.download_media(media.thumbs[0].file_id, file_name=thumb_dest)

                    if ph_path and os.path.exists(ph_path):
                        with Image.open(ph_path) as img:
                            img = img.convert("RGB")
                            # Preserves original aspect ratio within 320x320 box!
                            img.thumbnail((320, 320))
                            img.save(ph_path, "JPEG")
                except Exception as e:
                    print(f"Thumbnail processing error: {e}")
                    ph_path = None

            # 5. Format Clean Caption (100% Clean - NO copyright or branding inside file caption!)
            c_caption = await db.get_caption(user_id)
            if c_caption:
                try:
                    caption = c_caption.format(
                        filename=new_filename,
                        filesize=humanbytes(actual_file_size),
                        duration=convert(duration)
                    )
                except Exception:
                    caption = f"**{new_filename}**"
            else:
                caption = f"**{new_filename}**"

            # Check Bot Content Protection status
            protect_content = await db.get_protect_content()

            # 6. Determine 4GB Routing & Dump Channel
            user_dump = await db.get_dump_channel(user_id)
            dump_channel = user_dump or Config.FILES_CHANNEL or Config.LOG_CHANNEL

            is_4gb = actual_file_size > (1.95 * 1024 * 1024 * 1024)
            client_4gb = getattr(client, "app_4gb", None) or app_4gb
            uploader = client_4gb if (is_4gb and client_4gb) else client
            upload_mode_tag = "<b>◈ 4ɢʙ ᴘʀᴇᴍɪᴜᴍ ᴜᴘʟᴏᴀᴅɪɴɢ... 🚀</b>" if (is_4gb and client_4gb) else "<b>◈ ᴜᴘʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 🚀</b>"

            await ms.edit(upload_mode_tag)
            upload_start = time.time()
            user_sent_msgs = []

            try:
                # 4GB Upload Flow (> 1.95GB)
                if is_4gb and client_4gb:
                    upload_target = int(dump_channel) if (dump_channel and int(dump_channel) != 0) else user_id

                    if upload_type == "document":
                        sent_msg = await uploader.send_document(
                            chat_id=upload_target,
                            document=file_path,
                            file_name=new_filename,
                            thumb=ph_path,
                            caption=caption,
                            protect_content=protect_content if upload_target == user_id else False,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier)
                        )
                    elif upload_type == "video":
                        sent_msg = await uploader.send_video(
                            chat_id=upload_target,
                            video=file_path,
                            file_name=new_filename,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                            protect_content=protect_content if upload_target == user_id else False,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier)
                        )
                    elif upload_type == "audio":
                        sent_msg = await uploader.send_audio(
                            chat_id=upload_target,
                            audio=file_path,
                            file_name=new_filename,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            protect_content=protect_content if upload_target == user_id else False,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier)
                        )

                    if upload_target == user_id:
                        user_sent_msgs.append(sent_msg.id)
                        target_msg_id = sent_msg.id
                    else:
                        # Copy to user DM if uploaded via dump channel
                        copied = await client.copy_message(
                            chat_id=user_id,
                            from_chat_id=upload_target,
                            message_id=sent_msg.id,
                            caption=caption,
                            protect_content=protect_content
                        )
                        user_sent_msgs.append(copied.id)
                        target_msg_id = copied.id

                    # Send 15-Minute Copyright Auto-Delete notice as a SEPARATE reply message
                    warn_text = "⏳ **Note:** This file will be automatically deleted in **15 minutes** due to copyright protection. Please forward it to your **Saved Messages**!"
                    try:
                        warn_msg = await client.send_message(
                            chat_id=user_id,
                            text=warn_text,
                            reply_parameters=ReplyParameters(message_id=target_msg_id)
                        )
                        user_sent_msgs.append(warn_msg.id)
                    except Exception:
                        pass
                else:
                    # Standard Upload Flow (<= 1.95GB)
                    if upload_type == "document":
                        sent_msg = await client.send_document(
                            chat_id=user_id,
                            document=file_path,
                            file_name=new_filename,
                            thumb=ph_path,
                            caption=caption,
                            protect_content=protect_content,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier)
                        )
                    elif upload_type == "video":
                        sent_msg = await client.send_video(
                            chat_id=user_id,
                            video=file_path,
                            file_name=new_filename,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                            protect_content=protect_content,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier)
                        )
                    elif upload_type == "audio":
                        sent_msg = await client.send_audio(
                            chat_id=user_id,
                            audio=file_path,
                            file_name=new_filename,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            protect_content=protect_content,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client, effective_tier)
                        )

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

                    # Backup copy to dump channel if configured
                    if dump_channel and int(dump_channel) != 0 and int(dump_channel) != user_id:
                        try:
                            await sent_msg.copy(chat_id=int(dump_channel))
                        except Exception as e:
                            print(f"Dump channel backup error: {e}")

            except StopTransmission:
                return await ms.edit("❌ <b>Upload Cancelled by User!</b>\n\n⚡ @Nex_bots")
            except Exception as e:
                return await ms.edit(f"❌ <b>Upload Failed:</b> <code>{e}</code>")

            # Record usage for 4GB uploads if not tracked inside standard block
            if is_4gb:
                try:
                    await db.add_usage(user_id, actual_file_size)
                except Exception:
                    pass

            # 7. Sample Video Generation (No Thumbnail + Custom Timeline Mode)
            sample_settings = await db.get_sample_settings(user_id)
            sample_duration = sample_settings.get("duration", 0)
            should_sample = extras.get("sample", sample_duration > 0) if extras is not None else (sample_duration > 0)

            if should_sample and sample_duration > 0 and is_video:
                try:
                    await ms.edit("<b>◈ ɢᴇɴᴇʀᴀᴛɪɴɢ ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ... 🎬</b>")
                    sample_path = os.path.join(work_dir, f"sample_{new_filename}")
                    sample_ok = await generate_sample_video(
                        input_path=file_path,
                        output_path=sample_path,
                        total_duration=duration,
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

            # 8. Screenshots Generation (if enabled in settings)
            screenshots_count = await db.get_screenshots(user_id)
            should_ss = extras.get("ss", screenshots_count > 0) if extras is not None else (screenshots_count > 0)

            if should_ss and screenshots_count > 0 and is_video:
                try:
                    await ms.edit(f"<b>◈ ɢᴇɴᴇʀᴀᴛɪɴɢ {screenshots_count} ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 📸</b>")
                    ss_dir = os.path.join(work_dir, "screenshots")
                    ss_list = await generate_screenshots(file_path, ss_dir, duration, screenshots_count)
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

            # Log activity to real-time tracker
            try:
                user_fn = update.from_user.first_name if hasattr(update, 'from_user') and update.from_user else "User"
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
        return await ms.edit(f"❌ <b>Error occurred:</b> <code>{e}</code>")

    finally:
        ACTIVE_USER_TASKS[user_id] = max(0, ACTIVE_USER_TASKS.get(user_id, 1) - 1)
        # 9. Strict Cleanup of Temporary Files, Concurrency Counter & Persistent Task
        try:
            if 'task_id' in locals():
                await db.remove_active_task(task_id)
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
        if 'work_dir' in locals() and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)


@Client.on_message(filters.private & filters.command(["reset_task", "cleartask", "unfreeze"]))
async def reset_task_cmd(client, message):
    user_id = message.from_user.id
    ACTIVE_USER_TASKS[user_id] = 0
    USER_FILE_CONTEXT.pop(user_id, None)
    USER_RENAME_CACHE.pop(user_id, None)
    await db.reset_user_tasks(user_id)
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
                    ms=ms,
                    new_filename=file_name,
                    upload_type=upload_type,
                    file_msg=file_msg,
                    extras=task_extras
                )
            )
            await asyncio.sleep(2)

        await db.cleanup_stale_tasks(max_age_seconds=21600)
    except Exception as e:
        print(f"⚠️ [Recovery] Error in resume_interrupted_tasks: {e}")
