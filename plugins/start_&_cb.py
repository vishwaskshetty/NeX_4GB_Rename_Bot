import asyncio
import psutil
import time
import shutil
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from helper.database import db
from config import Config, Txt  
from helper.utils import get_readable_file_size, get_readable_time, edit_message_content

_DB_TIMEOUT = 5  # seconds – same guard as force_sub.py


async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        return default


@Client.on_message(filters.private & filters.command("start"))
async def start(client, message):
    user = message.from_user
    # Non-blocking add_user: skip on timeout so /start is instant
    await _safe(db.add_user(client, message))                
    rows = [
        [
            InlineKeyboardButton('📢 ᴜᴘᴅᴀᴛᴇꜱ', url='https://t.me/Nex_bots'),
            InlineKeyboardButton('💬 ꜱᴜᴘᴘᴏʀᴛ', url='https://t.me/Nex_bots')
        ],
        [
            InlineKeyboardButton('⚙️ ꜱᴇᴛᴛɪɴɢꜱ', callback_data='open_settings'),
            InlineKeyboardButton('📖 ʜᴇʟᴘ', callback_data='help')
        ],
        [
            InlineKeyboardButton('ℹ️ ᴀʙᴏᴜᴛ', callback_data='about'),
            InlineKeyboardButton('⚡ ᴅᴇᴠᴇʟᴏᴘᴇʀ', url='https://t.me/Nex_bots')
        ]
    ]
    if user.id in Config.ADMIN:
        rows.append([InlineKeyboardButton('👑 ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ', callback_data='owner_panel')])
    
    button = InlineKeyboardMarkup(rows)
    if Config.START_PIC:
        await message.reply_photo(Config.START_PIC, caption=Txt.START_TXT.format(user.mention), reply_markup=button)       
    else:
        await message.reply_text(text=Txt.START_TXT.format(user.mention), reply_markup=button)


@Client.on_callback_query(filters.regex(r"^(start|render|help|donation|about|close)$"))
async def cb_handler(client, query: CallbackQuery):
    data = query.data 
    if data == "start":
        rows = [
            [
                InlineKeyboardButton('📢 ᴜᴘᴅᴀᴛᴇꜱ', url='https://t.me/Nex_bots'),
                InlineKeyboardButton('💬 ꜱᴜᴘᴘᴏʀᴛ', url='https://t.me/Nex_bots')
            ],
            [
                InlineKeyboardButton('⚙️ ꜱᴇᴛᴛɪɴɢꜱ', callback_data='open_settings'),
                InlineKeyboardButton('📖 ʜᴇʟᴘ', callback_data='help')
            ],
            [
                InlineKeyboardButton('ℹ️ ᴀʙᴏᴜᴛ', callback_data='about'),
                InlineKeyboardButton('⚡ ᴅᴇᴠᴇʟᴏᴘᴇʀ', url='https://t.me/Nex_bots')
            ]
        ]
        if query.from_user.id in Config.ADMIN:
            rows.append([InlineKeyboardButton('👑 ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ', callback_data='owner_panel')])
        
        button = InlineKeyboardMarkup(rows)
        await edit_message_content(
            query.message,
            text=Txt.START_TXT.format(query.from_user.mention),
            reply_markup=button
        )
    elif data == "render":
        uptime = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time() - client.uptime))
        total, used, free = shutil.disk_usage(".")
        total = get_readable_file_size(total)
        used = get_readable_file_size(used)
        sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
        recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
        cpu_usage = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        stats = (
            f"⚡ NeX 4GB Rename Bot System Stats ⚡\n\n"
            f"╭➦ ʙᴏᴛ ᴜᴘᴛɪᴍᴇ : {uptime}\n"
            f"├❒ ᴛᴏᴛᴀʟ ᴅɪꜱᴋ : {total}\n"
            f"├❂ ᴜꜱᴇᴅ ᴅɪꜱᴋ : {used}\n"
            f"├▲ ᴛᴏᴛᴀʟ ᴜᴘʟᴏᴀᴅ : {sent}\n"
            f"├▼ ᴛᴏᴛᴀʟ ᴅᴏᴡɴʟᴏᴀᴅ : {recv}\n"
            f"├✤ ᴄᴘᴜ : {cpu_usage}%\n"
            f"├❖ ʀᴀᴍ : {memory}%\n"
            f"╰➥ ᴅɪꜱᴋ : {disk}%\n\n"
            f"Powered by @Nex_bots"
        )
        await query.answer(text=stats, show_alert=True)
    elif data == "help":
        await edit_message_content(
            query.message,
            text=Txt.HELP_TXT,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ ꜱᴇʀᴠᴇʀ ɪɴꜰᴏ", callback_data="render"),
                 InlineKeyboardButton("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="open_settings")],
                [InlineKeyboardButton("✖️ ᴄʟᴏꜱᴇ", callback_data="close"),
                 InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="start")]
            ])
        )
    elif data == "donation":
        buttons = [
            [InlineKeyboardButton('⚡ Support Channel', url='https://t.me/Nex_bots')],
            [InlineKeyboardButton('🏠 Home', callback_data='start'),
             InlineKeyboardButton('✖️ Close', callback_data='close')]
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
                 InlineKeyboardButton("💬 ꜱᴜᴘᴘᴏʀᴛ", url="https://t.me/Nex_bots")],
                [InlineKeyboardButton("🖥️ ꜱᴇʀᴠᴇʀ ɪɴꜰᴏ", callback_data="render")],
                [InlineKeyboardButton("✖️ ᴄʟᴏꜱᴇ", callback_data="close"),
                 InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="start")]
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
