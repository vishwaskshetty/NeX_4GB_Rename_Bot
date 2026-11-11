import os
import time
import re
import shutil
import asyncio
import mimetypes
import humanize
import pytz
from datetime import datetime
from PIL import Image

from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply,
    InputMediaPhoto,
    CallbackQuery
)
from pyrogram.file_id import FileId
try:
    from pyrogram import StopTransmission
except ImportError:
    from pyrogram.errors import StopTransmission

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
    get_video_duration_and_dims
)
from helper.database import db
from config import Config
from bot import app_4gb

# Concurrency queue lock - Max 2 heavy operations at once
RENAME_SEMAPHORE = asyncio.Semaphore(2)


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

    # Check 2GB threshold vs Premium access & 4GB Session configuration
    client_4gb = getattr(client, "app_4gb", None) or app_4gb
    if file_size > (2 * 1024 * 1024 * 1024):
        is_admin = user_id in Config.ADMIN
        is_premium = await db.is_premium_user(user_id)
        if not (is_admin or is_premium):
            await message.reply_text(
                "⭐ <b>4GB+ File Detected!</b>\n\n"
                "Files over 2GB require <b>Premium Access</b>.\n"
                "Contact the owner to upgrade!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Contact Owner", url="https://t.me/Nex_bots")],
                    [InlineKeyboardButton("⚡ Support Channel", url="https://t.me/Nex_bots")]
                ]),
                quote=True
            )
            return

        if not client_4gb:
            await message.reply_text(
                "🚫 <b>Files larger than 2GB require 4GB Premium Mode!</b>\n\n"
                "<i>Telegram restricts standard bot tokens to 2GB uploads.\n"
                "To enable 4GB uploads, configure <code>STRING_SESSION</code> with a Telegram Premium account.\n"
                "Need help? Contact @Nex_bots.</i>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Support Channel", url="https://t.me/Nex_bots")]]),
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
        reply_to_message_id=message.id,
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
        await execute_rename_pipeline(client, update, final_name, upload_mode.lower(), reply_msg)
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
    msg_id = update.message.reply_to_message_id
    await update.message.delete()
    await update.message.reply_text(
        "<b>◈ ᴘʟᴇᴀꜱᴇ ᴇɴᴛᴇʀ ɴᴇᴡ ꜰɪʟᴇ ɴᴀᴍᴇ...</b>\n\n"
        "<i>(You can omit the extension; the original extension will be preserved automatically.)</i>",
        reply_to_message_id=msg_id,
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
                reply_to_message_id=file_msg.id
            )
            # Create a mock callback object to execute the pipeline cleanly
            class MockCallback:
                def __init__(self, msg, user):
                    self.message = msg
                    self.from_user = user
                    self.data = f"upload_{upload_mode.lower()}"
            mock_cb = MockCallback(prompt_msg, message.from_user)
            await execute_rename_pipeline(client, mock_cb, final_name, upload_mode.lower(), file_msg)
            return

        buttons = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
        if file_msg.video or (file_msg.document and final_name.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))):
            buttons.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
        elif file_msg.audio or (file_msg.document and final_name.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg'))):
            buttons.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])

        await message.reply(
            text=f"**Select The Output File Type**\n\n**File Name :-** `{final_name}`",
            reply_to_message_id=file_msg.id,
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

    await execute_rename_pipeline(client, update, new_filename, upload_type, file_msg)


async def execute_rename_pipeline(client, update, new_filename: str, upload_type: str, file_msg):
    user_id = update.from_user.id
    ms = update.message if hasattr(update, 'message') else update

    # Verify 4GB Premium permission before entering semaphore
    file = file_msg.document or file_msg.video or file_msg.audio
    file_size = getattr(file, "file_size", 0) if file else 0
    if file_size > (2 * 1024 * 1024 * 1024):
        is_admin = user_id in Config.ADMIN
        is_premium = await db.is_premium_user(user_id)
        if not (is_admin or is_premium):
            return await ms.edit(
                "⭐ <b>4GB+ File Detected!</b>\n\n"
                "Files over 2GB require <b>Premium Access</b>.\n"
                "Contact the owner to upgrade!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact Owner", url="https://t.me/Nex_bots")]])
            )

    # Ensure queue concurrency limit
    await ms.edit("⏳ <b>Adding to processing queue... Please wait.</b>")
    
    async with RENAME_SEMAPHORE:
        work_dir = f"downloads/{user_id}_{int(time.time())}_{os.getpid()}"
        os.makedirs(work_dir, exist_ok=True)
        file_path = os.path.join(work_dir, new_filename)
        ph_path = None
        sample_path = None
        ss_dir = None

        await ms.edit("<b>◈ ꜰɪʟᴇ ʀᴇɴᴀᴍᴇ ᴍᴏᴅᴇ: ᴇɴɢᴀɢɪɴɢ! 💠</b>")

        try:
            # 1. Download media with live progress bar and cancellation hook
            try:
                start_time = time.time()
                path = await client.download_media(
                    message=file_msg,
                    file_name=file_path,
                    progress=progress_for_pyrogram,
                    progress_args=("<b>◈ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 📥</b>", ms, start_time, client)
                )
            except StopTransmission:
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir, ignore_errors=True)
                return await ms.edit("❌ <b>Download Cancelled by User!</b>\n\n⚡ @Nex_bots")
            except Exception as e:
                return await ms.edit(f"❌ <b>Download Failed:</b> <code>{e}</code>")

            if ms.id in CANCEL_REQUESTS or f"{ms.chat.id}_{ms.id}" in CANCEL_REQUESTS:
                return await ms.edit("❌ <b>Operation Aborted!</b>\n\n⚡ @Nex_bots")

            actual_file_size = os.path.getsize(file_path)

            # 2. Apply Custom Metadata via FFmpeg if enabled
            metadata_bool = await db.get_metadata_bool(user_id)
            metadata_code = await db.get_metadata_code(user_id) or "Telegram : @Nex_bots"

            if metadata_bool:
                await ms.edit("<b>◈ ᴀᴘᴘʟʏɪɴɢ ᴄᴜꜱᴛᴏᴍ ᴍᴇᴛᴀᴅᴀᴛᴀ... 🏷️</b>")
                meta_file = os.path.join(work_dir, f"meta_{new_filename}")
                success = await inject_metadata(file_path, meta_file, metadata_code)
                if success:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception:
                        pass
                    file_path = meta_file
                    actual_file_size = os.path.getsize(file_path)

            # 3. Extract accurate duration, width, and height using ffprobe & hachoir
            duration, width, height = await get_video_duration_and_dims(file_path)

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

            # 5. Format Custom Caption
            c_caption = await db.get_caption(user_id)
            if c_caption:
                try:
                    caption = c_caption.format(
                        filename=new_filename,
                        filesize=humanbytes(actual_file_size),
                        duration=convert(duration)
                    )
                except Exception:
                    caption = f"<b>{new_filename}</b>\n\n⚡ @Nex_bots"
            else:
                caption = f"<b>{new_filename}</b>\n\n⚡ @Nex_bots"

            # 6. Determine 4GB Routing & Dump Channel
            user_dump = await db.get_dump_channel(user_id)
            dump_channel = user_dump or Config.FILES_CHANNEL or Config.LOG_CHANNEL

            is_4gb = actual_file_size > (1.95 * 1024 * 1024 * 1024)
            client_4gb = getattr(client, "app_4gb", None) or app_4gb
            uploader = client_4gb if (is_4gb and client_4gb) else client
            upload_mode_tag = "<b>◈ 4ɢʙ ᴘʀᴇᴍɪᴜᴍ ᴜᴘʟᴏᴀᴅɪɴɢ... 🚀</b>" if (is_4gb and client_4gb) else "<b>◈ ᴜᴘʟᴏᴀᴅɪɴɢ ꜰɪʟᴇ... 🚀</b>"

            await ms.edit(upload_mode_tag)
            upload_start = time.time()

            try:
                # 4GB Upload Flow (> 1.95GB)
                if is_4gb and client_4gb:
                    upload_target = int(dump_channel) if (dump_channel and int(dump_channel) != 0) else user_id

                    if upload_type == "document":
                        sent_msg = await uploader.send_document(
                            chat_id=upload_target,
                            document=file_path,
                            thumb=ph_path,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client)
                        )
                    elif upload_type == "video":
                        sent_msg = await uploader.send_video(
                            chat_id=upload_target,
                            video=file_path,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client)
                        )
                    elif upload_type == "audio":
                        sent_msg = await uploader.send_audio(
                            chat_id=upload_target,
                            audio=file_path,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client)
                        )

                    # Copy to user DM if uploaded via dump channel
                    if upload_target != user_id:
                        await client.copy_message(
                            chat_id=user_id,
                            from_chat_id=upload_target,
                            message_id=sent_msg.id,
                            caption=caption
                        )
                else:
                    # Standard Upload Flow (<= 1.95GB)
                    if upload_type == "document":
                        sent_msg = await client.send_document(
                            chat_id=user_id,
                            document=file_path,
                            thumb=ph_path,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client)
                        )
                    elif upload_type == "video":
                        sent_msg = await client.send_video(
                            chat_id=user_id,
                            video=file_path,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client)
                        )
                    elif upload_type == "audio":
                        sent_msg = await client.send_audio(
                            chat_id=user_id,
                            audio=file_path,
                            caption=caption,
                            thumb=ph_path,
                            duration=duration,
                            progress=progress_for_pyrogram,
                            progress_args=(upload_mode_tag, ms, upload_start, client)
                        )

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

            # 7. Sample Video Generation (if enabled in settings)
            sample_duration = await db.get_sample_duration(user_id)
            is_video = (upload_type == "video") or new_filename.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))

            if sample_duration > 0 and is_video:
                try:
                    await ms.edit("<b>◈ ɢᴇɴᴇʀᴀᴛɪɴɢ ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ... 🎬</b>")
                    sample_path = os.path.join(work_dir, f"sample_{new_filename}")
                    sample_ok = await generate_sample_video(file_path, sample_path, duration, sample_duration)
                    if sample_ok:
                        sample_cap = f"🎬 <b>ꜱᴀᴍᴘʟᴇ ᴠɪᴅᴇᴏ ({sample_duration}ꜱ)</b>\n\n🏷 <code>{new_filename}</code>\n\n⚡ Powered by @Nex_bots"
                        sample_dur, s_w, s_h = await get_video_duration_and_dims(sample_path)
                        await client.send_video(
                            chat_id=user_id,
                            video=sample_path,
                            caption=sample_cap,
                            thumb=ph_path,
                            duration=sample_dur or sample_duration,
                            width=s_w or width,
                            height=s_h or height,
                            supports_streaming=True
                        )
                except Exception as e:
                    print(f"Sample video error: {e}")

            # 8. Screenshots Generation (if enabled in settings)
            screenshots_count = await db.get_screenshots(user_id)
            if screenshots_count > 0 and is_video:
                try:
                    await ms.edit(f"<b>◈ ɢᴇɴᴇʀᴀᴛɪɴɢ {screenshots_count} ꜱᴄʀᴇᴇɴꜱʜᴏᴛꜱ... 📸</b>")
                    ss_dir = os.path.join(work_dir, "screenshots")
                    ss_list = await generate_screenshots(file_path, ss_dir, duration, screenshots_count)
                    if ss_list:
                        media_group = []
                        for idx, sp in enumerate(ss_list):
                            cap = f"📸 Screenshot {idx+1}/{len(ss_list)} - {new_filename}\n⚡ @Nex_bots" if idx == 0 else ""
                            media_group.append(InputMediaPhoto(media=sp, caption=cap))
                        await client.send_media_group(chat_id=user_id, media=media_group)
                except Exception as e:
                    print(f"Screenshots error: {e}")

        except Exception as e:
            return await ms.edit(f"❌ <b>Error occurred:</b> <code>{e}</code>")

        finally:
            # 9. Strict Cleanup of Temporary Files & Cancellation Set
            CANCEL_REQUESTS.discard(ms.id)
            if ms.chat:
                CANCEL_REQUESTS.discard(f"{ms.chat.id}_{ms.id}")
            try:
                await ms.delete()
            except Exception:
                pass
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
