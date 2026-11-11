import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from config import Config
from helper.database import db

# NeX 4GB Rename Bot - Personal Bot Protection, Access Control & Force Sub
# Developed by @Nex_bots

_DB_TIMEOUT = 5  # seconds – max wait for any MongoDB call before fallback


async def _safe(coro, default=None):
    """Wrap any DB coroutine with a timeout so a slow/unreachable MongoDB
    never blocks the bot's message handlers."""
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        return default


async def is_subscribed(client: Client, user_id: int) -> bool:
    if not Config.FORCE_SUB:
        return True
    if user_id in Config.ADMIN:
        return True
    try:
        member = await asyncio.wait_for(
            client.get_chat_member(Config.FORCE_SUB, user_id),
            timeout=_DB_TIMEOUT
        )
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
        return True  # fail-open


async def get_invite_link(client: Client) -> str:
    channel = Config.FORCE_SUB
    if not channel:
        return "https://t.me/Nex_bots"
    if str(channel).startswith("-100"):
        try:
            chat = await asyncio.wait_for(client.get_chat(int(channel)), timeout=_DB_TIMEOUT)
            return chat.invite_link or "https://t.me/Nex_bots"
        except Exception:
            return "https://t.me/Nex_bots"
    channel_clean = str(channel).replace("@", "")
    return f"https://t.me/{channel_clean}"


# ---------------------------------------------------------------------------
# MESSAGE INTERCEPTOR (group=-1 → runs BEFORE all other handlers)
# Applies only to NON-admin users (admin always bypass via ~filters.user(ADMIN))
# ---------------------------------------------------------------------------
@Client.on_message(filters.private & ~filters.user(Config.ADMIN), group=-1)
async def force_sub_message_interceptor(client, message):
    user_id = message.from_user.id

    # 1. Ban Check (with timeout fallback – default=False means pass on timeout)
    is_banned = await _safe(db.is_banned(user_id), default=False)
    if is_banned:
        await message.reply_text(
            "🚫 <b>You are banned from using this bot.</b>\n\n"
            "If you believe this is an error, please contact @NexCRSupportbot.",
            quote=True
        )
        message.stop_propagation()
        return

    # 2. Bot Access Mode (private vs public) – default="private" on timeout/error
    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    if bot_mode == "private":
        # is_auth default=False means deny on DB timeout (safe for private mode)
        is_auth = await _safe(db.is_auth_user(user_id), default=False)
        if not is_auth:
            await message.reply_text(
                "🔒 <b>NeX 4GB Rename Bot is in Private Mode!</b>\n\n"
                "Only the owner and authorized users can access this bot.\n"
                "Please contact support to request access.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Contact Support", url="https://t.me/NexCRSupportbot")],
                    [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/Nex_bots")]
                ]),
                quote=True
            )
            message.stop_propagation()
            return

    # 3. Force Subscribe check (only in public mode when FORCE_SUB is configured)
    if Config.FORCE_SUB and bot_mode != "private":
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

    # User is allowed → DO NOT call stop_propagation() so group=0 handlers fire
    # (Pyrogram automatically continues to the next group when no stop is issued)


# ---------------------------------------------------------------------------
# CALLBACK INTERCEPTOR (group=-1 → runs BEFORE all other callback handlers)
# ---------------------------------------------------------------------------
@Client.on_callback_query(~filters.user(Config.ADMIN), group=-1)
async def force_sub_callback_interceptor(client, query: CallbackQuery):
    # Let check_sub handle itself (it has its own handler below)
    if query.data == "check_sub":
        return

    user_id = query.from_user.id

    # 1. Ban Check
    is_banned = await _safe(db.is_banned(user_id), default=False)
    if is_banned:
        await query.answer("🚫 You are banned from using this bot.", show_alert=True)
        query.stop_propagation()
        return

    # 2. Access Mode
    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    if bot_mode == "private":
        is_auth = await _safe(db.is_auth_user(user_id), default=False)
        if not is_auth:
            await query.answer("🔒 NeX 4GB Rename Bot is in Private Mode. Access Denied!", show_alert=True)
            query.stop_propagation()
            return

    # 3. Force Subscribe
    if Config.FORCE_SUB and bot_mode != "private":
        if not await is_subscribed(client, user_id):
            await query.answer("⚠️ Please join @Nex_bots first before performing this action!", show_alert=True)
            query.stop_propagation()
            return

    # Allowed → continue propagation naturally


@Client.on_callback_query(filters.regex(r"^check_sub$"))
async def check_sub_callback_handler(client, query: CallbackQuery):
    user_id = query.from_user.id

    is_banned = await _safe(db.is_banned(user_id), default=False)
    if is_banned:
        return await query.answer("🚫 You are banned from using this bot.", show_alert=True)

    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    if bot_mode == "private" and not await _safe(db.is_auth_user(user_id), default=False):
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
