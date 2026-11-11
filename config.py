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


class Txt(object):
    START_TXT = """Hello {} 👋 

🚀 <b>Welcome to NeX 4GB Rename Bot!</b>

⚡ <b>An ultra-fast, high-performance Telegram 4GB File & Video Renamer Bot.</b>

<b>🌟 Key Capabilities:</b>
• <b>4GB Telegram Premium Uploads:</b> Rename and upload files up to 4GB.
• <b>Custom Metadata Injection:</b> Add custom Title, Author, and Artist tags losslessly via FFmpeg.
• <b>Auto Clean & Rename:</b> One-click automatic word stripping, tag replacement, prefix/suffix.
• <b>Sample Video & Screenshots:</b> Auto-extract 30s clips & screenshot albums.
• <b>Interactive Dashboard:</b> Manage all your preferences in <code>/settings</code>.
• <b>Custom Thumbnail & Caption:</b> Full support for custom formatting tags.

📢 <b>Updates & Support:</b> @Nex_bots"""

    ABOUT_TXT = """🤖 <b>NeX 4GB Rename Bot</b> ⚡

• <b>Framework:</b> Pyrogram & FFmpeg
• <b>Language:</b> Python 3.10+
• <b>Speed:</b> High-Speed Multi-Worker
• <b>Max File Size:</b> Up to 4GB (Telegram Premium)
• <b>Database:</b> MongoDB Atlas

📢 <b>Channel:</b> @Nex_bots
💬 <b>Support:</b> @Nex_bots
👨‍💻 <b>Developer:</b> @Nex_bots

⚡ <i>Fastest 4GB File & Video Renamer Bot powered by @Nex_bots!</i>"""

    HELP_TXT = """🌌 <b><u>NeX 4GB Rename Bot (@Nex_bots) - Command Guide</u></b>

⚙️ <b><u>Settings & Dashboard</u></b>
• <code>/settings</code> - Interactive visual control panel for all features!

🖼️ <b><u>Thumbnail Commands</u></b>
• Send any photo to set it as your custom thumbnail.
• <code>/view_thumb</code> - View your current custom thumbnail.
• <code>/del_thumb</code> - Delete your custom thumbnail.

📑 <b><u>Custom Caption Commands</u></b>
• <code>/set_caption &lt;text&gt;</code> - Set a custom formatted caption.
  <i>Available Tags:</i> <code>{filename}</code>, <code>{filesize}</code>, <code>{duration}</code>
• <code>/see_caption</code> - View your current custom caption.
• <code>/del_caption</code> - Delete your custom caption.

🏷️ <b><u>Prefix & Suffix Commands</u></b>
• <code>/set_prefix &lt;prefix&gt;</code> - Add text before filename.
• <code>/see_prefix</code> - View your current prefix.
• <code>/del_prefix</code> - Delete your prefix.
• <code>/set_suffix &lt;suffix&gt;</code> - Add text after filename.
• <code>/see_suffix</code> - View your current suffix.
• <code>/del_suffix</code> - Delete your suffix.

⚡ <b><u>Metadata Engine (FFmpeg)</u></b>
• <code>/metadata</code> - View metadata status and current tag.
• <code>/set_metadata &lt;tag&gt;</code> - Set custom metadata tag.
• <code>/toggle_metadata</code> - One-click toggle metadata ON/OFF.

🧹 <b><u>Word Cleaner & Replacer</u></b>
• <code>/set_remove &lt;word1, word2&gt;</code> - Clean unwanted words/tags from filename.
• <code>/set_replace &lt;old:new, old2:new2&gt;</code> - Replace words automatically.
• <code>/see_cleaner</code> - View all your active cleaner rules.
• <code>/del_cleaner</code> - Clear all cleaner & replacer rules.

🎬 <b><u>Sample Video Generator</u></b>
• <code>/set_sample &lt;seconds&gt;</code> - Set sample duration (e.g. <code>30</code>, or <code>0</code> to disable).

📸 <b><u>Screenshot Generator</u></b>
• <code>/set_screenshots &lt;count&gt;</code> - Set screenshot count (1-10, or <code>0</code> to disable).

📦 <b><u>Custom Dump Channel</u></b>
• <code>/set_dump <channel_id></code> - Set private dump channel (e.g. <code>-1001234567890</code> or <code>off</code>).

🧹 <b><u>Maintenance & Cache (Admin Only)</u></b>
• <code>/clear_cache</code> - Clean up temp downloads directory and display free RAM & disk.
• <code>/status</code> - View bot uptime, ping, and user stats.
• <code>/restart</code> - Restart the bot process.

✏️ <b><u>How To Rename A File</u></b>
1. Send any document, video, or audio file up to 4GB.
2. Click <b>⚡ Auto Clean & Rename</b> for 1-click rename using your rules, or <b>📝 Type New Name</b> for manual name.
3. Select format [<b>📁 Document</b> | <b>🎥 Video</b> | <b>🎵 Audio</b>] or configure your default format in <code>/settings</code>!

📢 <b>Updates & Support:</b> <a href='https://t.me/Nex_bots'>@Nex_bots</a>"""

    PROGRESS_BAR = """
<b>🔗 Size :</b> {1} | {2}
<b>⏳ Done :</b> {0}%
<b>🚀 Speed :</b> {3}/s
<b>⏰ ETA :</b> {4}
⚡ <b>NeX 4GB Rename Bot</b>"""

    DONATE_TXT = """❤️ <b>Support NeX 4GB Rename Bot</b>

If you enjoy using our bots and services, feel free to support us!

📢 <b>Updates & Support:</b> @Nex_bots
💬 <b>Contact:</b> @Nex_bots"""

    DON_TXT = """Hey {} 👋
❤️ <b>Thanks For Showing Interest In Supporting Us!</b>

If you like our bots and services, feel free to support our development:

📢 <b>Channel:</b> @Nex_bots
💬 <b>Support:</b> @Nex_bots"""
