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
from helper.database import db, TIER_NAMES, TIER_LIMITS, format_user_time
from helper.utils import get_readable_file_size, humanbytes, edit_message_content

# NeX 4GB Rename Bot - Premium Plans, Stars/UPI Payments, Free Trial & Timezones
# Developed by @Nex_bots

_DB_TIMEOUT = 5

async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except Exception:
        return default


# ==================== PLANS HUB BUILDER ====================

async def build_plans_panel(user_id: int):
    prem_info = await db.get_premium_info(user_id)
    has_trial = await db.has_claimed_trial(user_id)
    
    current_plan = prem_info.get("plan_name", "Free")
    trial_status = "Claimed ✅" if has_trial else "Available 🎁"

    text = (
        "💎 <b><u>NeX 4GB Premium & Plans Hub</u></b> ⚡\n\n"
        f"◈ <b>Your Status :</b> <b>{current_plan}</b>\n"
        f"◈ <b>3-Day Trial :</b> <code>{trial_status}</code>\n\n"
        "<b>Available Premium Levels:</b>\n\n"
        "🥈 <b>Level 1: Silver (30 Days)</b>\n"
        "• 4GB Uploads | 25 GB/Day | 2 Concurrency\n"
        "• Price: ⭐ 50 Stars | ₹49 UPI\n\n"
        "🥇 <b>Level 2: Gold (30 Days)</b>\n"
        "• 4GB Uploads | 75 GB/Day | 3 Concurrency + Video Tools\n"
        "• Price: ⭐ 100 Stars | ₹99 UPI\n\n"
        "💎 <b>Level 3: Diamond (30 Days)</b>\n"
        "• 4GB Uploads | <b>UNLIMITED</b> | 5 Concurrency + VIP Queue\n"
        "• Price: ⭐ 200 Stars | ₹199 UPI\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    buttons = []
    if not has_trial:
        buttons.append([InlineKeyboardButton("🎁 Claim 3-Day Free Gold Trial", callback_data="claim_trial_cb")])

    buttons.extend([
        [
            InlineKeyboardButton("🥈 Silver (₹49)", callback_data="plan_details_1"),
            InlineKeyboardButton("🥇 Gold (₹99)", callback_data="plan_details_2")
        ],
        [
            InlineKeyboardButton("💎 Diamond VIP (₹199)", callback_data="plan_details_3")
        ],
        [
            InlineKeyboardButton("📊 My Plan & Usage", callback_data="my_plan_cb"),
            InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="redeem_coupon_btn")
        ],
        [
            InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot"),
            InlineKeyboardButton("🔙 Back to Start", callback_data="start")
        ]
    ])

    return text, InlineKeyboardMarkup(buttons)


# ==================== COMMAND HANDLERS ====================

@Client.on_message(filters.private & filters.command(["plan", "plans", "premium"]))
async def plans_cmd(client, message):
    text, markup = await build_plans_panel(message.from_user.id)
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
        await message.reply_text(
            "🎉 <b>Congratulations! 3-Day Gold Trial Activated!</b> ⚡\n\n"
            "◈ <b>Tier :</b> 🥇 Level 2 - Gold (4GB Mode)\n"
            "◈ <b>Daily Limit :</b> 75 GB / day\n"
            f"◈ <b>Valid Until :</b> <code>{expiry_str}</code>\n\n"
            "Enjoy ultra-fast 4GB transfers! Powered by @Nex_bots",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
                 InlineKeyboardButton("📊 My Usage", callback_data="my_plan_cb")]
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


@Client.on_message(filters.private & filters.command(["myplan", "usage"]))
async def usage_cmd(client, message):
    user_id = message.from_user.id
    text, markup = await build_usage_card(user_id)
    await message.reply_text(text, reply_markup=markup)


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


# ==================== CARD BUILDERS ====================

async def build_usage_card(user_id: int):
    prem_info = await db.get_premium_info(user_id)
    usage = await db.get_user_usage(user_id)
    tz_name = await db.get_timezone(user_id)

    tier = prem_info.get("tier", 0)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS[0])
    daily_limit = limits["daily_bytes"]

    used_bytes = usage.get("daily_bytes", 0)
    used_gb = used_bytes / (1024 ** 3)
    limit_gb = daily_limit / (1024 ** 3)

    if prem_info.get("is_owner"):
        countdown_str = "Permanent VIP"
        expiry_str = "Lifetime"
        limit_str = "Unlimited"
        pct = 0
    elif tier > 0:
        d = prem_info.get("days_left", 0)
        h = prem_info.get("hours_left", 0)
        countdown_str = f"{d}d {h}h left"
        expiry_str = format_user_time(prem_info.get("expiry", 0), tz_name)
        limit_str = f"{limit_gb:.0f} GB" if tier < 3 else "Unlimited"
        pct = min(100, int((used_bytes / daily_limit) * 100)) if tier < 3 else 0
    else:
        countdown_str = "Free Tier"
        expiry_str = "None"
        limit_str = f"{limit_gb:.0f} GB"
        pct = min(100, int((used_bytes / daily_limit) * 100))

    blocks = min(10, pct // 10)
    bar = "■" * blocks + "□" * (10 - blocks)

    text = (
        f"📊 <b><u>My Plan & Usage Dashboard</u></b> ⚡\n\n"
        f"◈ <b>User ID :</b> <code>{user_id}</code>\n"
        f"◈ <b>Current Tier :</b> <b>{prem_info['plan_name']}</b>\n"
        f"◈ <b>Plan Expiry :</b> <code>{expiry_str}</code> ({countdown_str})\n"
        f"◈ <b>Timezone :</b> <code>{tz_name}</code>\n\n"
        f"◈ <b>Today's Bandwidth :</b>\n"
        f"  <code>[{bar}]</code> {used_gb:.2f} GB / {limit_str}\n"
        f"  <i>Files renamed today: {usage.get('daily_files', 0)}</i>\n\n"
        f"◈ <b>Lifetime Activity :</b>\n"
        f"  • Total Files: <code>{usage.get('total_files', 0)}</code>\n"
        f"  • Total Bandwidth: <code>{humanbytes(usage.get('total_bytes', 0))}</code>\n\n"
        f"⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Upgrade / Extend Plan", callback_data="open_plans")],
        [InlineKeyboardButton("🌍 Change Timezone", callback_data="open_timezone_menu"),
         InlineKeyboardButton("🔄 Refresh", callback_data="my_plan_cb")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="open_settings")]
    ])
    return text, keyboard


async def build_timezone_menu(user_id: int):
    current_tz = await db.get_timezone(user_id)
    now_str = format_user_time(time.time(), current_tz)
    text = (
        "🌍 <b><u>Timezone Configuration</u></b> ⚡\n\n"
        f"◈ <b>Active Timezone :</b> <code>{current_tz}</code>\n"
        f"◈ <b>Current Local Time :</b> <code>{now_str}</code>\n\n"
        "<i>Select a region below or type <code>/timezone Region/City</code>:</i>\n\n"
        "⚡ @Nex_bots"
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
            InlineKeyboardButton("🔙 Back to Usage", callback_data="my_plan_cb")
        ]
    ])
    return text, keyboard


# ==================== CALLBACK QUERY ROUTING ====================

@Client.on_callback_query(filters.regex(r"^open_plans$"))
async def open_plans_cb(client, query: CallbackQuery):
    text, markup = await build_plans_panel(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^claim_trial_cb$"))
async def claim_trial_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    if await db.has_claimed_trial(user_id):
        return await query.answer("⚠️ You have already claimed your one-time 3-Day Free Trial!", show_alert=True)

    success = await db.claim_free_trial(user_id)
    if success:
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


@Client.on_callback_query(filters.regex(r"^plan_details_(\d+)$"))
async def plan_details_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    details = {
        1: {
            "name": "🥈 Level 1 - Silver (30 Days)",
            "size": "4GB Transfers",
            "daily": "25 GB / day",
            "conc": "2 Tasks Concurrency",
            "extra": "Custom Metadata + Auto Cleaner",
            "stars": 50,
            "inr": 49
        },
        2: {
            "name": "🥇 Level 2 - Gold (30 Days)",
            "size": "4GB Transfers",
            "daily": "75 GB / day",
            "conc": "3 Tasks Concurrency",
            "extra": "Sample Video Clips + Screenshots Album",
            "stars": 100,
            "inr": 99
        },
        3: {
            "name": "💎 Level 3 - Diamond (30 Days)",
            "size": "4GB Transfers",
            "daily": "UNLIMITED Bandwidth",
            "conc": "5 Tasks Concurrency",
            "extra": "Priority VIP Processing + All Video Tools",
            "stars": 200,
            "inr": 199
        }
    }
    p = details.get(tier, details[1])

    text = (
        f"<b><u>{p['name']}</u></b> ⚡\n\n"
        f"◈ <b>Max File Size :</b> {p['size']}\n"
        f"◈ <b>Daily Limit :</b> {p['daily']}\n"
        f"◈ <b>Concurrency :</b> {p['conc']}\n"
        f"◈ <b>Features :</b> {p['extra']}\n\n"
        f"💳 <b>Payment Options:</b>\n"
        f"• ⭐ <b>Telegram Stars :</b> {p['stars']} Stars (Instant 1-Tap)\n"
        f"• 🇮🇳 <b>UPI Transfer :</b> ₹{p['inr']} INR\n\n"
        f"⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ Pay with Stars ({p['stars']} XTR)", callback_data=f"pay_stars_{tier}")],
        [InlineKeyboardButton(f"🇮🇳 Pay via UPI (₹{p['inr']})", callback_data=f"pay_upi_{tier}")],
        [InlineKeyboardButton("🔙 Back to Plans", callback_data="open_plans")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^pay_upi_(\d+)$"))
async def pay_upi_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    upi_id = await db.get_upi_id()
    price_map = {1: 49, 2: 99, 3: 199}
    price = price_map.get(tier, 49)
    tier_name = TIER_NAMES.get(tier, "Premium")

    text = (
        f"🇮🇳 <b><u>UPI Payment - {tier_name}</u></b> ⚡\n\n"
        f"◈ <b>Amount to Pay :</b> <code>₹{price}</code> INR\n"
        f"◈ <b>UPI ID :</b> <code>{upi_id}</code> (tap to copy)\n\n"
        "<b>Steps to Activate:</b>\n"
        f"1. Send <b>₹{price}</b> to <code>{upi_id}</code> using GPay / PhonePe / Paytm / BHIM.\n"
        "2. Take a screenshot showing Transaction ID.\n"
        f"3. Send the screenshot to <b>@NexCRSupportbot</b> with your User ID (<code>{query.from_user.id}</code>).\n\n"
        "<i>Activation completes in 5-15 minutes upon verification!</i>\n\n"
        "⚡ @Nex_bots"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Screenshot (@NexCRSupportbot)", url="https://t.me/NexCRSupportbot")],
        [InlineKeyboardButton("🔔 Notify Admin of UPI Transfer", callback_data=f"notify_upi_paid_{tier}")],
        [InlineKeyboardButton("🔙 Back to Plan", callback_data=f"plan_details_{tier}")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^notify_upi_paid_(\d+)$"))
async def notify_upi_paid_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    tier_name = TIER_NAMES.get(tier, "Premium")
    user = query.from_user

    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"🔔 <b>UPI Payment Claimed!</b>\n\n"
                f"👤 <b>User:</b> {user.mention} (<code>{user.id}</code>)\n"
                f"💎 <b>Requested Tier:</b> {tier_name}\n"
                f"⏰ <b>Time:</b> <code>{format_user_time(time.time())}</code>\n\n"
                f"<i>Please verify screenshot at @NexCRSupportbot and approve via <code>/add_prem {user.id} {tier} 30</code>.</i>\n\n"
                f"⚡ @Nex_bots"
            )
        except Exception:
            pass

    await query.answer("🔔 Support and Admin notified! Please ensure you also send your screenshot to @NexCRSupportbot.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^pay_stars_(\d+)$"))
async def pay_stars_cb(client, query: CallbackQuery):
    tier = int(query.matches[0].group(1))
    star_prices = {1: 50, 2: 100, 3: 200}
    stars = star_prices.get(tier, 50)
    tier_name = TIER_NAMES.get(tier, "Premium")

    try:
        await client.send_invoice(
            chat_id=query.message.chat.id,
            title=f"NeX 4GB - {tier_name}",
            description=f"30 Days of {tier_name} 4GB High-Speed Rename Access",
            payload=f"premium_tier_{tier}_30d",
            currency="XTR",
            prices=[LabeledPrice(label=f"{tier_name} (30 Days)", amount=stars)],
            provider_token=""
        )
        await query.answer("⭐ Invoice sent! Tap 'Pay' on the invoice above.", show_alert=False)
    except Exception as e:
        await query.answer(f"❌ Error creating Stars invoice: {e}", show_alert=True)


@Client.on_pre_checkout_query()
async def pre_checkout_handler(client, pre_checkout_query: PreCheckoutQuery):
    # Auto-approve invoice
    try:
        await pre_checkout_query.answer(ok=True)
    except Exception:
        pass


@Client.on_message(filters.successful_payment)
async def successful_payment_handler(client, message: Message):
    payload = message.successful_payment.invoice_payload
    match = re.search(r'premium_tier_(\d+)_(\d+)d', payload)
    if match:
        tier = int(match.group(1))
        days = int(match.group(2))
        await db.set_user_premium(message.from_user.id, tier=tier, days=days)
        tier_title = TIER_NAMES.get(tier, "Premium")
        tz_name = await db.get_timezone(message.from_user.id)
        prem_info = await db.get_premium_info(message.from_user.id)
        expiry_str = format_user_time(prem_info.get("expiry", 0), tz_name)

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
                    f"👤 <b>User:</b> {message.from_user.mention} (<code>{message.from_user.id}</code>)\n"
                    f"💎 <b>Tier:</b> {tier_title}\n"
                    f"💰 <b>Stars:</b> {message.successful_payment.total_amount} XTR\n"
                    f"📅 <b>Expiry:</b> <code>{expiry_str}</code>\n\n"
                    f"⚡ @Nex_bots"
                )
            except Exception:
                pass


@Client.on_callback_query(filters.regex(r"^my_plan_cb$"))
async def my_plan_cb(client, query: CallbackQuery):
    text, markup = await build_usage_card(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


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
