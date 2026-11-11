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
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid

from config import Config
from helper.database import db, TIER_NAMES, format_user_time
from helper.utils import get_readable_file_size, humanbytes, edit_message_content

# NeX 4GB Rename Bot - Advanced Interactive Owner Control Panel & Broadcast Engine
# Developed by @Nex_bots

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_DB_TIMEOUT = 5

async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except Exception:
        return default

# Global broadcast message cache: admin_id -> replied Message
BROADCAST_CACHE = {}


# ==================== LIVE OWNER DASHBOARD BUILDER ====================

async def build_owner_panel(client: Client):
    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    mode_str = "🔒 Private (Owner/Auth)" if bot_mode == "private" else "🌍 Public (Everyone)"
    
    has_4gb = bool(getattr(client, "app_4gb", None))
    engine_str = "Active 🟢 (4GB Mode)" if has_4gb else "Inactive 🔴 (2GB Mode)"
    
    total_users = await _safe(db.total_users_count(), default=0)
    auth_users  = await _safe(db.get_auth_users(),    default=[])
    banned_users = await _safe(db.get_banned_users(), default=[])
    coupons     = await _safe(db.get_all_coupons(),    default={})
    default_meta = await _safe(db.get_default_metadata(), default="Telegram : @Nex_bots")
    upi_id      = await _safe(db.get_upi_id(), default=getattr(Config, "UPI_ID", "nexbots@upi"))
    usage_stats = await _safe(db.get_global_usage(), default={})

    total_disk, used_disk, free_disk = shutil.disk_usage(".")
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent

    total_prem = usage_stats.get("total_premium", 0)
    silver_cnt = usage_stats.get("silver_users", 0)
    gold_cnt   = usage_stats.get("gold_users", 0)
    diam_cnt   = usage_stats.get("diamond_users", 0)
    trials_cnt = usage_stats.get("trials_claimed", 0)
    tot_files  = usage_stats.get("global_files", 0)
    tot_bytes  = usage_stats.get("global_bytes", 0)

    text = (
        "👑 <b><u>NeX 4GB Owner Control Panel</u></b> ⚡\n\n"
        f"◈ <b>🌐 Bot Mode :</b> <code>{mode_str}</code>\n"
        f"◈ <b>🚀 4GB Engine :</b> <code>{engine_str}</code>\n"
        f"◈ <b>💳 Active UPI :</b> <code>{upi_id}</code>\n"
        f"◈ <b>🏷️ Global Meta :</b> <code>{default_meta}</code>\n\n"
        f"◈ <b>👥 Total Users :</b> <code>{total_users}</code> | <b>Trials :</b> <code>{trials_cnt}</code>\n"
        f"◈ <b>💎 Premium :</b> <code>{total_prem}</code> (🥈{silver_cnt} 🥇{gold_cnt} 💎{diam_cnt})\n"
        f"◈ <b>🛡️ Auth :</b> <code>{len(auth_users)}</code> | <b>🚫 Banned :</b> <code>{len(banned_users)}</code> | <b>🎟️ Coupons :</b> <code>{len(coupons)}</code>\n\n"
        f"◈ <b>📈 Activity :</b> <code>{tot_files}</code> files ({humanbytes(tot_bytes)})\n"
        f"◈ <b>💾 Free Disk :</b> <code>{get_readable_file_size(free_disk)}</code> / <code>{get_readable_file_size(total_disk)}</code>\n"
        f"◈ <b>🖥️ RAM :</b> <code>{ram}%</code> | <b>CPU :</b> <code>{cpu}%</code>\n\n"
        "⚡ <b>NeX 4GB Rename Bot</b> | @Nex_bots"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"🔄 Mode: {'🔒 Private' if bot_mode == 'private' else '🌍 Public'}", callback_data="cb_owner_toggle_mode")
        ],
        [
            InlineKeyboardButton(f"💎 Premium Users ({total_prem})", callback_data="cb_prem_page_0"),
            InlineKeyboardButton(f"🛡️ Auth Users ({len(auth_users)})", callback_data="cb_owner_auth")
        ],
        [
            InlineKeyboardButton(f"🎟️ Coupons ({len(coupons)})", callback_data="cb_owner_coupons"),
            InlineKeyboardButton("📈 Global Analytics", callback_data="cb_owner_analytics")
        ],
        [
            InlineKeyboardButton(f"🚫 Banned Users ({len(banned_users)})", callback_data="cb_owner_banned"),
            InlineKeyboardButton("🏷️ Global Meta", callback_data="cb_owner_meta")
        ],
        [
            InlineKeyboardButton("💳 Update UPI ID", callback_data="cb_owner_set_upi"),
            InlineKeyboardButton("📦 Channels & Dumps", callback_data="cb_owner_channels")
        ],
        [
            InlineKeyboardButton("⚙️ My Rename Settings", callback_data="open_settings"),
            InlineKeyboardButton("📊 Server Stats", callback_data="cb_owner_stats")
        ],
        [
            InlineKeyboardButton("🧹 Clear Cache", callback_data="clear_cache_owner"),
            InlineKeyboardButton("🔄 Restart Bot", callback_data="cb_owner_restart")
        ],
        [
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


@Client.on_message(filters.private & filters.command(["add_prem", "set_prem"]) & filters.user(Config.ADMIN))
async def add_prem_cmd(client, message):
    # Syntax: /add_prem <user_id> [tier 1-3] [days]
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
    # Syntax: /add_coupon <code> <tier 1-3> <days> <max_uses>
    args = message.text.split()
    if len(args) < 5:
        return await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/add_coupon &lt;code&gt; &lt;tier 1-3&gt; &lt;days&gt; &lt;max_uses&gt;</code>\n\n"
            "<i>Example:</i> <code>/add_coupon NEXGOLD 2 7 10</code>\n"
            "(Creates coupon NEXGOLD for Level 2 Gold, 7 days, 10 redemptions)\n\n"
            "⚡ @Nex_bots"
        )
    code = args[1].strip().upper()
    try:
        tier = max(1, min(3, int(args[2].strip())))
        days = int(args[3].strip())
        max_uses = int(args[4].strip())
    except ValueError:
        return await message.reply_text("❌ <b>Invalid Numbers!</b> Tier, days, and max_uses must be integers.")

    coupon = await db.create_coupon(code, tier=tier, days=days, max_uses=max_uses)
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
        return await message.reply_text("🎟️ <b>Active Coupons:</b> None created yet.\n\nUse <code>/add_coupon</code> to create one.")
    
    lines = []
    for c_code, c in coupons.items():
        pname = TIER_NAMES.get(c.get('tier', 1), 'Premium')
        lines.append(f"• <code>{c_code}</code> | {pname} | {c.get('days')}d | Used: {c.get('used_count', 0)}/{c.get('max_uses', 1)}")
    
    await message.reply_text(f"🎟️ <b><u>Active Coupons ({len(coupons)})</u></b>\n\n" + "\n".join(lines) + "\n\n⚡ @Nex_bots")


# ==================== INTERACTIVE OWNER CALLBACKS ====================

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
    curr = await _safe(db.get_bot_mode(), default="private")
    new_mode = "public" if curr == "private" else "private"
    await _safe(db.set_bot_mode(new_mode))
    await query.answer(f"Bot Mode: {new_mode.upper()}! 🌐", show_alert=True)
    text, markup = await build_owner_panel(client)
    await edit_message_content(query.message, text, reply_markup=markup)


# Paginated Premium Users list
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
            text += f"◈ <code>{u['user_id']}</code>\n  {u['plan_name']} | Exp: <code>{exp_str}</code>\n\n"

    text += "⚡ @Nex_bots"

    buttons = []
    # Row of actions for users on this page
    for u in current_users:
        uid = u['user_id']
        tier = u['tier']
        buttons.append([
            InlineKeyboardButton(f"❌ Revoke {uid}", callback_data=f"cb_revoke_prem_{uid}_{page}"),
            InlineKeyboardButton(f"⬆️ Level 3 {uid}", callback_data=f"cb_upgrade_prem_{uid}_{page}")
        ])

    # Navigation buttons
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cb_prem_page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"cb_prem_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("➕ Add Premium Help", callback_data="cb_add_prem_help"),
        InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")
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
    await query.answer(f"Revoked premium for {target_id}!", show_alert=True)
    # Refresh page
    query.matches = [type("MockMatch", (), {"group": lambda s, idx: page})()]
    await cb_prem_page(client, query)


@Client.on_callback_query(filters.regex(r"^cb_upgrade_prem_(\d+)_(\d+)$"))
async def cb_upgrade_prem(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    target_id = int(query.matches[0].group(1))
    page = int(query.matches[0].group(2))
    await db.set_user_premium(target_id, tier=3, days=30, plan_name="💎 Level 3 - Diamond")
    await query.answer(f"Upgraded {target_id} to Diamond (30 Days)!", show_alert=True)
    query.matches = [type("MockMatch", (), {"group": lambda s, idx: page})()]
    await cb_prem_page(client, query)


@Client.on_callback_query(filters.regex(r"^cb_add_prem_help$"))
async def cb_add_prem_help(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    text = (
        "➕ <b><u>Add Premium Command Guide</u></b> ⚡\n\n"
        "<b>Command:</b>\n"
        "<code>/add_prem &lt;user_id&gt; [tier 1-3] [days]</code>\n\n"
        "<b>Examples:</b>\n"
        "• <code>/add_prem 123456789</code> (Tier 3 Diamond, 30d)\n"
        "• <code>/add_prem 123456789 1 30</code> (Tier 1 Silver, 30d)\n"
        "• <code>/add_prem 123456789 2 60</code> (Tier 2 Gold, 60d)\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Premium Users", callback_data="cb_prem_page_0")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_auth$"))
async def cb_owner_auth(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    users = await _safe(db.get_auth_users(), default=[])
    text = (
        "🛡️ <b><u>Authorized Users (Private Mode)</u></b>\n\n"
        f"• <b>Count :</b> <code>{len(users)}</code>\n\n"
    )
    if users:
        text += "◈ <b>Active IDs :</b>\n" + ", ".join([f"<code>{u}</code>" for u in users[:12]]) + "\n\n"
    else:
        text += "<i>No authorized users. Only Admins can access in Private Mode.</i>\n\n"

    text += (
        "<b>Commands:</b>\n"
        "• <code>/add_user &lt;id&gt;</code>\n"
        "• <code>/rem_user &lt;id&gt;</code>\n\n"
        "⚡ @Nex_bots"
    )

    buttons = []
    # One-click delete buttons for up to 6 users
    for uid in users[:6]:
        buttons.append([InlineKeyboardButton(f"🗑️ Remove {uid}", callback_data=f"cb_del_auth_{uid}")])

    buttons.append([InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")])
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


@Client.on_callback_query(filters.regex(r"^cb_owner_banned$"))
async def cb_owner_banned(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    users = await _safe(db.get_banned_users(), default=[])
    text = (
        "🚫 <b><u>Banned Users Management</u></b>\n\n"
        f"• <b>Count :</b> <code>{len(users)}</code>\n\n"
    )
    if users:
        text += "◈ <b>Banned IDs :</b>\n" + ", ".join([f"<code>{u}</code>" for u in users[:12]]) + "\n\n"
    else:
        text += "<i>No users are currently banned.</i>\n\n"

    text += (
        "<b>Commands:</b>\n"
        "• <code>/ban &lt;id&gt;</code>\n"
        "• <code>/unban &lt;id&gt;</code>\n\n"
        "⚡ @Nex_bots"
    )

    buttons = []
    for uid in users[:6]:
        buttons.append([InlineKeyboardButton(f"✅ Unban {uid}", callback_data=f"cb_del_ban_{uid}")])

    buttons.append([InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")])
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


@Client.on_callback_query(filters.regex(r"^cb_owner_coupons$"))
async def cb_owner_coupons(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    coupons = await _safe(db.get_all_coupons(), default={})
    text = (
        "🎟️ <b><u>Coupon Code Manager</u></b> ⚡\n\n"
        f"• <b>Active Coupons :</b> <code>{len(coupons)}</code>\n\n"
    )
    if not coupons:
        text += "<i>No active coupons. Tap 'Quick Coupon' to generate one!</i>\n\n"
    else:
        for code, c in list(coupons.items())[:6]:
            pname = TIER_NAMES.get(c.get('tier', 1), 'Premium')
            text += f"◈ <code>{code}</code> | {pname} ({c.get('days')}d) | Used: <code>{c.get('used_count', 0)}/{c.get('max_uses', 1)}</code>\n"
        text += "\n"

    text += (
        "<b>Create Command:</b>\n"
        "<code>/add_coupon &lt;code&gt; &lt;tier 1-3&gt; &lt;days&gt; &lt;max_uses&gt;</code>\n\n"
        "⚡ @Nex_bots"
    )

    buttons = []
    # One-click delete for existing coupons
    for code in list(coupons.keys())[:4]:
        buttons.append([InlineKeyboardButton(f"🗑️ Delete {code}", callback_data=f"cb_del_coupon_{code}")])

    buttons.append([InlineKeyboardButton("🎲 Generate Quick Coupon", callback_data="cb_gen_quick_coupon")])
    buttons.append([InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")])

    await edit_message_content(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_gen_quick_coupon$"))
async def cb_gen_quick_coupon(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    
    rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    code = f"GOLD7D_{rnd}"
    await db.create_coupon(code, tier=2, days=7, max_uses=5)
    await query.answer(f"Created coupon {code}! (7 Days Gold, 5 uses)", show_alert=True)
    await cb_owner_coupons(client, query)


@Client.on_callback_query(filters.regex(r"^cb_del_coupon_(.+)$"))
async def cb_del_coupon(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    code = query.matches[0].group(1)
    await db.delete_coupon(code)
    await query.answer(f"Coupon {code} deleted!", show_alert=True)
    await cb_owner_coupons(client, query)


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
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_owner_set_upi$"))
async def cb_owner_set_upi_cb(client, query: CallbackQuery):
    if query.from_user.id not in Config.ADMIN:
        return await query.answer("❌ Owner only access!", show_alert=True)
    current_upi = await db.get_upi_id()
    text = (
        "💳 <b><u>Update UPI ID</u></b> ⚡\n\n"
        f"◈ <b>Current UPI :</b> <code>{current_upi}</code>\n\n"
        "To update the UPI ID shown on user payment screens, send:\n"
        "<code>/set_upi &lt;your_new_upi&gt;</code>\n\n"
        "<i>Example:</i> <code>/set_upi nexbots@okaxis</code>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]])
    await edit_message_content(query.message, text, reply_markup=markup)
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
        f"• <b>Your Private Dump:</b> <code>{owner_dump or 'None'}</code>\n"
        f"• <b>Support Bot:</b> <code>@NexCRSupportbot</code>\n\n"
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
    
    # Split by | or newline
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


# ==================== LEGACY /status & /restart ====================

@Client.on_message(filters.command(["stats", "status"]) & filters.user(Config.ADMIN))
async def get_stats(bot, message):
    st = await message.reply('⏳ <b>Calculating System Statistics...</b>')
    start_t = time.time()
    
    total_users = await db.total_users_count()
    uptime = time.strftime("%Hh %Mm %Ss", time.gmtime(time.time() - bot.uptime))
    end_t = time.time()
    ping_ms = (end_t - start_t) * 1000
    
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
        f"⚡ <b>Powered by :</b> @Nex_bots | 💬 Support: @NexCRSupportbot"
    )
    await st.edit(text=stats_text)


@Client.on_message(filters.private & filters.command("restart") & filters.user(Config.ADMIN))
async def restart_bot(b, m):
    await m.reply_text("<b>🔄 Restarting NeX 4GB Rename Bot Engine.....</b>\n\n⚡ @Nex_bots")
    os.execl(sys.executable, sys.executable, *sys.argv)
