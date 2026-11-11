from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from config import Config
from helper.database import db

# NeX 4GB Rename Bot - Personal Bot Protection, Access Control & Force Sub
# Developed by @Nex_bots


async def is_subscribed(client: Client, user_id: int) -> bool:
    if not Config.FORCE_SUB:
        return True
    if user_id in Config.ADMIN:
        return True
    try:
        member = await client.get_chat_member(Config.FORCE_SUB, user_id)
        if member.status in [
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.RESTRICTED
        ]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"Force sub check error: {e}")
        return True


async def get_invite_link(client: Client) -> str:
    channel = Config.FORCE_SUB
    if not channel:
        return "https://t.me/Nex_bots"
    if str(channel).startswith("-100"):
        try:
            chat = await client.get_chat(int(channel))
            return chat.invite_link or "https://t.me/Nex_bots"
        except Exception:
            return "https://t.me/Nex_bots"
    channel_clean = str(channel).replace("@", "")
    return f"https://t.me/{channel_clean}"


@Client.on_message(filters.private & ~filters.user(Config.ADMIN), group=-1)
async def force_sub_message_interceptor(client, message):
    user_id = message.from_user.id

    # 1. Ban Check
    if await db.is_banned(user_id):
        await message.reply_text(
            "🚫 <b>You are banned from using this bot.</b>\n\n"
            "If you believe this is an error, please contact @Nex_bots.",
            quote=True
        )
        message.stop_propagation()
        return

    # 2. Bot Access Mode Check (Private vs Public)
    bot_mode = await db.get_bot_mode()
    if bot_mode == "private":
        is_auth = await db.is_auth_user(user_id)
        if not is_auth:
            await message.reply_text(
                "🔒 <b>NeX 4GB Rename Bot is in Private Mode!</b>\n\n"
                "Only the owner and authorized users can access this bot.\n"
                "Please contact the owner to request access.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Contact Owner", url="https://t.me/Nex_bots")],
                    [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/Nex_bots")]
                ]),
                quote=True
            )
            message.stop_propagation()
            return

    # 3. Force Subscribe check in Public Mode
    if Config.FORCE_SUB:
        if not await is_subscribed(client, user_id):
            invite_link = await get_invite_link(client)
            button = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join @Nex_bots", url=invite_link)],
                [InlineKeyboardButton("🔄 Try Again", callback_data="check_sub")]
            ])
            await message.reply_text(
                f"👋 <b>Hello {message.from_user.mention}!</b>\n\n"
                f"⚠️ Please join <b>@Nex_bots</b> to use <b>NeX 4GB Rename Bot</b>.\n\n"
                f"Click the button below to join, then click <b>Try Again</b>!",
                reply_markup=button,
                quote=True
            )
            message.stop_propagation()
            return


@Client.on_callback_query(~filters.user(Config.ADMIN), group=-1)
async def force_sub_callback_interceptor(client, query: CallbackQuery):
    if query.data == "check_sub":
        return

    user_id = query.from_user.id

    # 1. Ban Check
    if await db.is_banned(user_id):
        await query.answer("🚫 You are banned from using this bot.", show_alert=True)
        query.stop_propagation()
        return

    # 2. Bot Access Mode Check
    bot_mode = await db.get_bot_mode()
    if bot_mode == "private":
        is_auth = await db.is_auth_user(user_id)
        if not is_auth:
            await query.answer("🔒 NeX 4GB Rename Bot is in Private Mode. Access Denied!", show_alert=True)
            query.stop_propagation()
            return

    # 3. Force Subscribe check
    if Config.FORCE_SUB:
        if not await is_subscribed(client, user_id):
            await query.answer("⚠️ Please join @Nex_bots first before performing this action!", show_alert=True)
            query.stop_propagation()
            return


@Client.on_callback_query(filters.regex(r"^check_sub$"))
async def check_sub_callback_handler(client, query: CallbackQuery):
    user_id = query.from_user.id

    if await db.is_banned(user_id):
        return await query.answer("🚫 You are banned from using this bot.", show_alert=True)

    bot_mode = await db.get_bot_mode()
    if bot_mode == "private" and not await db.is_auth_user(user_id):
        return await query.answer("🔒 The bot is currently in Private Mode. Contact owner!", show_alert=True)

    if await is_subscribed(client, user_id):
        try:
            await query.message.delete()
        except Exception:
            pass
        await client.send_message(
            chat_id=user_id,
            text=(
                "✅ <b>Thank you for joining!</b>\n\n"
                "Your subscription is verified. You now have full access to <b>NeX 4GB Rename Bot</b>!\n\n"
                "⚡ @Nex_bots"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
                 InlineKeyboardButton("📖 Help", callback_data="help")]
            ])
        )
    else:
        await query.answer("❌ You haven't joined yet! Please join @Nex_bots first.", show_alert=True)
