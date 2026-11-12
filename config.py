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
    START_TXT = """👋 <b>Hello {0}!</b>

Welcome to <b>NeX 4GB Rename Bot</b> ⚡
A fast, clean cloud media processor for Telegram files up to <b>4GB+</b>.

╭━━━〔 ✨ <b>Key Highlights</b> 〕━━━╮
┃ ⚡ <b>4GB+ High-Speed Renaming</b>
┃ 🏷️ <b>Clean Output & Metadata</b>
┃ 🎬 <b>Sample Video & Screen</b>
┃ 💧 <b>Custom Video Watermark</b>
╰━━━━━━━━━━━━━━━━━━━━━━━━━━━╯

📤 <i>Send any video, document, or audio file to begin!</i>"""

    ABOUT_TXT = """🤖 <b><u>About NeX 4GB Rename Bot</u></b> ⚡

• <b>Framework :</b> Pyrogram & FFmpeg
• <b>Max File Size :</b> Up to 4GB+
• <b>Speed :</b> Cloud High-Speed
• <b>Engine :</b> Clean Lossless Stream
• <b>Database :</b> MongoDB Atlas

📢 <b>Updates :</b> @Nex_bots
💬 <b>Support :</b> @NexCRSupportbot"""

    HELP_TXT = """📖 <b><u>NeX 4GB Rename Bot - Help</u></b> ⚡

✏️ <b><u>How To Rename:</u></b>
1. Send any file up to 4GB.
2. Tap <b>Auto Clean</b> or type name.
3. Select Doc, Video, or Audio.

⚙️ <b><u>Settings & Tools:</u></b>
• <code>/settings</code> - Custom Setup
• <code>/refer</code> - Refer & Earn Free VIP
• <code>/profile</code> - View Your Stats
• <code>/plan</code> - Upgrade to 4GB VIP

📢 <b>Updates :</b> @Nex_bots
💬 <b>Support :</b> @NexCRSupportbot"""

    CAPTION_TXT = """📑 <b><u>Custom Caption Guide</u></b> ⚡

• <code>/set_caption &lt;text&gt;</code> - Save
• <code>/see_caption</code> - View active
• <code>/del_caption</code> - Reset

<b>Available Tags:</b>
• <code>{filename}</code> - File name
• <code>{filesize}</code> - File size
• <code>{duration}</code> - Video length

<b>Example:</b>
<code>/set_caption 📕 {filename}
🔗 Size: {filesize}</code>

⚡ @Nex_bots"""

    THUMBNAIL_TXT = """🖼️ <b><u>Thumbnail Guide</u></b> ⚡

• Send any photo to set thumbnail.
• <code>/view_thumb</code> - View thumbnail
• <code>/del_thumb</code> - Delete thumbnail

💡 <i>16:9 movie thumbnails maintain true aspect ratio!</i>

⚡ @Nex_bots"""

    PREFIX = """➕ <b><u>Prefix Guide</u></b> ⚡

• <code>/set_prefix &lt;text&gt;</code> - Add text
• <code>/see_prefix</code> - View prefix
• <code>/del_prefix</code> - Remove prefix

<b>Example:</b>
<code>/set_prefix @Nex_bots</code>"""

    SUFFIX = """➕ <b><u>Suffix Guide</u></b> ⚡

• <code>/set_suffix &lt;text&gt;</code> - Add text
• <code>/see_suffix</code> - View suffix
• <code>/del_suffix</code> - Remove suffix

<b>Example:</b>
<code>/set_suffix @Nex_bots</code>"""

    PROGRESS_BAR = """
<b>🔗 Size :</b> {1} | {2}
<b>⏳ Done :</b> {0}%
<b>🚀 Speed :</b> {3}/s
<b>⏰ ETA :</b> {4}
⚡ <b>NeX 4GB Rename Bot</b>"""

    DONATE_TXT = """❤️ <b>Support NeX 4GB Rename Bot</b>

If you enjoy using our bots and services, feel free to support us!

📢 <b>Updates:</b> @Nex_bots
💬 <b>Support:</b> @NexCRSupportbot"""

    DON_TXT = """Hey {} 👋
❤️ <b>Thanks For Supporting Us!</b>

If you like our bots and services, feel free to support our development:

📢 <b>Channel:</b> @Nex_bots
💬 <b>Support:</b> @NexCRSupportbot"""
