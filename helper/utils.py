import os
import re
import math
import time
import asyncio
from datetime import datetime
from pytz import timezone
from config import Config, Txt 
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
try:
    from pyrogram import StopTransmission
except ImportError:
    from pyrogram.errors import StopTransmission

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]

def safe_reply_params(message_id: int):
    """
    Returns kwargs dictionary with reply_parameters=ReplyParameters(message_id=message_id)
    if supported, otherwise falls back to reply_to_message_id=message_id.
    """
    if not message_id:
        return {}
    try:
        from pyrogram.types import ReplyParameters
        return {"reply_parameters": ReplyParameters(message_id=int(message_id))}
    except (TypeError, ImportError, Exception):
        return {"reply_to_message_id": int(message_id)}


def sanitize_secrets(text: str) -> str:
    """
    Sanitizes sensitive information (Bot tokens, MongoDB URIs, API hashes,
    Pyrogram session strings) from text and error tracebacks.
    """
    if not text:
        return ""
    clean = str(text)
    for secret in [
        getattr(Config, "BOT_TOKEN", None),
        getattr(Config, "DB_URL", None),
        getattr(Config, "STRING_SESSION", None),
        getattr(Config, "API_HASH", None)
    ]:
        if secret and len(str(secret)) > 4:
            clean = clean.replace(str(secret), "***REDACTED***")
    # Redact MongoDB URIs
    clean = re.sub(r'mongodb(?:\+srv)?://[^\s\'\"<>]+', 'mongodb+srv://***REDACTED***', clean)
    # Redact Bot Tokens
    clean = re.sub(r'\b\d{8,12}:[A-Za-z0-9_-]{30,45}\b', '***REDACTED_TOKEN***', clean)
    # Redact Long Pyrogram Session strings
    clean = re.sub(r'\b[A-Za-z0-9+/=]{100,}\b', '***REDACTED_SESSION***', clean)
    return clean


def calc_plan_prices(months: int, base_inr: int = 139):
    """
    Calculates dynamic plan pricing with volume discounts:
    - 1 Month: 0% discount
    - 2-3 Months: 5% discount
    - 4-6 Months: 10% discount
    - 7-12 Months: 15% discount
    - >12 Months: 20% discount
    Stars: 100 ⭐ = ₹199
    USD: 1 USD = ₹84
    """
    months = max(1, min(24, int(months)))
    if months == 1:
        discount = 0.0
    elif months <= 3:
        discount = 0.05
    elif months <= 6:
        discount = 0.10
    elif months <= 12:
        discount = 0.15
    else:
        discount = 0.20
    
    inr = max(1, round(base_inr * months * (1.0 - discount)))
    stars = max(1, round((inr * 100) / 199))
    if inr == 199 and months == 1:
        usd = 2.39
    elif inr == 99 and months == 1:
        usd = 1.18
    elif inr == 139 and months == 1:
        usd = 1.65
    else:
        usd = round(inr / 84.0, 2)
    return inr, stars, usd

# Global set to track active operations marked for cancellation
CANCEL_REQUESTS = set()
# Global dicts to track progress edit timestamps and percentages for strictly 5.0s (min 2%) throttling
PROGRESS_TIMESTAMPS = {}
PROGRESS_PERCENTAGES = {}


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


TIER_SPEED_LIMITS = {
    0: 0,   # Full High-Speed (40-80+ MB/s)
    1: 0,
    2: 0,
    3: 0
}


async def progress_for_pyrogram(current, total, ud_type, message, start, client=None, tier=0):
    # Check if this task has been requested to cancel
    msg_id = getattr(message, 'id', None)
    chat_id = getattr(message.chat, 'id', None) if getattr(message, 'chat', None) else None
    key = f"{chat_id}_{msg_id}" if (chat_id and msg_id) else (msg_id or id(message))

    if msg_id in CANCEL_REQUESTS or (chat_id and (f"{chat_id}_{msg_id}" in CANCEL_REQUESTS or chat_id in CANCEL_REQUESTS)):
        PROGRESS_TIMESTAMPS.pop(key, None)
        PROGRESS_PERCENTAGES.pop(key, None)
        raise StopTransmission("Operation Cancelled by User")

    now = time.time()
    last_update = PROGRESS_TIMESTAMPS.get(key, 0)
    last_pct = PROGRESS_PERCENTAGES.get(key, -1.0)
    percentage = (current * 100 / total) if (total and total > 0) else 0
    pct_diff = abs(percentage - last_pct)

    # Strictly throttle UI progress edits to once every 5.0 seconds (or min 3% change) or upon completion
    if ((now - last_update >= 5.0 and pct_diff >= 3.0) or (now - last_update >= 10.0) or (current == total)):
        PROGRESS_TIMESTAMPS[key] = now
        PROGRESS_PERCENTAGES[key] = percentage
        diff = max(now - start, 0.001)
        speed = (current / diff) if diff > 0 else 0
        elapsed_time = round(diff) * 1000
        time_to_completion = (round((total - current) / speed) * 1000) if speed > 0 else 0

        elapsed_str = TimeFormatter(milliseconds=elapsed_time)
        eta_str = TimeFormatter(milliseconds=time_to_completion) if speed > 0 else "0s"

        completed_blocks = math.floor(percentage / 5)
        progress = '▣' * completed_blocks + '▢' * (20 - completed_blocks)
        speed_txt = f"{humanbytes(speed)}/s"

        status_text = (
            f"<b>{ud_type}</b>\n\n"
            f"{progress} <b>{round(percentage, 2)}%</b>\n\n"
            f"🔗 <b>Size :</b> {humanbytes(current)} / {humanbytes(total)}\n"
            f"🚀 <b>Speed :</b> {speed_txt}\n"
            f"⏰ <b>ETA :</b> {eta_str}\n\n"
            f"⚡ <b>NeX 4GB Rename Bot</b> | @Nex_bots"
        )
        try:
            cancel_data = f"cancel_{msg_id}" if msg_id else "cancel_action"
            await message.edit(
                text=status_text,               
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Cancel", callback_data=cancel_data)]])                                               
            )
        except FloodWait as f_err:
            await asyncio.sleep(f_err.value + 1)
        except Exception:
            pass

        if current == total:
            PROGRESS_TIMESTAMPS.pop(key, None)
            PROGRESS_PERCENTAGES.pop(key, None)


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
    or a media message (e.g. photo from START_PIC), avoiding caption/text mismatch errors,
    FloodWait, and MessageNotModified.
    """
    if not message:
        return None
    is_media = bool(getattr(message, "photo", None) or getattr(message, "media", None))
    for attempt in range(2):
        try:
            if is_media:
                kwargs = {"caption": text, "reply_markup": reply_markup}
                if parse_mode:
                    kwargs["parse_mode"] = parse_mode
                return await message.edit_caption(**kwargs)
            else:
                kwargs = {"text": text, "reply_markup": reply_markup}
                if parse_mode:
                    kwargs["parse_mode"] = parse_mode
                return await message.edit_text(**kwargs)
        except MessageNotModified:
            return message
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception:
            # Swap media / text on mismatch
            try:
                if is_media:
                    kwargs = {"text": text, "reply_markup": reply_markup}
                    if parse_mode:
                        kwargs["parse_mode"] = parse_mode
                    return await message.edit_text(**kwargs)
                else:
                    kwargs = {"caption": text, "reply_markup": reply_markup}
                    if parse_mode:
                        kwargs["parse_mode"] = parse_mode
                    return await message.edit_caption(**kwargs)
            except MessageNotModified:
                return message
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                return None
    return None


# ==================== AUTO-EPISODE BATCH RENAMER ====================
def parse_media_tags(filename: str) -> dict:
    """
    Parses TV series / anime / movie filenames to extract Title, Season, Episode,
    Quality, Codec, Audio tags, and Extension.
    """
    base, ext = os.path.splitext(filename)
    clean_base = base.replace(".", " ").replace("_", " ").strip()

    season = "01"
    episode = "01"
    quality = ""
    codec = ""
    audio = ""

    # Season & Episode extraction
    se_match = re.search(r'(?i)[sS](\d{1,2})\s*[eE](\d{1,3})', clean_base)
    if se_match:
        season = f"{int(se_match.group(1)):02d}"
        episode = f"{int(se_match.group(2)):02d}"
    else:
        x_match = re.search(r'(?i)\b(\d{1,2})[xX](\d{1,3})\b', clean_base)
        if x_match:
            season = f"{int(x_match.group(1)):02d}"
            episode = f"{int(x_match.group(2)):02d}"
        else:
            ep_match = re.search(r'(?i)(?:episode|ep|e)\s*(\d{1,3})\b', clean_base)
            if ep_match:
                episode = f"{int(ep_match.group(1)):02d}"
            s_match = re.search(r'(?i)(?:season|s)\s*(\d{1,2})\b', clean_base)
            if s_match:
                season = f"{int(s_match.group(1)):02d}"

    # Quality extraction
    q_match = re.search(r'(?i)\b(2160p|1080p|720p|480p|4k|uhd|fhd|hd)\b', clean_base)
    if q_match:
        quality = q_match.group(1).upper()

    # Codec extraction
    c_match = re.search(r'(?i)\b(hevc|x265|x264|h265|h264|10bit|8bit)\b', clean_base)
    if c_match:
        codec = c_match.group(1).upper()

    # Audio extraction
    a_match = re.search(r'(?i)\b(dual\s*audio|multi\s*audio|hindi|eng|japanese|tamil|telugu)\b', clean_base)
    if a_match:
        audio = a_match.group(1).title()

    # Extract clean title by taking text before SxxExx or Quality
    title_part = clean_base
    cut_match = re.search(r'(?i)([sS]\d{1,2}|E\d{1,3}|\d{1,2}x\d{1,3}|2160p|1080p|720p|480p)', clean_base)
    if cut_match:
        title_part = clean_base[:cut_match.start()].strip()
    title = re.sub(r'[\[\(].*?[\]\)]', '', title_part).strip(' -_')
    if not title:
        title = "Episode"

    return {
        "title": title,
        "season": season,
        "episode": episode,
        "quality": quality or "720p",
        "codec": codec or "x264",
        "audio": audio or "Original",
        "ext": ext or ".mkv"
    }


def apply_episode_template(filename: str, template: str) -> str:
    """
    Applies custom user template to an extracted media filename.
    Supported placeholders: {Title}, {Season}, {Episode}, {Quality}, {Codec}, {Audio}
    """
    tags = parse_media_tags(filename)
    res = template
    res = res.replace("{Title}", tags["title"]).replace("{title}", tags["title"])
    res = res.replace("{Season}", tags["season"]).replace("{season}", tags["season"])
    res = res.replace("{Episode}", tags["episode"]).replace("{episode}", tags["episode"])
    res = res.replace("{Quality}", tags["quality"]).replace("{quality}", tags["quality"])
    res = res.replace("{Codec}", tags["codec"]).replace("{codec}", tags["codec"])
    res = res.replace("{Audio}", tags["audio"]).replace("{audio}", tags["audio"])
    
    # Clean whitespace and append original extension if missing
    res = re.sub(r'\s+', ' ', res).strip()
    if not res.lower().endswith(tags["ext"].lower()):
        res = f"{res}{tags['ext']}"
    return res


