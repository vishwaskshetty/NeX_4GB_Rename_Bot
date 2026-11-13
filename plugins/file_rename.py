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
    CANCEL_REQUESTS
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
PENDING_MEDIA_EXTRAS = {}
ACTIVE_WORK_DIRS = set()


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

    # 2GB+ File Upsell for Normal Users
    if file_size > (2 * 1024 * 1024 * 1024) and user_tier == 0 and user_id not in Config.ADMIN:
        return await message.reply_text(
            f"💎 <b>4GB+ Premium File Detected!</b>\n\n"
            f"📦 <b>File Size:</b> <code>{filesize}</code>\n"
            f"⚠️ Normal users can rename files up to <b>2.0 GB</b>.\n\n"
            f"🚀 Upgrade to <b>Premium</b> to unlock <b>4GB+ High-Speed Renaming</b>, Custom Watermarks, and Sample Videos!",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💎 Buy Premium Plan", callback_data="open_plans"),
                    InlineKeyboardButton("🎁 Claim 3-Day Free Trial", callback_data="claim_trial_cb")
                ],
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

    media_info_text = (
        f"🗂️ <b><u>NeX 4GB Media Information</u></b>\n\n"
        f"◈ <b>ꜰɪʟᴇ ɴᴀᴍᴇ :</b> <code>{filename}</code>\n"
        f"◈ <b>ꜰɪʟᴇ ꜱɪᴢᴇ :</b> <code>{filesize}</code>\n"
        f"◈ <b>ꜰɪʟᴇ ᴇxᴛᴇɴꜱɪᴏɴ :</b> <code>.{file_extension}</code>\n"
        f"◈ <b>ᴍɪᴍᴇ ᴛʏᴘᴇ :</b> <code>{mime_type}</code>\n"
        f"◈ <b>ᴅᴄ ɪᴅ :</b> <code>{dcid}</code>\n\n"
        f"<b>ᴘʟᴇᴀꜱᴇ ᴄʜᴏᴏꜱᴇ ᴀɴ ᴀᴄᴛɪᴏɴ ʙᴇʟᴏᴡ:</b>"
    )

    buttons = [
        [
            InlineKeyboardButton("⚡ Auto Clean & Rename", callback_data="auto_rename"),
            InlineKeyboardButton("📝 Custom Rename", callback_data="rename")
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
            InlineKeyboardButton("✖️ Cancel", callback_data="close")
        ]
    ]

    await message.reply_text(
        text=media_info_text,
        reply_parameters=ReplyParameters(message_id=message.id),
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex('^auto_rename$'))
async def auto_rename_handler(client, update: CallbackQuery):
    user_id = update.from_user.id
    reply_msg = update.message.reply_to_message
    if not reply_msg:
        return await update.message.edit("❌ Original file message not found!")

    file = reply_msg.document or reply_msg.video or reply_msg.audio
    if not file:
        return await update.message.edit("❌ No media found in message!")

    orig_filename = file.file_name or "file.mkv"
    clean_words = await db.get_clean_words(user_id)
    replace_words = await db.get_replace_words(user_id)
    cleaned_name = apply_cleaner(orig_filename, clean_words, replace_words)

    prefix = await db.get_prefix(user_id)
    suffix = await db.get_suffix(user_id)
    final_name = apply_prefix_suffix(cleaned_name, prefix, suffix)

    upload_mode = await db.get_upload_mode(user_id)
    if upload_mode in ["Document", "Video", "Audio"]:
        # Auto proceed directly with user's preferred upload mode
        await route_to_extras_or_execute(client, update, final_name, upload_mode.lower(), reply_msg)
        return

    # If upload mode is "Ask", present format selection
    buttons = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
    if reply_msg.video or (reply_msg.document and final_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))):
        buttons.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
    elif reply_msg.audio or (reply_msg.document and final_name.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg'))):
        buttons.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])

    await update.message.edit_text(
        text=f"⚡ <b>Auto Cleaned & Formatted Name:</b>\n`{final_name}`\n\n<b>Select Output Format:</b>",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex('^rename$'))
async def rename_handler(client, update: CallbackQuery):
    msg_id = getattr(update.message.reply_to_message, "id", None) or getattr(update.message, "reply_to_message_id", None)
    await update.message.delete()
    await update.message.reply_text(
        "<b>◈ ᴘʟᴇᴀꜱᴇ ᴇɴᴛᴇʀ ɴᴇᴡ ꜰɪʟᴇ ɴᴀᴍᴇ...</b>\n\n"
        "<i>(You can omit the extension; the original extension will be preserved automatically.)</i>",
        reply_parameters=ReplyParameters(message_id=msg_id) if msg_id else None,
        reply_markup=ForceReply(True)
    )


@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if reply_message and reply_message.reply_markup and isinstance(reply_message.reply_markup, ForceReply):
        new_name = message.text.strip()
        await message.delete()
        
        msg = await client.get_messages(message.chat.id, reply_message.id)
        file_msg = msg.reply_to_message
        if not file_msg:
            return await message.reply_text("❌ Original media message could not be retrieved!")

        file = file_msg.document or file_msg.video or file_msg.audio
        if not file:
            return await message.reply_text("❌ Original media not found!")

        orig_name = file.file_name or "file.mkv"
        _, orig_ext = os.path.splitext(orig_name)

        if "." not in new_name:
            new_name = new_name + (orig_ext if orig_ext else ".mkv")

        # Apply prefix & suffix
        user_id = message.from_user.id
        prefix = await db.get_prefix(user_id)
        suffix = await db.get_suffix(user_id)
        final_name = apply_prefix_suffix(new_name, prefix, suffix)

        await reply_message.delete()

        upload_mode = await db.get_upload_mode(user_id)
        if upload_mode in ["Document", "Video", "Audio"]:
            prompt_msg = await message.reply(
                text=f"**Processing With Default Mode ({upload_mode})...**\n\n**File Name :-** `{final_name}`",
                reply_parameters=ReplyParameters(message_id=file_msg.id)
            )
            # Create a mock callback object to execute the pipeline cleanly
            class MockCallback:
                def __init__(self, msg, user):
                    self.message = msg
                    self.from_user = user
                    self.data = f"upload_{upload_mode.lower()}"
            mock_cb = MockCallback(prompt_msg, message.from_user)
            await route_to_extras_or_execute(client, mock_cb, final_name, upload_mode.lower(), file_msg)
            return

        buttons = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
        if file_msg.video or (file_msg.document and final_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))):
            buttons.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
        elif file_msg.audio or (file_msg.document and final_name.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg'))):
            buttons.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])

        await message.reply(
            text=f"**Select The Output File Type**\n\n**File Name :-** `{final_name}`",
            reply_parameters=ReplyParameters(message_id=file_msg.id),
            reply_markup=InlineKeyboardMarkup(buttons)
        )


@Client.on_callback_query(filters.regex("^upload_"))
async def upload_callback_router(client, update: CallbackQuery):
    upload_type = update.data.split("_")[1].lower()
    
    # Extract filename from message text
    match = re.search(r'`([^`]+)`', update.message.text)
    if match:
        new_filename = match.group(1).strip()
    elif ":-" in update.message.text:
        new_filename = update.message.text.split(":-", 1)[1].strip()
    else:
        new_filename = "NeX_Renamed_File"

    file_msg = update.message.reply_to_message
    if not file_msg:
        return await update.message.edit("❌ Original media message could not be retrieved!")

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

        buttons.append([InlineKeyboardButton("⏩ Skip Extras (Rename Only)", callback_data=f"ext_skip_{file_msg.id}")])
        buttons.append([
            InlineKeyboardButton("🔕 Disable Always in Settings", callback_data=f"ext_disable_{file_msg.id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="close")
        ])

        prompt_text = (
            "╭━━━━━━━━━━━━━━━━━━━╮\n"
            "┃   🎬 <b>Media Extras Confirmation</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"◈ <b>Target File :</b> <code>{new_filename}</code>\n"
            f"◈ <b>🎬 Sample Video :</b> <code>{sample_dur}s</code>\n"
            f"◈ <b>📸 Screenshots :</b> <code>{ss_count} frames</code>\n\n"
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

    # Ensure queue concurrency limit
    await ms.edit("⏳ <b>Adding to processing queue... Please wait.</b>")
    
    async with RENAME_SEMAPHORE:
        # High-Speed RAM-disk allocation (/dev/shm) if on Linux with > 2.2x file size free; fallback to SSD
        work_dir = get_optimal_work_dir(user_id, file_size)
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
                extra={"upload_type": upload_type, "work_dir": work_dir}
            )
        except Exception:
            pass

        await ms.edit("<b>◈ ꜰɪʟᴇ ʀᴇɴᴀᴍᴇ ᴍᴏᴅᴇ: ᴇɴɢᴀɢɪɴɢ! 💠</b>")

        try:
            # 1. Download media via parallel MTProto chunk streaming (40-80+ MB/s) with safe fallback
            try:
                start_time = time.time()
                is_4gb_file = file_size > (1.95 * 1024 * 1024 * 1024)
                downloader = client
                # Route downloads through 4GB Telegram Premium Client if active & file > 500MB
                if client_4gb and getattr(client_4gb, "is_connected", False) and (file_size > 500 * 1024 * 1024 or is_4gb_file):
                    downloader = client_4gb

                try:
                    path = await fast_download(
                        client=downloader,
                        message_or_file=file_msg,
                        file_path=file_path,
                        progress=progress_for_pyrogram,
                        progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>", ms, start_time, client, effective_tier)
                    )
                except Exception as down_err:
                    if downloader != client:
                        path = await fast_download(
                            client=client,
                            message_or_file=file_msg,
                            file_path=file_path,
                            progress=progress_for_pyrogram,
                            progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>", ms, start_time, client, effective_tier)
                        )
                    else:
                        raise down_err
            except StopTransmission:
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir, ignore_errors=True)
                return await ms.edit("❌ <b>Download Cancelled by User!</b>\n\n⚡ @Nex_bots")
            except Exception as e:
                return await ms.edit(f"❌ <b>Download Failed:</b> <code>{e}</code>")

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

            if is_video and is_prem and wm_info.get("enabled") and wm_info.get("text"):
                await ms.edit("<b>◈ ᴀᴘᴘʟʏɪɴɢ ᴠɪᴅᴇᴏ ᴡᴀᴛᴇʀᴍᴀʀᴋ... 💧</b>")
                wm_file = os.path.join(work_dir, f"wm_{new_filename}")
                wm_ok = await apply_video_watermark(
                    input_path=file_path,
                    output_path=wm_file,
                    text=wm_info.get("text"),
                    position=wm_info.get("position", "top_right"),
                    size=wm_info.get("size", 28),
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
            # 9. Strict Cleanup of Temporary Files, Concurrency Counter & Persistent Task
            try:
                if 'task_id' in locals():
                    await db.remove_active_task(task_id)
            except Exception:
                pass
            try:
                ACTIVE_WORK_DIRS.discard(abs_work_dir)
            except Exception:
                pass
            ACTIVE_USER_TASKS[user_id] = max(0, ACTIVE_USER_TASKS.get(user_id, 1) - 1)
            CANCEL_REQUESTS.discard(ms.id)
            CANCEL_REQUESTS.discard(user_id)
            if ms.chat:
                CANCEL_REQUESTS.discard(ms.chat.id)
                CANCEL_REQUESTS.discard(f"{ms.chat.id}_{ms.id}")
            try:
                await ms.delete()
            except Exception:
                pass
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
