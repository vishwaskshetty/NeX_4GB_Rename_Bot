from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from config import Config

# NeX 4GB Rename Bot - Personal Bot Protection & Force Sub
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
    # 1. Personal Bot Protection (OWNER_ONLY mode)
    if Config.OWNER_ONLY:
        await message.reply_text(
            "🔒 **NeX 4GB Rename Bot** is a private personal bot owned by @Nex_bots.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Channel", url="https://t.me/Nex_bots")]
            ])
        )
        message.stop_propagation()
        return

    # 2. Force Subscribe check
    if Config.FORCE_SUB:
        if not await is_subscribed(client, message.from_user.id):
            invite_link = await get_invite_link(client)
            button = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join @Nex_bots", url=invite_link)],
                [InlineKeyboardButton("🔄 Try Again", callback_data="check_sub")]
            ])
            await message.reply_text(
                f"👋 **Hello {message.from_user.mention}!**\n\n"
                f"⚠️ Please join **@Nex_bots** to use **NeX 4GB Rename Bot**.\n\n"
                f"Click the button below to join, then click **Try Again**!",
                reply_markup=button
            )
            message.stop_propagation()
            return


@Client.on_callback_query(~filters.user(Config.ADMIN), group=-1)
async def force_sub_callback_interceptor(client, query: CallbackQuery):
    if query.data == "check_sub":
        return

    # 1. Owner-Only check
    if Config.OWNER_ONLY:
        await query.answer("🔒 NeX 4GB Rename Bot is a private personal bot owned by @Nex_bots.", show_alert=True)
        query.stop_propagation()
        return

    # 2. Force Subscribe check
    if Config.FORCE_SUB:
        if not await is_subscribed(client, query.from_user.id):
            await query.answer("⚠️ Please join @Nex_bots first before performing this action!", show_alert=True)
            query.stop_propagation()
            return


@Client.on_callback_query(filters.regex(r"^check_sub$"))
async def check_sub_callback_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    if await is_subscribed(client, user_id):
        try:
            await query.message.delete()
        except Exception:
            pass
        await client.send_message(
            chat_id=user_id,
            text=(
                "✅ **Thank you for joining!**\n\n"
                "Your subscription is verified. You now have full access to **NeX 4GB Rename Bot**!\n\n"
                "⚡ @Nex_bots"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
                 InlineKeyboardButton("📖 Help", callback_data="help")]
            ])
        )
    else:
        await query.answer("❌ You haven't joined yet! Please join @Nex_bots first.", show_alert=True)
