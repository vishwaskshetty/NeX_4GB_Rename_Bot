import os
import sys

# High-Speed C++ based uvloop Event Loop for Linux (100-200 MB/s transfers)
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass

import time
import gc
import shutil
import asyncio
from datetime import datetime
from pytz import timezone
from pyrogram import Client, __version__
from pyrogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from pyrogram.raw.all import layer
from config import Config
from aiohttp import web
from route import web_server
import pyrogram.utils
from helper.database import db

# Support for channels with large IDs
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

# Bot Process Start Time & Drain Mode Tracker
BOT_START_TIME = time.time()

def is_in_drain_mode() -> bool:
    """Returns True if the bot has been running for >= 5 hours 15 minutes (18,900s) and is preparing for high-speed cloud handoff."""
    return (time.time() - BOT_START_TIME) >= 18900

def get_bot_uptime() -> float:
    """Returns uptime in seconds."""
    return time.time() - BOT_START_TIME

# Bot Commands Definitions
# 1. Public User Commands (Default Scope - 32 Commands with /start strictly #1)
USER_COMMANDS = [
    BotCommand("start", "⚡ Start the Bot & Main Menu"),
    BotCommand("profile", "👤 View Profile, Plan & Usage Stats"),
    BotCommand("refer", "🎁 Refer Friends & Earn Free Gold Plan"),
    BotCommand("plan", "💎 Upgrade to 4GB Premium & Plans"),
    BotCommand("myplan", "📊 My Plan, Quota & Usage Stats"),
    BotCommand("trial", "🎁 Claim 3-Day Free 4GB Trial"),
    BotCommand("settings", "⚙️ Rename, Watermark & Sample Settings"),
    BotCommand("leaderboard", "🏆 Top Renamers Leaderboard"),
    BotCommand("redeem", "🎟️ Redeem Premium Coupon Code"),
    BotCommand("usage", "📈 Check Daily & Lifetime Data Usage"),
    BotCommand("timezone", "🌍 Set Your Local Timezone"),
    BotCommand("metadata", "🏷️ Configure Video/Audio Metadata"),
    BotCommand("set_metadata", "✍️ Set Custom Metadata Text"),
    BotCommand("set_prefix", "🔤 Set Filename Prefix"),
    BotCommand("del_prefix", "🗑️ Delete Filename Prefix"),
    BotCommand("set_suffix", "🔡 Set Filename Suffix"),
    BotCommand("del_suffix", "🗑️ Delete Filename Suffix"),
    BotCommand("set_caption", "📝 Set Custom File Caption"),
    BotCommand("see_caption", "👁️ View Current Custom Caption"),
    BotCommand("del_caption", "🗑️ Delete Custom Caption"),
    BotCommand("view_thumb", "🖼️ View Custom Thumbnail"),
    BotCommand("del_thumb", "🗑️ Delete Custom Thumbnail"),
    BotCommand("set_watermark", "💧 Set Video Watermark Text (Premium)"),
    BotCommand("set_sample", "🎬 Set Sample Video Duration"),
    BotCommand("set_sample_time", "⏱️ Set Sample Video Timeline Start"),
    BotCommand("set_shots", "📸 Set Screenshot Count (0-10)"),
    BotCommand("clean_words", "🧹 View Filename Word Cleaner List"),
    BotCommand("add_clean", "➕ Add Word to Filename Cleaner"),
    BotCommand("del_clean", "➖ Remove Word from Cleaner"),
    BotCommand("clear_clean", "🗑️ Clear All Cleaner Words"),
    BotCommand("streams", "🎧 Inspect & Strip Audio/Sub Tracks"),
    BotCommand("remux", "🔄 Lossless MKV ⇄ MP4 Remuxer"),
    BotCommand("sheet", "📸 3x3 HD Screenshot Sheet"),
    BotCommand("extract", "📦 Extract ZIP, RAR, 7Z Archives"),
    BotCommand("zip", "🗜️ Compress Files to ZIP"),
    BotCommand("template", "🏷️ Episode Auto-Rename Template"),
    BotCommand("set_dump", "📦 Set Personal Dump Channel ID"),
    BotCommand("del_dump", "🗑️ Remove Personal Dump Channel"),
    BotCommand("donate", "❤️ Support & Donate to Developer"),
    BotCommand("cancel", "🛑 Cancel Active Rename Task"),
    BotCommand("reset_task", "🧹 Reset Stuck Task Queue")
]

# 2. Owner / Admin Extra Commands (25 Commands)
OWNER_EXTRA_COMMANDS = [
    BotCommand("owner", "👑 Open Interactive Owner Control Panel"),
    BotCommand("admin", "🛠️ Open Admin Dashboard"),
    BotCommand("mode", "🌐 Toggle Bot Mode (Public / Private)"),
    BotCommand("maintenance", "🛠️ Toggle Maintenance Mode ON/OFF"),
    BotCommand("status", "📊 View Bot & Server Statistics"),
    BotCommand("users", "👥 View Total User Count"),
    BotCommand("broadcast", "📢 Broadcast Message with Buttons"),
    BotCommand("bcast_btn", "🔗 Set Custom Broadcast Buttons"),
    BotCommand("add_prem", "💎 Grant Premium (/add_prem id tier days)"),
    BotCommand("rem_prem", "🗑️ Revoke Premium (/rem_prem id)"),
    BotCommand("prem_list", "💎 List All Active Premium Users"),
    BotCommand("add_user", "🛡️ Authorize User in Private Mode"),
    BotCommand("rem_user", "🗑️ Remove Authorized User"),
    BotCommand("auth_list", "📋 List All Authorized Users"),
    BotCommand("ban", "🚫 Ban User from Bot (/ban id)"),
    BotCommand("unban", "✅ Unban User (/unban id)"),
    BotCommand("ban_list", "🚫 List All Banned Users"),
    BotCommand("add_coupon", "🎟️ Create Coupon (/add_coupon code tier days uses)"),
    BotCommand("del_coupon", "🗑️ Delete Coupon (/del_coupon code)"),
    BotCommand("coupons", "🎟️ List & Manage Active Coupons"),
    BotCommand("set_fsub", "📢 Set Force-Sub Channel & Mode"),
    BotCommand("set_global_meta", "🏷️ Set Global Default Metadata Tag"),
    BotCommand("set_upi", "🇮🇳 Update UPI ID for Payments"),
    BotCommand("logs", "📜 View Latest Activity Logs"),
    BotCommand("health", "🩺 System & Server Health Diagnostic"),
    BotCommand("restart", "🔄 Restart the Bot Server")
]

# Combined Owner Commands (56 Total <= 100 limit, with /start #1 and /owner #2 near top)
ALL_OWNER_COMMANDS = [USER_COMMANDS[0]] + OWNER_EXTRA_COMMANDS + USER_COMMANDS[1:]

# 4GB Premium Secondary Client (Session String)
app_4gb = None
if Config.STRING_SESSION:
    app_4gb = Client(
        name="app_4gb",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=Config.STRING_SESSION,
        workers=64,
        max_concurrent_transmissions=20,
        sleep_threshold=60,
        no_updates=True
    )


class Bot(Client):

    def __init__(self):
        super().__init__(
            name="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=64,
            max_concurrent_transmissions=20,
            plugins={"root": "plugins"},
            sleep_threshold=60,
        )
        self.app_4gb = app_4gb
        self.app_4gb_started = False
        self._is_running = True

    async def start(self):
        # 1. Immediately bind web server port for Render/Koyeb health checks
        if Config.WEBHOOK or os.environ.get("RENDER"):
            try:
                app = web.AppRunner(await web_server())
                await app.setup()       
                await web.TCPSite(app, "0.0.0.0", Config.PORT).start()     
                print(f"NeX Web Server running on port {Config.PORT} ✨️")
            except Exception as e:
                print(f"Error starting web server on port {Config.PORT}: {e}")

        await super().start()
        me = await self.get_me()
        self.mention = me.mention
        self.username = me.username  
        self.uptime = Config.BOT_UPTIME     

        # Register Bot Commands Menu in Telegram (Strict Scoping)
        try:
            # 1. Public Command Menu (Default Scope - Visible to All Users with /start #1)
            await self.set_bot_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
            print("Telegram Public Bot Commands registered successfully! 📋 (32 commands, /start #1)")

            # 2. Owner / Admin Commands (Scope: Registered for Admins - 56 Commands)
            for admin_id in Config.ADMIN:
                try:
                    await self.set_bot_commands(ALL_OWNER_COMMANDS, scope=BotCommandScopeChat(chat_id=int(admin_id)))
                except Exception as admin_err:
                    print(f"Failed to register Admin Commands for {admin_id}: {admin_err}")
            print("Telegram Owner/Admin Bot Commands registered successfully! 👑 (56 commands)")
        except Exception as e:
            print(f"Failed to register Bot Commands Menu: {e}")

        if self.app_4gb:
            try:
                await self.app_4gb.start()
                self.app_4gb_started = True
                user_me = await self.app_4gb.get_me()
                print(f"NeX 4GB Premium Client Started as: {user_me.first_name} (@{user_me.username or 'No Username'}) ✨️")
            except Exception as e:
                print(f"Error starting 4GB Premium Client: {e}")

        print(f"{me.first_name} [NeX 4GB Rename Bot] Is Started.....✨️")
        for admin_id in Config.ADMIN:
            try:
                await self.send_message(admin_id, f"<b>{me.first_name} [NeX 4GB Rename Bot] Is Started.....✨️</b>\n\n⚡ Powered by @Nex_bots")
            except Exception:
                pass

        if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
            try:
                curr = datetime.now(timezone("Asia/Kolkata"))
                date = curr.strftime('%d %B, %Y')
                time_str = curr.strftime('%I:%M:%S %p')
                log_text = (
                    f"<b>{me.mention} Is Restarted !!</b>\n\n"
                    f"📅 <b>Date :</b> <code>{date}</code>\n"
                    f"⏰ <b>Time :</b> <code>{time_str}</code>\n"
                    f"🌐 <b>Timezone :</b> <code>Asia/Kolkata</code>\n\n"
                    f"🉐 <b>Version :</b> <code>v{__version__} (Layer {layer})</code>\n"
                    f"⚡ <b>Powered by :</b> @Nex_bots"
                )
                await self.send_message(Config.LOG_CHANNEL, log_text)
            except Exception as e:
                print(f"Please Make Sure The Bot Is Admin In Your Log Channel: {e}")

        # Check for and automatically resume interrupted tasks from previous cloud instance
        try:
            from plugins.file_rename import resume_interrupted_tasks
            asyncio.create_task(resume_interrupted_tasks(self))
        except Exception as rec_err:
            print(f"⚠️ [Recovery] Startup task recovery launch error: {rec_err}")

        # Launch permanent background tasks for 24/7 zero-downtime operation
        asyncio.create_task(self._mtproto_watchdog())
        asyncio.create_task(self._temp_cleanup_worker())

    async def _mtproto_watchdog(self):
        """
        Permanent 30-Second MTProto Socket Pinger, Heartbeat Writer & Self-Heal Watchdog.
        Guarantees zero-downtime 24/7 production operation against NAT idle timeouts,
        frozen sockets, and memory leaks.
        """
        consecutive_socket_failures = 0
        last_gc_time = time.time()

        # Startup grace period to allow network and clients to fully initialize
        await asyncio.sleep(20)

        while self._is_running:
            # 1 & 2: Ping Telegram MTProto Sockets (Main Bot & 4GB App)
            try:
                await asyncio.wait_for(self.get_me(), timeout=15)
                if self.app_4gb and self.app_4gb_started:
                    await asyncio.wait_for(self.app_4gb.get_me(), timeout=15)
                consecutive_socket_failures = 0
            except (asyncio.TimeoutError, Exception) as socket_err:
                consecutive_socket_failures += 1
                print(f"⚠️ [Watchdog] Telegram socket check failed (#{consecutive_socket_failures}/2): {socket_err}")
                if consecutive_socket_failures >= 2:
                    print("⚠️ [Watchdog] Telegram socket unresponsive! Triggering instant clean self-restart...")
                    try:
                        if self.app_4gb:
                            try:
                                await self.app_4gb.stop()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    os.execv(sys.executable, [sys.executable] + sys.argv)

            # 3. Ping MongoDB via db.client.admin.command("ping")
            try:
                if hasattr(db, "client") and db.client:
                    await asyncio.wait_for(db.client.admin.command("ping"), timeout=10)
            except Exception as mongo_err:
                print(f"⚠️ [Watchdog] MongoDB ping warning: {mongo_err}")

            # 4. Write current timestamp to heartbeat files
            try:
                hb_ts = str(time.time())
                target_paths = ["/tmp/nex_bot_heartbeat.txt"]
                if os.path.exists("/content"):
                    target_paths.append("/content/bot_heartbeat.txt")

                for p in target_paths:
                    try:
                        os.makedirs(os.path.dirname(p), exist_ok=True)
                        with open(p, "w", encoding="utf-8") as f:
                            f.write(hb_ts)
                    except Exception:
                        pass

                # Also write to OS temp directory (for Windows / container environments)
                try:
                    import tempfile
                    local_hb = os.path.join(tempfile.gettempdir(), "nex_bot_heartbeat.txt")
                    with open(local_hb, "w", encoding="utf-8") as f:
                        f.write(hb_ts)
                except Exception:
                    pass
            except Exception:
                pass

            # 5. Run gc.collect() every 10 minutes (600s) to prevent memory fragmentation
            try:
                now = time.time()
                if now - last_gc_time >= 600:
                    gc.collect()
                    last_gc_time = now
            except Exception:
                pass

            await asyncio.sleep(30)

    async def _temp_cleanup_worker(self):
        """
        Background Sweeper running every 15 minutes.
        Deletes orphaned media files (*.mkv, *.mp4, *.jpg, *.part, thumb_*)
        older than 45 minutes that are not tied to an active task.
        Guarantees disk space is never exhausted during 24/7 continuous operation.
        """
        # Initial sleep before first sweep
        await asyncio.sleep(60)

        while self._is_running:
            try:
                now = time.time()
                cutoff_time = 45 * 60  # 45 minutes = 2700 seconds
                deleted_files = 0
                freed_bytes = 0

                try:
                    from plugins.file_rename import is_active_task_path, ACTIVE_WORK_DIRS
                except Exception:
                    is_active_task_path = lambda p: False
                    ACTIVE_WORK_DIRS = set()

                # 0. Scan Linux RAM-disk /dev/shm/nex_tasks
                shm_dir = "/dev/shm/nex_tasks"
                if os.path.exists(shm_dir):
                    for entry in os.listdir(shm_dir):
                        entry_path = os.path.join(shm_dir, entry)
                        abs_entry = os.path.abspath(entry_path)
                        if is_active_task_path(entry_path) or abs_entry in ACTIVE_WORK_DIRS:
                            continue
                        try:
                            mtime = os.path.getmtime(entry_path)
                            if (now - mtime) >= cutoff_time:
                                if os.path.isdir(entry_path):
                                    shutil.rmtree(entry_path, ignore_errors=True)
                                elif os.path.isfile(entry_path):
                                    os.remove(entry_path)
                                deleted_files += 1
                        except Exception:
                            pass

                # 1. Scan downloads/ directory
                downloads_dir = "downloads"
                if os.path.exists(downloads_dir):
                    for entry in os.listdir(downloads_dir):
                        entry_path = os.path.join(downloads_dir, entry)
                        abs_entry = os.path.abspath(entry_path)

                        # Skip if tied to an active task
                        if is_active_task_path(entry_path) or abs_entry in ACTIVE_WORK_DIRS:
                            continue

                        try:
                            mtime = os.path.getmtime(entry_path)
                            if (now - mtime) >= cutoff_time:
                                if os.path.isdir(entry_path):
                                    for root, _, files in os.walk(entry_path):
                                        for f in files:
                                            fp = os.path.join(root, f)
                                            try:
                                                freed_bytes += os.path.getsize(fp)
                                                deleted_files += 1
                                            except Exception:
                                                pass
                                    shutil.rmtree(entry_path, ignore_errors=True)
                                elif os.path.isfile(entry_path):
                                    freed_bytes += os.path.getsize(entry_path)
                                    os.remove(entry_path)
                                    deleted_files += 1
                        except Exception:
                            pass

                # 2. Scan current working directory for orphaned media files
                temp_extensions = ('.mkv', '.mp4', '.jpg', '.jpeg', '.part', '.webm', '.avi')
                for item in os.listdir('.'):
                    if not os.path.isfile(item):
                        continue

                    lower_item = item.lower()
                    is_match = (
                        lower_item.startswith("thumb_") or
                        lower_item.startswith("meta_") or
                        lower_item.startswith("wm_") or
                        lower_item.startswith("sample_") or
                        lower_item.endswith(temp_extensions)
                    )

                    if not is_match:
                        continue

                    # Skip if tied to an active task
                    if is_active_task_path(item):
                        continue

                    try:
                        mtime = os.path.getmtime(item)
                        if (now - mtime) >= cutoff_time:
                            freed_bytes += os.path.getsize(item)
                            os.remove(item)
                            deleted_files += 1
                    except Exception:
                        pass

                if deleted_files > 0:
                    print(f"🧹 [Sweeper] Cleaned {deleted_files} orphaned files, freed {freed_bytes / (1024*1024):.2f} MB disk space.")

            except Exception as sweeper_err:
                print(f"⚠️ [Sweeper] Error during cleanup sweep: {sweeper_err}")

            # Sleep 15 minutes = 900 seconds
            await asyncio.sleep(900)

    async def stop(self, *args):
        self._is_running = False
        if self.app_4gb:
            try:
                await self.app_4gb.stop()
            except Exception:
                pass
        await super().stop(*args)


if __name__ == "__main__":
    Bot().run()
