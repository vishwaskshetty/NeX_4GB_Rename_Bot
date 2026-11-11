<p align="center">
  <img src="https://telegra.ph/file/0c9a5a3a5f98eb2b21cf5.jpg" alt="NeX 4GB Rename Bot Logo" width="180">
</p>

<h1 align="center">⚡ NeX 4GB Rename Bot ⚡</h1>

<p align="center">
  <b>The Most Advanced, Resilient & High-Speed Telegram 4GB File & Video Renamer Bot</b><br>
  Powered by <b>Pyrogram</b>, <b>FFmpeg</b>, and <b>MongoDB</b>.
</p>

<p align="center">
  <a href="https://t.me/Nex_bots"><img src="https://img.shields.io/badge/Channel-@Nex_bots-blue?style=for-the-badge&logo=telegram" alt="Channel"></a>
  <a href="https://t.me/Nex_bots"><img src="https://img.shields.io/badge/Support-@Nex_bots-blueviolet?style=for-the-badge&logo=telegram" alt="Support"></a>
  <img src="https://img.shields.io/badge/Upload_Limit-Up_to_4GB-brightgreen?style=for-the-badge" alt="4GB Limit">
  <img src="https://img.shields.io/badge/Python-3.10%2B-yellow?style=for-the-badge&logo=python" alt="Python">
</p>

---

## 🌟 Key Features

- 🚀 **Full 4GB Upload Capability**: Upload up to 4GB files via Telegram Premium Client (`STRING_SESSION`).
- ⚡ **Auto Clean & Rename Engine**: Strip unwanted words/channel tags, replace phrases, and format prefix/suffix with a single button click.
- 🏷️ **Lossless FFmpeg Metadata Injection**: Losslessly inject custom Title, Author, Artist, Comment, and Stream tags into video/audio files.
- ⚙️ **Interactive `/settings` Control Panel**: Modern inline dashboard to toggle metadata, upload format, sample clip duration, screenshots, cleaner rules, and dump channel with one tap.
- 🎬 **Sample Video Generator**: Automatically cuts a 15–120s sample video clip starting 20% into the media.
- 📸 **Screenshot Generator**: Extracts 1–10 high-resolution evenly spaced JPEG screenshots and delivers them as a media group album.
- 📦 **Private Dump Channel Routing**: Automatically backs up files to your private storage channel, and copies 4GB files straight to your DM.
- 🖼️ **Aspect-Ratio Preserved Custom Thumbnails**: Upload thumbnails without ugly squishing or 1:1 distortion.
- 📑 **Custom Captions**: Dynamic template variables `{filename}`, `{filesize}`, and `{duration}`.
- 🔒 **Owner-Only Mode & Force Subscribe**: Gatekeeper system with `/check_sub` validation and emergency owner-only lockdown.
- 🛡️ **Render RAM Protection**: Concurrency limiter (`asyncio.Semaphore(2)`) prevents memory spikes or disk overflow.
- ✖️ **Live Task Cancellation**: Abort ongoing downloads or uploads instantly from the progress bar.

---

## 📋 Bot Commands

### 👤 User Commands

| Command | Description | Example |
| :--- | :--- | :--- |
| `/start` | Start bot, view status, and navigation menu | `/start` |
| `/settings` | Open interactive visual dashboard | `/settings` |
| `/help` | Complete bot manual and feature guide | `/help` |
| `/about` | Bot specifications and developer info | `/about` |
| `/view_thumb` | View current custom thumbnail | `/view_thumb` |
| `/del_thumb` | Delete custom thumbnail | `/del_thumb` |
| `/set_caption` | Set custom caption with dynamic tags | `/set_caption 📕 {filename}\n📦 {filesize}` |
| `/see_caption` | View current custom caption | `/see_caption` |
| `/del_caption` | Reset custom caption | `/del_caption` |
| `/set_prefix` | Add prefix text before filenames | `/set_prefix @Nex_bots` |
| `/see_prefix` | View active prefix | `/see_prefix` |
| `/del_prefix` | Remove active prefix | `/del_prefix` |
| `/set_suffix` | Add suffix text before extension | `/set_suffix @Nex_bots` |
| `/see_suffix` | View active suffix | `/see_suffix` |
| `/del_suffix` | Remove active suffix | `/del_suffix` |
| `/metadata` | Check metadata engine status and tag | `/metadata` |
| `/set_metadata` | Set custom metadata tag string | `/set_metadata Encoded By @Nex_bots` |
| `/toggle_metadata`| Toggle metadata injection ON/OFF | `/toggle_metadata` |
| `/set_remove` | Set comma-separated words to strip | `/set_remove [MkvCinemas], @OldChannel` |
| `/set_replace` | Set word replacement pairs (`old:new`) | `/set_replace @Old:@Nex_bots, 1080p:720p` |
| `/see_cleaner` | View all active cleaner/replacer rules | `/see_cleaner` |
| `/del_cleaner` | Clear all active cleaner rules | `/del_cleaner` |
| `/set_sample` | Set sample clip duration in seconds (0-120) | `/set_sample 30` (or `0` to disable) |
| `/set_screenshots`| Set screenshot count (1-10) | `/set_screenshots 5` (or `0` to disable) |
| `/set_dump` | Set private dump channel ID | `/set_dump -1001234567890` (or `off`) |
| `/donate` | Support bot development and hosting | `/donate` |

### 🛠️ Admin Commands

| Command | Description |
| :--- | :--- |
| `/status` or `/stats` | View bot uptime, ping, total users, 4GB engine status, RAM/CPU/Disk usage |
| `/clear_cache` | Delete residual files in `downloads/` and display freed disk space |
| `/broadcast` | Broadcast a replied message to all registered bot users |
| `/restart` | Force-restart the bot process |

---

### 🤖 BotFather Commands (Copy & Paste)

Send these commands to [@BotFather](https://t.me/BotFather) using `/setcommands`:

```text
start - ⚡ Start the bot & check status
settings - ⚙️ Open interactive settings dashboard
commands - 📋 View all commands list
metadata - 🏷️ View current metadata settings
set_metadata - ✍️ Set custom metadata tag
toggle_metadata - 🔄 Turn metadata ON or OFF
set_remove - 🧹 Auto-remove words from filenames
set_replace - 🔁 Auto-replace words (old:new)
see_cleaner - 👀 View word cleaner & replacer rules
del_cleaner - 🗑️ Clear word cleaner & replacer rules
set_sample - 🎬 Set sample video duration (0-120s)
set_screenshots - 📸 Set screenshot count (0-10)
set_dump - 📦 Set private dump channel ID
set_caption - 📝 Set custom caption
see_caption - 👀 View custom caption
del_caption - 🗑️ Delete custom caption
view_thumb - 🖼️ View current thumbnail
del_thumb - 🗑️ Delete current thumbnail
set_prefix - ➕ Set filename prefix
see_prefix - 👀 View filename prefix
del_prefix - 🗑️ Delete filename prefix
set_suffix - ➕ Set filename suffix
see_suffix - 👀 View filename suffix
del_suffix - 🗑️ Delete filename suffix
status - 📊 Server & 4GB status (Admin)
clear_cache - 🧹 Clear temp downloads (Admin)
restart - 🔄 Restart the bot (Admin)
broadcast - 📢 Broadcast message (Admin)
```

---

## ⚙️ Environment Configuration

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `API_ID` | **Yes** | — | Telegram API ID from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | **Yes** | — | Telegram API Hash from [my.telegram.org](https://my.telegram.org) |
| `BOT_TOKEN` | **Yes** | — | Bot Token from [@BotFather](https://t.me/BotFather) |
| `STRING_SESSION` | Optional | `""` | Pyrogram Session String of a Telegram Premium account for **4GB uploads** |
| `DB_URL` | **Yes** | — | MongoDB Atlas Connection String (`mongodb+srv://...`) |
| `DB_NAME` | Optional | `NeX_4GB_Rename_Bot` | Database Name |
| `ADMIN` | **Yes** | — | Space-separated User IDs of bot administrators |
| `FORCE_SUB` | Optional | `Nex_bots` | Force subscribe channel username without `@` or channel ID |
| `FILES_CHANNEL` | Optional | `0` | Channel ID for media backups / 4GB file routing (`-100...`) |
| `LOG_CHANNEL` | Optional | `0` | Channel ID for system logs & restart notifications (`-100...`) |
| `START_PIC` | Optional | `""` | Direct photo URL for the `/start` message |
| `OWNER_ONLY` | Optional | `False` | Locks the bot for personal use by `ADMIN` users only |
| `WEBHOOK` | Optional | `True` | Starts an aiohttp web server on port `8080` for cloud health checks |

---

## 🚀 Deployment Guide

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/vishwaskshetty/NeX_4GB_Rename_Bot.git
cd NeX_4GB_Rename_Bot

# Copy environment template
cp .env.example .env
# Edit your .env with credentials

# Build and run Docker container
docker build -t nex-4gb-rename-bot .
docker run -d --name nex-bot --env-file .env nex-4gb-rename-bot
```

### Option 2: Render / Koyeb

1. Fork or push this repository to GitHub.
2. In Render, create a new **Web Service** and connect your repo.
3. Select **Docker** environment.
4. Add all configuration variables under the **Environment** tab.
5. Deploy!

### Option 3: VPS / Local Run

```bash
# Install FFmpeg
sudo apt-get update && sudo apt-get install -y ffmpeg

# Install Python requirements
pip install -r requirements.txt

# (Optional) Generate 4GB Telegram Premium String Session
python generate_session.py

# Run the Bot
python3 bot.py
```

---

## 🤝 Community & Support

- **Official Channel:** [@Nex_bots](https://t.me/Nex_bots)
- **Support Group:** [@Nex_bots](https://t.me/Nex_bots)
- **Developer:** [@Nex_bots](https://t.me/Nex_bots)

<p align="center">
  <b>Developed with ❤️ by <a href="https://t.me/Nex_bots">@Nex_bots</a></b>
</p>
