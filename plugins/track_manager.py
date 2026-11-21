"""
NeX 4GB Rename Bot — Interactive File Track Manager
Developed by @Nex_bots

Provides a fully interactive Audio & Subtitle Track Selector / Remover:
  • static_ffmpeg.add_paths() startup registration
  • ffprobe track inspection (-show_streams json)
  • Interactive toggle ✅ / ❌ for every Audio and Subtitle stream
  • Zero-loss stream-copy muxing (ffmpeg -c copy) in seconds
  • Preserves crisp LANCZOS thumbnail & saved bottom caption
  • 4GB routing: app_4gb via -1003792044224 bridge, client for <= 2000MB
  • Clean temporary scratch directory wiping
"""

import os
import sys
import time
import json
import shutil
import asyncio
import logging
import traceback

logger = logging.getLogger(__name__)
log = logger

# Ensure static_ffmpeg is in PATH
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception as fe:
    log.info(f"static_ffmpeg auto-init info: {fe}")

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    ForceReply,
    ReplyParameters,
)

from helper.database import db
from helper.utils import (
    humanbytes,
    USER_STATE,
    edit_message_content,
    prepare_crisp_thumbnail,
    safe_reply_params,
)
from helper.fast_transfer import (
    fast_download,
    fast_upload,
    send_input_file_big,
    _TRANSFER_SEMAPHORE,
    _cleanup_memory
)
from helper.ffmpeg_utils import _wrap_nice
from config import Config, parse_channel_id

# In-memory track state per user:
# _TRACK_CTX[user_id] = {
#     "file_msg_id": int,
#     "chat_id": int,
#     "file_id": str,
#     "file_size": int,
#     "orig_name": str,
#     "streams": {"audio": [...], "subtitle": [...]},
#     "selection": {map_id: bool},  # e.g. "0:a:0": True, "0:s:0": False
#     "local_path": str,
#     "work_dir": str,
#     "status_msg_id": int,
# }
_TRACK_CTX: dict = {}
_TMP_ROOT = "/tmp/nex_tracks"


def _lang_title(lang: str) -> str:
    """Returns human-readable language string from ISO code."""
    mapping = {
        "kan": "Kannada", "hin": "Hindi", "tam": "Tamil", "tel": "Telugu",
        "eng": "English", "mal": "Malayalam", "ben": "Bengali", "mar": "Marathi",
        "pun": "Punjabi", "guj": "Gujarati", "jpn": "Japanese", "kor": "Korean",
        "chi": "Chinese", "zho": "Chinese", "fre": "French", "fra": "French",
        "ger": "German", "deu": "German", "spa": "Spanish", "por": "Portuguese",
        "ita": "Italian", "rus": "Russian", "ara": "Arabic", "tur": "Turkish",
        "und": "Unknown",
    }
    return mapping.get((lang or "").strip().lower(), (lang or "Unknown").capitalize())


def _channel_layout(channels: int) -> str:
    if channels == 1:
        return "1.0"
    if channels == 2:
        return "2.0"
    if channels == 6:
        return "5.1"
    if channels == 8:
        return "7.1"
    return f"{channels}.0" if channels else "2.0"


async def inspect_media_streams(file_path: str) -> dict:
    """
    Runs ffprobe -v quiet -print_format json -show_streams on the file
    and returns parsed audio & subtitle tracks with map IDs (0:a:0, 0:s:0, etc.).
    """
    res = {"audio": [], "subtitle": []}
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            file_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if stdout:
            data = json.loads(stdout.decode(errors="replace"))
            a_idx = 0
            s_idx = 0
            for stream in data.get("streams", []):
                ctype = stream.get("codec_type")
                tags = stream.get("tags") or {}
                raw_codec = (stream.get("codec_name") or "unknown").upper()
                lang = tags.get("language") or tags.get("LANGUAGE") or "und"
                title = tags.get("title") or tags.get("TITLE") or tags.get("handler_name") or ""
                
                if ctype == "audio":
                    channels = int(stream.get("channels") or 2)
                    map_id = f"0:a:{a_idx}"
                    res["audio"].append({
                        "map_id": map_id,
                        "track_num": a_idx + 1,
                        "stream_index": int(stream.get("index", 0)),
                        "codec": raw_codec,
                        "channels": channels,
                        "layout": _channel_layout(channels),
                        "lang": _lang_title(lang),
                        "title": title.strip(),
                    })
                    a_idx += 1
                elif ctype == "subtitle":
                    map_id = f"0:s:{s_idx}"
                    sub_codec = "SRT" if "SUBRIP" in raw_codec else raw_codec
                    res["subtitle"].append({
                        "map_id": map_id,
                        "track_num": s_idx + 1,
                        "stream_index": int(stream.get("index", 0)),
                        "codec": sub_codec,
                        "lang": _lang_title(lang),
                        "title": title.strip(),
                    })
                    s_idx += 1
    except Exception as e:
        log.error(f"ffprobe inspect_media_streams error: {e}")
    return res


def _build_menu_keyboard(ctx: dict) -> InlineKeyboardMarkup:
    """Builds interactive inline keyboard with ✅ / ❌ buttons."""
    sel = ctx["selection"]
    buttons = []

    # Audio tracks
    for item in ctx["streams"].get("audio", []):
        mid = item["map_id"]
        status = "✅" if sel.get(mid, True) else "❌"
        # Example: ✅ 🔊 Audio #1: Kannada (AAC 2.0)
        label = f"{status} 🔊 Audio #{item['track_num']}: {item['lang']} ({item['codec']} {item['layout']})"
        if len(label) > 60:
            label = f"{status} 🔊 Audio #{item['track_num']}: {item['lang']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"trk_tog_{mid}")])

    # Subtitle tracks
    for item in ctx["streams"].get("subtitle", []):
        mid = item["map_id"]
        status = "✅" if sel.get(mid, True) else "❌"
        # Example: ✅ 💬 Sub #1: English (SRT)
        label = f"{status} 💬 Sub #{item['track_num']}: {item['lang']} ({item['codec']})"
        if len(label) > 60:
            label = f"{status} 💬 Sub #{item['track_num']}: {item['lang']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"trk_tog_{mid}")])

    # Bottom action buttons
    buttons.append([
        InlineKeyboardButton("⚡ Aᴘᴘʟʏ & Rᴇɴᴀᴍᴇ Fɪʟᴇ", callback_data="trk_apply")
    ])
    buttons.append([
        InlineKeyboardButton("✖️ Cᴀɴᴄᴇʟ", callback_data="trk_cancel")
    ])
    return InlineKeyboardMarkup(buttons)


def _build_menu_text(ctx: dict) -> str:
    n_a = len(ctx["streams"].get("audio", []))
    n_s = len(ctx["streams"].get("subtitle", []))
    kept_a = sum(1 for m in ctx["selection"] if m.startswith("0:a:") and ctx["selection"][m])
    kept_s = sum(1 for m in ctx["selection"] if m.startswith("0:s:") and ctx["selection"][m])
    return (
        "<b>◈ NᴇX Tʀᴀᴄᴋ Mᴀɴᴀɢᴇʀ 🎧</b>\n\n"
        f"▸ <b>Fɪʟᴇ :</b> <code>{ctx['orig_name']}</code>\n"
        f"▸ <b>Sɪᴢᴇ :</b> <code>{humanbytes(ctx['file_size'])}</code>\n"
        f"▸ <b>Aᴜᴅɪᴏ Tʀᴀᴄᴋꜱ :</b> <code>{kept_a}/{n_a} Selected</code>\n"
        f"▸ <b>Sᴜʙᴛɪᴛʟᴇꜱ :</b> <code>{kept_s}/{n_s} Selected</code>\n\n"
        "<i>Tap any track to toggle between ✅ Keep and ❌ Remove.\n"
        "Once configured, click <b>⚡ Apply & Rename File</b> below.</i>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point: User clicks "🎧 Eᴅɪᴛ Tʀᴀᴄᴋꜱ (Aᴜᴅɪᴏ / Sᴜʙ)"
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^inspect_tracks(?:_(\d+))?$"))
async def inspect_tracks_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    await query.answer("🎧 Opening Track Manager...")

    # Resolve original media message
    target_id = None
    if query.matches and query.matches[0].groups() and query.matches[0].group(1):
        target_id = int(query.matches[0].group(1))

    file_msg = None
    if target_id:
        try:
            file_msg = await client.get_messages(query.message.chat.id, target_id)
        except Exception:
            pass

    if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
        if query.message.reply_to_message and (
            query.message.reply_to_message.document
            or query.message.reply_to_message.video
        ):
            file_msg = query.message.reply_to_message

    if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
        from plugins.file_rename import USER_FILE_CONTEXT
        ctx_data = USER_FILE_CONTEXT.get(user_id, {})
        c_id = ctx_data.get("file_msg_id")
        if c_id:
            try:
                file_msg = await client.get_messages(query.message.chat.id, c_id)
            except Exception:
                pass

    if not file_msg or not (file_msg.document or file_msg.video or file_msg.audio):
        return await query.message.reply_text(
            "❌ <b>Original media not found!</b> Please forward the file again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close")]])
        )

    file = file_msg.document or file_msg.video or file_msg.audio
    orig_name = file.file_name or "video.mkv"
    file_size = file.file_size or 0

    # Ensure scratch directory
    work_dir = os.path.join(_TMP_ROOT, f"{user_id}_{int(time.time())}")
    os.makedirs(work_dir, exist_ok=True)
    _, ext = os.path.splitext(orig_name)
    local_path = os.path.join(work_dir, f"source{ext or '.mkv'}")

    status_msg = await query.message.reply_text(
        "⏳ <b>Inspecting file streams with ffprobe...</b>",
        **safe_reply_params(file_msg.id)
    )

    try:
        # Fast download to local scratch
        await fast_download(
            client=client,
            message_or_file=file_msg,
            file_path=local_path,
            progress=None,
            progress_args=(),
        )
    except Exception as dl_err:
        log.warning(f"fast_download for track inspector failed: {dl_err}. Falling back to standard download...")
        try:
            await client.download_media(file_msg, file_name=local_path)
        except Exception as dl_err2:
            log.error(f"Fallback download failed: {dl_err2}")
            try:
                await status_msg.edit(f"❌ <b>Download failed:</b> <code>{dl_err2}</code>")
            except Exception:
                pass
            shutil.rmtree(work_dir, ignore_errors=True)
            from bot import app_4gb
            _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)
            return

    if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
        try:
            await status_msg.edit("❌ <b>Failed to download file header for inspection.</b>")
        except Exception:
            pass
        shutil.rmtree(work_dir, ignore_errors=True)
        from bot import app_4gb
        _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)
        return

    # Run ffprobe stream extraction
    streams = await inspect_media_streams(local_path)
    audio_tracks = streams.get("audio", [])
    sub_tracks = streams.get("subtitle", [])

    if not audio_tracks and not sub_tracks:
        try:
            await status_msg.edit(
                "⚠️ <b>No secondary audio or subtitle tracks found in this file!</b>\n\n"
                "This file has only a single stream or is unsupported for track stripping.\n"
                "Use the standard <b>✏️ Rename File</b> button instead.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="close")]])
            )
        except Exception:
            pass
        shutil.rmtree(work_dir, ignore_errors=True)
        from bot import app_4gb
        _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)
        return

    # Initialize selection: all tracks checked ✅ by default
    selection = {}
    for a in audio_tracks:
        selection[a["map_id"]] = True
    for s in sub_tracks:
        selection[s["map_id"]] = True

    _TRACK_CTX[user_id] = {
        "file_msg_id": file_msg.id,
        "chat_id": query.message.chat.id,
        "file_id": file.file_id,
        "file_size": file_size,
        "orig_name": orig_name,
        "streams": streams,
        "selection": selection,
        "local_path": local_path,
        "work_dir": work_dir,
        "status_msg_id": status_msg.id,
    }

    text = _build_menu_text(_TRACK_CTX[user_id])
    markup = _build_menu_keyboard(_TRACK_CTX[user_id])
    try:
        await status_msg.edit(text, reply_markup=markup)
    except Exception:
        await query.message.reply_text(text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: User toggles an Audio or Subtitle stream (✅ ⇄ ❌)
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^trk_tog_(0:[as]:\d+)$"))
async def trk_toggle_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    ctx = _TRACK_CTX.get(user_id)
    if not ctx:
        return await query.answer("❌ Session expired. Please tap 🎧 Edit Tracks again.", show_alert=True)

    map_id = query.matches[0].group(1)
    current_state = ctx["selection"].get(map_id, True)
    new_state = not current_state

    # Guard: prevent removing ALL audio tracks
    if map_id.startswith("0:a:") and not new_state:
        remaining_audio = sum(
            1 for m in ctx["selection"]
            if m.startswith("0:a:") and (ctx["selection"][m] if m != map_id else False)
        )
        if remaining_audio == 0:
            return await query.answer("⚠️ You must keep at least 1 Audio Track!", show_alert=True)

    ctx["selection"][map_id] = new_state
    text = _build_menu_text(ctx)
    markup = _build_menu_keyboard(ctx)
    try:
        await edit_message_content(query.message, text, reply_markup=markup)
    except Exception:
        pass
    await query.answer("✅ Track Kept" if new_state else "❌ Track Removed")


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: User clicks "⚡ Aᴘᴘʟʏ & Rᴇɴᴀᴍᴇ Fɪʟᴇ"
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^trk_apply$"))
async def trk_apply_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    ctx = _TRACK_CTX.get(user_id)
    if not ctx:
        return await query.answer("❌ Session expired. Please tap 🎧 Edit Tracks again.", show_alert=True)

    USER_STATE[user_id] = "waiting_track_rename"
    orig = ctx.get("orig_name", "file.mkv")

    prompt_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷️ Keep Original Name", callback_data="trk_keep_name")],
        [InlineKeyboardButton("✖️ Cancel", callback_data="trk_cancel")]
    ])

    await query.message.reply_text(
        "<b>◈ Rᴇɴᴀᴍᴇ Tʀᴀᴄᴋ-Eᴅɪᴛᴇᴅ Fɪʟᴇ ✏️</b>\n\n"
        f"▸ <b>Cᴜʀʀᴇɴᴛ Nᴀᴍᴇ :</b> <code>{orig}</code>\n\n"
        "<i>Reply to this message with your new filename (including extension),\n"
        "or click <b>🏷️ Keep Original Name</b> below:</i>",
        reply_markup=prompt_markup,
    )
    await query.answer("Ready for new name!")


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: User chooses "Keep Original Name"
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^trk_keep_name$"))
async def trk_keep_name_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    USER_STATE.pop(user_id, None)
    ctx = _TRACK_CTX.pop(user_id, None)
    if not ctx:
        return await query.answer("❌ Session expired.", show_alert=True)
    await query.answer("Using original name...")
    try:
        await query.message.delete()
    except Exception:
        pass
    asyncio.create_task(
        _execute_track_mux_and_upload(client, query.message, ctx, ctx["orig_name"])
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: User replies with a new filename
# ─────────────────────────────────────────────────────────────────────────────

async def handle_track_rename_reply(client, message):
    user_id = message.from_user.id
    USER_STATE.pop(user_id, None)
    ctx = _TRACK_CTX.pop(user_id, None)
    if not ctx:
        return await message.reply_text("❌ Track editing session expired. Please start again.")

    new_name = (message.text or "").strip()
    if not new_name or new_name.lower() == "keep":
        new_name = ctx["orig_name"]

    _, orig_ext = os.path.splitext(ctx["orig_name"])
    if "." not in new_name:
        new_name += (orig_ext or ".mkv")

    # Apply saved prefix & suffix
    prefix = await db.get_prefix(user_id)
    suffix = await db.get_suffix(user_id)
    from helper.utils import apply_prefix_suffix
    new_name = apply_prefix_suffix(new_name, prefix, suffix)

    try:
        await message.delete()
    except Exception:
        pass

    asyncio.create_task(
        _execute_track_mux_and_upload(client, message, ctx, new_name)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Lossless ffmpeg -c copy Muxing + Crisp Thumbnail + 4GB Upload
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_track_mux_and_upload(client, message, ctx: dict, new_filename: str):
    user_id = message.from_user.id if message.from_user else ctx.get("chat_id")
    work_dir = ctx.get("work_dir", os.path.join(_TMP_ROOT, str(user_id)))
    local_path = ctx.get("local_path")
    chat_id = ctx.get("chat_id", user_id)
    file_msg_id = ctx.get("file_msg_id")
    selection = ctx.get("selection", {})

    status_msg = None
    transfer_sem_held = False
    try:
        await _TRANSFER_SEMAPHORE.acquire()
        transfer_sem_held = True

        try:
            status_msg = await client.send_message(
                chat_id=chat_id,
                text=(
                    "<b>◈ NᴇX Tʀᴀᴄᴋ Mᴜxᴇʀ ⚡</b>\n\n"
                    f"▸ <b>Fɪʟᴇ :</b> <code>{new_filename}</code>\n"
                    "▸ <b>Sᴛᴀᴛᴜꜱ :</b> Muxing streams losslessly with <code>ffmpeg -c copy</code>...\n\n"
                    "⏳ <i>Stream copy takes ~5–10 seconds with zero re-encoding!</i>"
                ),
                **safe_reply_params(file_msg_id)
            )
        except Exception:
            pass

        # Build exact ffmpeg -map command
        # ffmpeg -y -i "<input>" -map 0:v:0 -map 0:a:0 -map 0:s:0 -c copy "<output>"
        output_path = os.path.join(work_dir, f"out_{new_filename}")
        cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-i", local_path,
            "-map", "0:v:0"  # keep primary video
        ]

        # Map kept audio streams
        audio_mapped = 0
        for mid, kept in selection.items():
            if mid.startswith("0:a:") and kept:
                cmd.extend(["-map", mid])
                audio_mapped += 1

        if audio_mapped == 0:
            # Fallback: keep first audio or -an
            first_audio = next((m for m in selection if m.startswith("0:a:")), None)
            if first_audio:
                cmd.extend(["-map", first_audio])
            else:
                cmd.append("-an")

        # Map kept subtitle streams
        sub_mapped = 0
        for mid, kept in selection.items():
            if mid.startswith("0:s:") and kept:
                cmd.extend(["-map", mid])
                sub_mapped += 1

        if sub_mapped == 0:
            cmd.append("-sn")

        cmd.extend(["-c", "copy", output_path])

        log.info(f"Running track mux command: {' '.join(cmd)}")

        mux_ok = False
        try:
            proc = await asyncio.create_subprocess_exec(
                *_wrap_nice(cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=300)
            mux_ok = os.path.exists(output_path) and os.path.getsize(output_path) > 0
            if not mux_ok:
                log.error(f"Track mux failed: {stderr_bytes.decode(errors='replace')[-500:]}")
        except Exception as mux_err:
            log.error(f"Track mux exception: {mux_err}")

        if not mux_ok:
            if status_msg:
                try:
                    await status_msg.edit("❌ <b>Stream muxing failed!</b> Please verify the file format.")
                except Exception:
                    pass
            return

        output_size = os.path.getsize(output_path)

        if status_msg:
            try:
                await status_msg.edit(
                    "<b>◈ NᴇX Tʀᴀᴄᴋ Mᴜxᴇʀ ⚡</b>\n\n"
                    f"▸ <b>Fɪʟᴇ :</b> <code>{new_filename}</code>\n"
                    f"▸ <b>Sɪᴢᴇ :</b> <code>{humanbytes(output_size)}</code>\n"
                    "▸ <b>Sᴛᴀᴛᴜꜱ :</b> Uploading remuxed file... 🚀\n\n"
                    "⚡ <i>Fast multi-socket streaming in progress...</i>"
                )
            except Exception:
                pass

        # Setup Premium 4GB routing & uploader
        from bot import app_4gb
        is_4gb = output_size > (1.95 * 1024 * 1024 * 1024)
        client_4gb = getattr(client, "app_4gb", None) or app_4gb
        is_prem_active = bool(client_4gb and (getattr(client, "app_4gb_started", False) or getattr(client_4gb, "is_connected", False) or getattr(client_4gb, "storage", None)))
        uploader = client_4gb if is_prem_active else client

        # Prepare crisp LANCZOS 4:4:4 thumbnail
        thumb_path = None
        try:
            c_thumb = await db.get_thumbnail(user_id)
            if c_thumb:
                t_dir = os.path.join(work_dir, "thumb")
                os.makedirs(t_dir, exist_ok=True)
                t_raw = os.path.join(t_dir, "thumb_raw.jpg")
                t_crisp = os.path.join(t_dir, "thumb_crisp.jpg")
                await client.download_media(c_thumb, file_name=t_raw)
                if os.path.exists(t_raw):
                    thumb_path = prepare_crisp_thumbnail(t_raw, t_crisp)
        except Exception as th_err:
            log.warning(f"Track manager thumb error: {th_err}")
            thumb_path = None

        # Prepare Bottom Caption: {new_file_name}\n\n{bottom_caption}
        b_caption = await db.get_bottom_caption(user_id)
        base_name, _ = os.path.splitext(new_filename)
        if b_caption:
            caption = f"<b>{base_name}</b>\n\n{b_caption}"
        else:
            caption = f"<b>{base_name}</b>"

        # Determine upload type
        low = new_filename.lower()
        if low.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv")):
            upload_type = "video"
        elif low.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac")):
            upload_type = "audio"
        else:
            upload_type = "document"

        # Upload using fast_upload
        sent_msg = None
        uploaded_file = None
        try:
            uploaded_file = await fast_upload(
                client=uploader,
                file_path=output_path,
                progress=None,
                progress_args=(),
                is_prem=is_4gb
            )
        except Exception as up_err:
            log.warning(f"fast_upload error in track manager: {up_err}")

        # Determine bridge channel for 4GB transfers
        user_dump = await db.get_dump_channel(user_id)
        bridge_channel = parse_channel_id(
            user_dump or Config.DUMP_CHANNEL or Config.FILES_CHANNEL or Config.LOG_CHANNEL or -1003792044224
        )

        try:
            if (is_prem_active or (is_4gb and client_4gb)) and bridge_channel and bridge_channel != 0:
                bridge_msg = None
                if uploaded_file:
                    bridge_msg = await send_input_file_big(
                        uploader_client=uploader,
                        target_chat_id=bridge_channel,
                        input_file_big=uploaded_file,
                        thumb_path=thumb_path,
                        media_msg=None,
                        new_filename=new_filename,
                        caption=caption,
                        upload_type=upload_type,
                    )
                elif upload_type == "video":
                    bridge_msg = await uploader.send_video(
                        chat_id=bridge_channel,
                        video=output_path,
                        file_name=new_filename,
                        caption=caption,
                        thumb=thumb_path,
                        supports_streaming=True
                    )
                else:
                    bridge_msg = await uploader.send_document(
                        chat_id=bridge_channel,
                        document=output_path,
                        file_name=new_filename,
                        caption=caption,
                        thumb=thumb_path
                    )

                if bridge_msg and hasattr(bridge_msg, "id"):
                    sent_msg = await client.copy_message(
                        chat_id=chat_id,
                        from_chat_id=bridge_channel,
                        message_id=bridge_msg.id,
                        caption=caption
                    )
            else:
                if uploaded_file:
                    sent_msg = await send_input_file_big(
                        uploader_client=uploader,
                        target_chat_id=chat_id,
                        input_file_big=uploaded_file,
                        thumb_path=thumb_path,
                        media_msg=None,
                        new_filename=new_filename,
                        caption=caption,
                        upload_type=upload_type,
                    )
                elif upload_type == "video":
                    sent_msg = await uploader.send_video(
                        chat_id=chat_id,
                        video=output_path,
                        file_name=new_filename,
                        caption=caption,
                        thumb=thumb_path,
                        supports_streaming=True,
                        **safe_reply_params(file_msg_id)
                    )
                else:
                    sent_msg = await uploader.send_document(
                        chat_id=chat_id,
                        document=output_path,
                        file_name=new_filename,
                        caption=caption,
                        thumb=thumb_path,
                        **safe_reply_params(file_msg_id)
                    )
        except Exception as send_err:
            log.error(f"Track manager message delivery error: {send_err}")

        if sent_msg:
            if status_msg:
                try:
                    await status_msg.edit(
                        "<b>◈ NᴇX Tʀᴀᴄᴋ Mᴀɴᴀɢᴇʀ ⚡</b>\n\n"
                        f"▸ <b>Fɪʟᴇ :</b> <code>{new_filename}</code>\n"
                        f"▸ <b>Sɪᴢᴇ :</b> <code>{humanbytes(output_size)}</code>\n"
                        "▸ <b>Sᴛᴀᴛᴜꜱ :</b> ✅ <b>Tʀᴀᴄᴋꜱ Eᴅɪᴛᴇᴅ & Dᴇʟɪᴠᴇʀᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n\n"
                        "⚡ <b>Powered by :</b> @Nex_bots"
                    )
                except Exception:
                    pass
        else:
            if status_msg:
                try:
                    await status_msg.edit("❌ <b>Delivery failed.</b> Please try again.")
                except Exception:
                    pass
    except Exception as e:
        log.error(f"Track manager execution error: {e}")
        if status_msg:
            try:
                await status_msg.edit(f"❌ <b>Error:</b> <code>{e}</code>")
            except Exception:
                pass
    finally:
        if transfer_sem_held:
            try:
                _TRANSFER_SEMAPHORE.release()
            except Exception:
                pass
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass
        from bot import app_4gb
        _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)


# ─────────────────────────────────────────────────────────────────────────────
# Cancel handler
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^trk_cancel$"))
async def trk_cancel_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    ctx = _TRACK_CTX.pop(user_id, None)
    USER_STATE.pop(user_id, None)
    if ctx and ctx.get("work_dir"):
        shutil.rmtree(ctx["work_dir"], ignore_errors=True)
    try:
        await query.message.delete()
    except Exception:
        pass
    from bot import app_4gb
    _cleanup_memory(client, getattr(client, "app_4gb", None) or app_4gb)
    await query.answer("Track editing cancelled! ❌")
