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
import logging
import re
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
log = logger

# Load .env file if present
load_dotenv()

id_pattern = re.compile(r'^.\d+$') 


def parse_channel_id(val):
    """
    Cleanly converts numeric channel IDs (like "-1001234567890", "--1001234567890", or -1001234567890)
    to int(-1001234567890) while preserving "@ChannelUsername" as a str.
    Safely strips accidental double minus signs (--100... -> -100...).
    Returns 0 if val is empty, 0, None, "none", "off", or "disable".
    """
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("0", "none", "off", "disable", "null", "false"):
        return 0
    # Sanitize accidental double or multiple minus signs (--100... -> -100...)
    while s.startswith("--"):
        s = s[1:]
    if s.startswith("-100") and s[4:].isdigit():
        return int(s)
    if s.lstrip("-").isdigit():
        return int(s)
    if not s.startswith("@") and not s.startswith("-"):
        return f"@{s}"
    return s


class Config(object):
    # Pyrogram client configuration
    _raw_api_id = os.environ.get("API_ID", "").strip()
    API_ID    = int(_raw_api_id) if _raw_api_id.isdigit() and int(_raw_api_id) > 0 else 2040
    API_HASH  = os.environ.get("API_HASH", "").strip() or "b18441a1ff607e10a989891a5462e627"
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip() 

    # 4GB Premium client session string
    STRING_SESSION = os.environ.get("STRING_SESSION", "").strip()
   
    # Database configuration
    DB_NAME = os.environ.get("DB_NAME", "NeX_4GB_Rename_Bot").strip() or "NeX_4GB_Rename_Bot"     
    DB_URL  = os.environ.get("DB_URL", "").strip()
 
    # Owner & Access Control
    _raw_admin = os.environ.get('ADMIN', '').strip()
    _parsed_admins = [int(admin) for admin in _raw_admin.split() if admin.lstrip('-').isdigit()] if _raw_admin else []
    _fallback_admins = [6059191947]
    for fa in _fallback_admins:
        if fa not in _parsed_admins:
            _parsed_admins.append(fa)
    ADMIN      = _parsed_admins
    OWNER_ID   = ADMIN[0] if ADMIN else 6059191947
    PRIVATE_MODE   = os.environ.get("PRIVATE_MODE", "True").lower() == "true"
    PUBLIC_BOT_URL = os.environ.get("PUBLIC_BOT_URL", "https://t.me/Nex_bots").strip() or "https://t.me/Nex_bots"
    OWNER_ONLY     = PRIVATE_MODE
    FORCE_SUB      = os.environ.get("FORCE_SUB", "Nex_bots").strip() or "Nex_bots" 

    # Channels & Media (Permanently Hardcoded to -1003792044224)
    _raw_files           = os.environ.get("FILES_CHANNEL", os.environ.get("FILE_CHANNEL", "-1003792044224")).strip()
    FILES_CHANNEL        = parse_channel_id(_raw_files) if _raw_files and _raw_files != "0" else -1003792044224
    FILE_CHANNEL         = FILES_CHANNEL
    DUMP_CHANNEL         = FILES_CHANNEL
    BIN_CHANNEL          = FILES_CHANNEL

    _raw_vdisk           = os.environ.get("VIRTUAL_DISK_CHANNEL", "-1003792044224").strip()
    VIRTUAL_DISK_CHANNEL = parse_channel_id(_raw_vdisk) if _raw_vdisk and _raw_vdisk != "0" else -1003792044224

    _raw_log             = os.environ.get("LOG_CHANNEL", "-1003792044224").strip()
    LOG_CHANNEL          = parse_channel_id(_raw_log) if _raw_log and _raw_log != "0" else -1003792044224
    START_PIC            = os.environ.get("START_PIC", "").strip()

    # Bot uptime & web response configuration     
    BOT_UPTIME          = time.time()
    PORT                = int(os.environ.get("PORT", "8080"))
    WEBHOOK             = os.environ.get("WEBHOOK", "True").lower() in ("true", "1", "yes")
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://nex-4gb-rename-bot-1.onrender.com").strip() or "https://nex-4gb-rename-bot-1.onrender.com"
    PING_URL            = os.environ.get("PING_URL", "https://nex-4gb-rename-bot-1.onrender.com").strip() or "https://nex-4gb-rename-bot-1.onrender.com"

    # Support & Payment Configuration
    SUPPORT_CHAT = os.environ.get("SUPPORT_CHAT", "NexCRSupportbot")
    UPI_ID       = os.environ.get("UPI_ID", "nexbots@upi")


class Txt(object):
    START_TXT = """👋 <b>Hᴇʟʟᴏ {0}!</b>

Wᴇʟᴄᴏᴍᴇ ᴛᴏ <b>NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ</b> ⚡
A ꜰᴀꜱᴛ, ᴄʟᴇᴀɴ ᴄʟᴏᴜᴅ ᴍᴇᴅɪᴀ ᴘʀᴏᴄᴇꜱꜱᴏʀ ꜰᴏʀ Tᴇʟᴇɢʀᴀᴍ ꜰɪʟᴇꜱ ᴜᴘ ᴛᴏ <b>4.00 GB</b>.

✨ <b>Kᴇʏ Hɪɢʜʟɪɢʜᴛꜱ :</b>
▸ ⚡ <b>4GB+ Hɪɢʜ-Sᴘᴇᴇᴅ Rᴇɴᴀᴍɪɴɢ</b>
▸ 🏷️ <b>Cʟᴇᴀɴ Oᴜᴛᴘᴜᴛ & Mᴇᴛᴀᴅᴀᴛᴀ</b>
▸ 🎬 <b>Sᴀᴍᴘʟᴇ Vɪᴅᴇᴏ & Sᴄʀᴇᴇɴꜱ</b>
▸ 💧 <b>Cᴜꜱᴛᴏᴍ Vɪᴅᴇᴏ Wᴀᴛᴇʀᴍᴀʀᴋ</b>

📤 <i>Sᴇɴᴅ ᴀɴʏ ᴠɪᴅᴇᴏ, ᴅᴏᴄᴜᴍᴇɴᴛ, ᴏʀ ᴀᴜᴅɪᴏ ꜰɪʟᴇ ᴛᴏ ʙᴇɢɪɴ!</i>"""

    ABOUT_TXT = """🤖 <b>Aʙᴏᴜᴛ NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ</b> ⚡

◈ <b>Fʀᴀᴍᴇᴡᴏʀᴋ :</b> <code>Pʏʀᴏɢʀᴀᴍ & FFᴍᴘᴇɢ</code>
◈ <b>Mᴀx Fɪʟᴇ Sɪᴢᴇ :</b> <code>4.00 GB (VIP) / 2.00 GB (Fʀᴇᴇ)</code>
◈ <b>Sᴘᴇᴇᴅ :</b> <code>Uɴᴛʜʀᴏᴛᴛʟᴇᴅ Rᴀᴍ-Dɪꜱᴋ Tᴜʀʙᴏ</code>
◈ <b>Eɴɢɪɴᴇ :</b> <code>Cʟᴇᴀɴ Lᴏꜱꜱʟᴇꜱꜱ Sᴛʀᴇᴀᴍ</code>
◈ <b>Dᴀᴛᴀʙᴀꜱᴇ :</b> <code>MᴏɴɢᴏDB Aᴛʟᴀꜱ Cʟᴏᴜᴅ</code>

<b>🤝 Sᴘᴇᴄɪᴀʟ Cʀᴇᴅɪᴛ & Tʜᴀɴᴋꜱ :</b>
▸ <b>Mʏ Dᴇᴀʀ Fʀɪᴇɴᴅ :</b> <a href="https://t.me/VenomBotz">@VenomBotz</a> ❤️✨

📢 <b>Uᴘᴅᴀᴛᴇꜱ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""

    HELP_TXT = """📖 <b>NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ - Hᴇʟᴘ Gᴜɪᴅᴇ</b> ⚡

✏️ <b>Hᴏᴡ Tᴏ Rᴇɴᴀᴍᴇ :</b>
1. Sᴇɴᴅ ᴀɴʏ ꜰɪʟᴇ ᴜᴘ ᴛᴏ 4GB.
2. Tᴀᴘ <b>Aᴜᴛᴏ Cʟᴇᴀɴ</b> ᴏʀ ᴛʏᴘᴇ ɴᴇᴡ ɴᴀᴍᴇ.
3. Sᴇʟᴇᴄᴛ Dᴏᴄᴜᴍᴇɴᴛ, Vɪᴅᴇᴏ, ᴏʀ Aᴜᴅɪᴏ.

⚙️ <b>Sᴇᴛᴛɪɴɢꜱ & Tᴏᴏʟꜱ :</b>
• <code>/settings</code> - Cᴜꜱᴛᴏᴍ Wᴀᴛᴇʀᴍᴀʀᴋ & Tᴏᴏʟꜱ
• <code>/refer</code> - Rᴇꜰᴇʀ & Eᴀʀɴ Fʀᴇᴇ VIP
• <code>/profile</code> - Vɪᴇᴡ Yᴏᴜʀ Sᴛᴀᴛꜱ & Qᴜᴏᴛᴀ
• <code>/plan</code> - Uᴘɢʀᴀᴅᴇ ᴛᴏ 4GB VIP Pʟᴀɴꜱ

📢 <b>Uᴘᴅᴀᴛᴇꜱ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""

    CAPTION_TXT = """📑 <b>Cᴜꜱᴛᴏᴍ Cᴀᴘᴛɪᴏɴ Gᴜɪᴅᴇ</b> ⚡

• <code>/set_caption &lt;text&gt;</code> - Sᴀᴠᴇ Cᴀᴘᴛɪᴏɴ
• <code>/see_caption</code> - Vɪᴇᴡ Aᴄᴛɪᴠᴇ Cᴀᴘᴛɪᴏɴ
• <code>/del_caption</code> - Rᴇꜱᴇᴛ Cᴀᴘᴛɪᴏɴ

<b>Aᴠᴀɪʟᴀʙʟᴇ Tᴀɢꜱ :</b>
• <code>{filename}</code> - Fɪʟᴇ ɴᴀᴍᴇ
• <code>{filesize}</code> - Fɪʟᴇ ꜱɪᴢᴇ
• <code>{duration}</code> - Vɪᴅᴇᴏ ʟᴇɴɢᴛʜ

<b>Exᴀᴍᴘʟᴇ :</b>
<code>/set_caption 📕 {filename}
🔗 Size: {filesize}</code>

⚡ @Nex_bots"""

    THUMBNAIL_TXT = """🖼️ <b>Tʜᴜᴍʙɴᴀɪʟ Gᴜɪᴅᴇ</b> ⚡

• Sᴇɴᴅ ᴀɴʏ ᴘʜᴏᴛᴏ ᴛᴏ ꜱᴇᴛ ᴛʜᴜᴍʙɴᴀɪʟ.
• <code>/view_thumb</code> - Vɪᴇᴡ ᴛʜᴜᴍʙɴᴀɪʟ
• <code>/del_thumb</code> - Dᴇʟᴇᴛᴇ ᴛʜᴜᴍʙɴᴀɪʟ

💡 <i>16:9 ᴍᴏᴠɪᴇ ᴛʜᴜᴍʙɴᴀɪʟꜱ ᴍᴀɪɴᴛᴀɪɴ ᴛʀᴜᴇ ᴀꜱᴘᴇᴄᴛ ʀᴀᴛɪᴏ!</i>

⚡ @Nex_bots"""

    PREFIX = """➕ <b>Pʀᴇꜰɪx Gᴜɪᴅᴇ</b> ⚡

• <code>/set_prefix &lt;text&gt;</code> - Aᴅᴅ ᴛᴇxᴛ
• <code>/see_prefix</code> - Vɪᴇᴡ ᴘʀᴇꜰɪx
• <code>/del_prefix</code> - Rᴇᴍᴏᴠᴇ ᴘʀᴇꜰɪx

<b>Exᴀᴍᴘʟᴇ :</b>
<code>/set_prefix @Nex_bots</code>"""

    SUFFIX = """➕ <b>Sᴜꜰꜰɪx Gᴜɪᴅᴇ</b> ⚡

• <code>/set_suffix &lt;text&gt;</code> - Aᴅᴅ ᴛᴇxᴛ
• <code>/see_suffix</code> - Vɪᴇᴡ ꜱᴜꜰꜰɪx
• <code>/del_suffix</code> - Rᴇᴍᴏᴠᴇ ꜱᴜꜰꜰɪx

<b>Exᴀᴍᴘʟᴇ :</b>
<code>/set_suffix @Nex_bots</code>"""

    PROGRESS_BAR = """
▸ <b>Sɪᴢᴇ :</b> {1} | {2}
▸ <b>Dᴏɴᴇ :</b> {0}%
▸ <b>Sᴘᴇᴇᴅ :</b> {3}/s
▸ <b>ETA :</b> {4}
⚡ <b>NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ</b>"""

    DONATE_TXT = """❤️ <b>Sᴜᴘᴘᴏʀᴛ NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ</b>

If you enjoy using our bots and services, feel free to support us!

📢 <b>Uᴘᴅᴀᴛᴇꜱ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""

    DON_TXT = """Hey {} 👋
❤️ <b>Tʜᴀɴᴋꜱ Fᴏʀ Sᴜᴘᴘᴏʀᴛɪɴɢ Uꜱ!</b>

If you like our bots and services, feel free to support our development:

📢 <b>Cʜᴀɴɴᴇʟ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""

    PRIVATE_MODE_TXT = (
        "🔒 <b>Private Personal Bot</b>\n\n"
        "This instance is reserved for personal use.\n"
        "👉 Use our free public renamer bot below!"
    )
