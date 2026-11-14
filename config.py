import os
import re
import time
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

id_pattern = re.compile(r'^.\d+$') 

class Config(object):
    # Pyrogram client configuration
    API_ID    = int(os.environ.get("API_ID", "0")) if os.environ.get("API_ID") else 0
    API_HASH  = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "") 

    # 4GB Premium client session string
    STRING_SESSION = os.environ.get("STRING_SESSION", "")
   
    # Database configuration
    DB_NAME = os.environ.get("DB_NAME", "NeX_4GB_Rename_Bot")     
    DB_URL  = os.environ.get("DB_URL", "")
 
    # Owner & Access Control
    ADMIN      = [int(admin) if id_pattern.search(admin) else admin for admin in os.environ.get('ADMIN', '').split()]
    OWNER_ONLY = os.environ.get("OWNER_ONLY", "True").lower() == "true"
    FORCE_SUB  = os.environ.get("FORCE_SUB", "Nex_bots") 

    # Channels & Media
    LOG_CHANNEL   = int(os.environ.get("LOG_CHANNEL", "0")) if os.environ.get("LOG_CHANNEL") else 0
    FILES_CHANNEL = int(os.environ.get("FILES_CHANNEL", "0")) if os.environ.get("FILES_CHANNEL") else 0
    START_PIC     = os.environ.get("START_PIC", "")

    # Bot uptime & web response configuration     
    BOT_UPTIME = time.time()
    PORT       = int(os.environ.get("PORT", "8080"))
    WEBHOOK    = os.environ.get("WEBHOOK", "True").lower() in ("true", "1", "yes")

    # Support & Payment Configuration
    SUPPORT_CHAT = os.environ.get("SUPPORT_CHAT", "NexCRSupportbot")
    UPI_ID       = os.environ.get("UPI_ID", "nexbots@upi")


class Txt(object):
    START_TXT = """👋 <b>Hᴇʟʟᴏ {0}!</b>

Wᴇʟᴄᴏᴍᴇ ᴛᴏ <b>NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ</b> ⚡
A ꜰᴀꜱᴛ, ᴄʟᴇᴀɴ ᴄʟᴏᴜᴅ ᴍᴇᴅɪᴀ ᴘʀᴏᴄᴇꜱꜱᴏʀ ꜰᴏʀ Tᴇʟᴇɢʀᴀᴍ ꜰɪʟᴇꜱ ᴜᴘ ᴛᴏ <b>4GB+</b>.

✨ <b>Kᴇʏ Hɪɢʜʟɪɢʜᴛꜱ :</b>
───────────────
▸ ⚡ <b>4GB+ Hɪɢʜ-Sᴘᴇᴇᴅ Rᴇɴᴀᴍɪɴɢ</b>
▸ 🏷️ <b>Cʟᴇᴀɴ Oᴜᴛᴘᴜᴛ & Mᴇᴛᴀᴅᴀᴛᴀ</b>
▸ 🎬 <b>Sᴀᴍᴘʟᴇ Vɪᴅᴇᴏ & Sᴄʀᴇᴇɴꜱ</b>
▸ 💧 <b>Cᴜꜱᴛᴏᴍ Vɪᴅᴇᴏ Wᴀᴛᴇʀᴍᴀʀᴋ</b>
───────────────

📤 <i>Sᴇɴᴅ ᴀɴʏ ᴠɪᴅᴇᴏ, ᴅᴏᴄᴜᴍᴇɴᴛ, ᴏʀ ᴀᴜᴅɪᴏ ꜰɪʟᴇ ᴛᴏ ʙᴇɢɪɴ!</i>"""

    ABOUT_TXT = """🤖 <b><u>Aʙᴏᴜᴛ NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ</u></b> ⚡
───────────────
▸ <b>Fʀᴀᴍᴇᴡᴏʀᴋ :</b> Pʏʀᴏɢʀᴀᴍ & FFᴍᴘᴇɢ
▸ <b>Mᴀx Fɪʟᴇ Sɪᴢᴇ :</b> Uᴘ ᴛᴏ 4GB+
▸ <b>Sᴘᴇᴇᴅ :</b> Cʟᴏᴜᴅ Hɪɢʜ-Sᴘᴇᴇᴅ
▸ <b>Eɴɢɪɴᴇ :</b> Cʟᴇᴀɴ Lᴏꜱꜱʟᴇꜱꜱ Sᴛʀᴇᴀᴍ
▸ <b>Dᴀᴛᴀʙᴀꜱᴇ :</b> MᴏɴɢᴏDB Aᴛʟᴀꜱ
───────────────
<b>🤝 Sᴘᴇᴄɪᴀʟ Cʀᴇᴅɪᴛ & Sᴘᴇᴄɪᴀʟ Tʜᴀɴᴋꜱ :</b>
▸ <b>Mʏ Dᴇᴀʀ Fʀɪᴇɴᴅ :</b> <a href="https://t.me/VenomBotz">@VenomBotz</a> ❤️✨
───────────────
📢 <b>Uᴘᴅᴀᴛᴇꜱ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""

    HELP_TXT = """📖 <b><u>NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ - Hᴇʟᴘ</u></b> ⚡
───────────────
✏️ <b><u>Hᴏᴡ Tᴏ Rᴇɴᴀᴍᴇ :</u></b>
1. Sᴇɴᴅ ᴀɴʏ ꜰɪʟᴇ ᴜᴘ ᴛᴏ 4GB.
2. Tᴀᴘ <b>Aᴜᴛᴏ Cʟᴇᴀɴ</b> ᴏʀ ᴛʏᴘᴇ ɴᴀᴍᴇ.
3. Sᴇʟᴇᴄᴛ Dᴏᴄ, Vɪᴅᴇᴏ, ᴏʀ Aᴜᴅɪᴏ.

⚙️ <b><u>Sᴇᴛᴛɪɴɢꜱ & Tᴏᴏʟꜱ :</u></b>
• <code>/settings</code> - Cᴜꜱᴛᴏᴍ Sᴇᴛᴜᴘ
• <code>/refer</code> - Rᴇꜰᴇʀ & Eᴀʀɴ Fʀᴇᴇ VIP
• <code>/profile</code> - Vɪᴇᴡ Yᴏᴜʀ Sᴛᴀᴛꜱ
• <code>/plan</code> - Uᴘɢʀᴀᴅᴇ ᴛᴏ 4GB VIP
───────────────
📢 <b>Uᴘᴅᴀᴛᴇꜱ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""

    CAPTION_TXT = """📑 <b><u>Cᴜꜱᴛᴏᴍ Cᴀᴘᴛɪᴏɴ Gᴜɪᴅᴇ</u></b> ⚡
───────────────
• <code>/set_caption &lt;text&gt;</code> - Sᴀᴠᴇ
• <code>/see_caption</code> - Vɪᴇᴡ ᴀᴄᴛɪᴠᴇ
• <code>/del_caption</code> - Rᴇꜱᴇᴛ

<b>Aᴠᴀɪʟᴀʙʟᴇ Tᴀɢꜱ :</b>
• <code>{filename}</code> - Fɪʟᴇ ɴᴀᴍᴇ
• <code>{filesize}</code> - Fɪʟᴇ ꜱɪᴢᴇ
• <code>{duration}</code> - Vɪᴅᴇᴏ ʟᴇɴɢᴛʜ

<b>Exᴀᴍᴘʟᴇ :</b>
<code>/set_caption 📕 {filename}
🔗 Size: {filesize}</code>
───────────────
⚡ @Nex_bots"""

    THUMBNAIL_TXT = """🖼️ <b><u>Tʜᴜᴍʙɴᴀɪʟ Gᴜɪᴅᴇ</u></b> ⚡
───────────────
• Sᴇɴᴅ ᴀɴʏ ᴘʜᴏᴛᴏ ᴛᴏ ꜱᴇᴛ ᴛʜᴜᴍʙɴᴀɪʟ.
• <code>/view_thumb</code> - Vɪᴇᴡ ᴛʜᴜᴍʙɴᴀɪʟ
• <code>/del_thumb</code> - Dᴇʟᴇᴛᴇ ᴛʜᴜᴍʙɴᴀɪʟ

💡 <i>16:9 ᴍᴏᴠɪᴇ ᴛʜᴜᴍʙɴᴀɪʟꜱ ᴍᴀɪɴᴛᴀɪɴ ᴛʀᴜᴇ ᴀꜱᴘᴇᴄᴛ ʀᴀᴛɪᴏ!</i>
───────────────
⚡ @Nex_bots"""

    PREFIX = """➕ <b><u>Pʀᴇꜰɪx Gᴜɪᴅᴇ</u></b> ⚡
───────────────
• <code>/set_prefix &lt;text&gt;</code> - Aᴅᴅ ᴛᴇxᴛ
• <code>/see_prefix</code> - Vɪᴇᴡ ᴘʀᴇꜰɪx
• <code>/del_prefix</code> - Rᴇᴍᴏᴠᴇ ᴘʀᴇꜰɪx

<b>Exᴀᴍᴘʟᴇ :</b>
<code>/set_prefix @Nex_bots</code>"""

    SUFFIX = """➕ <b><u>Sᴜꜰꜰɪx Gᴜɪᴅᴇ</u></b> ⚡
───────────────
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
───────────────
If you enjoy using our bots and services, feel free to support us!

📢 <b>Uᴘᴅᴀᴛᴇꜱ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""

    DON_TXT = """Hey {} 👋
❤️ <b>Tʜᴀɴᴋꜱ Fᴏʀ Sᴜᴘᴘᴏʀᴛɪɴɢ Uꜱ!</b>
───────────────
If you like our bots and services, feel free to support our development:

📢 <b>Cʜᴀɴɴᴇʟ :</b> @Nex_bots
💬 <b>Sᴜᴘᴘᴏʀᴛ :</b> @NexCRSupportbot"""
