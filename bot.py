import os
from datetime import datetime
from pytz import timezone
from pyrogram import Client, __version__
from pyrogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from pyrogram.raw.all import layer
from config import Config
from aiohttp import web
from route import web_server
import pyrogram.utils

# Support for channels with large IDs
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

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
    BotCommand("set_dump", "📦 Set Personal Dump Channel ID"),
    BotCommand("del_dump", "🗑️ Remove Personal Dump Channel"),
    BotCommand("donate", "❤️ Support & Donate to Developer"),
    BotCommand("cancel", "🛑 Cancel Active Rename Task")
]

# 2. Owner / Admin Extra Commands (24 Commands)
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
        workers=32,
        max_concurrent_transmissions=10,
        no_updates=True
    )


class Bot(Client):

    def __init__(self):
        super().__init__(
            name="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=32,
            max_concurrent_transmissions=10,
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
