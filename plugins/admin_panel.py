import os
import sys
import time
import shutil
import psutil
import asyncio
import logging
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

from config import Config
from helper.database import db
from helper.utils import get_readable_file_size, edit_message_content

# NeX 4GB Rename Bot - Interactive Owner Control Panel & Admin Operations
# Developed by @Nex_bots

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ==================== LIVE OWNER DASHBOARD BUILDER ====================

async def build_owner_panel(client: Client):
    bot_mode = await db.get_bot_mode()
    mode_str = "🔒 Private (Owner/Auth)" if bot_mode == "private" else "🌍 Public (Everyone)"
    
    has_4gb = bool(getattr(client, "app_4gb", None))
    engine_str = "Active 🟢 (4GB Mode)" if has_4gb else "Inactive 🔴 (2GB Mode)"
    
    total_users = await db.total_users_count()
    auth_users = await db.get_auth_users()
    prem_users = await db.get_premium_users()
    banned_users = await db.get_banned_users()
    default_meta = await db.get_default_metadata()

    total_disk, used_disk, free_disk = shutil.disk_usage(".")
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent

    text = (
        f"👑 <b><u>NeX 4GB Owner Control Panel</u></b> ⚡\n\n"
        f"◈ <b>🌐 Bot Mode :</b> <code>{mode_str}</code>\n"
        f"◈ <b>🚀 4GB Engine :</b> <code>{engine_str}</code>\n"
        f"◈ <b>🏷️ Global Meta :</b> <code>{default_meta}</code>\n\n"
        f"◈ <b>👥 Total Users :</b> <code>{total_users}</code>\n"
        f"◈ <b>🛡️ Auth Users :</b> <code>{len(auth_users)}</code>\n"
        f"◈ <b>💎 Premium Users :</b> <code>{len(prem_users)}</code>\n"
        f"◈ <b>🚫 Banned Users :</b> <code>{len(banned_users)}</code>\n\n"
        f"◈ <b>💾 Free Disk :</b> <code>{get_readable_file_size(free_disk)}</code> / <code>{get_readable_file_size(total_disk)}</code>\n"
        f"◈ <b>🖥️ RAM :</b> <code>{ram}%</code> | <b>CPU :</b> <code>{cpu}%</code>\n\n"
        f"<i>💡 Select an option below to manage bot settings in real time:</i>\n\n"
        f"⚡ <b>NeX 4GB Rename Bot</b> | @Nex_bots"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"🔄 Mode: {'🔒 Private' if bot_mode == 'private' else '🌍 Public'}", callback_data="cb_owner_toggle_mode")
        ],
        [
            InlineKeyboardButton(f"🛡️ Auth Users ({len(auth_users)})", callback_data="cb_owner_auth"),
            InlineKeyboardButton(f"💎 Premium ({len(prem_users)})", callback_data="cb_owner_prem")
        ],
        [
            InlineKeyboardButton(f"🚫 Banned ({len(banned_users)})", callback_data="cb_owner_banned"),
            InlineKeyboardButton("🏷️ Global Meta", callback_data="cb_owner_meta")
        ],
        [
            InlineKeyboardButton("📦 Channels & Dumps", callback_data="cb_owner_channels"),
            InlineKeyboardButton("⚙️ My Rename Settings", callback_data="open_settings")
        ],
        [
            InlineKeyboardButton("📊 Server Stats", callback_data="cb_owner_stats"),
            InlineKeyboardButton("🧹 Clear Cache", callback_data="clear_cache_owner")
        ],
        [
            InlineKeyboardButton("🔄 Restart Bot", callback_data="cb_owner_restart"),
            InlineKeyboardButton("🔙 Back to Start", callback_data="start")
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ==================== OWNER COMMAND HANDLERS ====================

@Client.on_message(filters.private & filters.command(["owner", "admin"]) & filters.user(Config.ADMIN))
async def owner_panel_cmd(client, message):
    text, markup = await build_owner_panel(client)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("mode") & filters.user(Config.ADMIN))
async def mode_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        target = args[1].strip().lower()
        if target in ("private", "public"):
            await db.set_bot_mode(target)
            return await message.reply_text(f"🌐 <b>Bot Mode Updated:</b> <code>{target.upper()}</code>\n\n⚡ @Nex_bots")
    
    current = await db.get_bot_mode()
    new_mode = "public" if current == "private" else "private"
    await db.set_bot_mode(new_mode)
    await message.reply_text(
        f"🌐 <b>Bot Mode Toggled!</b>\n\n"
        f"<b>Previous:</b> <code>{current.upper()}</code>\n"
        f"<b>Active:</b> <code>{new_mode.upper()}</code>\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["add_user", "auth_user"]) & filters.user(Config.ADMIN))
async def add_auth_user_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/add_user &lt;user_id&gt;</code>")
    try:
        target_id = int(args[1].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid User ID!</b> Please provide numeric ID.")
    
    await db.add_auth_user(target_id)
    await message.reply_text(
        f"🛡️ <b>User Authorized Successfully!</b>\n\n"
        f"User ID <code>{target_id}</code> is now granted full bot access in Private Mode.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["rem_user", "remove_user"]) & filters.user(Config.ADMIN))
async def rem_auth_user_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/rem_user &lt;user_id&gt;</code>")
    try:
        target_id = int(args[1].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid User ID!</b> Please provide numeric ID.")
    
    await db.remove_auth_user(target_id)
    await message.reply_text(
        f"🗑️ <b>User Removed!</b>\n\n"
        f"User ID <code>{target_id}</code> has been revoked from Authorized Users.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["auth_list", "users_list"]) & filters.user(Config.ADMIN))
async def auth_list_cmd(client, message):
    users = await db.get_auth_users()
    if not users:
        return await message.reply_text("🛡️ <b>Authorized Users:</b> None (Admins always have access).")
    formatted = "\n".join([f"• <code>{uid}</code>" for uid in users])
    await message.reply_text(f"🛡️ <b><u>Authorized Users ({len(users)})</u></b>\n\n{formatted}\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command(["add_prem", "set_prem"]) & filters.user(Config.ADMIN))
async def add_prem_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/add_prem &lt;user_id&gt;</code>")
    try:
        target_id = int(args[1].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid User ID!</b> Please provide numeric ID.")
    
    await db.add_premium_user(target_id)
    await message.reply_text(
        f"💎 <b>4GB Premium Access Granted!</b>\n\n"
        f"User ID <code>{target_id}</code> can now upload files up to 4GB.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["rem_prem", "del_prem"]) & filters.user(Config.ADMIN))
async def rem_prem_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/rem_prem &lt;user_id&gt;</code>")
    try:
        target_id = int(args[1].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid User ID!</b> Please provide numeric ID.")
    
    await db.remove_premium_user(target_id)
    await message.reply_text(
        f"🗑️ <b>4GB Premium Access Revoked!</b>\n\n"
        f"User ID <code>{target_id}</code> is restricted to 2GB.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("prem_list") & filters.user(Config.ADMIN))
async def prem_list_cmd(client, message):
    users = await db.get_premium_users()
    if not users:
        return await message.reply_text("💎 <b>Premium Users:</b> None (Admins always have 4GB access).")
    formatted = "\n".join([f"• <code>{uid}</code>" for uid in users])
    await message.reply_text(f"💎 <b><u>4GB Premium Users ({len(users)})</u></b>\n\n{formatted}\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command("ban") & filters.user(Config.ADMIN))
async def ban_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/ban &lt;user_id&gt;</code>")
    try:
        target_id = int(args[1].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid User ID!</b> Please provide numeric ID.")
    
    if target_id in Config.ADMIN:
        return await message.reply_text("❌ <b>Cannot ban a Bot Administrator!</b>")
    
    await db.ban_user(target_id)
    await message.reply_text(
        f"🚫 <b>User Banned!</b>\n\n"
        f"User ID <code>{target_id}</code> is blocked from using the bot.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("unban") & filters.user(Config.ADMIN))
async def unban_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/unban &lt;user_id&gt;</code>")
    try:
        target_id = int(args[1].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid User ID!</b> Please provide numeric ID.")
    
    await db.unban_user(target_id)
    await message.reply_text(
        f"✅ <b>User Unbanned!</b>\n\n"
        f"User ID <code>{target_id}</code> has been unbanned.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("set_global_meta") & filters.user(Config.ADMIN))
async def set_global_meta_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/set_global_meta &lt;tag_text&gt;</code>\n\n"
            "<i>Example:</i> <code>/set_global_meta Encoded By @Nex_bots</code>"
        )
    tag = args[1].strip()
    await db.set_default_metadata(tag)
    await message.reply_text(
        f"🏷️ <b>Global Default Metadata Updated!</b>\n\n"
        f"<b>New Tag:</b> <code>{tag}</code>\n\n"
        f"<i>This tag will be used for all files unless an individual user sets their own tag.</i>\n\n"
        f"⚡ @Nex_bots"
    )


# ==================== INTERACTIVE OWNER CALLBACK HANDLERS ====================

@Client.on_callback_query(filters.regex(r"^owner_panel$"))
async def owner_panel_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_toggle_mode$"))
async def cb_owner_toggle_mode(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    curr = await db.get_bot_mode()
    new_mode = "public" if curr == "private" else "private"
    await db.set_bot_mode(new_mode)
    await query.answer(f"Bot Mode switched to {new_mode.upper()}! 🌐", show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_owner_auth$"))
async def cb_owner_auth(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    users = await db.get_auth_users()
    users_preview = ", ".join(map(str, users[:10])) if users else "None"
    if len(users) > 10:
        users_preview += f" (+{len(users)-10} more)"
    
    text = (
        "🛡️ <b><u>Authorized Users (Private Mode)</u></b>\n\n"
        f"• <b>Active Count:</b> <code>{len(users)}</code>\n"
        f"• <b>IDs:</b> <code>{users_preview}</code>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/add_user &lt;id&gt;</code> - Grant access\n"
        "• <code>/rem_user &lt;id&gt;</code> - Revoke access\n"
        "• <code>/auth_list</code> - View full list\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]])
    await edit_message_content(query.message, text, reply_markup=btn)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_prem$"))
async def cb_owner_prem(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    users = await db.get_premium_users()
    users_preview = ", ".join(map(str, users[:10])) if users else "None"
    if len(users) > 10:
        users_preview += f" (+{len(users)-10} more)"
    
    text = (
        "💎 <b><u>4GB Premium Users Management</u></b>\n\n"
        f"• <b>Premium Count:</b> <code>{len(users)}</code>\n"
        f"• <b>IDs:</b> <code>{users_preview}</code>\n\n"
        "<i>Premium users get 4GB uploads & priority queue in Public Mode!</i>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/add_prem &lt;id&gt;</code> - Grant 4GB access\n"
        "• <code>/rem_prem &lt;id&gt;</code> - Revoke 4GB access\n"
        "• <code>/prem_list</code> - View full list\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]])
    await edit_message_content(query.message, text, reply_markup=btn)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_banned$"))
async def cb_owner_banned(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    users = await db.get_banned_users()
    users_preview = ", ".join(map(str, users[:10])) if users else "None"
    if len(users) > 10:
        users_preview += f" (+{len(users)-10} more)"
    
    text = (
        "🚫 <b><u>Banned Users Management</u></b>\n\n"
        f"• <b>Banned Count:</b> <code>{len(users)}</code>\n"
        f"• <b>IDs:</b> <code>{users_preview}</code>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/ban &lt;id&gt;</code> - Ban user from bot\n"
        "• <code>/unban &lt;id&gt;</code> - Unban user\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]])
    await edit_message_content(query.message, text, reply_markup=btn)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_meta$"))
async def cb_owner_meta(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    default_meta = await db.get_default_metadata()
    text = (
        "🏷️ <b><u>Global Bot Metadata Tag</u></b>\n\n"
        f"• <b>Current Global Tag:</b> <code>{default_meta}</code>\n\n"
        "<b>Commands to manage:</b>\n"
        "• <code>/set_global_meta &lt;tag&gt;</code> - Update bot default\n"
        "• <code>/set_metadata &lt;tag&gt;</code> - Update personal tag\n"
        "• <code>/toggle_metadata</code> - Toggle your metadata\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]])
    await edit_message_content(query.message, text, reply_markup=btn)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_channels$"))
async def cb_owner_channels(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    owner_dump = await db.get_dump_channel(query.from_user.id)
    text = (
        "📦 <b><u>Channels & ForceSub Configuration</u></b>\n\n"
        f"• <b>Log Channel:</b> <code>{Config.LOG_CHANNEL or 'Disabled'}</code>\n"
        f"• <b>Files Backup Channel:</b> <code>{Config.FILES_CHANNEL or 'Disabled'}</code>\n"
        f"• <b>ForceSub Channel:</b> <code>{Config.FORCE_SUB or 'Disabled'}</code>\n"
        f"• <b>Your Private Dump:</b> <code>{owner_dump or 'None'}</code>\n\n"
        "<b>Command:</b> <code>/set_dump &lt;channel_id&gt;</code>\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]])
    await edit_message_content(query.message, text, reply_markup=btn)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_stats$"))
async def cb_owner_stats(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    uptime = time.strftime("%Hh %Mm %Ss", time.gmtime(time.time() - client.uptime))
    total_users = await db.total_users_count()
    total_disk, used_disk, free_disk = shutil.disk_usage(".")
    cpu = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory().percent
    
    stats_msg = (
        f"⚡ NeX Live Stats ⚡\n"
        f"⏱️ Uptime: {uptime}\n"
        f"👥 Users: {total_users}\n"
        f"🖥️ CPU: {cpu}% | ❖ RAM: {ram}%\n"
        f"💿 Free: {get_readable_file_size(free_disk)}"
    )
    await query.answer(stats_msg, show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^clear_cache_owner$"))
async def clear_cache_owner_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    downloads_dir = "downloads"
    deleted_files = 0
    deleted_size = 0

    if os.path.exists(downloads_dir):
        for root, dirs, files in os.walk(downloads_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    deleted_size += os.path.getsize(file_path)
                    os.remove(file_path)
                    deleted_files += 1
                except Exception:
                    pass
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                except Exception:
                    pass

    freed = get_readable_file_size(deleted_size)
    await query.answer(f"🧹 Cache Cleared!\nDeleted: {deleted_files} files\nFreed: {freed}", show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_owner_restart$"))
async def cb_owner_restart(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    await query.answer("🔄 Restarting NeX Engine...", show_alert=True)
    try:
        await edit_message_content(query.message, "<b>🔄 Restarting NeX 4GB Rename Bot Engine.....</b>\n\n⚡ @Nex_bots")
    except Exception:
        pass
    os.execl(sys.executable, sys.executable, *sys.argv)


# ==================== LEGACY STATS & RESTART HANDLERS ====================

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
