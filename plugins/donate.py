import re
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from helper.database import db
from helper.utils import edit_message_content
from config import Config

# NeX 4GB Rename Bot - Stars & UPI Donations
# Developed by @Nex_bots


async def build_donate_panel():
    upi_id = await db.get_upi_id()
    text = (
        "<b>◈ Sᴜᴘᴘᴏʀᴛ & Dᴏɴᴀᴛᴇ ❤️</b>\n"
        "───────────────\n"
        "NeX 4GB Rename Bot is built with passion and hosted on high-performance cloud servers.\n\n"
        "Your donations directly fund server costs, high-speed bandwidth, and new feature development!\n\n"
        f"▸ <b>Oꜰꜰɪᴄɪᴀʟ UPI ID :</b> <code>{upi_id}</code> (tap to copy)\n"
        "▸ <b>Tᴇʟᴇɢʀᴀᴍ Sᴛᴀʀꜱ :</b> 1-Tap instant tip below\n\n"
        "<i>Every single contribution is deeply appreciated!</i>\n\n"
        "⚡ @Nex_bots | 💬 Sᴜᴘᴘᴏʀᴛ: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ 25 Sᴛᴀʀꜱ", callback_data="donate_stars_25"),
            InlineKeyboardButton("⭐ 50 Sᴛᴀʀꜱ", callback_data="donate_stars_50")
        ],
        [
            InlineKeyboardButton("⭐ 100 Sᴛᴀʀꜱ", callback_data="donate_stars_100"),
            InlineKeyboardButton("⭐ 250 Sᴛᴀʀꜱ", callback_data="donate_stars_250")
        ],
        [
            InlineKeyboardButton("⭐ 500 Sᴛᴀʀꜱ (Mᴇɢᴀ Tɪᴘ)", callback_data="donate_stars_500")
        ],
        [
            InlineKeyboardButton("🇮🇳 Pᴀʏ ᴠɪᴀ UPI", callback_data="donate_upi_info"),
            InlineKeyboardButton("📢 Uᴘᴅᴀᴛᴇꜱ", url="https://t.me/Nex_bots")
        ],
        [
            InlineKeyboardButton("⬅️ Bᴀᴄᴋ ᴛᴏ Sᴛᴀʀᴛ", callback_data="start"),
            InlineKeyboardButton("❌ Cʟᴏꜱᴇ", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_message(filters.private & filters.command(["donate", "donation"]))
async def donate_cmd(client, message: Message):
    text, markup = await build_donate_panel()
    await message.reply_text(text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^(donation|cb_donate)$"))
async def donate_cb(client, query: CallbackQuery):
    text, markup = await build_donate_panel()
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^donate_stars_(\d+)$"))
async def donate_stars_cb(client, query: CallbackQuery):
    stars = int(query.matches[0].group(1))
    try:
        await client.send_invoice(
            chat_id=query.message.chat.id,
            title=f"NeX Bot Donation - {stars} Stars",
            description=f"Voluntary donation of {stars} Stars to support NeX 4GB Rename Bot",
            payload=f"donation_{stars}_stars",
            currency="XTR",
            prices=[LabeledPrice(label=f"Donate {stars} Stars", amount=stars)],
            provider_token=""
        )
        await query.answer(f"⭐ Invoice for {stars} Stars generated! Tap 'Pay' above.", show_alert=False)
    except Exception as e:
        await query.answer(f"❌ Error creating donation invoice: {e}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^donate_upi_info$"))
async def donate_upi_info_cb(client, query: CallbackQuery):
    upi_id = await db.get_upi_id()
    text = (
        "<b>◈ UPI Dᴏɴᴀᴛɪᴏɴ Dᴇᴛᴀɪʟꜱ 🇮🇳</b>\n"
        "───────────────\n"
        f"▸ <b>UPI ID :</b> <code>{upi_id}</code> (tap to copy)\n\n"
        "<b>Hᴏᴡ ᴛᴏ Dᴏɴᴀᴛᴇ ᴠɪᴀ UPI:</b>\n"
        "1. Open GPay, PhonePe, Paytm, or BHIM.\n"
        f"2. Pay any amount of your choice to <code>{upi_id}</code>.\n"
        "3. Optional: forward the receipt to <b>@NexCRSupportbot</b> so we can feature you on our support wall!\n\n"
        "⚡ Thank you for keeping NeX running strong!"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Sᴜᴘᴘᴏʀᴛ Bᴏᴛ", url="https://t.me/NexCRSupportbot")],
        [InlineKeyboardButton("⬅️ Bᴀᴄᴋ ᴛᴏ Dᴏɴᴀᴛᴇ", callback_data="cb_donate"),
         InlineKeyboardButton("❌ Cʟᴏꜱᴇ", callback_data="close")]
    ])
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()
