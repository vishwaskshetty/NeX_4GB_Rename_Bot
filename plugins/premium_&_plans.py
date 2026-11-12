import re
import time
import asyncio
from datetime import datetime
import pytz
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    PreCheckoutQuery
)

from config import Config
from helper.database import db, TIER_NAMES, TIER_LIMITS, PLAN_DURATIONS, PLAN_PRICING, format_user_time
from helper.utils import get_readable_file_size, humanbytes, edit_message_content

# NeX 4GB Rename Bot - Multi-Duration Premium Plans, Stars/UPI Payments, Profiles & Timezones
# Developed by @Nex_bots

_DB_TIMEOUT = 5

async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except Exception:
        return default


DURATION_LABELS = {
    30: "1 Month (30 Days)",
    90: "3 Months (90 Days)",
    180: "6 Months (180 Days)",
    365: "1 Year (365 Days)"
}

TIER_INFO = {
    1: {
        "icon": "🥈",
        "name": "Silver Tier",
        "size": "4GB Max File Size",
        "daily": "25 GB / Day",
        "speed": "12 MB/s Fast Speed",
        "conc": "2 Tasks Concurrency",
        "features": "4GB Uploads + Custom Metadata + Cleaner"
    },
    2: {
        "icon": "🥇",
        "name": "Gold Tier",
        "size": "4GB Max File Size",
        "daily": "100 GB / Day",
        "speed": "25 MB/s Blazing Speed",
        "conc": "3 Tasks Concurrency",
        "features": "4GB Uploads + Sample Video + Screenshots + Watermark"
    },
    3: {
        "icon": "💎",
        "name": "Diamond VIP",
        "size": "4GB Max File Size",
        "daily": "UNLIMITED Bandwidth",
        "speed": "⚡ Unlimited VIP Speed",
        "conc": "5 Tasks Concurrency",
        "features": "4GB Uploads + Priority Queue + All Video Tools"
    }
}


# ==================== PLANS HUB BUILDER ====================

async def build_plans_panel(user_id: int):
    prem_info = await db.get_premium_info(user_id)
    has_trial = await db.has_claimed_trial(user_id)
    
    current_plan = prem_info.get("plan_name", "Free")
    trial_status = "Claimed ✅" if has_trial else "Available 🎁"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   💎 <b>NeX 4GB Premium Hub</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Your Status :</b> <b>{current_plan}</b>\n"
        f"◈ <b>3-Day Trial :</b> <code>{trial_status}</code>\n\n"
        "<b>Choose Your Premium Tier:</b>\n"
        "🥈 <b>Silver :</b> 4GB | 25 GB/Day | 12 MB/s | from ₹79 / 70 ⭐\n"
        "🥇 <b>Gold :</b> 4GB | 100 GB/Day | 25 MB/s | from ₹129 / 110 ⭐\n"
        "💎 <b>Diamond VIP :</b> 4GB | <b>UNLIMITED</b> | Max Speed | from ₹199 / 175 ⭐\n\n"
        "<i>All tiers available for 1M, 3M, 6M, or 1 Year (Min 1 Month).</i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    buttons = []
    if not has_trial:
        buttons.append([InlineKeyboardButton("🎁 Claim 3-Day Free Gold Trial", callback_data="claim_trial_cb")])

    buttons.extend([
        [
            InlineKeyboardButton("🥈 Silver Tier", callback_data="plan_tier_1"),
            InlineKeyboardButton("🥇 Gold Tier", callback_data="plan_tier_2")
        ],
        [
            InlineKeyboardButton("💎 Diamond VIP Tier", callback_data="plan_tier_3")
        ],
        [
            InlineKeyboardButton("👤 My Profile & Plan", callback_data="cb_user_profile"),
            InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="redeem_coupon_btn")
        ],
        [
            InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot"),
            InlineKeyboardButton("⬅️ Back", callback_data="start")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])

    return text, InlineKeyboardMarkup(buttons)


async def build_tier_durations_view(tier: int):
    info = TIER_INFO.get(tier, TIER_INFO[1])
    prices = PLAN_PRICING.get(tier, PLAN_PRICING[1])

    text = (
        f"╭━━━━━━━━━━━━━━━━━━━╮\n"
        f"┃   {info['icon']} <b>{info['name']} Plans</b>\n"
        f"╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Max File Size :</b> {info['size']}\n"
        f"◈ <b>Daily Bandwidth :</b> {info['daily']}\n"
        f"◈ <b>Max Transfer Speed :</b> {info['speed']}\n"
        f"◈ <b>Concurrency :</b> {info['conc']}\n"
        f"◈ <b>Features :</b> {info['features']}\n\n"
        "<b>Available Durations & Pricing:</b>\n"
        f"• <b>1 Month (30D) :</b> ₹{prices[30]['inr']} INR / {prices[30]['stars']} ⭐\n"
        f"• <b>3 Months (90D) :</b> ₹{prices[90]['inr']} INR / {prices[90]['stars']} ⭐\n"
        f"• <b>6 Months (180D) :</b> ₹{prices[180]['inr']} INR / {prices[180]['stars']} ⭐\n"
        f"• <b>1 Year (365D) :</b> ₹{prices[365]['inr']} INR / {prices[365]['stars']} ⭐\n\n"
        "<i>Select duration below to proceed to checkout:</i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"📅 1M (₹{prices[30]['inr']} / {prices[30]['stars']}⭐)", callback_data=f"buy_{tier}_30"),
            InlineKeyboardButton(f"📅 3M (₹{prices[90]['inr']} / {prices[90]['stars']}⭐)", callback_data=f"buy_{tier}_90")
        ],
        [
            InlineKeyboardButton(f"📅 6M (₹{prices[180]['inr']} / {prices[180]['stars']}⭐)", callback_data=f"buy_{tier}_180"),
            InlineKeyboardButton(f"📅 1Y (₹{prices[365]['inr']} / {prices[365]['stars']}⭐)", callback_data=f"buy_{tier}_365")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Tiers", callback_data="open_plans"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


async def build_checkout_view(tier: int, days: int):
    info = TIER_INFO.get(tier, TIER_INFO[1])
    prices = PLAN_PRICING.get(tier, {}).get(days, {"inr": 99, "stars": 100})
    dur_label = DURATION_LABELS.get(days, f"{days} Days")

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   💳 <b>NeX Plan Checkout</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Selected Plan :</b> {info['icon']} <b>{info['name']}</b>\n"
        f"◈ <b>Duration :</b> <code>{dur_label}</code>\n"
        f"◈ <b>Max File Size :</b> 4GB Mode\n"
        f"◈ <b>Daily Limit :</b> {info['daily']}\n"
        f"◈ <b>Speed Cap :</b> {info['speed']}\n\n"
        f"◈ <b>Price (Stars) :</b> <code>{prices['stars']} ⭐</code> (1-Tap Native)\n"
        f"◈ <b>Price (INR) :</b> <code>₹{prices['inr']} INR</code> (GPay/PhonePe/UPI)\n\n"
        "<i>Choose your preferred payment method below:</i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ Pay with Stars ({prices['stars']} XTR)", callback_data=f"pay_stars_{tier}_{days}")],
        [InlineKeyboardButton(f"🇮🇳 Pay via UPI (₹{prices['inr']})", callback_data=f"pay_upi_{tier}_{days}")],
        [InlineKeyboardButton("⬅️ Back to Durations", callback_data=f"plan_tier_{tier}"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


# ==================== PROFILE CARD BUILDER ====================

async def build_profile_card(user_id: int):
    prem_info = await db.get_premium_info(user_id)
    usage = await db.get_user_usage(user_id)
    tz_name = await db.get_timezone(user_id)
    settings = await db.get_user_settings(user_id)
    wm = await db.get_watermark(user_id)
    sample_set = await db.get_sample_settings(user_id)

    tier = prem_info.get("tier", 0)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS[0])
    daily_limit = limits["daily_bytes"]

    used_bytes = usage.get("daily_bytes", 0)
    used_gb = used_bytes / (1024 ** 3)
    limit_gb = daily_limit / (1024 ** 3)

    tier_badges = {3: "💎 PRO - Diamond", 2: "🥇 PRO - Gold", 1: "🥈 PRO - Silver", 0: "🆓 Free User"}
    badge = tier_badges.get(tier, "🆓 Free User")

    if prem_info.get("is_owner"):
        badge = "👑 Bot Owner (VIP)"
        countdown_str = "Permanent Lifetime"
        expiry_str = "Never Expires"
        limit_str = "Unlimited"
        speed_str = "⚡ Unlimited VIP Speed"
        pct = 0
    elif tier > 0:
        d = prem_info.get("days_left", 0)
        h = prem_info.get("hours_left", 0)
        countdown_str = f"{d}d {h}h remaining"
        expiry_str = format_user_time(prem_info.get("expiry", 0), tz_name)
        limit_str = f"{limit_gb:.0f} GB" if tier < 3 else "Unlimited"
        speed_str = TIER_INFO.get(tier, {}).get("speed", "High Speed")
        pct = min(100, int((used_bytes / daily_limit) * 100)) if tier < 3 else 0
    else:
        countdown_str = "Free Tier"
        expiry_str = "None"
        limit_str = f"{limit_gb:.0f} GB"
        speed_str = "3.5 MB/s (Free Limit)"
        pct = min(100, int((used_bytes / daily_limit) * 100))

    blocks = min(10, pct // 10)
    bar = "■" * blocks + "□" * (10 - blocks)

    file_mode = "Video 🎬" if settings.get("as_file") is False else "Document 📁"
    thumb_str = "Custom Set ✅" if settings.get("thumbnail") else "Default ❌"
    wm_str = f"Active ({wm.get('text')[:8]}..)" if wm.get("enabled") and tier >= 1 else "None ❌"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   👤 <b>NeX User Profile & Stats</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>User ID :</b> <code>{user_id}</code>\n"
        f"◈ <b>Membership :</b> <b>[{badge}]</b>\n"
        f"◈ <b>Speed Cap :</b> <code>{speed_str}</code>\n"
        f"◈ <b>Expiry :</b> <code>{expiry_str}</code> ({countdown_str})\n"
        f"◈ <b>Timezone :</b> <code>{tz_name}</code>\n\n"
        f"◈ <b>Today's Bandwidth :</b>\n"
        f"  <code>[{bar}]</code> {used_gb:.2f} GB / {limit_str} ({pct}%)\n"
        f"  <i>Files renamed today: {usage.get('daily_files', 0)}</i>\n\n"
        f"◈ <b>Lifetime Activity :</b>\n"
        f"  • Files: <code>{usage.get('total_files', 0)}</code> | Bandwidth: <code>{humanbytes(usage.get('total_bytes', 0))}</code>\n\n"
        f"◈ <b>Active Setup :</b> Mode: <code>{file_mode}</code> | Thumb: <code>{thumb_str}</code> | WM: <code>{wm_str}</code>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Upgrade / Extend Plan", callback_data="open_plans"),
         InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="cb_leaderboard"),
         InlineKeyboardButton("🔄 Refresh", callback_data="cb_user_profile")],
        [InlineKeyboardButton("⬅️ Back to Start", callback_data="start"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


# ==================== TIMEZONE MENU BUILDER ====================

async def build_timezone_menu(user_id: int):
    current_tz = await db.get_timezone(user_id)
    now_str = format_user_time(time.time(), current_tz)
    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   🌍 <b>Timezone Configuration</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Active Timezone :</b> <code>{current_tz}</code>\n"
        f"◈ <b>Current Local Time :</b> <code>{now_str}</code>\n\n"
        "<i>Select a region below or type <code>/timezone Region/City</code>:</i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇮🇳 IST (India)", callback_data="select_tz_Asia/Kolkata"),
            InlineKeyboardButton("🌐 UTC", callback_data="select_tz_UTC")
        ],
        [
            InlineKeyboardButton("🇺🇸 New York (EST)", callback_data="select_tz_America/New_York"),
            InlineKeyboardButton("🇬🇧 London (GMT)", callback_data="select_tz_Europe/London")
        ],
        [
            InlineKeyboardButton("🇦🇪 Dubai (GST)", callback_data="select_tz_Asia/Dubai"),
            InlineKeyboardButton("🇸🇬 Singapore (SGT)", callback_data="select_tz_Asia/Singapore")
        ],
        [
            InlineKeyboardButton("🇦🇺 Sydney (AEST)", callback_data="select_tz_Australia/Sydney")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Settings", callback_data="open_settings"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, keyboard


# ==================== COMMAND HANDLERS ====================

@Client.on_message(filters.private & filters.command(["plan", "plans", "premium"]))
async def plans_cmd(client, message):
    text, markup = await build_plans_panel(message.from_user.id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command(["profile", "myplan", "usage"]))
async def profile_cmd(client, message):
    text, markup = await build_profile_card(message.from_user.id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command(["trial", "free_trial"]))
async def trial_cmd(client, message):
    user_id = message.from_user.id
    if await db.has_claimed_trial(user_id):
        return await message.reply_text(
            "⚠️ <b>You have already claimed your one-time 3-Day Free Trial!</b>\n\n"
            "To continue enjoying 4GB high-speed uploads, view our affordable plans via <code>/plan</code>.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 View Plans", callback_data="open_plans")]])
        )

    success = await db.claim_free_trial(user_id)
    if success:
        prem_info = await db.get_premium_info(user_id)
        tz_name = await db.get_timezone(user_id)
        expiry_str = format_user_time(prem_info.get("expiry", 0), tz_name)
        await db.log_activity(user_id, message.from_user.first_name, "claim_trial", "3-Day Free Gold Trial")
        await message.reply_text(
            "🎉 <b>Congratulations! 3-Day Gold Trial Activated!</b> ⚡\n\n"
            "◈ <b>Tier :</b> 🥇 Level 2 - Gold (4GB Mode)\n"
            "◈ <b>Daily Limit :</b> 100 GB / day\n"
            f"◈ <b>Valid Until :</b> <code>{expiry_str}</code>\n\n"
            "Enjoy ultra-fast 4GB transfers! Powered by @Nex_bots",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
                 InlineKeyboardButton("👤 My Profile", callback_data="cb_user_profile")]
            ])
        )
        if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
            try:
                await client.send_message(
                    Config.LOG_CHANNEL,
                    f"🎁 <b>3-Day Free Trial Claimed!</b>\n\n"
                    f"👤 <b>User:</b> {message.from_user.mention} (<code>{user_id}</code>)\n"
                    f"📅 <b>Expires:</b> <code>{expiry_str}</code>\n\n"
                    f"⚡ @Nex_bots"
                )
            except Exception:
                pass


@Client.on_message(filters.private & filters.command(["redeem", "coupon"]))
async def redeem_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text(
            "⚠️ <b>Usage:</b> <code>/redeem &lt;coupon_code&gt;</code>\n\n"
            "<i>Example:</i> <code>/redeem NEXGOLD</code>\n\n"
            "⚡ @Nex_bots"
        )
    code = args[1].strip()
    success, reply_msg = await db.redeem_coupon(message.from_user.id, code)
    if success:
        await db.log_activity(message.from_user.id, message.from_user.first_name, "redeem_coupon", f"Code: {code}")
    await message.reply_text(reply_msg)


@Client.on_message(filters.private & filters.command("timezone"))
async def timezone_cmd(client, message):
    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id
    if len(args) > 1:
        tz_target = args[1].strip()
        ok = await db.set_timezone(user_id, tz_target)
        if ok:
            now_str = format_user_time(time.time(), tz_target)
            return await message.reply_text(
                f"✅ <b>Timezone Updated!</b>\n\n"
                f"◈ <b>Zone :</b> <code>{tz_target}</code>\n"
                f"◈ <b>Local Time :</b> <code>{now_str}</code>\n\n"
                f"⚡ @Nex_bots"
            )
        else:
            return await message.reply_text("❌ <b>Invalid Timezone!</b> Example: <code>/timezone Asia/Kolkata</code>")

    text, markup = await build_timezone_menu(user_id)
    await message.reply_text(text, reply_markup=markup)


# ==================== CALLBACK QUERY ROUTING ====================

@Client.on_callback_query(filters.regex(r"^open_plans$"))
async def open_plans_cb(client, query: CallbackQuery):
    text, markup = await build_plans_panel(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^(cb_user_profile|my_plan_cb)$"))
async def user_profile_cb(client, query: CallbackQuery):
    text, markup = await build_profile_card(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^claim_trial_cb$"))
async def claim_trial_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    if await db.has_claimed_trial(user_id):
        return await query.answer("⚠️ You have already claimed your one-time 3-Day Free Trial!", show_alert=True)

    success = await db.claim_free_trial(user_id)
    if success:
        await db.log_activity(user_id, query.from_user.first_name, "claim_trial", "3-Day Free Gold Trial")
        await query.answer("🎉 3-Day Gold Trial Activated Successfully!", show_alert=True)
        text, markup = await build_plans_panel(user_id)
        await edit_message_content(query.message, text, reply_markup=markup)
        if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
            try:
                await client.send_message(
                    Config.LOG_CHANNEL,
                    f"🎁 <b>3-Day Free Trial Claimed!</b>\n\n"
                    f"👤 <b>User:</b> {query.from_user.mention} (<code>{user_id}</code>)\n"
                    f"⚡ @Nex_bots"
                )
            except Exception:
                pass
    else:
        await query.answer("❌ Failed to claim trial.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^plan_tier_(\d+)$"))
async def plan_tier_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    text, markup = await build_tier_durations_view(tier)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^buy_(\d+)_(\d+)$"))
async def buy_tier_dur_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    text, markup = await build_checkout_view(tier, days)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^pay_upi_(\d+)_(\d+)$"))
async def pay_upi_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    upi_id = await db.get_upi_id()
    prices = PLAN_PRICING.get(tier, {}).get(days, {"inr": 99, "stars": 100})
    tier_info = TIER_INFO.get(tier, TIER_INFO[1])
    dur_label = DURATION_LABELS.get(days, f"{days} Days")

    text = (
        f"🇮🇳 <b><u>UPI Payment - {tier_info['name']}</u></b> ⚡\n\n"
        f"◈ <b>Plan :</b> {tier_info['icon']} <b>{tier_info['name']}</b> ({dur_label})\n"
        f"◈ <b>Amount to Pay :</b> <code>₹{prices['inr']}</code> INR\n"
        f"◈ <b>UPI ID :</b> <code>{upi_id}</code> (tap to copy)\n\n"
        "<b>Steps to Complete:</b>\n"
        f"1. Send <b>₹{prices['inr']}</b> to <code>{upi_id}</code> via GPay / PhonePe / Paytm / BHIM.\n"
        "2. Take a clear screenshot showing Transaction / UTR ID.\n"
        f"3. Send screenshot to <b>@NexCRSupportbot</b> with your User ID (<code>{query.from_user.id}</code>).\n\n"
        "<i>Activation completes in 5-15 minutes upon verification!</i>\n\n"
        "⚡ @Nex_bots"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Screenshot (@NexCRSupportbot)", url="https://t.me/NexCRSupportbot")],
        [InlineKeyboardButton("🔔 Notify Admin of Transfer", callback_data=f"notify_upi_paid_{tier}_{days}")],
        [InlineKeyboardButton("⬅️ Back to Checkout", callback_data=f"buy_{tier}_{days}"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^notify_upi_paid_(\d+)_(\d+)$"))
async def notify_upi_paid_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    tier_info = TIER_INFO.get(tier, TIER_INFO[1])
    user = query.from_user

    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"🔔 <b>UPI Payment Claimed!</b>\n\n"
                f"👤 <b>User:</b> {user.mention} (<code>{user.id}</code>)\n"
                f"💎 <b>Requested Tier:</b> {tier_info['name']} ({days} Days)\n"
                f"⏰ <b>Time:</b> <code>{format_user_time(time.time())}</code>\n\n"
                f"<i>Please verify screenshot at @NexCRSupportbot and approve via <code>/add_prem {user.id} {tier} {days}</code>.</i>\n\n"
                f"⚡ @Nex_bots"
            )
        except Exception:
            pass

    await query.answer("🔔 Support & Admin notified! Please make sure to forward your payment screenshot to @NexCRSupportbot.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^pay_stars_(\d+)_(\d+)$"))
async def pay_stars_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    days = int(query.matches[0].group(2))
    prices = PLAN_PRICING.get(tier, {}).get(days, {"inr": 99, "stars": 100})
    stars = prices["stars"]
    tier_info = TIER_INFO.get(tier, TIER_INFO[1])
    dur_label = DURATION_LABELS.get(days, f"{days} Days")

    try:
        await client.send_invoice(
            chat_id=query.message.chat.id,
            title=f"NeX 4GB - {tier_info['name']}",
            description=f"{dur_label} of {tier_info['name']} 4GB High-Speed Rename Access",
            payload=f"premium_tier_{tier}_{days}d",
            currency="XTR",
            prices=[LabeledPrice(label=f"{tier_info['name']} ({days}D)", amount=stars)],
            provider_token=""
        )
        await query.answer("⭐ Invoice sent! Tap 'Pay' on the invoice above.", show_alert=False)
    except Exception as e:
        await query.answer(f"❌ Error creating Stars invoice: {e}", show_alert=True)


@Client.on_pre_checkout_query()
async def pre_checkout_handler(client, pre_checkout_query: PreCheckoutQuery):
    try:
        await pre_checkout_query.answer(ok=True)
    except Exception:
        pass


@Client.on_message(filters.successful_payment)
async def successful_payment_handler(client, message: Message):
    payload = message.successful_payment.invoice_payload
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    # Donation check
    if payload.startswith("donation_"):
        match_don = re.search(r'donation_(\d+)_stars', payload)
        don_amount = int(match_don.group(1)) if match_don else message.successful_payment.total_amount
        await db.log_activity(user_id, user_name, "donation", f"{don_amount} Stars")
        await message.reply_text(
            f"❤️ <b>Thank you so much for your donation of {don_amount} Telegram Stars!</b>\n\n"
            f"Your generous support helps keep NeX 4GB Rename Bot fast, free, and continuously updated for everyone! ⚡\n\n"
            f"⚡ @Nex_bots",
            quote=True
        )
        if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
            try:
                await client.send_message(
                    Config.LOG_CHANNEL,
                    f"❤️ <b>New Stars Donation!</b>\n\n"
                    f"👤 <b>Donor:</b> {message.from_user.mention} (<code>{user_id}</code>)\n"
                    f"⭐ <b>Amount:</b> {don_amount} Stars\n\n"
                    f"⚡ @Nex_bots"
                )
            except Exception:
                pass
        return

    # Premium Tier check
    match = re.search(r'premium_tier_(\d+)_(\d+)d', payload)
    if match:
        tier = int(match.group(1))
        days = int(match.group(2))
        await db.set_user_premium(user_id, tier=tier, days=days)
        tier_title = TIER_NAMES.get(tier, "Premium")
        tz_name = await db.get_timezone(user_id)
        prem_info = await db.get_premium_info(user_id)
        expiry_str = format_user_time(prem_info.get("expiry", 0), tz_name)
        stars_paid = message.successful_payment.total_amount

        await db.log_activity(user_id, user_name, "buy_premium", f"{tier_title} ({days}D) for {stars_paid} Stars")

        await message.reply_text(
            f"🎉 <b>Payment Successful!</b>\n\n"
            f"Your <b>{tier_title}</b> is active for <b>{days} days</b>!\n"
            f"◈ <b>Expires :</b> <code>{expiry_str}</code>\n\n"
            f"⚡ Thank you for supporting @Nex_bots!",
            quote=True
        )

        if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
            try:
                await client.send_message(
                    Config.LOG_CHANNEL,
                    f"⭐ <b>Telegram Stars Payment!</b>\n\n"
                    f"👤 <b>User:</b> {message.from_user.mention} (<code>{user_id}</code>)\n"
                    f"💎 <b>Tier:</b> {tier_title} ({days} Days)\n"
                    f"💰 <b>Stars:</b> {stars_paid} XTR\n"
                    f"📅 <b>Expiry:</b> <code>{expiry_str}</code>\n\n"
                    f"⚡ @Nex_bots"
                )
            except Exception:
                pass


@Client.on_callback_query(filters.regex(r"^redeem_coupon_btn$"))
async def redeem_coupon_btn_cb(client, query: CallbackQuery):
    text = (
        "🎟️ <b><u>Redeem Coupon Code</u></b> ⚡\n\n"
        "To redeem a coupon code, simply send:\n"
        "<code>/redeem &lt;your_code&gt;</code>\n\n"
        "<i>Example:</i> <code>/redeem NEXGOLD</code>\n\n"
        "<i>Coupon codes grant instant free days of Silver, Gold, or Diamond 4GB Premium!</i>\n\n"
        "⚡ @Nex_bots"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Plans", callback_data="open_plans")]])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^open_timezone_menu$"))
async def open_timezone_menu_cb(client, query: CallbackQuery):
    text, markup = await build_timezone_menu(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^select_tz_(.+)$"))
async def select_tz_cb(client, query: CallbackQuery):
    tz_target = query.matches[0].group(1)
    ok = await db.set_timezone(query.from_user.id, tz_target)
    if ok:
        await query.answer(f"Timezone set to {tz_target}! 🌍", show_alert=True)
        text, markup = await build_timezone_menu(query.from_user.id)
        await edit_message_content(query.message, text, reply_markup=markup)
    else:
        await query.answer("❌ Invalid timezone selected.", show_alert=True)
