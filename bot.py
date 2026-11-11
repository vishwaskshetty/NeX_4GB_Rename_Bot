import os
from datetime import datetime
from pytz import timezone
from pyrogram import Client, __version__
from pyrogram.types import BotCommand
from pyrogram.raw.all import layer
from config import Config
from aiohttp import web
from route import web_server
import pyrogram.utils

# Support for channels with large IDs
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

# 4GB Premium Secondary Client (Session String)
app_4gb = None
if Config.STRING_SESSION:
    app_4gb = Client(
        name="app_4gb",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=Config.STRING_SESSION,
        no_updates=True
    )


class Bot(Client):

    def __init__(self):
        super().__init__(
            name="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=15,
        )
        self.app_4gb = app_4gb

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

        # Register Bot Commands Menu in Telegram
        try:
            commands = [
                BotCommand("start", "⚡ Start the bot & check status"),
                BotCommand("settings", "⚙️ Open interactive settings dashboard"),
                BotCommand("metadata", "🏷️ View current metadata settings"),
                BotCommand("set_metadata", "✍️ Set custom metadata tag"),
                BotCommand("toggle_metadata", "🔄 Turn metadata ON or OFF"),
                BotCommand("set_remove", "🧹 Auto-remove words from filenames"),
                BotCommand("set_replace", "🔁 Auto-replace words (old:new)"),
                BotCommand("see_cleaner", "👀 View word cleaner & replacer rules"),
                BotCommand("del_cleaner", "🗑️ Clear word cleaner & replacer rules"),
                BotCommand("set_sample", "🎬 Set sample video duration (0-120s)"),
                BotCommand("set_screenshots", "📸 Set screenshot count (0-10)"),
                BotCommand("set_dump", "📦 Set private dump channel ID"),
                BotCommand("set_caption", "📝 Set custom caption"),
                BotCommand("see_caption", "👀 View custom caption"),
                BotCommand("del_caption", "🗑️ Delete custom caption"),
                BotCommand("view_thumb", "🖼️ View current thumbnail"),
                BotCommand("del_thumb", "🗑️ Delete current thumbnail"),
                BotCommand("set_prefix", "➕ Set filename prefix"),
                BotCommand("see_prefix", "👀 View filename prefix"),
                BotCommand("del_prefix", "🗑️ Delete filename prefix"),
                BotCommand("set_suffix", "➕ Set filename suffix"),
                BotCommand("see_suffix", "👀 View filename suffix"),
                BotCommand("del_suffix", "🗑️ Delete filename suffix"),
                BotCommand("owner", "👑 Open Owner Control Panel (Admin)"),
                BotCommand("mode", "🌐 Toggle Public / Private Mode (Admin)"),
                BotCommand("add_user", "🛡️ Authorize user for Private Mode (Admin)"),
                BotCommand("rem_user", "🗑️ Revoke authorized user (Admin)"),
                BotCommand("auth_list", "📋 List all authorized users (Admin)"),
                BotCommand("add_prem", "💎 Grant 4GB Premium access (Admin)"),
                BotCommand("rem_prem", "🗑️ Remove 4GB Premium access (Admin)"),
                BotCommand("prem_list", "💎 List all 4GB Premium users (Admin)"),
                BotCommand("ban", "🚫 Ban a user from the bot (Admin)"),
                BotCommand("unban", "✅ Unban a user (Admin)"),
                BotCommand("set_global_meta", "🏷️ Set bot default metadata tag (Admin)"),
                BotCommand("status", "📊 Server & 4GB status (Admin)"),
                BotCommand("clear_cache", "🧹 Clear temp downloads (Admin)"),
                BotCommand("restart", "🔄 Restart the bot (Admin)"),
                BotCommand("broadcast", "📢 Broadcast message (Admin)")
            ]
            await self.set_bot_commands(commands)
            print("Telegram Bot Commands Menu registered successfully! 📋")
        except Exception as e:
            print(f"Failed to register Bot Commands Menu: {e}")

        if self.app_4gb:
            try:
                await self.app_4gb.start()
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

    async def stop(self, *args):
        if self.app_4gb:
            try:
                await self.app_4gb.stop()
            except Exception:
                pass
        await super().stop(*args)


if __name__ == "__main__":
    Bot().run()
