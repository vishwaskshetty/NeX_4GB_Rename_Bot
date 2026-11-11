import sys
import asyncio
import psutil
import time
import shutil
from pyrogram import Client, filters, enums, __version__
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from helper.database import db
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
            InlineKeyboardButton('💎 ᴜᴘɢʀᴀᴅᴇ ᴛᴏ 4ɢʙ ᴘʀᴇᴍɪᴜᴍ', callback_data='open_plans')
        ],
        [
            InlineKeyboardButton('⚙️ ꜱᴇᴛᴛɪɴɢꜱ', callback_data='open_settings'),
            InlineKeyboardButton('🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ', callback_data='cb_leaderboard')
        ],
        [
            InlineKeyboardButton('📖 ʜᴇʟᴘ', callback_data='help'),
            InlineKeyboardButton('ℹ️ ᴀʙᴏᴜᴛ', callback_data='about')
        ],
        [
            InlineKeyboardButton('📢 ᴜᴘᴅᴀᴛᴇꜱ', url='https://t.me/Nex_bots'),
            InlineKeyboardButton('💬 ꜱᴜᴘᴘᴏʀᴛ', url='https://t.me/NexCRSupportbot')
        ]
    ]
    if user_id in Config.ADMIN:
        rows.append([InlineKeyboardButton('👑 ᴏᴡɴᴇʀ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ', callback_data='owner_panel')])
    return InlineKeyboardMarkup(rows)


async def build_leaderboard_view(viewer_id: int):
    top_users = await _safe(db.get_top_renamers(10), default=[])
    my_rank_info = await _safe(db.get_user_rank(viewer_id), default={"rank": "-", "files": 0, "bytes": 0})
    
    tier_badges = {3: "💎", 2: "🥇", 1: "🥈", 0: "🆓"}
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    lines = [
        "╭━━━━━━━━━━━━━━━━━━━╮",
        "┃   🏆 <b>Top Renamers Leaderboard</b>",
        "╰━━━━━━━━━━━━━━━━━━━╯\n"
    ]

    if not top_users:
        lines.append("<i>No active renaming records yet! Be the first to rename a file.</i>\n")
    else:
        for idx, u in enumerate(top_users, start=1):
            badge = tier_badges.get(u.get("tier", 0), "🆓")
            rank_icon = medals.get(idx, f"<b>{idx}.</b>")
            name = (u.get("first_name") or "User")[:14]
            files = u.get("files", 0)
            vol = humanbytes(u.get("bytes", 0))
            lines.append(f"{rank_icon} {badge} <b>{name}</b> — <code>{files}</code> files ({vol})")

    lines.append("\n" + "─" * 26)
    r = my_rank_info.get("rank", "-")
    f = my_rank_info.get("files", 0)
    v = humanbytes(my_rank_info.get("bytes", 0))
    lines.append(f"👤 <b>Your Rank :</b> #{r} | <code>{f}</code> files ({v})\n")
    lines.append("⚡ @Nex_bots | 💬 Support: @NexCRSupportbot")

    text = "\n".join(lines)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 View Premium Plans", callback_data="open_plans")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="cb_leaderboard"),
         InlineKeyboardButton("⬅️ Back", callback_data="start")],
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
    # Non-blocking add_user: skip on timeout so /start is instant
    await _safe(db.add_user(client, message))                
    button = build_start_keyboard(user.id)
    if Config.START_PIC:
        await message.reply_photo(Config.START_PIC, caption=Txt.START_TXT.format(user.mention), reply_markup=button)       
    else:
        await message.reply_text(text=Txt.START_TXT.format(user.mention), reply_markup=button)


@Client.on_message(filters.private & filters.command("leaderboard"))
async def leaderboard_cmd(client, message):
    text, markup = await build_leaderboard_view(message.from_user.id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^(start|render|help|donation|about|close|cb_leaderboard)$"))
async def cb_handler(client, query: CallbackQuery):
    data = query.data 
    if data == "start":
        button = build_start_keyboard(query.from_user.id)
        await edit_message_content(
            query.message,
            text=Txt.START_TXT.format(query.from_user.mention),
            reply_markup=button
        )
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
                [InlineKeyboardButton("🖥️ ꜱᴇʀᴠᴇʀ ɪɴꜰᴏ", callback_data="render"),
                 InlineKeyboardButton("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="open_settings")],
                [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="start"),
                 InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="close")]
            ])
        )
    elif data == "donation":
        buttons = [
            [
                InlineKeyboardButton('📢 Updates Channel', url='https://t.me/Nex_bots'),
                InlineKeyboardButton('💬 Support Bot', url='https://t.me/NexCRSupportbot')
            ],
            [InlineKeyboardButton('⬅️ Back', callback_data='start'),
             InlineKeyboardButton('❌ Close', callback_data='close')]
        ]
        await edit_message_content(
            query.message,
            text=Txt.DON_TXT.format(query.from_user.mention),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML
        )
    elif data == "about":
        await edit_message_content(
            query.message,
            text=Txt.ABOUT_TXT.format(client.mention),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/Nex_bots"),
                 InlineKeyboardButton("💬 ꜱᴜᴘᴘᴏʀᴛ", url="https://t.me/NexCRSupportbot")],
                [InlineKeyboardButton("🖥️ ꜱᴇʀᴠᴇʀ ɪɴꜰᴏ", callback_data="render")],
                [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="start"),
                 InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="close")]
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
