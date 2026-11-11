import math
import time
from datetime import datetime
from pytz import timezone
from config import Config, Txt 
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
try:
    from pyrogram import StopTransmission
except ImportError:
    from pyrogram.errors import StopTransmission

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]

# Global set to track active operations marked for cancellation
CANCEL_REQUESTS = set()


def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return "0B"
    index = 0
    size_in_bytes = float(size_in_bytes)
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1
    return f"{round(size_in_bytes, 2)}{SIZE_UNITS[index]}"


def get_readable_time(seconds: int) -> str:
    result = ""
    (days, remainder) = divmod(int(seconds), 86400)
    if days != 0:
        result += f"{days}d "
    (hours, remainder) = divmod(remainder, 3600)
    if hours != 0:
        result += f"{hours}h "
    (minutes, seconds) = divmod(remainder, 60)
    if minutes != 0:
        result += f"{minutes}m "
    result += f"{seconds}s"
    return result.strip()


async def progress_for_pyrogram(current, total, ud_type, message, start, client=None):
    # Check if this task has been requested to cancel
    msg_id = getattr(message, 'id', None)
    chat_id = getattr(message.chat, 'id', None) if getattr(message, 'chat', None) else None

    if msg_id in CANCEL_REQUESTS or (chat_id and f"{chat_id}_{msg_id}" in CANCEL_REQUESTS):
        raise StopTransmission("Operation Cancelled by User")

    now = time.time()
    diff = max(now - start, 0.001)
    # Update UI every 5 seconds or when download/upload is complete
    if round(diff % 5.0) == 0 or current == total:
        percentage = (current * 100 / total) if (total and total > 0) else 0
        speed = (current / diff) if diff > 0 else 0
        elapsed_time = round(diff) * 1000
        time_to_completion = (round((total - current) / speed) * 1000) if speed > 0 else 0
        estimated_total_time = elapsed_time + time_to_completion

        elapsed_str = TimeFormatter(milliseconds=elapsed_time)
        eta_str = TimeFormatter(milliseconds=time_to_completion) if speed > 0 else "0s"

        completed_blocks = math.floor(percentage / 5)
        progress = '▣' * completed_blocks + '▢' * (20 - completed_blocks)

        status_text = (
            f"<b>{ud_type}</b>\n\n"
            f"{progress} <b>{round(percentage, 2)}%</b>\n\n"
            f"🔗 <b>Size :</b> {humanbytes(current)} / {humanbytes(total)}\n"
            f"🚀 <b>Speed :</b> {humanbytes(speed)}/s\n"
            f"⏰ <b>ETA :</b> {eta_str}\n\n"
            f"⚡ <b>NeX 4GB Rename Bot</b> | @Nex_bots"
        )
        try:
            cancel_data = f"cancel_{msg_id}" if msg_id else "cancel_action"
            await message.edit(
                text=status_text,               
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Cancel Process", callback_data=cancel_data)]])                                               
            )
        except Exception:
            pass


def humanbytes(size):    
    if not size:
        return "0 B"
    power = 2**10
    n = 0
    dic_power_n = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < 4:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + dic_power_n[n] + 'B'


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "") + \
        ((str(milliseconds) + "ms, ") if milliseconds else "")
    return tmp[:-2] if tmp else "0s"


def convert(seconds):
    seconds = int(seconds) % (24 * 3600)
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60      
    return "%d:%02d:%02d" % (hour, minutes, seconds)


async def send_log(b, u):
    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
        curr = datetime.now(timezone("Asia/Kolkata"))
        date = curr.strftime('%d %B, %Y')
        time_str = curr.strftime('%I:%M:%S %p')
        try:
            await b.send_message(
                Config.LOG_CHANNEL,
                f"#New_User\n<b><u>New User Started The Bot</u></b>\n\n"
                f"👤 <b>User Mention :</b> {u.mention}\n"
                f"🆔 <b>User ID :</b> <code>{u.id}</code>\n"
                f"📝 <b>First Name :</b> {u.first_name}\n"
                f"📝 <b>Last Name :</b> {u.last_name or ''}\n"
                f"🌐 <b>Username :</b> @{u.username or 'No Username'}\n"
                f"🔗 <b>User Link :</b> <a href='tg://openmessage?user_id={u.id}'>Click Here</a>\n\n"
                f"📅 <b>Date :</b> <code>{date}</code>\n"
                f"⏰ <b>Time :</b> <code>{time_str}</code>\n\n"
                f"⚡ <b>NeX 4GB Rename Bot</b> : @Nex_bots"
            )
        except Exception:
            pass


async def edit_message_content(message, text, reply_markup=None, parse_mode=None):
    """
    Safely edits a message's content whether it is a regular text message
    or a media message (e.g. photo from START_PIC), avoiding caption/text mismatch errors.
    """
    is_media = bool(getattr(message, "photo", None) or getattr(message, "media", None))
    if is_media:
        kwargs = {"caption": text, "reply_markup": reply_markup}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        try:
            return await message.edit_caption(**kwargs)
        except Exception:
            kwargs_fallback = {"text": text, "reply_markup": reply_markup}
            if parse_mode:
                kwargs_fallback["parse_mode"] = parse_mode
            return await message.edit_text(**kwargs_fallback)
    else:
        kwargs = {"text": text, "reply_markup": reply_markup}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        try:
            return await message.edit_text(**kwargs)
        except Exception:
            kwargs_fallback = {"caption": text, "reply_markup": reply_markup}
            if parse_mode:
                kwargs_fallback["parse_mode"] = parse_mode
            return await message.edit_caption(**kwargs_fallback)

