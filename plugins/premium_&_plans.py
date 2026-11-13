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
from helper.utils import get_readable_file_size, humanbytes, edit_message_content, sanitize_secrets

# NeX 4GB Rename Bot - Dynamic Month Stepper Premium Plans, Stars/UPI/USD Payments & Profiles
# Developed by @Nex_bots

_DB_TIMEOUT = 5

async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except Exception:
        return default


def calc_plan_prices(months: int, base_inr: int = 139):
    """
    Internal Pricing Formula:
    - Base 1-Month INR Price: configurable (default ₹139)
    - Multi-month fair discount applied (5% for 3-5M, 10% for 6-11M, 15% for 12+M)
    - Telegram Stars: stars_price = round((inr_price * 100) / 199)
    - USD Price: usd_price = round(inr_price / 84.0, 2)
    Conversion formula is 100% internal and NEVER shown in the UI.
    """
    months = max(1, min(24, int(months)))
    discount = 0.0
    if months >= 12:
        discount = 0.15
    elif months >= 6:
        discount = 0.10
    elif months >= 3:
        discount = 0.05
    inr_price = max(1, round(base_inr * months * (1.0 - discount)))
    stars_price = max(1, round((inr_price * 100) / 199))
    usd_price = round(inr_price / 84.0, 2)
    return inr_price, stars_price, usd_price


# ==================== DYNAMIC PLANS HUB BUILDER (MONTH STEPPER) ====================

async def build_plans_panel(user_id: int, months: int = 1):
    months = max(1, min(24, int(months)))
    days = months * 30
    prem_info = await db.get_premium_info(user_id)
    has_trial = await db.has_claimed_trial(user_id)
    bot_settings = await db.get_bot_settings()
    base_inr = bot_settings.get("base_month_price_inr", 139)
    trial_enabled = bot_settings.get("trial_enabled", True)

    tier = prem_info.get("tier", 0)
    is_prem = (tier > 0) or prem_info.get("is_owner", False)

    inr_price, stars_price, usd_price = calc_plan_prices(months, base_inr)
    month_str = "1 Month" if months == 1 else f"{months} Months"

    text = (
        "╭━━━〔 💎 𝗡𝗲𝗫 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗣𝗟𝗔𝗡 〕━━━╮\n"
        f"┃ 📅 Duration   : {month_str} ({days} Days)\n"
        f"┃ 🇮🇳 Price (INR) : ₹{inr_price}\n"
        f"┃ ⭐ Stars      : {stars_price} ⭐\n"
        f"┃ 💵 Price (USD) : ${usd_price:.2f}\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ ✅ 4GB File Renaming (Top Speed)\n"
        "┃ ✅ 4x Parallel Tasks (15 Queued)\n"
        "┃ ✅ Unlimited Daily Bandwidth\n"
        "┃ ✅ Audio/Sub Remover & Batch Mode\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    )

    buttons = []
    # Stepper row
    dec_target = max(1, months - 1)
    inc_target = min(24, months + 1)
    buttons.append([
        InlineKeyboardButton("➖", callback_data=f"plan_step_{dec_target}"),
        InlineKeyboardButton(f"📅 {month_str}", callback_data=f"plan_step_curr_{months}"),
        InlineKeyboardButton("➕", callback_data=f"plan_step_{inc_target}")
    ])

    # Payment action buttons
    buttons.append([
        InlineKeyboardButton(f"⭐ Pay {stars_price} Stars", callback_data=f"pay_stars_m_{months}"),
        InlineKeyboardButton(f"🇮🇳 Pay ₹{inr_price} (UPI)", callback_data=f"pay_upi_m_{months}")
    ])
    buttons.append([
        InlineKeyboardButton(f"💵 Pay ${usd_price:.2f} (USD)", callback_data=f"pay_usd_m_{months}")
    ])

    # Free trial button if not claimed, not premium, and trial is enabled
    if not has_trial and not is_prem and trial_enabled:
        buttons.append([InlineKeyboardButton("🎁 Claim 3-Day Free 4GB Trial", callback_data="claim_trial_cb")])

    # Navigation buttons
    buttons.append([
        InlineKeyboardButton("👤 My Profile", callback_data="cb_user_profile"),
        InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="redeem_coupon_btn")
    ])
    buttons.append([
        InlineKeyboardButton("💬 Support", url="https://t.me/NexCRSupportbot"),
        InlineKeyboardButton("⬅️ Back", callback_data="start")
    ])
    buttons.append([
        InlineKeyboardButton("❌ Close", callback_data="close")
    ])

    return text, InlineKeyboardMarkup(buttons)


async def build_upi_payment_view(months: int, base_inr: int = 139):
    months = max(1, min(24, int(months)))
    days = months * 30
    inr_price, _, _ = calc_plan_prices(months, base_inr)
    upi_id = await db.get_upi_id()
    month_str = "1 Month" if months == 1 else f"{months} Months"

    text = (
        "╭━━━〔 🇮🇳 𝗨𝗣𝗜 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 〕━━━╮\n"
        f"┃ 📅 Duration   : {month_str} ({days} Days)\n"
        f"┃ 💵 Amount     : ₹{inr_price} INR\n"
        f"┃ 💳 UPI ID     : <code>{upi_id}</code>\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃ 1. Send ₹{inr_price} to <code>{upi_id}</code>\n"
        "┃    via GPay / PhonePe / Paytm / BHIM\n"
        "┃ 2. Take a screenshot showing UTR/Ref\n"
        "┃ 3. Send screenshot to @NexCRSupportbot\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "<i>⚡ Active in 5-15 mins upon verification!</i>"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Screenshot (@NexCRSupportbot)", url="https://t.me/NexCRSupportbot")],
        [InlineKeyboardButton("🔔 Notify Admin of Transfer", callback_data=f"notify_upi_paid_m_{months}")],
        [InlineKeyboardButton("⬅️ Back to Plan", callback_data=f"plan_step_{months}"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


async def build_usd_payment_view(months: int, base_inr: int = 139):
    months = max(1, min(24, int(months)))
    days = months * 30
    _, _, usd_price = calc_plan_prices(months, base_inr)
    month_str = "1 Month" if months == 1 else f"{months} Months"

    text = (
        "╭━━━〔 💵 𝗨𝗦𝗗 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 〕━━━╮\n"
        f"┃ 📅 Duration   : {month_str} ({days} Days)\n"
        f"┃ 💵 Price (USD): ${usd_price:.2f}\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ For international payments via:\n"
        "┃ • Crypto (USDT TRC20 / TON / BTC)\n"
        "┃ • PayPal / International Cards\n"
        "┃ Contact @NexCRSupportbot to pay!\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Contact Support to Pay", url="https://t.me/NexCRSupportbot")],
        [InlineKeyboardButton("⬅️ Back to Plan", callback_data=f"plan_step_{months}"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


# ==================== PROFILE CARD BUILDER ====================

async def build_profile_card(user_id: int):
    prem_info = await db.get_premium_info(user_id)
    usage = await db.get_user_usage(user_id)
    tz_name = await db.get_timezone(user_id)
    g_stats = await db.get_user_granular_stats(user_id)
    ref_settings = await db.get_referral_settings()

    tier = prem_info.get("tier", 0)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS[0])
    daily_limit = limits["daily_bytes"]

    used_bytes = usage.get("daily_bytes", 0)
    used_gb = used_bytes / (1024 ** 3)
    limit_gb = daily_limit / (1024 ** 3)

    tier_badges = {3: "💎 Diamond VIP", 2: "🥇 Gold Plan", 1: "🥈 Silver Plan", 0: "🆓 Free User"}
    badge = tier_badges.get(tier, "🆓 Free User")

    if prem_info.get("is_owner"):
        badge = "👑 Bot Owner"
        expiry_str = "Lifetime VIP"
        speed_str = "Unlimited"
    elif tier > 0:
        d = prem_info.get("days_left", 0)
        h = prem_info.get("hours_left", 0)
        expiry_str = f"{d}d {h}h left"
        speed_str = TIER_INFO.get(tier, {}).get("speed", "Fast")
    else:
        expiry_str = "Free Tier"
        speed_str = "Turbo (40-80 MB/s)"

    pct = min(100, int((used_bytes / daily_limit) * 100)) if (tier < 3 and not prem_info.get("is_owner")) else 0
    blocks = min(10, pct // 10)
    bar = "■" * blocks + "□" * (10 - blocks)

    req_ref = ref_settings.get("required", 3)
    pts_ref = g_stats.get("referral_points", 0)
    tot_ref = g_stats.get("referrals", 0)

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   👤 <b>NeX User Profile</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>User ID :</b> <code>{user_id}</code>\n"
        f"◈ <b>Plan :</b> <b>{badge}</b>\n"
        f"◈ <b>Expiry :</b> <code>{expiry_str}</code>\n"
        f"◈ <b>Speed Cap :</b> <code>{speed_str}</code>\n\n"
        f"◈ <b>Today's Bandwidth :</b>\n"
        f"  <code>[{bar}]</code> {used_gb:.1f} / {limit_gb:.0f} GB\n\n"
        "◈ <b>Your Activity Stats :</b>\n"
        f"  • 📁 Renamed : <code>{g_stats['files_renamed']}</code> files\n"
        f"  • 💾 Data : <code>{humanbytes(g_stats['bytes_processed'])}</code>\n"
        f"  • 🎬 Samples : <code>{g_stats['samples_generated']}</code>\n"
        f"  • 📸 Shots : <code>{g_stats['screenshots_generated']}</code>\n"
        f"  • 💧 Watermarks : <code>{g_stats['watermarks_applied']}</code>\n"
        f"  • 🎁 Invites : <code>{tot_ref}</code> ({pts_ref}/{req_ref})\n\n"
        "⚡ @Nex_bots | 💬 @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Premium Plans", callback_data="open_plans"),
         InlineKeyboardButton("🎁 Refer & Earn", callback_data="cb_referral")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
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


@Client.on_callback_query(filters.regex(r"^plan_step_(\d+)$"))
async def plan_step_cb(client, query: CallbackQuery):
    months = int(query.matches[0].group(1))
    text, markup = await build_plans_panel(query.from_user.id, months=months)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^plan_step_curr_(\d+)$"))
async def plan_step_curr_cb(client, query: CallbackQuery):
    months = int(query.matches[0].group(1))
    month_str = "1 Month" if months == 1 else f"{months} Months"
    await query.answer(f"Selected: {month_str} ({months*30} Days) 💎")


@Client.on_callback_query(filters.regex(r"^pay_stars_m_(\d+)$"))
async def pay_stars_month_cb(client, query: CallbackQuery):
    months = int(query.matches[0].group(1))
    days = months * 30
    bot_settings = await db.get_bot_settings()
    base_inr = bot_settings.get("base_month_price_inr", 139)
    inr_price, stars_price, _ = calc_plan_prices(months, base_inr)
    month_str = "1 Month" if months == 1 else f"{months} Months"

    try:
        await client.send_invoice(
            chat_id=query.message.chat.id,
            title=f"NeX 4GB Premium - {month_str}",
            description=f"{days} Days of NeX 4GB High-Speed Premium VIP Access",
            payload=f"premium_months_{months}",
            currency="XTR",
            prices=[LabeledPrice(label=f"NeX VIP ({days} Days)", amount=stars_price)],
            provider_token=""
        )
        await query.answer("⭐ Invoice sent! Tap 'Pay' on the invoice above.", show_alert=False)
    except Exception as e:
        await query.answer(f"❌ Error creating Stars invoice: {e}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^pay_upi_m_(\d+)$"))
async def pay_upi_month_cb(client, query: CallbackQuery):
    months = int(query.matches[0].group(1))
    bot_settings = await db.get_bot_settings()
    base_inr = bot_settings.get("base_month_price_inr", 139)
    text, markup = await build_upi_payment_view(months, base_inr)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^notify_upi_paid_m_(\d+)$"))
async def notify_upi_paid_month_cb(client, query: CallbackQuery):
    months = int(query.matches[0].group(1))
    days = months * 30
    user = query.from_user
    month_str = "1 Month" if months == 1 else f"{months} Months"

    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
        try:
            alert = (
                "🔔 <b>UPI Payment Claimed!</b>\n\n"
                f"👤 <b>User:</b> {user.mention} (<code>{user.id}</code>)\n"
                f"💎 <b>Requested Plan:</b> {month_str} ({days} Days VIP)\n"
                f"⏰ <b>Time:</b> <code>{format_user_time(time.time())}</code>\n\n"
                f"<i>Please verify screenshot at @NexCRSupportbot and approve via <code>/add_prem {user.id} 3 {days}</code>.</i>\n\n"
                "⚡ @Nex_bots"
            )
            await client.send_message(Config.LOG_CHANNEL, sanitize_secrets(alert))
        except Exception:
            pass

    await query.answer("🔔 Support & Admin notified! Please make sure to forward your payment screenshot to @NexCRSupportbot.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^pay_usd_m_(\d+)$"))
async def pay_usd_month_cb(client, query: CallbackQuery):
    months = int(query.matches[0].group(1))
    bot_settings = await db.get_bot_settings()
    base_inr = bot_settings.get("base_month_price_inr", 139)
    text, markup = await build_usd_payment_view(months, base_inr)
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
    prem_info = await db.get_premium_info(user_id)
    tier = prem_info.get("tier", 0)
    is_prem = (tier > 0) or prem_info.get("is_owner", False)
    if await db.has_claimed_trial(user_id) or is_prem:
        await query.answer("❌ You have already used your one-time Free Trial!", show_alert=True)
        text, markup = await build_plans_panel(user_id)
        return await edit_message_content(query.message, text, reply_markup=markup)

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
    pricing = await db.get_premium_pricing()
    prices = pricing.get(tier, {}).get(days, PLAN_PRICING.get(tier, {}).get(days, {"inr": 103, "stars": 103}))
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
    pricing = await db.get_premium_pricing()
    prices = pricing.get(tier, {}).get(days, PLAN_PRICING.get(tier, {}).get(days, {"inr": 103, "stars": 103}))
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
                alert = (
                    "❤️ <b>New Stars Donation!</b>\n\n"
                    f"👤 <b>Donor:</b> {message.from_user.mention} (<code>{user_id}</code>)\n"
                    f"⭐ <b>Amount:</b> {don_amount} Stars\n\n"
                    "⚡ @Nex_bots"
                )
                await client.send_message(Config.LOG_CHANNEL, sanitize_secrets(alert))
            except Exception:
                pass
        return

    # Dynamic Month Stepper Payment check
    if payload.startswith("premium_months_"):
        try:
            months = int(payload.split("_")[-1])
        except Exception:
            months = 1
        days = months * 30
        await db.set_user_premium(user_id, tier=3, days=days, plan_name="Diamond VIP")
        tz_name = await db.get_timezone(user_id)
        prem_info = await db.get_premium_info(user_id)
        expiry_str = format_user_time(prem_info.get("expiry", 0), tz_name)
        stars_paid = message.successful_payment.total_amount

        await db.log_activity(user_id, user_name, "buy_premium", f"{months}M VIP ({days}D) for {stars_paid} Stars")

        month_str = "1 Month" if months == 1 else f"{months} Months"
        await message.reply_text(
            f"🎉 <b>Payment Successful!</b>\n\n"
            f"Your <b>4GB Diamond VIP Access</b> is active for <b>{month_str} ({days} days)</b>!\n"
            f"◈ <b>Expires :</b> <code>{expiry_str}</code>\n\n"
            f"⚡ Thank you for supporting @Nex_bots!",
            quote=True
        )

        if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
            try:
                alert = (
                    "⭐ <b>Telegram Stars Payment!</b>\n\n"
                    f"👤 <b>User:</b> {message.from_user.mention} (<code>{user_id}</code>)\n"
                    f"💎 <b>Plan:</b> {month_str} ({days} Days 4GB VIP)\n"
                    f"💰 <b>Stars:</b> {stars_paid} XTR\n"
                    f"📅 <b>Expiry:</b> <code>{expiry_str}</code>\n\n"
                    "⚡ @Nex_bots"
                )
                await client.send_message(Config.LOG_CHANNEL, sanitize_secrets(alert))
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
                alert = (
                    "⭐ <b>Telegram Stars Payment!</b>\n\n"
                    f"👤 <b>User:</b> {message.from_user.mention} (<code>{user_id}</code>)\n"
                    f"💎 <b>Tier:</b> {tier_title} ({days} Days)\n"
                    f"💰 <b>Stars:</b> {stars_paid} XTR\n"
                    f"📅 <b>Expiry:</b> <code>{expiry_str}</code>\n\n"
                    "⚡ @Nex_bots"
                )
                await client.send_message(Config.LOG_CHANNEL, sanitize_secrets(alert))
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
