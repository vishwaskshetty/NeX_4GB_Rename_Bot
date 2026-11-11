from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Txt 

# NeX 4GB Rename Bot - Donation & Support
# Developed by @Nex_bots


@Client.on_message(filters.private & filters.command("donate"))
async def donate(client, message):
    text = Txt.DONATE_TXT
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Channel", url="https://t.me/Nex_bots"), 
            InlineKeyboardButton("🏠 Home", callback_data="start")
        ]
    ])
    await message.reply_text(text=text, reply_markup=keyboard)
