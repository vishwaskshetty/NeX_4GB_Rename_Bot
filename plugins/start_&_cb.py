import sys
import asyncio
import psutil
import time
import shutil
from pyrogram import Client, filters, enums, __version__
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, BotCommandScopeChat
from helper.database import db, TIER_NAMES
from config import Config, Txt  
from helper.utils import get_readable_file_size, get_readable_time, humanbytes, edit_message_content

_DB_TIMEOUT = 5  # seconds – guard so DB never blocks message handlers


async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        return default


def build_start_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton('💎 Premium Plans', callback_data='open_plans'),
            InlineKeyboardButton('🎁 Refer & Earn', callback_data='cb_referral')
        ],
        [
            InlineKeyboardButton('⚙️ Settings', callback_data='open_settings'),
            InlineKeyboardButton('👤 My Profile', callback_data='cb_user_profile')
        ],
        [
            InlineKeyboardButton('📚 Help', callback_data='help'),
            InlineKeyboardButton('ℹ️ About', callback_data='about')
        ]
    ]
    if user_id in Config.ADMIN:
        rows.append([InlineKeyboardButton('👑 Owner Control Panel', callback_data='owner_panel')])
    return InlineKeyboardMarkup(rows)


async def build_referral_panel(client: Client, user_id: int):
    settings = await db.get_referral_settings()
    if not settings.get("enabled", True):
        text = (
            "😂 <b>Hold Up Bro!</b>\n\n"
            "Bro I know you are ready to invite your whole contact list, "
            "<b>but Refer & Earn is not available right now!</b> 🛑😎\n\n"
            "💤 <i>The Owner has paused referrals for now. "
            "Chill & check back later, or grab a VIP plan below!</i>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans")],
            [InlineKeyboardButton("⬅️ Back to Start", callback_data="start"),
             InlineKeyboardButton("❌ Close", callback_data="close")]
        ])
        return text, markup

    ref_info = await db.get_user_referral_info(user_id)
    req = settings["required"]
    reward_days = settings["reward_days"]
    tier_name = TIER_NAMES.get(settings["reward_tier"], "Gold")

    pts = ref_info.get("points", 0)
    total = ref_info.get("total", 0)
    claimed = ref_info.get("claimed", 0)
    days_won = claimed * reward_days

    bot_me = getattr(client, "me", None) or await client.get_me()
    bot_username = bot_me.username or "Nex_Rename_bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    share_url = f"https://t.me/share/url?url={ref_link}&text=⚡%20Rename%20files%20up%20to%204GB%20with%20NeX%20Bot!"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   🎁 <b>Refer & Earn Free VIP</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Share your link with friends!\n"
        f"🎯 <b>Rule :</b> Invite {req} = {reward_days} Days {tier_name}!\n\n"
        f"◈ <b>Progress :</b> <code>{pts} / {req}</code> Invites\n"
        f"◈ <b>Total Friends :</b> <code>{total}</code>\n"
        f"◈ <b>VIP Earned :</b> <code>{days_won} Days</code>\n\n"
        "🔗 <b>Your Personal Invite Link :</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Invite Link", url=share_url)],
        [InlineKeyboardButton("🔄 Refresh", callback_data="cb_referral"),
         InlineKeyboardButton("⬅️ Back to Start", callback_data="start")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


async def build_leaderboard_view(viewer_id: int):
    top_users = await _safe(db.get_top_renamers(10), default=[])
    my_rank_info = await _safe(db.get_user_rank(viewer_id), default={"rank": "-", "files": 0, "bytes": 0})
    my_prem = await _safe(db.get_premium_info(viewer_id), default={})
    
    tier_badges = {
        3: "[💎 PRO - Diamond]",
        2: "[🥇 PRO - Gold]",
        1: "[🥈 PRO - Silver]",
        0: "[🆓 Free]"
    }
    medals = {1: "🥇 1.", 2: "🥈 2.", 3: "🥉 3."}

    lines = [
        "╭━━━━━━━━━━━━━━━━━━━╮",
        "┃   🏆 <b>Top Renamers Leaderboard</b>",
        "╰━━━━━━━━━━━━━━━━━━━╯\n"
    ]

    if not top_users:
        lines.append("<i>No active records yet. Rename a file to join!</i>\n")
    else:
        for idx, u in enumerate(top_users, start=1):
            badge = tier_badges.get(u.get("tier", 0), "[🆓 Free]")
            rank_icon = medals.get(idx, f"<b>{idx}.</b>")
            name = (u.get("first_name") or "User")[:12]
            files = u.get("files", 0)
            vol = humanbytes(u.get("bytes", 0))
            lines.append(f"{rank_icon} <b>{name}</b> <code>{badge}</code> — {files} files ({vol})")

    lines.append("\n" + "─" * 26)
    r = my_rank_info.get("rank", "-")
    f = my_rank_info.get("files", 0)
    v = humanbytes(my_rank_info.get("bytes", 0))
    my_badge = tier_badges.get(my_prem.get("tier", 0), "[🆓 Free]")
    lines.append(f"👤 <b>Your Rank :</b> #{r} <code>{my_badge}</code> | <code>{f}</code> files ({v})\n")
    lines.append("⚡ @Nex_bots | 💬 Support: @NexCRSupportbot")

    text = "\n".join(lines)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans"),
         InlineKeyboardButton("👤 My Profile", callback_data="cb_user_profile")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="cb_leaderboard"),
         InlineKeyboardButton("⬅️ Back to Start", callback_data="start")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


async def build_server_diagnostics(back_cb: str = "start"):
    uptime = time.strftime("%Hh %Mm %Ss", time.gmtime(time.time() - (Config.BOT_UPTIME or time.time())))
    total, used, free = shutil.disk_usage(".")
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   📊 <b>Live Server Diagnostics</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>⏱️ Bot Uptime :</b> <code>{uptime}</code>\n"
        f"◈ <b>🖥️ CPU Load :</b> <code>{cpu}%</code>\n"
        f"◈ <b>🧠 RAM Used :</b> <code>{ram}%</code>\n"
        f"◈ <b>💾 Disk Free :</b> <code>{get_readable_file_size(free)}</code> / <code>{get_readable_file_size(total)}</code>\n"
        f"◈ <b>📡 Net Sent :</b> <code>{sent}</code>\n"
        f"◈ <b>📥 Net Recv :</b> <code>{recv}</code>\n"
        f"◈ <b>🐍 Python :</b> <code>v{py_ver}</code> | <b>Pyrogram :</b> <code>v{__version__}</code>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="render"),
         InlineKeyboardButton("⬅️ Back", callback_data=back_cb)],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


@Client.on_message(filters.private & filters.command("start"))
async def start(client, message):
    user = message.from_user
    user_id = user.id

    # Check if user is brand-new BEFORE adding to DB
    is_new = not await _safe(db.is_user_exist(user_id), default=False)

    # Non-blocking add_user: skip on timeout so /start is instant
    await _safe(db.add_user(client, message))

    # Process Referral Deep Link
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) > 1 and is_new:
        param = text_parts[1].strip()
        if param.startswith("ref_"):
            try:
                inviter_id = int(param.split("ref_")[1])
                ok, res = await _safe(db.process_referral(inviter_id, user_id), default=(False, {}))
                if ok and res.get("reward_triggered"):
                    r_days = res.get("reward_days", 3)
                    r_tier = res.get("reward_tier", 2)
                    t_name = TIER_NAMES.get(r_tier, "Gold")
                    try:
                        await client.send_message(
                            chat_id=inviter_id,
                            text=(
                                "🎉 <b>Referral Reward Unlocked!</b> ⚡\n\n"
                                "A friend joined via your invite link!\n"
                                f"You hit your referral target and earned:\n"
                                f"🎁 <b>{r_days} Days of {t_name} Plan!</b>\n\n"
                                "Keep inviting friends to earn more VIP days!"
                            )
                        )
                    except Exception:
                        pass
                    if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
                        try:
                            await client.send_message(
                                Config.LOG_CHANNEL,
                                f"🎁 <b>Referral Milestone Reward!</b>\n\n"
                                f"👤 <b>Inviter:</b> <code>{inviter_id}</code>\n"
                                f"💎 <b>Reward:</b> {r_days} Days of {t_name}\n"
                                f"👥 <b>New User:</b> {user.mention} (<code>{user_id}</code>)\n\n"
                                f"⚡ @Nex_bots"
                            )
                        except Exception:
                            pass
            except Exception:
                pass

    # Dynamically ensure all Owner Commands are registered for Admin
    if user_id in Config.ADMIN:
        try:
            from bot import ALL_OWNER_COMMANDS
            asyncio.create_task(client.set_bot_commands(ALL_OWNER_COMMANDS, scope=BotCommandScopeChat(chat_id=user_id)))
        except Exception:
            pass

    button = build_start_keyboard(user_id)
    if Config.START_PIC:
        await message.reply_photo(Config.START_PIC, caption=Txt.START_TXT.format(user.mention), reply_markup=button)       
    else:
        await message.reply_text(text=Txt.START_TXT.format(user.mention), reply_markup=button)


@Client.on_message(filters.private & filters.command(["refer", "referral"]))
async def refer_cmd(client, message):
    text, markup = await build_referral_panel(client, message.from_user.id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("leaderboard"))
async def leaderboard_cmd(client, message):
    text, markup = await build_leaderboard_view(message.from_user.id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^(start|render|help|about|close|cb_leaderboard|cb_referral)$"))
async def cb_handler(client, query: CallbackQuery):
    data = query.data 
    if data == "start":
        button = build_start_keyboard(query.from_user.id)
        await edit_message_content(
            query.message,
            text=Txt.START_TXT.format(query.from_user.mention),
            reply_markup=button
        )
    elif data == "cb_referral":
        text, markup = await build_referral_panel(client, query.from_user.id)
        await edit_message_content(query.message, text=text, reply_markup=markup)
        await query.answer()
    elif data == "cb_leaderboard":
        text, markup = await build_leaderboard_view(query.from_user.id)
        await edit_message_content(query.message, text=text, reply_markup=markup)
        await query.answer("Leaderboard updated! 🏆")
    elif data == "render":
        text, markup = await build_server_diagnostics(back_cb="start")
        await edit_message_content(query.message, text=text, reply_markup=markup)
        await query.answer("Diagnostics refreshed! 📊")
    elif data == "help":
        await edit_message_content(
            query.message,
            text=Txt.HELP_TXT,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Server Info", callback_data="render"),
                 InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")],
                [InlineKeyboardButton("⬅️ Back to Start", callback_data="start"),
                 InlineKeyboardButton("❌ Close", callback_data="close")]
            ])
        )
    elif data == "about":
        await edit_message_content(
            query.message,
            text=Txt.ABOUT_TXT,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/Nex_bots"),
                 InlineKeyboardButton("💬 Support Bot", url="https://t.me/NexCRSupportbot")],
                [InlineKeyboardButton("🖥️ Server Info", callback_data="render")],
                [InlineKeyboardButton("⬅️ Back to Start", callback_data="start"),
                 InlineKeyboardButton("❌ Close", callback_data="close")]
            ])
        )
    elif data == "close":
        try:
            await query.message.delete()
            if query.message.reply_to_message:
                await query.message.reply_to_message.delete()
            await query.message.continue_propagation()
        except Exception:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.continue_propagation()
