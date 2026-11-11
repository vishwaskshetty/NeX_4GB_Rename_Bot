import os
import sys
import time
import shutil
import psutil
import asyncio
import logging
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

from config import Config
from helper.database import db
from helper.utils import get_readable_file_size

# NeX 4GB Rename Bot - Admin Operations
# Developed by @Nex_bots

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

 
@Client.on_message(filters.command(["stats", "status"]) & filters.user(Config.ADMIN))
async def get_stats(bot, message):
    st = await message.reply('⏳ <b>Calculating System Statistics...</b>')
    start_t = time.time()
    
    total_users = await db.total_users_count()
    uptime = time.strftime("%Hh %Mm %Ss", time.gmtime(time.time() - bot.uptime))
    end_t = time.time()
    ping_ms = (end_t - start_t) * 1000
    
    # Check 4GB status
    has_4gb = bool(getattr(bot, "app_4gb", None))
    client_4gb_status = "Connected 🟢 (4GB Mode)" if has_4gb else "Disabled 🔴 (2GB Mode)"

    total_disk, used_disk, free_disk = shutil.disk_usage(".")
    cpu_usage = psutil.cpu_percent(interval=0.2)
    ram_usage = psutil.virtual_memory().percent

    stats_text = (
        f"⚡ <b><u>NeX 4GB Rename Bot Status</u></b> ⚡\n\n"
        f"⏱️ <b>Bot Uptime :</b> <code>{uptime}</code>\n"
        f"📶 <b>Current Ping :</b> <code>{ping_ms:.2f} ms</code>\n"
        f"👥 <b>Total Bot Users :</b> <code>{total_users}</code>\n"
        f"🚀 <b>4GB Premium Engine :</b> <code>{client_4gb_status}</code>\n\n"
        f"💾 <b>RAM Usage :</b> <code>{ram_usage}%</code>\n"
        f"🖥️ <b>CPU Load :</b> <code>{cpu_usage}%</code>\n"
        f"💿 <b>Free Storage :</b> <code>{get_readable_file_size(free_disk)}</code> / <code>{get_readable_file_size(total_disk)}</code>\n\n"
        f"⚡ <b>Powered by :</b> @Nex_bots"
    )
    await st.edit(text=stats_text)


# Restart Bot Process
@Client.on_message(filters.private & filters.command("restart") & filters.user(Config.ADMIN))
async def restart_bot(b, m):
    await m.reply_text("<b>🔄 Restarting NeX 4GB Rename Bot Engine.....</b>\n\n⚡ @Nex_bots")
    os.execl(sys.executable, sys.executable, *sys.argv)


# Broadcast message to all registered bot users
@Client.on_message(filters.command("broadcast") & filters.user(Config.ADMIN) & filters.reply)
async def broadcast_handler(bot: Client, m: Message):
    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
        try:
            await bot.send_message(
                Config.LOG_CHANNEL,
                f"📢 <b>Broadcast Initialized</b> by {m.from_user.mention} (<code>{m.from_user.id}</code>)..."
            )
        except Exception:
            pass

    all_users = await db.get_all_users()
    broadcast_msg = m.reply_to_message
    sts_msg = await m.reply_text("📢 <b>Broadcast In Progress...</b>") 
    
    done = 0
    failed = 0
    success = 0
    start_time = time.time()
    total_users = await db.total_users_count()

    async for user in all_users:
        sts = await send_msg(user['_id'], broadcast_msg)
        if sts == 200:
            success += 1
        else:
            failed += 1
        if sts == 400:
            await db.delete_user(user['_id'])
        done += 1
        if done % 20 == 0:
            await sts_msg.edit(
                f"📢 <b>Broadcast In Progress:</b>\n\n"
                f"• <b>Total Users:</b> <code>{total_users}</code>\n"
                f"• <b>Processed:</b> <code>{done} / {total_users}</code>\n"
                f"• <b>Success:</b> <code>{success}</code>\n"
                f"• <b>Failed:</b> <code>{failed}</code>\n\n"
                f"⚡ @Nex_bots"
            )

    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts_msg.edit(
        f"✅ <b>Broadcast Completed Successfully!</b>\n\n"
        f"⏱️ <b>Time Taken:</b> <code>{completed_in}</code>\n"
        f"👥 <b>Total Users:</b> <code>{total_users}</code>\n"
        f"🟢 <b>Delivered:</b> <code>{success}</code>\n"
        f"🔴 <b>Failed/Deleted:</b> <code>{failed}</code>\n\n"
        f"⚡ <b>NeX 4GB Rename Bot</b> | @Nex_bots"
    )

           
async def send_msg(user_id, message):
    try:
        await message.copy(chat_id=int(user_id))
        return 200
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await send_msg(user_id, message)
    except InputUserDeactivated:
        logger.info(f"{user_id} : Deactivated")
        return 400
    except UserIsBlocked:
        logger.info(f"{user_id} : Blocked The Bot")
        return 400
    except PeerIdInvalid:
        logger.info(f"{user_id} : User ID Invalid")
        return 400
    except Exception as e:
        logger.error(f"{user_id} : {e}")
        return 500
