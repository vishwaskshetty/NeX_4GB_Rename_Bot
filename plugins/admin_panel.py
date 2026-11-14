import os
import sys
import time
import shutil
import psutil
import asyncio
import logging
import random
import string
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, BotCommandScopeChat
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

from config import Config
from helper.database import db, TIER_NAMES, format_user_time
from helper.utils import get_readable_file_size, humanbytes, edit_message_content, sanitize_secrets, calc_plan_prices

# NeX 4GB Rename Bot - 100% Button-Driven Owner Control Panel, Wizards & Broadcast Engine
# Developed by @Nex_bots

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_DB_TIMEOUT = 5

async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except Exception:
        return default

# Broadcast message cache: admin_id -> replied Message
BROADCAST_CACHE = {}

# Owner interactive wizard state: admin_id -> state dict
OWNER_STATE = {}


async def send_security_alert(client: Client, user, action_desc: str):
    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
        try:
            alert_msg = (
                "🚨 <b>SECURITY ALERT: Unauthorized Owner Access Attempt!</b>\n\n"
                f"👤 <b>User :</b> {user.mention} (<code>{user.id}</code>)\n"
                f"🏷 <b>Username :</b> @{user.username or 'No Username'}\n"
                f"⚠️ <b>Action :</b> <code>{action_desc}</code>\n"
                f"⏰ <b>Time :</b> <code>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                "⚡ @Nex_bots"
            )
            await client.send_message(Config.LOG_CHANNEL, sanitize_secrets(alert_msg))
        except Exception:
            pass


ADMIN_COMMANDS = [
    "owner", "admin", "mode", "maintenance", "status", "users", "broadcast", "bcast_btn",
    "add_prem", "rem_prem", "prem_list", "add_user", "rem_user", "auth_list",
    "ban", "unban", "ban_list", "add_coupon", "del_coupon", "coupons",
    "set_fsub", "fsub", "set_global_meta", "set_upi", "restart", "logs", "health"
]


@Client.on_message(filters.private & filters.command(ADMIN_COMMANDS) & ~filters.user(Config.ADMIN), group=1)
async def unauthorized_owner_cmd(client, message):
    user = message.from_user
    await message.reply_text(
        "🚨 <b>SECURITY ALERT: Unauthorized Access!</b>\n\n"
        "This command is strictly restricted to the Bot Owner. Your attempt has been logged."
    )
    await send_security_alert(client, user, f"Command: {message.text}")


@Client.on_callback_query(filters.regex(r"^(cb_owner_|owner_|clear_cache_owner|cb_prem_page_|cb_prem_wiz_|cb_pwiz_|cb_cwiz_|cb_oref_|cb_oprice_|cb_otrial_|cb_oquota_|cb_otoggle_|cb_opay_)") & ~filters.user(Config.ADMIN), group=1)
async def unauthorized_owner_cb(client, query: CallbackQuery):
    await query.answer("🚨 SECURITY ALERT: Unauthorized Access! This action has been logged.", show_alert=True)
    await send_security_alert(client, query.from_user, f"Callback: {query.data}")


# ==================== LIVE OWNER DASHBOARD BUILDER ====================

async def build_owner_panel(client: Client):
    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    mode_str = "🔒 Private" if bot_mode == "private" else "🌍 Public"
    
    maint_on = await _safe(db.get_maintenance(), default=False)
    maint_str = "ON 🔴" if maint_on else "OFF 🟢"

    protect_on = await _safe(db.get_protect_content(), default=False)
    protect_str = "ON 🔒" if protect_on else "OFF 🔓"

    fsub = await _safe(db.get_fsub_settings(), default={"channel": Config.FORCE_SUB, "mode": "normal", "enabled": bool(Config.FORCE_SUB)})
    fsub_mode_str = "Request 🔒" if fsub.get("mode") == "request" else "Normal 🌐"
    
    has_4gb = bool(getattr(client, "app_4gb", None))
    engine_str = "Active 🟢 (4GB Session)" if has_4gb else "Inactive 🔴 (2GB Mode)"
    
    total_users = await _safe(db.total_users_count(), default=0)
    auth_users  = await _safe(db.get_auth_users(),    default=[])
    banned_users = await _safe(db.get_banned_users(), default=[])
    coupons     = await _safe(db.get_all_coupons(),    default={})
    default_meta = await _safe(db.get_default_metadata(), default="Telegram : @Nex_bots")
    upi_id      = await _safe(db.get_upi_id(), default=getattr(Config, "UPI_ID", "nexbots@upi"))
    usage_stats = await _safe(db.get_global_usage(), default={})
    rename_stats = await _safe(db.get_global_rename_stats(), default={})

    total_disk, used_disk, free_disk = shutil.disk_usage(".")
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent

    total_prem = usage_stats.get("total_premium", 0)
    silver_cnt = usage_stats.get("silver_users", 0)
    gold_cnt   = usage_stats.get("gold_users", 0)
    diam_cnt   = usage_stats.get("diamond_users", 0)
    trials_cnt = usage_stats.get("trials_claimed", 0)
    tot_files  = rename_stats.get("total_files") or usage_stats.get("global_files", 0)
    tot_bytes  = rename_stats.get("total_bytes") or usage_stats.get("global_bytes", 0)
    today_files = rename_stats.get("today_files", 0)
    today_bytes = rename_stats.get("today_bytes", 0)

    text = (
        "<b>◈ 👑 <b>NeX Owner Control Panel</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>🌐 Mode :</b> <code>{mode_str}</code> | <b>🛠️ Maint :</b> <code>{maint_str}</code>\n"
        f"◈ <b>🛡️ Lock :</b> <code>{protect_str}</code> | <b>📢 FSub :</b> <code>{fsub_mode_str}</code>\n"
        f"◈ <b>🚀 4GB Client :</b> <code>{engine_str}</code>\n"
        f"◈ <b>💳 Active UPI :</b> <code>{upi_id}</code>\n\n"
        f"◈ <b>👥 Total Users :</b> <code>{total_users}</code> | <b>Trials :</b> <code>{trials_cnt}</code>\n"
        f"◈ <b>💎 Premium :</b> <code>{total_prem}</code> (🥈{silver_cnt} 🥇{gold_cnt} 💎{diam_cnt})\n"
        f"◈ <b>🛡️ Auth :</b> <code>{len(auth_users)}</code> | <b>🚫 Ban :</b> <code>{len(banned_users)}</code> | <b>🎟️ Coupons :</b> <code>{len(coupons)}</code>\n\n"
        f"◈ <b>📁 Renamed :</b> <code>{tot_files}</code> (Today: <code>{today_files}</code>)\n"
        f"◈ <b>📊 Bandwidth :</b> <code>{humanbytes(tot_bytes)}</code> (Today: <code>{humanbytes(today_bytes)}</code>)\n"
        f"◈ <b>🖥️ RAM :</b> <code>{ram}%</code> | <b>CPU :</b> <code>{cpu}%</code> | <b>Disk :</b> <code>{get_readable_file_size(free_disk)}</code>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"🌐 Mode: {mode_str}", callback_data="cb_owner_toggle_mode"),
            InlineKeyboardButton(f"🛠️ Maint: {maint_str}", callback_data="cb_owner_toggle_maint")
        ],
        [
            InlineKeyboardButton("💎 Pricing Editor", callback_data="cb_owner_pricing"),
            InlineKeyboardButton("🎁 Free Trial Config", callback_data="cb_owner_trial_cfg")
        ],
        [
            InlineKeyboardButton("⚡ Quota & Workers", callback_data="cb_owner_quota_cfg"),
            InlineKeyboardButton("⚙️ Feature Toggles", callback_data="cb_owner_toggles")
        ],
        [
            InlineKeyboardButton("💳 Payment & QR", callback_data="cb_owner_payment_cfg"),
            InlineKeyboardButton("📢 FSub Channel", callback_data="cb_owner_fsub")
        ],
        [
            InlineKeyboardButton(f"💎 Premium ({total_prem})", callback_data="cb_prem_page_0"),
            InlineKeyboardButton(f"🛡️ Auth Users ({len(auth_users)})", callback_data="cb_owner_auth")
        ],
        [
            InlineKeyboardButton(f"🎟️ Coupons ({len(coupons)})", callback_data="cb_owner_coupons"),
            InlineKeyboardButton(f"🚫 Banned ({len(banned_users)})", callback_data="cb_owner_banned")
        ],
        [
            InlineKeyboardButton("🩺 Health Diagnostic", callback_data="cb_owner_health"),
            InlineKeyboardButton("📊 Server Stats", callback_data="cb_owner_stats")
        ],
        [
            InlineKeyboardButton("📜 Activity Logs", callback_data="cb_owner_logs"),
            InlineKeyboardButton("📈 Analytics", callback_data="cb_owner_analytics")
        ],
        [
            InlineKeyboardButton("🧹 Clear Stuck Tasks", callback_data="cb_owner_reset_stuck"),
            InlineKeyboardButton("🔄 Restart Bot", callback_data="cb_owner_restart")
        ],
        [
            InlineKeyboardButton("📋 Commands List", callback_data="cb_owner_cmds"),
            InlineKeyboardButton("📦 Dumps & Channels", callback_data="cb_owner_channels")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Start", callback_data="start"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ==================== ACTIVITY LOGS BUILDER ====================

async def build_activity_logs_view():
    logs = await db.get_activity_logs(15)
    text = (
        "<b>◈ 📜 <b>Live Activity Logs (Latest 15)</b></b>\n"
        "───────────────\n\n"
    )
    if not logs:
        text += "<i>No activity logged yet.</i>\n\n"
    else:
        for item in logs:
            t_str = datetime.datetime.fromtimestamp(item.get("timestamp", time.time())).strftime("%H:%M:%S")
            uid = item.get("user_id", "N/A")
            uname = (item.get("user_name") or "User")[:10]
            action = item.get("action", "action")
            details = (item.get("details") or "")[:25]
            text += f"• <code>[{t_str}]</code> <b>{uname}</b> (<code>{uid}</code>)\n  ↳ <b>{action}</b>: <i>{details}</i>\n"
        text += "\n"

    text += "⚡ @Nex_bots"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Logs", callback_data="cb_owner_logs"),
         InlineKeyboardButton("🗑️ Clear Logs", callback_data="cb_owner_clear_logs")],
        [InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


# ==================== OWNER COMMAND HANDLERS ====================

@Client.on_message(filters.private & filters.command(["owner", "admin"]) & filters.user(Config.ADMIN))
async def owner_panel_cmd(client, message):
    try:
        from bot import ALL_OWNER_COMMANDS
        asyncio.create_task(client.set_bot_commands(ALL_OWNER_COMMANDS, scope=BotCommandScopeChat(chat_id=message.from_user.id)))
    except Exception:
        pass
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
        f"🛡️ <b>User Authorized!</b>\n\n"
        f"User <code>{target_id}</code> can now use the bot in Private Mode.\n\n"
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
        f"User <code>{target_id}</code> is no longer authorized.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["auth_list", "users_list"]) & filters.user(Config.ADMIN))
async def auth_list_cmd(client, message):
    users = await db.get_auth_users()
    if not users:
        return await message.reply_text("🛡️ <b>Authorized Users:</b> None (Admins always have access).")
    formatted = "\n".join([f"• <code>{uid}</code>" for uid in users])
    await message.reply_text(f"🛡️ <b><u>Authorized Users ({len(users)})</u></b>\n\n{formatted}\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command("users") & filters.user(Config.ADMIN))
async def total_users_cmd(client, message):
    total = await _safe(db.total_users_count(), default=0)
    auth_cnt = len(await _safe(db.get_auth_users(), default=[]))
    ban_cnt = len(await _safe(db.get_banned_users(), default=[]))
    prem_stats = await _safe(db.get_global_usage(), default={})
    prem_cnt = prem_stats.get("total_premium", 0)
    
    text = (
        "<b>◈ 👥 <b>NeX Registered Bot Users</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Total Registered Users :</b> <code>{total}</code>\n"
        f"◈ <b>Active 4GB Premium Users :</b> <code>{prem_cnt}</code>\n"
        f"◈ <b>Authorized Users (Private) :</b> <code>{auth_cnt}</code>\n"
        f"◈ <b>Banned / Blocked Users :</b> <code>{ban_cnt}</code>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command(["add_prem", "set_prem"]) & filters.user(Config.ADMIN))
async def add_prem_cmd(client, message):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/add_prem &lt;user_id&gt; [tier 1-3] [days]</code>\n\n"
            "<i>Examples:</i>\n"
            "• <code>/add_prem 123456789</code> (Tier 3 Diamond, 30 days)\n"
            "• <code>/add_prem 123456789 2 60</code> (Tier 2 Gold, 60 days)\n\n"
            "⚡ @Nex_bots"
        )
    try:
        target_id = int(args[1].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid User ID!</b> Please provide numeric ID.")

    tier = int(args[2].strip()) if len(args) > 2 and args[2].isdigit() else 3
    tier = max(1, min(3, tier))
    days = int(args[3].strip()) if len(args) > 3 and args[3].isdigit() else 30

    new_expiry = await db.set_user_premium(target_id, tier=tier, days=days)
    plan_name = TIER_NAMES.get(tier, f"Tier {tier}")
    expiry_str = format_user_time(new_expiry)

    await db.log_activity(message.from_user.id, "Owner", "admin_add_prem", f"User {target_id} -> {plan_name} ({days}D)")

    await message.reply_text(
        f"💎 <b>Premium Granted Successfully!</b>\n\n"
        f"◈ <b>User ID :</b> <code>{target_id}</code>\n"
        f"◈ <b>Level :</b> <b>{plan_name}</b>\n"
        f"◈ <b>Duration :</b> <code>{days} Days</code>\n"
        f"◈ <b>Expiry :</b> <code>{expiry_str}</code>\n\n"
        f"⚡ @Nex_bots"
    )

    try:
        await client.send_message(
            chat_id=target_id,
            text=(
                f"🎉 <b>Premium Activated by Owner!</b> ⚡\n\n"
                f"◈ <b>Plan :</b> <b>{plan_name}</b> (4GB Access)\n"
                f"◈ <b>Duration :</b> <code>{days} Days</code>\n"
                f"◈ <b>Expiry :</b> <code>{expiry_str}</code>\n\n"
                f"Enjoy high-speed renaming! Powered by @Nex_bots"
            )
        )
    except Exception:
        pass


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
    await db.log_activity(message.from_user.id, "Owner", "admin_rem_prem", f"User {target_id} -> Free")
    await message.reply_text(
        f"🗑️ <b>Premium Access Revoked!</b>\n\n"
        f"User <code>{target_id}</code> reverted to Free Tier.\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("prem_list") & filters.user(Config.ADMIN))
async def prem_list_cmd(client, message):
    users = await db.get_all_premium_users()
    if not users:
        return await message.reply_text("💎 <b>Active Premium Users:</b> None (Admins always have 4GB access).")
    
    lines = []
    for u in users:
        exp = format_user_time(u['expiry'])
        lines.append(f"• <code>{u['user_id']}</code> | {u['plan_name']} | <code>{exp}</code>")
    
    formatted = "\n".join(lines[:20])
    if len(lines) > 20:
        formatted += f"\n<i>...and {len(lines)-20} more (use /owner for pagination).</i>"

    await message.reply_text(f"💎 <b><u>Active Premium Users ({len(users)})</u></b>\n\n{formatted}\n\n⚡ @Nex_bots")


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
        f"User <code>{target_id}</code> is blocked from using the bot.\n\n"
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
    await message.reply_text(f"✅ <b>User Unbanned!</b> <code>{target_id}</code>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command("ban_list") & filters.user(Config.ADMIN))
async def ban_list_cmd(client, message):
    banned = await _safe(db.get_banned_users(), default=[])
    if not banned:
        return await message.reply_text("✅ <b>No users are currently banned from NeX Bot!</b>\n\n⚡ @Nex_bots")
    
    text = (
        "<b>◈ 🚫 <b>Banned Users Directory</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Total Banned Users :</b> <code>{len(banned)}</code>\n\n"
    )
    for idx, uid in enumerate(banned[:30], 1):
        text += f"{idx}. <code>{uid}</code>\n"
    if len(banned) > 30:
        text += f"\n<i>... and {len(banned) - 30} more users.</i>\n"
    text += "\n<i>To unban: <code>/unban &lt;user_id&gt;</code></i>\n⚡ @Nex_bots"
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("set_global_meta") & filters.user(Config.ADMIN))
async def set_global_meta_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/set_global_meta &lt;tag_text&gt;</code>")
    tag = args[1].strip()
    await db.set_default_metadata(tag)
    await message.reply_text(f"🏷️ <b>Global Metadata Updated:</b> <code>{tag}</code>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command("set_upi") & filters.user(Config.ADMIN))
async def set_upi_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/set_upi &lt;your_upi_id&gt;</code>\n\n<i>Example:</i> <code>/set_upi myname@okaxis</code>")
    upi_id = args[1].strip()
    await db.set_upi_id(upi_id)
    await message.reply_text(f"💳 <b>UPI ID Updated!</b>\n\nActive UPI: <code>{upi_id}</code>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command(["add_coupon", "set_coupon"]) & filters.user(Config.ADMIN))
async def add_coupon_cmd(client, message):
    args = message.text.split()
    if len(args) < 5:
        return await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/add_coupon &lt;code&gt; &lt;tier 1-3&gt; &lt;days&gt; &lt;max_uses&gt;</code>\n\n"
            "<i>Example:</i> <code>/add_coupon NEXGOLD 2 30 10</code>\n\n"
            "⚡ @Nex_bots"
        )
    code = args[1].strip().upper()
    try:
        tier = max(1, min(3, int(args[2].strip())))
        days = int(args[3].strip())
        max_uses = int(args[4].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid Numbers!</b> Tier, days, and max_uses must be integers.")

    await db.create_coupon(code, tier=tier, days=days, max_uses=max_uses)
    plan_name = TIER_NAMES.get(tier, f"Level {tier}")
    await message.reply_text(
        f"🎟️ <b>Coupon Created Successfully!</b>\n\n"
        f"◈ <b>Code :</b> <code>{code}</code>\n"
        f"◈ <b>Plan :</b> {plan_name}\n"
        f"◈ <b>Duration :</b> <code>{days} Days</code>\n"
        f"◈ <b>Max Uses :</b> <code>{max_uses}</code>\n\n"
        f"Users can redeem via <code>/redeem {code}</code>!\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["del_coupon", "rem_coupon"]) & filters.user(Config.ADMIN))
async def del_coupon_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/del_coupon &lt;code&gt;</code>")
    code = args[1].strip().upper()
    await db.delete_coupon(code)
    await message.reply_text(f"🗑️ <b>Coupon Deleted:</b> <code>{code}</code>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command("coupons") & filters.user(Config.ADMIN))
async def coupons_cmd(client, message):
    coupons = await db.get_all_coupons()
    if not coupons:
        return await message.reply_text("🎟️ <b>Active Coupons:</b> None created yet.\n\nUse <code>/owner</code> to create one via wizard.")
    
    lines = []
    for c_code, c in coupons.items():
        pname = TIER_NAMES.get(c.get('tier', 1), 'Premium')
        lines.append(f"• <code>{c_code}</code> | {pname} | {c.get('days')}d | Used: {c.get('used_count', 0)}/{c.get('max_uses', 1)}")
    
    await message.reply_text(f"🎟️ <b><u>Active Coupons ({len(coupons)})</u></b>\n\n" + "\n".join(lines) + "\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command("logs") & filters.user(Config.ADMIN))
async def logs_cmd(client, message):
    text, markup = await build_activity_logs_view()
    await message.reply_text(text, reply_markup=markup)


# ==================== INTERACTIVE OWNER CALLBACKS & WIZARDS ====================

@Client.on_callback_query(filters.regex(r"^owner_panel$"))
async def owner_panel_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    OWNER_STATE.pop(query.from_user.id, None)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_toggle_mode$"))
async def cb_owner_toggle_mode(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    curr = await _safe(db.get_bot_mode(), default="private")
    new_mode = "public" if curr == "private" else "private"
    await _safe(db.set_bot_mode(new_mode))
    await query.answer(f"Bot Mode: {new_mode.upper()}! 🌐", show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


# ==================== INTERACTIVE PREMIUM MANAGER ====================

@Client.on_callback_query(filters.regex(r"^cb_prem_page_(\d+)$"))
async def cb_prem_page(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    page = int(query.matches[0].group(1))
    users = await db.get_all_premium_users()
    page_size = 4
    total_pages = max(1, (len(users) + page_size - 1) // page_size)
    page = min(page, total_pages - 1)

    start_idx = page * page_size
    current_users = users[start_idx:start_idx + page_size]

    text = (
        f"💎 <b><u>Active Premium Users</u></b> (Page {page+1}/{total_pages})\n\n"
        f"• <b>Total Active:</b> <code>{len(users)}</code>\n\n"
    )
    if not current_users:
        text += "<i>No active premium users currently.</i>\n\n"
    else:
        for u in current_users:
            exp_str = format_user_time(u['expiry'])
            text += f"◈ <code>{u['user_id']}</code> | {u['plan_name']}\n  Exp: <code>{exp_str}</code>\n\n"

    text += "⚡ @Nex_bots"

    buttons = []
    # Quick action rows per user
    for u in current_users:
        uid = u['user_id']
        buttons.append([
            InlineKeyboardButton(f"⬆️ Diamond", callback_data=f"cb_upgrade_prem_{uid}_{page}"),
            InlineKeyboardButton(f"➕ +30D", callback_data=f"cb_extend_prem_{uid}_30_{page}"),
            InlineKeyboardButton(f"➕ +90D", callback_data=f"cb_extend_prem_{uid}_90_{page}"),
            InlineKeyboardButton(f"❌ Revoke", callback_data=f"cb_revoke_prem_{uid}_{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cb_prem_page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"cb_prem_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("➕ Add Premium User (Wizard)", callback_data="cb_prem_wiz_start")
    ])
    buttons.append([
        InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    await edit_message_content(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_revoke_prem_(\d+)_(\d+)$"))
async def cb_revoke_prem(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    target_id = int(query.matches[0].group(1))
    page = int(query.matches[0].group(2))
    await db.remove_premium_user(target_id)
    await db.log_activity(query.from_user.id, "Owner", "admin_revoke", f"User {target_id}")
    await query.answer(f"Revoked premium for {target_id}!", show_alert=True)
    query.matches = [type("MockMatch", (), {"group": lambda s, idx: page})()]
    await cb_prem_page(client, query)


@Client.on_callback_query(filters.regex(r"^cb_upgrade_prem_(\d+)_(\d+)$"))
async def cb_upgrade_prem(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    target_id = int(query.matches[0].group(1))
    page = int(query.matches[0].group(2))
    await db.upgrade_user_tier(target_id, 3)
    await db.log_activity(query.from_user.id, "Owner", "admin_upgrade", f"User {target_id} -> Diamond")
    await query.answer(f"Upgraded {target_id} to Diamond VIP!", show_alert=True)
    query.matches = [type("MockMatch", (), {"group": lambda s, idx: page})()]
    await cb_prem_page(client, query)


@Client.on_callback_query(filters.regex(r"^cb_extend_prem_(\d+)_(\d+)_(\d+)$"))
async def cb_extend_prem(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    target_id = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    page = int(query.matches[0].group(3))
    new_exp = await db.extend_premium_days(target_id, days)
    await db.log_activity(query.from_user.id, "Owner", "admin_extend", f"User {target_id} +{days}D")
    await query.answer(f"Extended {target_id} by {days} days!", show_alert=True)
    query.matches = [type("MockMatch", (), {"group": lambda s, idx: page})()]
    await cb_prem_page(client, query)


# ➕ Add Premium User Wizard
@Client.on_callback_query(filters.regex(r"^cb_prem_wiz_start$"))
async def cb_prem_wiz_start(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    OWNER_STATE[query.from_user.id] = {"action": "prem_uid"}
    text = (
        "💎 <b><u>Add Premium User Wizard (Step 1/3)</u></b>\n\n"
        "Please send the <b>Telegram User ID</b> of the user you want to upgrade:\n\n"
        "<i>Or tap Cancel below to exit.</i>"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_pwiz_tier_(\d+)$"))
async def cb_pwiz_tier_choice(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    tier = int(query.matches[0].group(1))
    state = OWNER_STATE.get(query.from_user.id, {})
    state["tier"] = tier
    target_id = state.get("target_id", "N/A")
    tier_name = TIER_NAMES.get(tier, f"Tier {tier}")

    text = (
        "📅 <b><u>Add Premium User Wizard (Step 3/3)</u></b>\n\n"
        f"◈ <b>Target User ID :</b> <code>{target_id}</code>\n"
        f"◈ <b>Selected Tier :</b> <b>{tier_name}</b>\n\n"
        "Select the <b>duration</b> to grant:\n"
        "<i>(Minimum 1 Month — NO weekly options)</i>"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 1 Month (30D)", callback_data="cb_pwiz_dur_30"),
            InlineKeyboardButton("📅 3 Months (90D)", callback_data="cb_pwiz_dur_90")
        ],
        [
            InlineKeyboardButton("📅 6 Months (180D)", callback_data="cb_pwiz_dur_180"),
            InlineKeyboardButton("📅 1 Year (365D)", callback_data="cb_pwiz_dur_365")
        ],
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_pwiz_dur_(\d+)$"))
async def cb_pwiz_dur_choice(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    days = int(query.matches[0].group(1))
    state = OWNER_STATE.pop(query.from_user.id, {})
    target_id = state.get("target_id")
    tier = state.get("tier", 3)

    if not target_id:
        return await query.answer("❌ Wizard session expired! Please start over.", show_alert=True)

    new_exp = await db.set_user_premium(target_id, tier=tier, days=days)
    plan_name = TIER_NAMES.get(tier, f"Tier {tier}")
    exp_str = format_user_time(new_exp)

    await db.log_activity(query.from_user.id, "Owner", "wizard_add_prem", f"User {target_id} -> {plan_name} ({days}D)")

    text = (
        "🎉 <b><u>Premium Granted Successfully!</u></b> ⚡\n\n"
        f"◈ <b>User ID :</b> <code>{target_id}</code>\n"
        f"◈ <b>Plan Level :</b> <b>{plan_name}</b>\n"
        f"◈ <b>Duration :</b> <code>{days} Days</code>\n"
        f"◈ <b>Valid Until :</b> <code>{exp_str}</code>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Premium Users List", callback_data="cb_prem_page_0"),
         InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer("Premium Granted! ✅", show_alert=True)

    try:
        await client.send_message(
            chat_id=target_id,
            text=(
                f"🎉 <b>Premium Activated by Bot Owner!</b> ⚡\n\n"
                f"◈ <b>Plan :</b> <b>{plan_name}</b> (4GB Access)\n"
                f"◈ <b>Duration :</b> <code>{days} Days</code>\n"
                f"◈ <b>Expiry :</b> <code>{exp_str}</code>\n\n"
                f"Enjoy high-speed renaming! Powered by @Nex_bots"
            )
        )
    except Exception:
        pass


# ==================== INTERACTIVE COUPON BUILDER WIZARD ====================

@Client.on_callback_query(filters.regex(r"^cb_owner_coupons$"))
async def cb_owner_coupons(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    coupons = await _safe(db.get_all_coupons(), default={})
    text = (
        "<b>◈ 🎟️ <b>NeX Coupon Manager</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Active Coupons :</b> <code>{len(coupons)}</code>\n\n"
    )
    if not coupons:
        text += "<i>No active coupons. Tap 'Create New Coupon' to start!</i>\n\n"
    else:
        for code, c in list(coupons.items())[:6]:
            pname = TIER_NAMES.get(c.get('tier', 1), 'Premium')
            text += f"• <code>{code}</code> | {pname} ({c.get('days')}d) | Used: <code>{c.get('used_count', 0)}/{c.get('max_uses', 1)}</code>\n"
        text += "\n"

    text += "⚡ @Nex_bots"

    buttons = []
    # One-click delete for existing coupons
    for code in list(coupons.keys())[:4]:
        buttons.append([InlineKeyboardButton(f"🗑️ Delete {code}", callback_data=f"cb_del_coupon_{code}")])

    buttons.append([InlineKeyboardButton("➕ Create New Coupon (Wizard)", callback_data="cb_coupon_wiz_start")])
    buttons.append([
        InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    await edit_message_content(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_coupon_wiz_start$"))
async def cb_coupon_wiz_start(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    text = (
        "🎟️ <b><u>Coupon Builder (Step 1/4)</u></b>\n\n"
        "Select the <b>Premium Tier</b> this coupon will grant:"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🥈 Silver Tier", callback_data="cb_cwiz_tier_1"),
            InlineKeyboardButton("🥇 Gold Tier", callback_data="cb_cwiz_tier_2")
        ],
        [InlineKeyboardButton("💎 Diamond VIP Tier", callback_data="cb_cwiz_tier_3")],
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_cwiz_tier_(\d+)$"))
async def cb_cwiz_tier_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    tier = int(query.matches[0].group(1))
    text = (
        "📅 <b><u>Coupon Builder (Step 2/4)</u></b>\n\n"
        f"Tier: <b>{TIER_NAMES.get(tier, 'Premium')}</b>\n"
        "Select the <b>duration</b> for this coupon:"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 3 Days (Promo)", callback_data=f"cb_cwiz_dur_{tier}_3"),
            InlineKeyboardButton("📅 1 Month (30D)", callback_data=f"cb_cwiz_dur_{tier}_30")
        ],
        [
            InlineKeyboardButton("📅 3 Months (90D)", callback_data=f"cb_cwiz_dur_{tier}_90"),
            InlineKeyboardButton("📅 1 Year (365D)", callback_data=f"cb_cwiz_dur_{tier}_365")
        ],
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_cwiz_dur_(\d+)_(\d+)$"))
async def cb_cwiz_dur_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))

    text = (
        "👥 <b><u>Coupon Builder (Step 3/4)</u></b>\n\n"
        f"Tier: <b>{TIER_NAMES.get(tier, 'Premium')}</b> | Duration: <code>{days} Days</code>\n"
        "Select <b>Maximum Redemptions (Uses)</b>:"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 Use", callback_data=f"cb_cwiz_uses_{tier}_{days}_1"),
            InlineKeyboardButton("5 Uses", callback_data=f"cb_cwiz_uses_{tier}_{days}_5"),
            InlineKeyboardButton("10 Uses", callback_data=f"cb_cwiz_uses_{tier}_{days}_10")
        ],
        [
            InlineKeyboardButton("25 Uses", callback_data=f"cb_cwiz_uses_{tier}_{days}_25"),
            InlineKeyboardButton("50 Uses", callback_data=f"cb_cwiz_uses_{tier}_{days}_50"),
            InlineKeyboardButton("100 Uses", callback_data=f"cb_cwiz_uses_{tier}_{days}_100")
        ],
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_cwiz_uses_(\d+)_(\d+)_(\d+)$"))
async def cb_cwiz_uses_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    uses = int(query.matches[0].group(3))

    text = (
        "🏷️ <b><u>Coupon Builder (Step 4/4)</u></b>\n\n"
        f"Tier: <b>{TIER_NAMES.get(tier, 'Premium')}</b>\n"
        f"Duration: <code>{days} Days</code> | Max Uses: <code>{uses}</code>\n\n"
        "Choose how to generate the coupon code:"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Auto-Generate Random Code", callback_data=f"cb_cwiz_auto_{tier}_{days}_{uses}")],
        [InlineKeyboardButton("✏️ Enter Custom Code", callback_data=f"cb_cwiz_custom_{tier}_{days}_{uses}")],
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_cwiz_auto_(\d+)_(\d+)_(\d+)$"))
async def cb_cwiz_auto_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    uses = int(query.matches[0].group(3))

    tier_tag = {1: "SILVER", 2: "GOLD", 3: "DIAMOND"}.get(tier, "PREM")
    rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    code = f"NEX_{tier_tag}_{days}D_{rnd}"

    await db.create_coupon(code, tier=tier, days=days, max_uses=uses)
    await db.log_activity(query.from_user.id, "Owner", "create_coupon", f"Code: {code} ({days}D, {uses} uses)")

    pname = TIER_NAMES.get(tier, "Premium")
    text = (
        "🎉 <b><u>Coupon Created Successfully!</u></b> ⚡\n\n"
        f"◈ <b>Coupon Code :</b> <code>{code}</code> (tap to copy)\n"
        f"◈ <b>Plan Level :</b> <b>{pname}</b>\n"
        f"◈ <b>Duration :</b> <code>{days} Days</code>\n"
        f"◈ <b>Max Redemptions :</b> <code>{uses} Uses</code>\n\n"
        f"Users can redeem via: <code>/redeem {code}</code>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Coupons Manager", callback_data="cb_owner_coupons"),
         InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer("Coupon Created! 🎟️", show_alert=True)


@Client.on_callback_query(filters.regex(r"^cb_cwiz_custom_(\d+)_(\d+)_(\d+)$"))
async def cb_cwiz_custom_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    uses = int(query.matches[0].group(3))

    OWNER_STATE[query.from_user.id] = {
        "action": "coupon_custom_code",
        "tier": tier,
        "days": days,
        "uses": uses
    }

    text = (
        "✏️ <b><u>Enter Custom Coupon Code</u></b>\n\n"
        f"Plan: <b>{TIER_NAMES.get(tier, 'Premium')}</b> | <code>{days} Days</code> | <code>{uses} Uses</code>\n\n"
        "Please type the custom coupon code you want to create (e.g. <code>SPECIAL50</code>):\n\n"
        "<i>Or tap Cancel below to exit.</i>"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_del_coupon_(.+)$"))
async def cb_del_coupon(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    code = query.matches[0].group(1)
    await db.delete_coupon(code)
    await db.log_activity(query.from_user.id, "Owner", "delete_coupon", f"Code: {code}")
    await query.answer(f"Coupon {code} deleted!", show_alert=True)
    await cb_owner_coupons(client, query)


# ==================== SINGLE-VALUE PROMPT WIZARDS ====================

@Client.on_callback_query(filters.regex(r"^cb_owner_auth$"))
async def cb_owner_auth(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    users = await _safe(db.get_auth_users(), default=[])
    text = (
        "<b>◈ 🛡️ <b>Authorized Users (Private Mode)</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Total Count :</b> <code>{len(users)}</code>\n\n"
    )
    if users:
        text += "◈ <b>Active IDs :</b>\n" + ", ".join([f"<code>{u}</code>" for u in users[:12]]) + "\n\n"
    else:
        text += "<i>No authorized users. Only Admins can access in Private Mode.</i>\n\n"

    text += "⚡ @Nex_bots"

    buttons = []
    for uid in users[:6]:
        buttons.append([InlineKeyboardButton(f"🗑️ Remove {uid}", callback_data=f"cb_del_auth_{uid}")])

    buttons.append([InlineKeyboardButton("➕ Add Auth User (Prompt)", callback_data="cb_owner_add_auth_wiz")])
    buttons.append([
        InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    await edit_message_content(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_del_auth_(\d+)$"))
async def cb_del_auth_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    target_id = int(query.matches[0].group(1))
    await db.remove_auth_user(target_id)
    await query.answer(f"Removed {target_id} from Auth Users!", show_alert=True)
    await cb_owner_auth(client, query)


@Client.on_callback_query(filters.regex(r"^cb_owner_add_auth_wiz$"))
async def cb_owner_add_auth_wiz(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    OWNER_STATE[query.from_user.id] = {"action": "add_auth"}
    text = "🛡️ <b>Send the Telegram User ID to authorize for Private Mode:</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_cancel_state")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_banned$"))
async def cb_owner_banned(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    users = await _safe(db.get_banned_users(), default=[])
    text = (
        "<b>◈ 🚫 <b>Banned Users Directory</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Total Banned :</b> <code>{len(users)}</code>\n\n"
    )
    if users:
        text += "◈ <b>Banned IDs :</b>\n" + ", ".join([f"<code>{u}</code>" for u in users[:12]]) + "\n\n"
    else:
        text += "<i>No users are currently banned.</i>\n\n"

    text += "⚡ @Nex_bots"

    buttons = []
    for uid in users[:6]:
        buttons.append([InlineKeyboardButton(f"✅ Unban {uid}", callback_data=f"cb_del_ban_{uid}")])

    buttons.append([InlineKeyboardButton("🚫 Ban User (Prompt)", callback_data="cb_owner_ban_wiz")])
    buttons.append([
        InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])
    await edit_message_content(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_del_ban_(\d+)$"))
async def cb_del_ban_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    target_id = int(query.matches[0].group(1))
    await db.unban_user(target_id)
    await query.answer(f"Unbanned {target_id}!", show_alert=True)
    await cb_owner_banned(client, query)


@Client.on_callback_query(filters.regex(r"^cb_owner_ban_wiz$"))
async def cb_owner_ban_wiz(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    OWNER_STATE[query.from_user.id] = {"action": "ban_user"}
    text = "🚫 <b>Send the Telegram User ID to ban from the bot:</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_cancel_state")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_upi_wiz$"))
async def cb_owner_upi_wiz(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    current_upi = await db.get_upi_id()
    OWNER_STATE[query.from_user.id] = {"action": "set_upi"}
    text = (
        "💳 <b><u>Update UPI ID</u></b> ⚡\n\n"
        f"◈ <b>Active UPI ID :</b> <code>{current_upi}</code>\n\n"
        "Please type your new UPI ID (e.g. <code>myname@okaxis</code>):"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_cancel_state")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_meta_wiz$"))
async def cb_owner_meta_wiz(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    current_meta = await db.get_default_metadata()
    OWNER_STATE[query.from_user.id] = {"action": "set_meta"}
    text = (
        "🏷️ <b><u>Update Global Default Metadata</u></b> ⚡\n\n"
        f"◈ <b>Current Default Tag :</b> <code>{current_meta}</code>\n\n"
        "Please type the new global metadata tag for all users (e.g. <code>Telegram : @Nex_bots</code>):"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_cancel_state")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_cancel_state$"))
async def cb_owner_cancel_state(client, query: CallbackQuery):
    OWNER_STATE.pop(query.from_user.id, None)
    await query.answer("Wizard Cancelled! ❌", show_alert=False)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


# ==================== ACTIVITY LOGS CALLBACKS ====================

@Client.on_callback_query(filters.regex(r"^cb_owner_logs$"))
async def cb_owner_logs_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    text, markup = await build_activity_logs_view()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer("Logs refreshed! 📜")


@Client.on_callback_query(filters.regex(r"^cb_owner_clear_logs$"))
async def cb_owner_clear_logs_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    await db.clear_activity_logs()
    await query.answer("Activity logs cleared! 🗑️", show_alert=True)
    text, markup = await build_activity_logs_view()
    await edit_message_content(query.message, text, reply_markup=markup)


# ==================== OWNER STATE MACHINE INPUT HANDLER ====================

@Client.on_message(filters.private & filters.user(Config.ADMIN) & ~filters.command(ADMIN_COMMANDS), group=2)
async def owner_state_input_handler(client: Client, message: Message):
    admin_id = message.from_user.id
    if admin_id not in OWNER_STATE:
        return await message.continue_propagation()

    state = OWNER_STATE.get(admin_id, {})
    action = state.get("action")
    input_text = message.text.strip() if message.text else ""

    if not input_text:
        return await message.reply_text("⚠️ Please send valid text or ID.")

    if action == "prem_uid":
        try:
            target_id = int(input_text)
        except ValueError:
            return await message.reply_text("❌ <b>Invalid ID!</b> Please enter numeric Telegram User ID.")
        
        OWNER_STATE[admin_id] = {"action": "prem_tier", "target_id": target_id}
        text = (
            "💎 <b><u>Add Premium User Wizard (Step 2/3)</u></b>\n\n"
            f"◈ <b>Target User ID :</b> <code>{target_id}</code>\n\n"
            "Select the <b>Premium Tier</b> to grant:"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🥈 Silver Tier", callback_data="cb_pwiz_tier_1"),
                InlineKeyboardButton("🥇 Gold Tier", callback_data="cb_pwiz_tier_2")
            ],
            [InlineKeyboardButton("💎 Diamond VIP Tier", callback_data="cb_pwiz_tier_3")],
            [InlineKeyboardButton("❌ Cancel Wizard", callback_data="cb_owner_cancel_state")]
        ])
        return await message.reply_text(text, reply_markup=markup)

    elif action == "coupon_custom_code":
        code = input_text.upper().replace(" ", "_")
        tier = state.get("tier", 1)
        days = state.get("days", 30)
        uses = state.get("uses", 5)
        OWNER_STATE.pop(admin_id, None)

        await db.create_coupon(code, tier=tier, days=days, max_uses=uses)
        await db.log_activity(admin_id, "Owner", "create_coupon", f"Code: {code} ({days}D, {uses} uses)")

        pname = TIER_NAMES.get(tier, "Premium")
        text = (
            "🎉 <b><u>Coupon Created Successfully!</u></b> ⚡\n\n"
            f"◈ <b>Coupon Code :</b> <code>{code}</code> (tap to copy)\n"
            f"◈ <b>Plan Level :</b> <b>{pname}</b>\n"
            f"◈ <b>Duration :</b> <code>{days} Days</code>\n"
            f"◈ <b>Max Redemptions :</b> <code>{uses} Uses</code>\n\n"
            f"Users can redeem via: <code>/redeem {code}</code>\n\n"
            "⚡ @Nex_bots"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟️ Coupons Manager", callback_data="cb_owner_coupons"),
             InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]
        ])
        return await message.reply_text(text, reply_markup=markup)

    elif action == "add_auth":
        OWNER_STATE.pop(admin_id, None)
        try:
            target_id = int(input_text)
            await db.add_auth_user(target_id)
            return await message.reply_text(
                f"🛡️ <b>User Authorized!</b> <code>{target_id}</code>\n\n⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]])
            )
        except ValueError:
            return await message.reply_text("❌ <b>Invalid ID!</b> Must be numeric.")

    elif action == "ban_user":
        OWNER_STATE.pop(admin_id, None)
        try:
            target_id = int(input_text)
            if target_id in Config.ADMIN:
                return await message.reply_text("❌ Cannot ban an Admin!")
            await db.ban_user(target_id)
            return await message.reply_text(
                f"🚫 <b>User Banned!</b> <code>{target_id}</code>\n\n⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]])
            )
        except ValueError:
            return await message.reply_text("❌ <b>Invalid ID!</b> Must be numeric.")

    elif action == "set_upi":
        OWNER_STATE.pop(admin_id, None)
        await db.set_upi_id(input_text)
        return await message.reply_text(
            f"💳 <b>UPI ID Updated!</b>\n\nActive UPI: <code>{input_text}</code>\n\n⚡ @Nex_bots",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]])
        )

    elif action == "set_meta":
        OWNER_STATE.pop(admin_id, None)
        await db.set_default_metadata(input_text)
        return await message.reply_text(
            f"🏷️ <b>Global Metadata Updated!</b>\n\n<code>{input_text}</code>\n\n⚡ @Nex_bots",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]])
        )

    elif action == "set_qr_url":
        OWNER_STATE.pop(admin_id, None)
        await db.update_bot_settings(payment_qr_url=input_text)
        return await message.reply_text(
            f"🖼️ <b>Payment QR URL Updated!</b>\n\n<code>{input_text}</code>\n\n⚡ @Nex_bots",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]])
        )

    elif action == "set_contact":
        OWNER_STATE.pop(admin_id, None)
        clean_contact = input_text.lstrip('@')
        await db.update_bot_settings(admin_contact=clean_contact)
        return await message.reply_text(
            f"💬 <b>Support Contact Updated!</b>\n\n@{clean_contact}\n\n⚡ @Nex_bots",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]])
        )

    elif action == "set_plan_price":
        tier = state.get("tier", 1)
        days = state.get("days", 30)
        OWNER_STATE.pop(admin_id, None)
        try:
            val = int(input_text.replace("₹", "").replace("⭐", "").strip())
            await db.set_plan_price(tier, days, val)
            t_name = TIER_NAMES.get(tier, f"Tier {tier}")
            return await message.reply_text(
                f"💎 <b>Price Updated!</b>\n\n"
                f"<b>{t_name} ({days} Days):</b> <code>₹{val}</code> / <code>{val}⭐</code>\n\n"
                f"⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Pricing Panel", callback_data="cb_owner_pricing")]])
            )
        except ValueError:
            return await message.reply_text("❌ <b>Invalid Price!</b> Please send a numeric integer.")

    elif action in ["set_tier_base_price", "set_base_price"]:
        tier = state.get("tier", 2)
        OWNER_STATE.pop(admin_id, None)
        try:
            val = int(input_text.replace("₹", "").replace("$", "").replace("⭐", "").strip())
            if val <= 0:
                return await message.reply_text("❌ <b>Invalid Price!</b> Price must be greater than 0.")
            update_kw = {f"plan_{tier}_base_inr": val}
            if tier == 2:
                update_kw["base_month_price_inr"] = val
            await db.update_bot_settings(**update_kw)
            inr, stars, usd = calc_plan_prices(1, val)
            t_names = {1: "Silver (Starter)", 2: "Gold (Pro)", 3: "Diamond (VIP Ultimate)"}
            t_name = t_names.get(tier, f"Tier {tier}")
            return await message.reply_text(
                f"💎 <b>{t_name} Base Price Updated!</b>\n\n"
                f"◈ <b>1 Month Base INR :</b> <code>₹{val}</code>\n"
                f"◈ <b>Calculated Stars :</b> <code>{stars} ⭐</code>\n"
                f"◈ <b>Calculated USD :</b> <code>${usd:.2f}</code>\n\n"
                f"<i>All dynamic durations (1–24 months) for {t_name} will now use this rate.</i>\n\n"
                f"⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Pricing Panel", callback_data="cb_owner_pricing")]])
            )
        except ValueError:
            return await message.reply_text("❌ <b>Invalid Price!</b> Please send a numeric integer (e.g. <code>99</code>).")

    elif action == "reset_user_trial":
        OWNER_STATE.pop(admin_id, None)
        try:
            target_id = int(input_text)
            await db.reset_user_trial(target_id)
            return await message.reply_text(
                f"🎁 <b>Free Trial Reset!</b>\n\nUser <code>{target_id}</code> can now claim the free trial again.\n\n⚡ @Nex_bots",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")]])
            )
        except ValueError:
            return await message.reply_text("❌ <b>Invalid ID!</b> Please enter numeric Telegram User ID.")

    await message.continue_propagation()


# ==================== OTHER OWNER PANELS & CONTROLS ====================

@Client.on_callback_query(filters.regex(r"^cb_owner_toggle_maint$") & filters.user(Config.ADMIN))
async def cb_owner_toggle_maint_cb(client, query: CallbackQuery):
    current = await db.get_maintenance()
    new_state = not current
    await db.set_maintenance(new_state)
    await query.answer(f"Maintenance Mode {'ENABLED 🔴' if new_state else 'DISABLED 🟢'}", show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_owner_toggle_protect$") & filters.user(Config.ADMIN))
async def cb_owner_toggle_protect_cb(client, query: CallbackQuery):
    current = await db.get_protect_content()
    new_state = not current
    await db.set_protect_content(new_state)
    await query.answer(f"Forward Lock {'ENABLED 🔒' if new_state else 'DISABLED 🔓'}", show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("maintenance") & filters.user(Config.ADMIN))
async def maintenance_cmd(client, message):
    current = await db.get_maintenance()
    new_state = not current
    await db.set_maintenance(new_state)
    await message.reply_text(
        f"🛠️ <b>Maintenance Mode:</b> {'ENABLED 🔴' if new_state else 'DISABLED 🟢'}\n\n"
        f"<i>When enabled, only Admins can start tasks or access the bot.</i>\n⚡ @Nex_bots"
    )


async def build_fsub_view():
    fsub = await db.get_fsub_settings()
    channel = fsub.get("channel") or "Not Configured"
    mode = fsub.get("mode", "normal")
    enabled = fsub.get("enabled", True)

    mode_label = "🔒 Request-to-Join Mode" if mode == "request" else "🌐 Normal Join Mode"
    status_label = "ENABLED 🟢" if enabled else "DISABLED 🔴"

    text = (
        "<b>◈ 📢 <b>Dynamic Force-Sub Settings</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Channel :</b> <code>{channel}</code>\n"
        f"◈ <b>Mode :</b> <b>{mode_label}</b>\n"
        f"◈ <b>Status :</b> <b>{status_label}</b>\n\n"
        "<b>Commands to manage:</b>\n"
        "• <code>/set_fsub &lt;channel_id_or_username&gt; [normal|request]</code>\n"
        "• <code>/set_fsub off</code> (to disable Force-Sub)\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Mode: {'Switch to Normal 🌐' if mode == 'request' else 'Switch to Request 🔒'}", callback_data="cb_owner_fsub_toggle_mode")],
        [InlineKeyboardButton(f"Status: {'Disable ❌' if enabled else 'Enable ✅'}", callback_data="cb_owner_fsub_toggle_enabled")],
        [InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


@Client.on_message(filters.private & filters.command("fsub") & filters.user(Config.ADMIN))
async def fsub_cmd(client, message):
    text, markup = await build_fsub_view()
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("set_fsub") & filters.user(Config.ADMIN))
async def set_fsub_cmd(client, message):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        return await message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "• <code>/set_fsub @ChannelUsername [normal|request]</code>\n"
            "• <code>/set_fsub -100xxxxxxxxxx [normal|request]</code>\n"
            "• <code>/set_fsub off</code>"
        )
    channel = args[1].strip()
    if channel.lower() in ("off", "disable", "none"):
        await db.set_fsub_settings(None, enabled=False)
        return await message.reply_text("❌ <b>Force-Sub Disabled!</b>\n\n⚡ @Nex_bots")
    
    mode = "normal"
    if len(args) > 2 and args[2].strip().lower() in ("request", "req"):
        mode = "request"

    await db.set_fsub_settings(channel, mode=mode, enabled=True)
    await message.reply_text(
        f"✅ <b>Force-Sub Settings Updated!</b>\n\n"
        f"📢 <b>Channel:</b> <code>{channel}</code>\n"
        f"⚙️ <b>Mode:</b> <code>{mode.upper()}</code>\n"
        f"🟢 <b>Status:</b> ENABLED\n\n⚡ @Nex_bots"
    )


@Client.on_callback_query(filters.regex(r"^cb_owner_fsub$") & filters.user(Config.ADMIN))
async def cb_owner_fsub_cb(client, query: CallbackQuery):
    text, markup = await build_fsub_view()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_fsub_toggle_mode$") & filters.user(Config.ADMIN))
async def cb_owner_fsub_toggle_mode(client, query: CallbackQuery):
    fsub = await db.get_fsub_settings()
    current_mode = fsub.get("mode", "normal")
    new_mode = "normal" if current_mode == "request" else "request"
    await db.set_fsub_settings(fsub.get("channel"), mode=new_mode, enabled=fsub.get("enabled", True))
    await query.answer(f"Switched to {new_mode.upper()} mode! 🔄")
    text, markup = await build_fsub_view()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_owner_fsub_toggle_enabled$") & filters.user(Config.ADMIN))
async def cb_owner_fsub_toggle_enabled(client, query: CallbackQuery):
    fsub = await db.get_fsub_settings()
    new_state = not fsub.get("enabled", True)
    await db.set_fsub_settings(fsub.get("channel"), mode=fsub.get("mode", "normal"), enabled=new_state)
    await query.answer(f"Force-Sub {'ENABLED 🟢' if new_state else 'DISABLED 🔴'}")
    text, markup = await build_fsub_view()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_owner_analytics$"))
async def cb_owner_analytics(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    stats = await _safe(db.get_global_usage(), default={})
    total_users = await _safe(db.total_users_count(), default=0)

    text = (
        "📈 <b><u>Global Usage & Analytics</u></b> ⚡\n\n"
        f"◈ <b>Total Bot Users :</b> <code>{total_users}</code>\n"
        f"◈ <b>Total Files Renamed :</b> <code>{stats.get('global_files', 0)}</code>\n"
        f"◈ <b>Total Bandwidth Processed :</b> <code>{humanbytes(stats.get('global_bytes', 0))}</code>\n\n"
        "◈ <b>Active Premium Breakdown:</b>\n"
        f"  • 🥈 Silver (Tier 1) : <code>{stats.get('silver_users', 0)}</code>\n"
        f"  • 🥇 Gold (Tier 2)   : <code>{stats.get('gold_users', 0)}</code>\n"
        f"  • 💎 Diamond (Tier 3): <code>{stats.get('diamond_users', 0)}</code>\n"
        f"  • 🎁 Trials Claimed  : <code>{stats.get('trials_claimed', 0)}</code>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_channels$"))
async def cb_owner_channels(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    owner_dump = await db.get_dump_channel(query.from_user.id)
    text = (
        "📦 <b><u>Channels & Backup Configuration</u></b>\n\n"
        f"• <b>Log Channel:</b> <code>{Config.LOG_CHANNEL or 'Disabled'}</code>\n"
        f"• <b>Files Backup Channel:</b> <code>{Config.FILES_CHANNEL or 'Disabled'}</code>\n"
        f"• <b>ForceSub Channel:</b> <code>{Config.FORCE_SUB or 'Disabled'}</code>\n"
        f"• <b>Your Private Dump:</b> <code>{owner_dump or 'None'}</code>\n"
        f"• <b>Support Bot:</b> <code>@NexCRSupportbot</code>\n\n"
        "<b>Command:</b> <code>/set_dump &lt;channel_id&gt;</code>\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await edit_message_content(query.message, text, reply_markup=btn)
    await query.answer()


# ==================== COMPREHENSIVE BOT & SERVER STATS ====================

async def build_admin_stats_view(client: Client):
    uptime_sec = time.time() - (Config.BOT_UPTIME or time.time())
    uptime = time.strftime("%Hh %Mm %Ss", time.gmtime(uptime_sec))
    total_users = await _safe(db.total_users_count(), default=0)
    usage = await _safe(db.get_global_usage(), default={})
    rename_stats = await _safe(db.get_global_rename_stats(), default={})
    banned = await _safe(db.get_banned_users(), default=[])
    
    total_disk, used_disk, free_disk = shutil.disk_usage(".")
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent

    shm_free_str = "N/A"
    if os.path.exists('/dev/shm'):
        try:
            _, _, free_shm = shutil.disk_usage('/dev/shm')
            shm_free_str = get_readable_file_size(free_shm)
        except Exception:
            pass

    from plugins.file_rename import ACTIVE_USER_TASKS
    active_tasks = sum(ACTIVE_USER_TASKS.values()) if ACTIVE_USER_TASKS else 0

    tot_files = rename_stats.get("total_files") or usage.get("global_files", 0)
    tot_bytes = rename_stats.get("total_bytes") or usage.get("global_bytes", 0)
    today_files = rename_stats.get("today_files", 0)
    today_bytes = rename_stats.get("today_bytes", 0)

    # Next cloud handoff countdown (at 5h 15m = 18900s)
    if uptime_sec < 18900:
        rem_sec = int(18900 - uptime_sec)
        handoff_str = f"{rem_sec // 3600}h {(rem_sec % 3600) // 60}m"
    else:
        handoff_str = "Drain Mode Active 🔄"

    has_4gb = "Connected 🟢" if getattr(client, "app_4gb", None) else "Disabled 🔴"

    text = (
        "<b>◈ 📊 <b>NeX Telemetry Dashboard</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Users :</b> <code>{total_users}</code> | <b>Banned :</b> <code>{len(banned)}</code>\n"
        f"◈ <b>VIPs :</b> <code>{usage.get('total_premium', 0)}</code> "
        f"(🥈{usage.get('silver_users', 0)} 🥇{usage.get('gold_users', 0)} 💎{usage.get('diamond_users', 0)})\n"
        f"◈ <b>Active Tasks :</b> <code>{active_tasks}</code> | <b>4GB App :</b> <code>{has_4gb}</code>\n\n"
        "🚀 <b>Speed Engine & Hardware:</b>\n"
        "  • Engine: <code>uvloop + TgCrypto + 64 Workers</code>\n"
        f"  • RAM: <code>{ram}%</code> | CPU: <code>{cpu}%</code>\n"
        f"  • RAM-Disk: <code>{shm_free_str} Free</code>\n"
        f"  • Free SSD: <code>{get_readable_file_size(free_disk)}</code>\n"
        f"  • Uptime: <code>{uptime}</code>\n"
        f"  • Relay Handoff: <code>{handoff_str}</code>\n\n"
        f"📁 Renamed: <code>{tot_files}</code> (Today: <code>{today_files}</code>)\n"
        f"📊 Bandwidth: <code>{humanbytes(tot_bytes)}</code> (Today: <code>{humanbytes(today_bytes)}</code>)\n\n"
        "⚡ @Nex_bots | 💬 @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="cb_owner_stats"),
         InlineKeyboardButton("🩺 Health Diagnostic", callback_data="cb_owner_health")],
        [InlineKeyboardButton("🧹 Clear Stuck Tasks", callback_data="cb_owner_reset_stuck"),
         InlineKeyboardButton("📜 Activity Logs", callback_data="cb_owner_logs")],
        [InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_owner_stats$") & filters.user(Config.ADMIN))
async def cb_owner_stats(client, query: CallbackQuery):
    text, markup = await build_admin_stats_view(client)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer("Stats Refreshed! 📊")


# ==================== LIVE HEALTH & DIAGNOSTIC SYSTEM ====================

async def build_health_report(client: Client):
    t0 = time.time()
    try:
        await asyncio.wait_for(client.get_me(), timeout=5.0)
        bot_ping = f"{(time.time() - t0)*1000:.1f}ms 🟢"
    except Exception:
        bot_ping = "Timeout/Error 🔴"

    app_4gb = getattr(client, "app_4gb", None)
    if app_4gb and getattr(app_4gb, "is_connected", False):
        t1 = time.time()
        try:
            await asyncio.wait_for(app_4gb.get_me(), timeout=5.0)
            prem_status = f"Connected ({(time.time() - t1)*1000:.1f}ms) 🟢"
        except Exception:
            prem_status = "Connected 🟢"
    elif app_4gb:
        prem_status = "Configured 🟡"
    else:
        prem_status = "Disabled ⚪"

    t2 = time.time()
    try:
        await asyncio.wait_for(db.ping(), timeout=5.0)
        db_ping = f"{(time.time() - t2)*1000:.1f}ms 🟢"
    except Exception:
        db_ping = "Error 🔴"

    ff_path = shutil.which("ffmpeg")
    ff_status = "Installed 🟢" if ff_path else "Missing 🔴"

    try:
        ram = psutil.virtual_memory().percent
        swap = psutil.swap_memory().percent
        cpu = psutil.cpu_percent(interval=0.1)
        _, _, free_disk = shutil.disk_usage(".")
        disk_free_str = get_readable_file_size(free_disk)
    except Exception:
        ram, swap, cpu, disk_free_str = 0, 0, 0, "N/A"

    shm_str = "N/A"
    if os.path.exists('/dev/shm'):
        try:
            _, _, free_shm = shutil.disk_usage('/dev/shm')
            shm_str = f"{get_readable_file_size(free_shm)} free"
        except Exception:
            pass

    try:
        uptime_sec = time.time() - (Config.BOT_UPTIME or time.time())
        uptime_str = time.strftime("%Hh %Mm %Ss", time.gmtime(uptime_sec))
    except Exception:
        uptime_str = "N/A"

    try:
        glob_stats = await db.get_global_rename_stats()
        total_renamed = glob_stats.get("total_files", 0)
        total_bytes = glob_stats.get("total_bytes", 0)
        total_bytes_str = get_readable_file_size(total_bytes)
    except Exception:
        total_renamed = 0
        total_bytes_str = "0 B"

    try:
        from plugins.file_rename import ACTIVE_USER_TASKS, USER_QUEUE
    except (ImportError, Exception):
        ACTIVE_USER_TASKS = {}
        USER_QUEUE = {}
    active_cnt = sum(ACTIVE_USER_TASKS.values()) if ACTIVE_USER_TASKS else 0
    queued_cnt = sum(len(q) for q in USER_QUEUE.values()) if USER_QUEUE else 0
    db_tasks_cnt = await _safe(db.tasks.count_documents({}), default=0)

    text = (
        "<b>◈ 🩺 <b>NeX Health Diagnostic</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>🤖 Bot MTProto :</b> <code>{bot_ping}</code>\n"
        f"◈ <b>🚀 4GB Client :</b> <code>{prem_status}</code>\n"
        f"◈ <b>🍃 MongoDB Ping :</b> <code>{db_ping}</code>\n"
        f"◈ <b>🎬 FFmpeg Binary :</b> <code>{ff_status}</code>\n\n"
        f"◈ <b>⏱️ Bot Uptime :</b> <code>{uptime_str}</code>\n"
        f"◈ <b>📁 Total Renamed :</b> <code>{total_renamed} files</code> (<code>{total_bytes_str}</code>)\n\n"
        f"◈ <b>🖥️ CPU :</b> <code>{cpu}%</code> | <b>RAM :</b> <code>{ram}%</code>\n"
        f"◈ <b>🔄 Swap :</b> <code>{swap}%</code> | <b>SSD :</b> <code>{disk_free_str}</code>\n"
        f"◈ <b>⚡ RAM-Disk :</b> <code>{shm_str}</code>\n\n"
        f"◈ <b>⚙️ Active Tasks :</b> <code>{active_cnt}</code>\n"
        f"◈ <b>📥 In-Memory Queue :</b> <code>{queued_cnt}</code>\n"
        f"◈ <b>🗄️ DB Tasks :</b> <code>{db_tasks_cnt}</code>\n\n"
        "⚡ @Nex_bots"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Health", callback_data="cb_owner_health"),
         InlineKeyboardButton("🧹 Clear Stuck Tasks", callback_data="cb_owner_reset_stuck")],
        [InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


@Client.on_message(filters.private & filters.command(["health", "health_check"]) & filters.user(Config.ADMIN))
async def health_cmd(client: Client, message: Message):
    try:
        text, markup = await build_health_report(client)
        await message.reply_text(text, reply_markup=markup)
    except Exception as err:
        await message.reply_text(f"⚠️ Health Diagnostic Error: <code>{err}</code>")


@Client.on_callback_query(filters.regex(r"^(cb_owner_health|owner_health|health_check|refresh_health)$") & filters.user(Config.ADMIN))
async def cb_owner_health(client: Client, query: CallbackQuery):
    try:
        await query.answer("Fetching diagnostic report... 🩺")
    except Exception:
        pass
    try:
        text, markup = await build_health_report(client)
        await edit_message_content(query.message, text, reply_markup=markup)
    except Exception as err:
        try:
            await query.message.edit_text(f"⚠️ Health Diagnostic Error: <code>{err}</code>")
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^cb_owner_reset_stuck$") & filters.user(Config.ADMIN))
async def cb_owner_reset_stuck(client: Client, query: CallbackQuery):
    try:
        await db.tasks.delete_many({})
    except Exception:
        pass
    try:
        from plugins.file_rename import ACTIVE_USER_TASKS, USER_QUEUE
        ACTIVE_USER_TASKS.clear()
        USER_QUEUE.clear()
    except (ImportError, Exception):
        pass
    await query.answer("All active queues and pending tasks cleared! 🧹", show_alert=True)
    text, markup = await build_health_report(client)
    await edit_message_content(query.message, text, reply_markup=markup)


# ==================== DYNAMIC PRICING PANEL & CONTROLS ====================

async def build_owner_pricing_panel():
    settings = await db.get_bot_settings()
    p1_inr = settings.get("plan_1_base_inr", 99)
    p2_inr = settings.get("plan_2_base_inr", 139)
    p3_inr = settings.get("plan_3_base_inr", 199)

    p1_stars = max(1, round((p1_inr * 100) / 199))
    p1_usd = round(p1_inr / 84.0, 2)

    p2_stars = max(1, round((p2_inr * 100) / 199))
    p2_usd = round(p2_inr / 84.0, 2)

    p3_stars = max(1, round((p3_inr * 100) / 199))
    p3_usd = round(p3_inr / 84.0, 2)

    text = (
        "<b>◈ Oᴡɴᴇʀ Pʀɪᴄɪɴɢ Eᴅɪᴛᴏʀ 💎</b>\n───────────────\n\n"
        "🥈 <b>𝟭. 𝗦𝗜𝗟𝗩𝗘𝗥 𝗣𝗟𝗔𝗡 (𝗦𝘁𝗮𝗿𝘁𝗲𝗿)</b>\n"
        f"┣ Base Rate : <code>₹{p1_inr}/mo</code>  |  <code>{p1_stars} ⭐</code>  |  <code>${p1_usd:.2f}</code>\n\n"
        "🥇 <b>𝟮. 𝗚𝗢𝗟𝗗 𝗣𝗟𝗔𝗡 (𝗣𝗿𝗼)</b>\n"
        f"┣ Base Rate : <code>₹{p2_inr}/mo</code>  |  <code>{p2_stars} ⭐</code>  |  <code>${p2_usd:.2f}</code>\n\n"
        "💎 <b>𝟯. 𝗗𝗜𝗔𝗠𝗢𝗡𝗗 𝗣𝗟𝗔𝗡 (𝗩𝗜𝗣)</b>\n"
        f"┣ Base Rate : <code>₹{p3_inr}/mo</code>  |  <code>{p3_stars} ⭐</code>  |  <code>${p3_usd:.2f}</code>\n\n"
        "<i>Tap a tier button below to edit its 1-month base INR price. Stars & USD auto-sync.</i>\n\n"
        "⚡ @Nex_bots"
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🥈 Edit Silver (₹)", callback_data="cb_oprice_edit_1"),
            InlineKeyboardButton("🥇 Edit Gold (₹)", callback_data="cb_oprice_edit_2")
        ],
        [
            InlineKeyboardButton("💎 Edit Diamond (₹)", callback_data="cb_oprice_edit_3")
        ],
        [
            InlineKeyboardButton("🚀 +30% Boost All", callback_data="cb_oprice_boost"),
            InlineKeyboardButton("🔄 Reset Defaults", callback_data="cb_oprice_reset")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_owner_pricing$") & filters.user(Config.ADMIN))
async def cb_owner_pricing_handler(client, query: CallbackQuery):
    text, markup = await build_owner_pricing_panel()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^(?:cb_oprice_edit_|cb_oprice_tier_)(\d+)$") & filters.user(Config.ADMIN))
async def cb_oprice_edit_tier_handler(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    tier = tier if tier in [1, 2, 3] else 2
    t_names = {1: "Silver (Starter)", 2: "Gold (Pro)", 3: "Diamond (VIP)"}
    t_name = t_names.get(tier, f"Tier {tier}")
    settings = await db.get_bot_settings()
    default_bases = {1: 99, 2: 139, 3: 199}
    curr_inr = settings.get(f"plan_{tier}_base_inr", default_bases.get(tier, 139))
    OWNER_STATE[query.from_user.id] = {"action": "set_tier_base_price", "tier": tier}
    text = (
        f"💎 <b><u>Set 1-Month Base Price for {t_name}</u></b>\n\n"
        f"◈ <b>Current Price :</b> <code>₹{curr_inr}</code>\n\n"
        f"Please send the new 1-month base price in INR as an integer (e.g. <code>{default_bases.get(tier, 139)}</code>):\n\n"
        "<i>Telegram Stars and USD will automatically recalculate for all durations (1–24 months). Send /cancel to abort.</i>"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_pricing")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_oprice_base_wiz$") & filters.user(Config.ADMIN))
async def cb_oprice_base_wiz_handler(client, query: CallbackQuery):
    query.matches = [type("Match", (), {"group": lambda self, x: "2"})()]
    await cb_oprice_edit_tier_handler(client, query)


@Client.on_callback_query(filters.regex(r"^cb_oprice_boost$") & filters.user(Config.ADMIN))
async def cb_oprice_boost_handler(client, query: CallbackQuery):
    settings = await db.get_bot_settings()
    p1 = max(1, round(settings.get("plan_1_base_inr", 99) * 1.30))
    p2 = max(1, round(settings.get("plan_2_base_inr", 139) * 1.30))
    p3 = max(1, round(settings.get("plan_3_base_inr", 199) * 1.30))
    await db.update_bot_settings(
        plan_1_base_inr=p1,
        plan_2_base_inr=p2,
        plan_3_base_inr=p3,
        base_month_price_inr=p2
    )
    await db.boost_all_prices_percent(30.0)
    await query.answer("All 3 plans boosted by +30%! 🚀", show_alert=True)
    text, markup = await build_owner_pricing_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_oprice_reset$") & filters.user(Config.ADMIN))
async def cb_oprice_reset_handler(client, query: CallbackQuery):
    await db.update_bot_settings(
        plan_1_base_inr=99,
        plan_2_base_inr=139,
        plan_3_base_inr=199,
        base_month_price_inr=139
    )
    await db.reset_pricing_defaults()
    await query.answer("Pricing reset to defaults (₹99 / ₹139 / ₹199)! 🔄", show_alert=True)
    text, markup = await build_owner_pricing_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_oprice_set_(\d+)_(\d+)$") & filters.user(Config.ADMIN))
async def cb_oprice_set_handler(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    OWNER_STATE[query.from_user.id] = {"action": "set_plan_price", "tier": tier, "days": days}
    t_name = TIER_NAMES.get(tier, f"Tier {tier}")
    text = (
        f"💎 <b><u>Set Price for {t_name} ({days} Days)</u></b>\n\n"
        f"Please send the new price in <b>INR / Telegram Stars</b> (e.g. <code>199</code>):\n\n"
        f"<i>1:1 parity is strictly maintained. Send /cancel or tap Cancel below to exit.</i>"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_pricing")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


# ==================== FREE TRIAL CONFIG PANEL & CONTROLS ====================

async def build_owner_trial_panel():
    settings = await db.get_bot_settings()
    usage = await _safe(db.get_global_usage(), default={})
    trials_claimed = usage.get("trials_claimed", 0)
    
    t_enabled = settings.get("trial_enabled", True)
    t_status = "ENABLED 🟢" if t_enabled else "DISABLED 🔴"
    t_days = settings.get("trial_days", 3)
    
    text = (
        "<b>◈ 🎁 <b>Free Trial Configuration</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Trial Status :</b> <code>{t_status}</code>\n"
        f"◈ <b>Trial Duration :</b> <code>{t_days} Days</code>\n"
        f"◈ <b>Total Trials Claimed :</b> <code>{trials_claimed}</code>\n\n"
        "<i>Users can claim a 1-time 4GB Gold Trial with unthrottled speed. Once claimed or expired, the trial button is hidden.</i>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{'🔴 Disable Trial' if t_enabled else '🟢 Enable Trial'}", callback_data="cb_otrial_toggle")
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if t_days==1 else ''}1 Day", callback_data="cb_otrial_days_1"),
            InlineKeyboardButton(f"{'✅ ' if t_days==3 else ''}3 Days", callback_data="cb_otrial_days_3"),
            InlineKeyboardButton(f"{'✅ ' if t_days==7 else ''}7 Days", callback_data="cb_otrial_days_7")
        ],
        [
            InlineKeyboardButton("🔄 Reset User Trial", callback_data="cb_otrial_reset_wiz")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_owner_trial_cfg$") & filters.user(Config.ADMIN))
async def cb_owner_trial_cfg_handler(client, query: CallbackQuery):
    text, markup = await build_owner_trial_panel()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_otrial_toggle$") & filters.user(Config.ADMIN))
async def cb_otrial_toggle_handler(client, query: CallbackQuery):
    settings = await db.get_bot_settings()
    cur = settings.get("trial_enabled", True)
    await db.update_bot_settings(trial_enabled=not cur)
    await query.answer(f"Trial {'DISABLED 🔴' if cur else 'ENABLED 🟢'}", show_alert=True)
    text, markup = await build_owner_trial_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_otrial_days_(\d+)$") & filters.user(Config.ADMIN))
async def cb_otrial_days_handler(client, query: CallbackQuery):
    days = int(query.matches[0].group(1))
    await db.update_bot_settings(trial_days=days)
    await query.answer(f"Trial duration set to {days} Days! 🎁")
    text, markup = await build_owner_trial_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_otrial_reset_wiz$") & filters.user(Config.ADMIN))
async def cb_otrial_reset_wiz_handler(client, query: CallbackQuery):
    OWNER_STATE[query.from_user.id] = {"action": "reset_user_trial"}
    text = (
        "🎁 <b><u>Reset User Free Trial</u></b>\n\n"
        "Send the <b>Telegram User ID</b> whose free trial you want to reset:\n\n"
        "<i>Or tap Cancel below to exit.</i>"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_trial_cfg")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


# ==================== QUOTA & CONCURRENCY CONTROLS ====================

async def build_owner_quota_panel():
    settings = await db.get_bot_settings()
    free_gb = settings.get("free_quota_gb", 20)
    f_conc = settings.get("free_concurrency", 1)
    p_conc = settings.get("prem_concurrency", 4)

    text = (
        "<b>◈ ⚡ <b>Quota & Concurrency Manager</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Free Daily Quota :</b> <code>{free_gb} GB/day</code>\n"
        f"◈ <b>Free Concurrency :</b> <code>{f_conc} parallel task(s)</code>\n"
        f"◈ <b>Premium Concurrency :</b> <code>{p_conc} parallel task(s)</code>\n\n"
        "<i>Select options below to update dynamically:</i>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{'✅ ' if free_gb==5 else ''}5 GB", callback_data="cb_oquota_free_5"),
            InlineKeyboardButton(f"{'✅ ' if free_gb==10 else ''}10 GB", callback_data="cb_oquota_free_10"),
            InlineKeyboardButton(f"{'✅ ' if free_gb==20 else ''}20 GB", callback_data="cb_oquota_free_20"),
            InlineKeyboardButton(f"{'✅ ' if free_gb==50 else ''}50 GB", callback_data="cb_oquota_free_50")
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if f_conc==1 else ''}Free: 1 Task", callback_data="cb_oquota_fconc_1"),
            InlineKeyboardButton(f"{'✅ ' if f_conc==2 else ''}Free: 2 Tasks", callback_data="cb_oquota_fconc_2")
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if p_conc==2 else ''}Prem: 2", callback_data="cb_oquota_pconc_2"),
            InlineKeyboardButton(f"{'✅ ' if p_conc==4 else ''}Prem: 4", callback_data="cb_oquota_pconc_4"),
            InlineKeyboardButton(f"{'✅ ' if p_conc==8 else ''}Prem: 8", callback_data="cb_oquota_pconc_8")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_owner_quota_cfg$") & filters.user(Config.ADMIN))
async def cb_owner_quota_cfg_handler(client, query: CallbackQuery):
    text, markup = await build_owner_quota_panel()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_oquota_free_(\d+)$") & filters.user(Config.ADMIN))
async def cb_oquota_free_handler(client, query: CallbackQuery):
    gb = int(query.matches[0].group(1))
    await db.update_bot_settings(free_quota_gb=gb)
    await query.answer(f"Free daily quota set to {gb} GB/day! ⚡")
    text, markup = await build_owner_quota_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_oquota_fconc_(\d+)$") & filters.user(Config.ADMIN))
async def cb_oquota_fconc_handler(client, query: CallbackQuery):
    conc = int(query.matches[0].group(1))
    await db.update_bot_settings(free_concurrency=conc)
    await query.answer(f"Free concurrency set to {conc} task(s)! ⚡")
    text, markup = await build_owner_quota_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_oquota_pconc_(\d+)$") & filters.user(Config.ADMIN))
async def cb_oquota_pconc_handler(client, query: CallbackQuery):
    conc = int(query.matches[0].group(1))
    await db.update_bot_settings(prem_concurrency=conc)
    await query.answer(f"Premium concurrency set to {conc} task(s)! ⚡")
    text, markup = await build_owner_quota_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


# ==================== FEATURE TOGGLES CONTROLS ====================

async def build_owner_toggles_panel():
    settings = await db.get_bot_settings()
    sample_on = settings.get("auto_sample_enabled", True)
    ss_on = settings.get("auto_screenshot_enabled", True)
    ramdisk_on = settings.get("ram_disk_enabled", True)
    session_on = settings.get("session_upload_enabled", True)

    text = (
        "<b>◈ ⚙️ <b>Bot Feature Toggles</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>🎬 Sample Video :</b> <code>{'ON 🟢' if sample_on else 'OFF 🔴'}</code>\n"
        f"◈ <b>📸 Screenshots :</b> <code>{'ON 🟢' if ss_on else 'OFF 🔴'}</code>\n"
        f"◈ <b>⚡ RAM-Disk Accel :</b> <code>{'ON 🟢' if ramdisk_on else 'OFF 🔴'}</code>\n"
        f"◈ <b>🚀 4GB Session Upload :</b> <code>{'ON 🟢' if session_on else 'OFF 🔴'}</code>\n\n"
        "<i>Tap a feature button to toggle ON/OFF:</i>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🎬 Sample: {'ON 🟢' if sample_on else 'OFF 🔴'}", callback_data="cb_otoggle_sample"),
            InlineKeyboardButton(f"📸 SS: {'ON 🟢' if ss_on else 'OFF 🔴'}", callback_data="cb_otoggle_ss")
        ],
        [
            InlineKeyboardButton(f"⚡ RAM-Disk: {'ON 🟢' if ramdisk_on else 'OFF 🔴'}", callback_data="cb_otoggle_ramdisk"),
            InlineKeyboardButton(f"🚀 4GB Session: {'ON 🟢' if session_on else 'OFF 🔴'}", callback_data="cb_otoggle_session")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_owner_toggles$") & filters.user(Config.ADMIN))
async def cb_owner_toggles_handler(client, query: CallbackQuery):
    text, markup = await build_owner_toggles_panel()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_otoggle_sample$") & filters.user(Config.ADMIN))
async def cb_otoggle_sample_handler(client, query: CallbackQuery):
    s = await db.get_bot_settings()
    cur = s.get("auto_sample_enabled", True)
    await db.update_bot_settings(auto_sample_enabled=not cur)
    await query.answer(f"Sample Video {'DISABLED 🔴' if cur else 'ENABLED 🟢'}")
    text, markup = await build_owner_toggles_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_otoggle_ss$") & filters.user(Config.ADMIN))
async def cb_otoggle_ss_handler(client, query: CallbackQuery):
    s = await db.get_bot_settings()
    cur = s.get("auto_screenshot_enabled", True)
    await db.update_bot_settings(auto_screenshot_enabled=not cur)
    await query.answer(f"Screenshots {'DISABLED 🔴' if cur else 'ENABLED 🟢'}")
    text, markup = await build_owner_toggles_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_otoggle_ramdisk$") & filters.user(Config.ADMIN))
async def cb_otoggle_ramdisk_handler(client, query: CallbackQuery):
    s = await db.get_bot_settings()
    cur = s.get("ram_disk_enabled", True)
    await db.update_bot_settings(ram_disk_enabled=not cur)
    await query.answer(f"RAM-Disk {'DISABLED 🔴' if cur else 'ENABLED 🟢'}")
    text, markup = await build_owner_toggles_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_otoggle_session$") & filters.user(Config.ADMIN))
async def cb_otoggle_session_handler(client, query: CallbackQuery):
    s = await db.get_bot_settings()
    cur = s.get("session_upload_enabled", True)
    await db.update_bot_settings(session_upload_enabled=not cur)
    await query.answer(f"4GB Session Upload {'DISABLED 🔴' if cur else 'ENABLED 🟢'}")
    text, markup = await build_owner_toggles_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


# ==================== PAYMENT & SUPPORT CONFIG CONTROLS ====================

async def build_owner_payment_panel():
    settings = await db.get_bot_settings()
    upi_id = await db.get_upi_id()
    qr_url = settings.get("payment_qr_url", getattr(Config, "QR_PIC", ""))
    contact = settings.get("admin_contact", "NexCRSupportbot")

    text = (
        "<b>◈ 💳 <b>Payment & Support Config</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Active UPI ID :</b> <code>{upi_id}</code>\n"
        f"◈ <b>Payment QR Pic :</b> <code>{qr_url[:40]}...</code>\n"
        f"◈ <b>Support Contact :</b> @{contact}\n\n"
        "<i>Tap a button below to update settings interactively:</i>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💳 Set UPI ID", callback_data="cb_owner_upi_wiz"),
            InlineKeyboardButton("🖼️ Set QR URL", callback_data="cb_opay_qr_wiz")
        ],
        [
            InlineKeyboardButton("💬 Set Support Handle", callback_data="cb_opay_contact_wiz")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_owner_payment_cfg$") & filters.user(Config.ADMIN))
async def cb_owner_payment_cfg_handler(client, query: CallbackQuery):
    text, markup = await build_owner_payment_panel()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_opay_qr_wiz$") & filters.user(Config.ADMIN))
async def cb_opay_qr_wiz_handler(client, query: CallbackQuery):
    OWNER_STATE[query.from_user.id] = {"action": "set_qr_url"}
    text = (
        "🖼️ <b><u>Update Payment QR Picture URL</u></b>\n\n"
        "Send the direct image URL for the payment QR code (e.g. Telegraph / Imgur link):\n\n"
        "<i>Or tap Cancel below to exit.</i>"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_payment_cfg")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_opay_contact_wiz$") & filters.user(Config.ADMIN))
async def cb_opay_contact_wiz_handler(client, query: CallbackQuery):
    OWNER_STATE[query.from_user.id] = {"action": "set_contact"}
    text = (
        "💬 <b><u>Update Support / Admin Username</u></b>\n\n"
        "Send the Telegram username (with or without @) for support inquiries:\n\n"
        "<i>Or tap Cancel below to exit.</i>"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cb_owner_payment_cfg")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


# ==================== OWNER REFERRAL SYSTEM PANEL ====================

async def build_owner_referral_panel():
    settings = await db.get_referral_settings()
    status_str = "Enabled 🟢" if settings["enabled"] else "Disabled 🔴"
    req = settings["required"]
    days = settings["reward_days"]
    tier_name = TIER_NAMES.get(settings["reward_tier"], "Gold")

    text = (
        "<b>◈ 🎁 <b>Referral System Control</b></b>\n"
        "───────────────\n\n"
        f"◈ <b>Status :</b> <code>{status_str}</code>\n"
        f"◈ <b>Target :</b> <code>{req} Invites</code>\n"
        f"◈ <b>Reward :</b> <b>{days} Days {tier_name}</b>\n\n"
        "<i>Tap buttons below to change settings:</i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    status_btn_text = "🔴 Disable Referrals" if settings["enabled"] else "🟢 Enable Referrals"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(status_btn_text, callback_data="cb_oref_toggle_status")],
        [
            InlineKeyboardButton("1 Inv" + (" ✅" if req == 1 else ""), callback_data="cb_oref_req_1"),
            InlineKeyboardButton("3 Inv" + (" ✅" if req == 3 else ""), callback_data="cb_oref_req_3"),
            InlineKeyboardButton("5 Inv" + (" ✅" if req == 5 else ""), callback_data="cb_oref_req_5"),
            InlineKeyboardButton("10 Inv" + (" ✅" if req == 10 else ""), callback_data="cb_oref_req_10")
        ],
        [
            InlineKeyboardButton("1D" + (" ✅" if days == 1 else ""), callback_data="cb_oref_days_1"),
            InlineKeyboardButton("3D" + (" ✅" if days == 3 else ""), callback_data="cb_oref_days_3"),
            InlineKeyboardButton("7D" + (" ✅" if days == 7 else ""), callback_data="cb_oref_days_7"),
            InlineKeyboardButton("15D" + (" ✅" if days == 15 else ""), callback_data="cb_oref_days_15"),
            InlineKeyboardButton("30D" + (" ✅" if days == 30 else ""), callback_data="cb_oref_days_30")
        ],
        [
            InlineKeyboardButton("🥈 Silver" + (" ✅" if settings["reward_tier"] == 1 else ""), callback_data="cb_oref_tier_1"),
            InlineKeyboardButton("🥇 Gold" + (" ✅" if settings["reward_tier"] == 2 else ""), callback_data="cb_oref_tier_2"),
            InlineKeyboardButton("💎 Diamond" + (" ✅" if settings["reward_tier"] == 3 else ""), callback_data="cb_oref_tier_3")
        ],
        [InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_owner_referral$") & filters.user(Config.ADMIN))
async def cb_owner_referral_cb(client, query: CallbackQuery):
    text, markup = await build_owner_referral_panel()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_oref_toggle_status$") & filters.user(Config.ADMIN))
async def cb_oref_toggle_status_cb(client, query: CallbackQuery):
    settings = await db.get_referral_settings()
    new_state = not settings["enabled"]
    await db.set_referral_settings(enabled=new_state)
    await query.answer(f"Referrals {'Enabled 🟢' if new_state else 'Disabled 🔴'}")
    text, markup = await build_owner_referral_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_oref_req_(\d+)$") & filters.user(Config.ADMIN))
async def cb_oref_req_cb(client, query: CallbackQuery):
    req = int(query.matches[0].group(1))
    await db.set_referral_settings(required=req)
    await query.answer(f"Target set to {req} Invites!")
    text, markup = await build_owner_referral_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_oref_days_(\d+)$") & filters.user(Config.ADMIN))
async def cb_oref_days_cb(client, query: CallbackQuery):
    days = int(query.matches[0].group(1))
    await db.set_referral_settings(reward_days=days)
    await query.answer(f"Reward set to {days} Days!")
    text, markup = await build_owner_referral_panel()
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^cb_oref_tier_(\d+)$") & filters.user(Config.ADMIN))
async def cb_oref_tier_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    await db.set_referral_settings(reward_tier=tier)
    await query.answer(f"Reward Tier set to {TIER_NAMES.get(tier, 'Tier ' + str(tier))}!")
    text, markup = await build_owner_referral_panel()
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


@Client.on_callback_query(filters.regex(r"^cb_owner_cmds$") & filters.user(Config.ADMIN))
async def cb_owner_cmds_view(client, query: CallbackQuery):
    text = (
        "<b>◈ 📋 <b>NeX Bot Commands Cheat-Sheet</b></b>\n"
        "───────────────\n\n"
        "👑 <b>Owner Commands:</b>\n"
        "• <code>/owner</code> | <code>/admin</code> - Open Control Panel\n"
        "• <code>/mode</code> [pub|priv] | <code>/maintenance</code> - Modes\n"
        "• <code>/status</code> | <code>/users</code> - System Stats & Count\n"
        "• <code>/broadcast</code> (reply) | <code>/bcast_btn</code>\n"
        "• <code>/add_prem &lt;id&gt; &lt;tier&gt; &lt;days&gt;</code>\n"
        "• <code>/rem_prem &lt;id&gt;</code> | <code>/prem_list</code>\n"
        "• <code>/add_user &lt;id&gt;</code> | <code>/rem_user &lt;id&gt;</code> | <code>/auth_list</code>\n"
        "• <code>/ban &lt;id&gt;</code> | <code>/unban &lt;id&gt;</code> | <code>/ban_list</code>\n"
        "• <code>/add_coupon &lt;code&gt; &lt;tier&gt; &lt;days&gt; &lt;uses&gt;</code>\n"
        "• <code>/del_coupon &lt;code&gt;</code> | <code>/coupons</code>\n"
        "• <code>/set_fsub &lt;channel&gt;</code> | <code>/set_global_meta &lt;tag&gt;</code>\n"
        "• <code>/set_upi &lt;id&gt;</code> | <code>/restart</code>\n\n"
        "⚡ <b>Key User Commands:</b>\n"
        "• <code>/start</code> | <code>/profile</code> | <code>/refer</code> | <code>/plan</code>\n"
        "• <code>/settings</code> | <code>/leaderboard</code> | <code>/usage</code> | <code>/timezone</code>\n"
        "• <code>/metadata</code> | <code>/set_metadata</code> | <code>/set_watermark</code>\n"
        "• <code>/set_sample</code> | <code>/set_sample_time</code> | <code>/set_shots</code>\n"
        "• <code>/set_prefix</code> | <code>/set_suffix</code> | <code>/set_caption</code>\n"
        "• <code>/clean_words</code> | <code>/add_clean</code> | <code>/del_clean</code>\n"
        "• <code>/set_dump</code> | <code>/del_dump</code> | <code>/donate</code> | <code>/cancel</code>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Owner", callback_data="owner_panel"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


# ==================== ADVANCED INTERACTIVE BROADCAST ====================

@Client.on_message(filters.command("broadcast") & filters.user(Config.ADMIN) & filters.reply)
async def broadcast_panel_cmd(bot: Client, message: Message):
    admin_id = message.from_user.id
    target_msg = message.reply_to_message
    BROADCAST_CACHE[admin_id] = target_msg

    text = (
        "📢 <b><u>Interactive Broadcast Control Panel</u></b> ⚡\n\n"
        "Your message is ready to broadcast. Choose an option below:\n\n"
        "1. <b>🚀 Send Without Buttons:</b> Broadcast as-is.\n"
        "2. <b>⚡ Ready: Join & Support:</b> Channel & Support buttons.\n"
        "3. <b>💎 Ready: Free Trial & Plans:</b> Claim Trial & Plans buttons.\n"
        "4. <b>🤖 Ready: Use Bot Now:</b> Start Bot & Updates buttons.\n"
        "5. <b>✍️ Custom Buttons:</b> Type <code>/bcast_btn</code> to set custom buttons.\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Send Without Buttons", callback_data="bcast_send_raw")],
        [InlineKeyboardButton("⚡ Ready: Join & Support", callback_data="bcast_send_support")],
        [InlineKeyboardButton("💎 Ready: Free Trial & Plans", callback_data="bcast_send_trial")],
        [InlineKeyboardButton("🤖 Ready: Use Bot Now", callback_data="bcast_send_use")],
        [InlineKeyboardButton("✍️ Custom Button Instructions", callback_data="bcast_custom_info")],
        [InlineKeyboardButton("❌ Cancel Broadcast", callback_data="bcast_cancel")]
    ])
    await message.reply_text(text, reply_markup=markup, quote=True)


@Client.on_callback_query(filters.regex(r"^bcast_custom_info$"))
async def bcast_custom_info(client, query: CallbackQuery):
    text = (
        "✍️ <b><u>Custom Broadcast Buttons Guide</u></b> ⚡\n\n"
        "To broadcast with custom buttons, send:\n"
        "<code>/bcast_btn Button 1 - https://link1 | Button 2 - https://link2</code>\n\n"
        "<b>Example:</b>\n"
        "<code>/bcast_btn 📢 Updates - https://t.me/Nex_bots | 💬 Support - https://t.me/NexCRSupportbot</code>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Options", callback_data="bcast_reopen")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^bcast_reopen$"))
async def bcast_reopen(client, query: CallbackQuery):
    text = (
        "📢 <b><u>Interactive Broadcast Control Panel</u></b> ⚡\n\n"
        "Choose how to broadcast your message:\n\n"
        "1. <b>🚀 Send Without Buttons</b>\n"
        "2. <b>⚡ Ready: Join & Support</b>\n"
        "3. <b>💎 Ready: Free Trial & Plans</b>\n"
        "4. <b>🤖 Ready: Use Bot Now</b>\n"
        "5. <b>✍️ Custom Buttons</b>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Send Without Buttons", callback_data="bcast_send_raw")],
        [InlineKeyboardButton("⚡ Ready: Join & Support", callback_data="bcast_send_support")],
        [InlineKeyboardButton("💎 Ready: Free Trial & Plans", callback_data="bcast_send_trial")],
        [InlineKeyboardButton("🤖 Ready: Use Bot Now", callback_data="bcast_send_use")],
        [InlineKeyboardButton("✍️ Custom Button Instructions", callback_data="bcast_custom_info")],
        [InlineKeyboardButton("❌ Cancel Broadcast", callback_data="bcast_cancel")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^bcast_cancel$"))
async def bcast_cancel_cb(client, query: CallbackQuery):
    BROADCAST_CACHE.pop(query.from_user.id, None)
    await query.message.delete()
    await query.answer("Broadcast Cancelled!", show_alert=True)


@Client.on_callback_query(filters.regex(r"^bcast_send_(raw|support|trial|use)$"))
async def bcast_send_preset(client: Client, query: CallbackQuery):
    action = query.matches[0].group(1)
    admin_id = query.from_user.id
    target_msg = BROADCAST_CACHE.get(admin_id)
    if not target_msg:
        return await query.answer("❌ Message expired from broadcast cache! Please reply with /broadcast again.", show_alert=True)

    bot_me = await client.get_me()
    bot_user = bot_me.username or "Nex_bots"

    reply_markup = None
    if action == "support":
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 Updates Channel", url="https://t.me/Nex_bots"),
                InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")
            ]
        ])
    elif action == "trial":
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎁 Claim 3-Day Free Trial", url=f"https://t.me/{bot_user}?start=trial"),
                InlineKeyboardButton("💎 View Plans", url=f"https://t.me/{bot_user}?start=plan")
            ],
            [
                InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")
            ]
        ])
    elif action == "use":
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ Start Rename Bot", url=f"https://t.me/{bot_user}?start=start"),
                InlineKeyboardButton("📢 Updates Channel", url="https://t.me/Nex_bots")
            ]
        ])

    await edit_message_content(query.message, "📢 <b>Initializing Broadcast Process...</b>")
    await run_broadcast_worker(client, query.message, target_msg, reply_markup)


@Client.on_message(filters.private & filters.command("bcast_btn") & filters.user(Config.ADMIN))
async def bcast_custom_btn_cmd(client: Client, message: Message):
    admin_id = message.from_user.id
    target_msg = BROADCAST_CACHE.get(admin_id) or message.reply_to_message
    if not target_msg:
        return await message.reply_text("❌ No message found to broadcast! Please reply to a message with <code>/broadcast</code> first.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/bcast_btn Text 1 - https://url1 | Text 2 - https://url2</code>")

    raw_btns = args[1].strip()
    btn_rows = []
    current_row = []
    
    parts = [p.strip() for p in raw_btns.replace("\n", "|").split("|") if p.strip()]
    for p in parts:
        if " - " in p:
            b_text, b_url = p.split(" - ", 1)
            b_text = b_text.strip()
            b_url = b_url.strip()
            if b_url.startswith("http"):
                current_row.append(InlineKeyboardButton(b_text, url=b_url))
        if len(current_row) == 2:
            btn_rows.append(current_row)
            current_row = []
    if current_row:
        btn_rows.append(current_row)

    if not btn_rows:
        return await message.reply_text("❌ Failed to parse buttons! Please check the syntax: <code>Button Text - https://link</code>")

    markup = InlineKeyboardMarkup(btn_rows)
    sts_msg = await message.reply_text("📢 <b>Broadcasting with Custom Buttons...</b>")
    await run_broadcast_worker(client, sts_msg, target_msg, markup)


async def run_broadcast_worker(bot: Client, sts_msg, target_msg: Message, reply_markup):
    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
        try:
            await bot.send_message(
                Config.LOG_CHANNEL,
                f"📢 <b>Broadcast Initialized!</b>"
            )
        except Exception:
            pass

    all_users = await db.get_all_users()
    done = 0
    failed = 0
    success = 0
    start_time = time.time()
    total_users = await db.total_users_count()

    async for user in all_users:
        sts = await send_msg(user['_id'], target_msg, reply_markup)
        if sts == 200:
            success += 1
        else:
            failed += 1
        if sts == 400:
            await db.delete_user(user['_id'])
        done += 1
        if done % 20 == 0:
            try:
                await sts_msg.edit_text(
                    f"📢 <b>Broadcast In Progress:</b>\n\n"
                    f"• <b>Total Users:</b> <code>{total_users}</code>\n"
                    f"• <b>Processed:</b> <code>{done} / {total_users}</code>\n"
                    f"• <b>Delivered:</b> <code>{success}</code>\n"
                    f"• <b>Failed:</b> <code>{failed}</code>\n\n"
                    f"⚡ @Nex_bots"
                )
            except Exception:
                pass

    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    try:
        await sts_msg.edit_text(
            f"✅ <b>Broadcast Completed Successfully!</b>\n\n"
            f"⏱️ <b>Time Taken:</b> <code>{completed_in}</code>\n"
            f"👥 <b>Total Users:</b> <code>{total_users}</code>\n"
            f"🟢 <b>Delivered:</b> <code>{success}</code>\n"
            f"🔴 <b>Failed/Deleted:</b> <code>{failed}</code>\n\n"
            f"⚡ <b>NeX 4GB Rename Bot</b> | @Nex_bots"
        )
    except Exception:
        pass


async def send_msg(user_id, message: Message, reply_markup=None):
    try:
        kwargs = {"chat_id": int(user_id)}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        await message.copy(**kwargs)
        return 200
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await send_msg(user_id, message, reply_markup)
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


# ==================== /status & /restart ====================

@Client.on_message(filters.command(["stats", "status"]) & filters.user(Config.ADMIN))
async def get_stats(bot, message):
    text, markup = await build_admin_stats_view(bot)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("restart") & filters.user(Config.ADMIN))
async def restart_bot(b, m):
    await m.reply_text("<b>🔄 Restarting NeX 4GB Rename Bot Engine.....</b>\n\n⚡ @Nex_bots")
    os.execl(sys.executable, sys.executable, *sys.argv)
