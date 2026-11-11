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
            # 1. Public Command Menu (Default Scope - Visible to All Users)
            public_commands = [
                BotCommand("plan", "💎 Upgrade to 4GB Premium & Plans"),
                BotCommand("myplan", "📊 My Plan, Quota & Usage"),
                BotCommand("trial", "🎁 Claim 3-Day Free 4GB Trial"),
                BotCommand("start", "⚡ Start the Bot"),
                BotCommand("settings", "⚙️ Configure Rename, Watermark & Sample Settings"),
                BotCommand("leaderboard", "🏆 Top Renamers Leaderboard"),
                BotCommand("redeem", "🎟️ Redeem Premium Coupon Code"),
                BotCommand("metadata", "🏷️ Configure File Metadata"),
                BotCommand("set_caption", "📝 Set Custom File Caption"),
                BotCommand("del_caption", "🗑️ Delete Custom Caption"),
                BotCommand("view_thumb", "🖼️ View Custom Thumbnail"),
                BotCommand("del_thumb", "🗑️ Delete Custom Thumbnail"),
                BotCommand("clean_words", "🧹 Manage Filename Word Cleaner"),
                BotCommand("cancel", "🛑 Cancel Stuck Rename Task")
            ]
            await self.set_bot_commands(public_commands, scope=BotCommandScopeDefault())
            print("Telegram Public Bot Commands registered successfully! 📋")

            # 2. Owner / Admin Commands (Scope: Registered ONLY for Admins)
            admin_commands = public_commands + [
                BotCommand("owner", "👑 Open Owner Control Panel"),
                BotCommand("mode", "🌐 Toggle Public / Private Mode"),
                BotCommand("maintenance", "🛠️ Toggle Maintenance Mode"),
                BotCommand("fsub", "📢 Force-Sub Settings & Mode"),
                BotCommand("add_user", "🛡️ Authorize user for Private Mode"),
                BotCommand("rem_user", "🗑️ Revoke authorized user"),
                BotCommand("auth_list", "📋 List all authorized users"),
                BotCommand("add_prem", "💎 Grant 4GB Premium access"),
                BotCommand("rem_prem", "🗑️ Remove 4GB Premium access"),
                BotCommand("prem_list", "💎 List all 4GB Premium users"),
                BotCommand("coupons", "🎟️ View active coupons"),
                BotCommand("add_coupon", "➕ Create a coupon code"),
                BotCommand("del_coupon", "🗑️ Delete a coupon code"),
                BotCommand("set_upi", "💳 Update active UPI ID"),
                BotCommand("ban", "🚫 Ban a user from the bot"),
                BotCommand("unban", "✅ Unban a user"),
                BotCommand("set_global_meta", "🏷️ Set bot default metadata tag"),
                BotCommand("status", "📊 Server & 4GB status"),
                BotCommand("clear_cache", "🧹 Clear temp downloads"),
                BotCommand("restart", "🔄 Restart the bot"),
                BotCommand("broadcast", "📢 Broadcast message")
            ]
            for admin_id in Config.ADMIN:
                try:
                    await self.set_bot_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(admin_id)))
                except Exception as admin_err:
                    print(f"Failed to register Admin Commands for {admin_id}: {admin_err}")
            print("Telegram Owner/Admin Bot Commands registered successfully! 👑")
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
