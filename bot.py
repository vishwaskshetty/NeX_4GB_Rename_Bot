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
    BotCommand("set_prefix", "🏷️ Set Filename Prefix"),
    BotCommand("del_prefix", "🗑️ Delete Filename Prefix"),
    BotCommand("set_suffix", "🏷️ Set Filename Suffix"),
    BotCommand("del_suffix", "🗑️ Delete Filename Suffix"),
    BotCommand("set_caption", "📝 Set Custom File Caption"),
    BotCommand("see_caption", "👀 View Custom File Caption"),
    BotCommand("del_caption", "🗑️ Delete Custom File Caption"),
    BotCommand("view_thumb", "🖼️ View Custom Thumbnail"),
    BotCommand("del_thumb", "🗑️ Delete Custom Thumbnail"),
    BotCommand("set_watermark", "💧 Set Video Watermark Position & Size"),
    BotCommand("set_sample", "🎬 Toggle Sample Video Generator (ON/OFF)"),
    BotCommand("set_sample_time", "⏱️ Set Sample Duration (10s-120s)"),
    BotCommand("set_shots", "📸 Set Sample Screenshots Count (0-10)"),
    BotCommand("clean_words", "🧹 View Filename Word Cleaner Rules"),
    BotCommand("add_clean", "➕ Add Word to Clean from Filenames"),
    BotCommand("del_clean", "➖ Remove Word from Cleaner Rules"),
    BotCommand("clear_clean", "🗑️ Clear All Cleaner Rules"),
    BotCommand("set_dump", "📦 Set Private Dump Channel ID"),
    BotCommand("del_dump", "🗑️ Remove Private Dump Channel"),
    BotCommand("donate", "☕ Support Bot with Telegram Stars / UPI"),
    BotCommand("cancel", "🛑 Cancel Active File Rename Task")
]

# 2. Owner / Admin Extra Commands (24 Commands)
OWNER_EXTRA_COMMANDS = [
    BotCommand("owner", "👑 Open Owner Control Panel"),
    BotCommand("admin", "👑 Quick Admin Actions"),
    BotCommand("mode", "🌐 Toggle Public / Private Bot Mode"),
    BotCommand("maintenance", "🛠️ Toggle Maintenance Mode"),
    BotCommand("status", "📊 Server Diagnostics & System Stats"),
    BotCommand("users", "👥 Total Registered Bot Users Count"),
    BotCommand("broadcast", "📢 Broadcast Message to All Users"),
    BotCommand("bcast_btn", "📢 Broadcast with Inline Button"),
    BotCommand("add_prem", "💎 Grant User 4GB Premium Access"),
    BotCommand("rem_prem", "🗑️ Revoke User 4GB Premium Access"),
    BotCommand("prem_list", "📋 View All Active 4GB Premium Users"),
    BotCommand("add_user", "🛡️ Authorize User for Private Mode"),
    BotCommand("rem_user", "🗑️ Revoke Authorized User"),
    BotCommand("auth_list", "📋 View Authorized Users in Private Mode"),
    BotCommand("ban", "🚫 Ban a User from the Bot"),
    BotCommand("unban", "✅ Unban a Blocked User"),
    BotCommand("ban_list", "📋 View All Banned Users"),
    BotCommand("add_coupon", "➕ Create New Discount/Premium Coupon"),
    BotCommand("del_coupon", "🗑️ Delete an Existing Coupon Code"),
    BotCommand("coupons", "🎟️ View All Active Coupon Codes"),
    BotCommand("set_fsub", "📢 Configure Force-Subscription Channels"),
    BotCommand("set_global_meta", "🏷️ Set Bot Default Global Metadata"),
    BotCommand("set_upi", "💳 Update Active Payment UPI ID"),
    BotCommand("restart", "🔄 Restart the Bot Server")
]

# Combined Owner Commands (56 Total <= 100 limit)
ALL_OWNER_COMMANDS = USER_COMMANDS + OWNER_EXTRA_COMMANDS

# 4GB Premium Secondary Client (Session String)
app_4gb = None
if Config.STRING_SESSION:
    app_4gb = Client(
        name="app_4gb",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=Config.STRING_SESSION,
        workers=16,
        max_concurrent_transmissions=8,
        no_updates=True
    )


class Bot(Client):

    def __init__(self):
        super().__init__(
            name="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=16,
            max_concurrent_transmissions=8,
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
