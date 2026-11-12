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
    START_TXT = """Hello {} 👋 

🚀 <b><u>NeX 4GB Rename Bot</u></b> ⚡
<i>Commercial-grade, ultra-fast 4GB file renamer!</i>

✨ <b>Core Capabilities:</b>
◈ ⚡ <b>4GB+ Cloud Transfers :</b> Full 4GB files via Telegram Premium
◈ 🏷️ <b>100% Clean Output :</b> No prefixes, custom metadata, prefix/suffix & cleaner
◈ 💧 <b>Video Watermark :</b> Burn your channel tag directly into frames
◈ 🎬 <b>Sample Video & Shots :</b> Custom timeline clips & photo albums
◈ 📦 <b>Personal Dump Channel :</b> Auto-forward renamed files securely
◈ 🚀 <b>High-Speed Engine :</b> Multi-worker 24/7 cloud bandwidth

<i>Send any document, video, or audio to start renaming!</i>

📢 <b>Updates:</b> @Nex_bots | 💬 <b>Support:</b> @NexCRSupportbot"""

    ABOUT_TXT = """🤖 <b><u>About NeX 4GB Rename Bot</u></b> ⚡

• <b>Framework:</b> Pyrotgfork & FFmpeg
• <b>Speed:</b> Multi-Worker High Speed
• <b>Max File Size:</b> Up to 4GB (Telegram Premium)
• <b>Database:</b> MongoDB Atlas
• <b>Metadata Engine:</b> Lossless Stream Tagging

📢 <b>Channel:</b> @Nex_bots
💬 <b>Support:</b> @NexCRSupportbot
👨‍💻 <b>Developer:</b> @Nex_bots"""

    HELP_TXT = """📖 <b><u>NeX 4GB Rename Bot - Help</u></b> ⚡

⚙️ <b><u>Settings & Controls:</u></b>
• <code>/settings</code> - Interactive visual dashboard
• <code>/commands</code> - Full list of bot commands

✏️ <b><u>How To Rename:</u></b>
1. Send any document, video, or audio up to 4GB.
2. Tap <b>⚡ Auto Clean</b> or <b>📝 Type Name</b>.
3. Choose: [<b>📁 Doc</b> | <b>🎥 Video</b> | <b>🎵 Audio</b>].

🏷️ <b><u>Key Commands:</u></b>
• <code>/metadata</code> | <code>/set_metadata &lt;tag&gt;</code>
• <code>/set_remove &lt;words&gt;</code> | <code>/set_replace &lt;old:new&gt;</code>
• <code>/set_sample &lt;sec&gt;</code> | <code>/set_screenshots &lt;1-10&gt;</code>
• <code>/set_caption &lt;text&gt;</code> | <code>/view_thumb</code> | <code>/del_thumb</code>
• <code>/set_prefix &lt;text&gt;</code> | <code>/set_suffix &lt;text&gt;</code>

📢 <b>Updates:</b> @Nex_bots"""

    CAPTION_TXT = """📑 <b><u>Custom Caption Guide</u></b> ⚡

• <code>/set_caption &lt;text&gt;</code> - Save your custom caption
• <code>/see_caption</code> - View your current caption
• <code>/del_caption</code> - Reset to default filename

<b>Available Tags:</b>
• <code>{filename}</code> - Renamed file name
• <code>{filesize}</code> - Human-readable size
• <code>{duration}</code> - Video or audio duration

<b>Example:</b>
<code>/set_caption 📕 <b>Name:</b> {filename}
🔗 <b>Size:</b> {filesize}
⏰ <b>Duration:</b> {duration}

⚡ @Nex_bots</code>"""

    THUMBNAIL_TXT = """🖼️ <b><u>Custom Thumbnail Guide</u></b> ⚡

• Send any photo to set it as your thumbnail.
• <code>/view_thumb</code> - View your current thumbnail
• <code>/del_thumb</code> - Delete your thumbnail

<i>💡 16:9 widescreen movie thumbnails keep their proper aspect ratio without stretching!</i>

⚡ @Nex_bots"""

    PREFIX = """➕ <b><u>Prefix Guide</u></b> ⚡

• <code>/set_prefix &lt;text&gt;</code> - Add text before filename
• <code>/see_prefix</code> - View your active prefix
• <code>/del_prefix</code> - Delete your active prefix

<b>Example:</b>
<code>/set_prefix @Nex_bots</code>"""

    SUFFIX = """➕ <b><u>Suffix Guide</u></b> ⚡

• <code>/set_suffix &lt;text&gt;</code> - Add text before file extension
• <code>/see_suffix</code> - View your active suffix
• <code>/del_suffix</code> - Delete your active suffix

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
