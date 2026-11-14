import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatJoinRequest
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from config import Config
from helper.database import db

# NeX 4GB Rename Bot - Personal Bot Protection, Access Control & Dynamic Force Sub
# Developed by @Nex_bots

_DB_TIMEOUT = 5  # seconds – max wait for any MongoDB call before fallback
USER_FLOOD_TRACK = {}


async def _safe(coro, default=None):
    """Wrap any DB coroutine with a timeout so slow MongoDB never blocks handlers."""
    try:
        return await asyncio.wait_for(coro, timeout=_DB_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        return default


async def is_subscribed(client: Client, user_id: int, channel=None) -> bool:
    target_channel = channel or Config.FORCE_SUB
    if not target_channel:
        return True
    if user_id in Config.ADMIN:
        return True
    try:
        chat_id = int(target_channel) if str(target_channel).startswith("-100") else target_channel
        member = await asyncio.wait_for(
            client.get_chat_member(chat_id, user_id),
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
    except Exception:
        return True  # fail-open for resilience


async def get_invite_link(client: Client, channel=None, creates_join_request: bool = False) -> str:
    target_channel = channel or Config.FORCE_SUB
    if not target_channel:
        return "https://t.me/Nex_bots"
    
    if creates_join_request and str(target_channel).startswith("-100"):
        try:
            invite = await asyncio.wait_for(
                client.create_chat_invite_link(int(target_channel), creates_join_request=True),
                timeout=_DB_TIMEOUT
            )
            return invite.invite_link
        except Exception:
            pass

    if str(target_channel).startswith("-100"):
        try:
            chat = await asyncio.wait_for(client.get_chat(int(target_channel)), timeout=_DB_TIMEOUT)
            return chat.invite_link or "https://t.me/Nex_bots"
        except Exception:
            return "https://t.me/Nex_bots"
    
    channel_clean = str(target_channel).replace("@", "")
    return f"https://t.me/{channel_clean}"


# ---------------------------------------------------------------------------
# CHAT JOIN REQUEST LISTENER (for Request-to-Join Force-Sub Mode)
# ---------------------------------------------------------------------------
@Client.on_chat_join_request()
async def join_req_listener(client: Client, request: ChatJoinRequest):
    try:
        await db.add_fsub_request(request.chat.id, request.from_user.id)
    except Exception as e:
        print(f"Error saving chat join request: {e}")


# ---------------------------------------------------------------------------
# MESSAGE INTERCEPTOR (group=-1 → runs BEFORE all other handlers)
# Applies only to NON-admin users (admin always bypass via ~filters.user(ADMIN))
# ---------------------------------------------------------------------------
@Client.on_message(filters.private & ~filters.user(Config.ADMIN), group=-1)
async def force_sub_message_interceptor(client, message):
    user_id = message.from_user.id

    # 1. Anti-Flood / Anti-Spam Rate Limiter (Max 4 msgs / second)
    now = time.time()
    times = [t for t in USER_FLOOD_TRACK.get(user_id, []) if now - t < 1.0]
    if len(times) >= 4:
        message.stop_propagation()
        return
    times.append(now)
    USER_FLOOD_TRACK[user_id] = times

    # 2. Maintenance Mode Check
    is_maint = await _safe(db.get_maintenance(), default=False)
    if is_maint:
        await message.reply_text(
            "🛠️ <b>Bot Under Maintenance!</b>\n\n"
            "We are currently upgrading the servers for faster 4GB performance. Please try again shortly!\n\n"
            "💬 Support: @NexCRSupportbot",
            quote=True
        )
        message.stop_propagation()
        return

    # 3. Ban Check (with timeout fallback – default=False means pass on timeout)
    is_banned = await _safe(db.is_banned(user_id), default=False)
    if is_banned:
        await message.reply_text(
            "🚫 <b>You are banned from using this bot.</b>\n\n"
            "If you believe this is an error, please contact @NexCRSupportbot.",
            quote=True
        )
        message.stop_propagation()
        return

    # 4. Bot Access Mode (private vs public) – default="private" on timeout/error
    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    if bot_mode == "private":
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

    # 5. Dynamic Force Subscribe Check
    fsub = await _safe(db.get_fsub_settings(), default={"channel": Config.FORCE_SUB, "mode": "normal", "enabled": bool(Config.FORCE_SUB)})
    fsub_enabled = fsub.get("enabled", True)
    fsub_channel = fsub.get("channel")

    if fsub_enabled and fsub_channel and bot_mode != "private":
        mode = fsub.get("mode", "normal")
        chat_id_val = int(fsub_channel) if str(fsub_channel).startswith("-100") else fsub_channel

        if mode == "request":
            # Pass if already a chat member OR has submitted a join request
            is_member = await is_subscribed(client, user_id, fsub_channel)
            has_req = False
            if isinstance(chat_id_val, int):
                has_req = await _safe(db.has_fsub_request(chat_id_val, user_id), default=False)
            
            if not is_member and not has_req:
                invite_link = await get_invite_link(client, fsub_channel, creates_join_request=True)
                button = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Request to Join Channel", url=invite_link)],
                    [InlineKeyboardButton("🔄 Verify Join / Request", callback_data="check_sub")]
                ])
                await message.reply_text(
                    f"👋 <b>Hello {message.from_user.mention}!</b>\n\n"
                    f"⚠️ Please request to join our channel to use <b>NeX 4GB Rename Bot</b>.\n\n"
                    f"Click below to request, then tap <b>Verify Join / Request</b>!",
                    reply_markup=button,
                    quote=True
                )
                message.stop_propagation()
                return
        else:
            # Normal Mode: must be actual member
            if not await is_subscribed(client, user_id, fsub_channel):
                invite_link = await get_invite_link(client, fsub_channel, creates_join_request=False)
                button = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Channel", url=invite_link)],
                    [InlineKeyboardButton("🔄 Try Again", callback_data="check_sub")]
                ])
                await message.reply_text(
                    f"👋 <b>Hello {message.from_user.mention}!</b>\n\n"
                    f"⚠️ Please join our channel to use <b>NeX 4GB Rename Bot</b>.\n\n"
                    f"Click the button below to join, then click <b>Try Again</b>!",
                    reply_markup=button,
                    quote=True
                )
                message.stop_propagation()
                return

    # Allowed → Continue propagation to other handlers


# ---------------------------------------------------------------------------
# CALLBACK INTERCEPTOR (group=-1 → runs BEFORE all other callback handlers)
# ---------------------------------------------------------------------------
@Client.on_callback_query(~filters.user(Config.ADMIN), group=-1)
async def force_sub_callback_interceptor(client, query: CallbackQuery):
    if query.data == "check_sub":
        return

    user_id = query.from_user.id

    # 1. Maintenance Check
    is_maint = await _safe(db.get_maintenance(), default=False)
    if is_maint:
        await query.answer("🛠️ Bot is currently under maintenance! Please try again shortly.", show_alert=True)
        query.stop_propagation()
        return

    # 2. Ban Check
    is_banned = await _safe(db.is_banned(user_id), default=False)
    if is_banned:
        await query.answer("🚫 You are banned from using this bot.", show_alert=True)
        query.stop_propagation()
        return

    # 3. Access Mode
    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    if bot_mode == "private":
        is_auth = await _safe(db.is_auth_user(user_id), default=False)
        if not is_auth:
            await query.answer("🔒 NeX 4GB Rename Bot is in Private Mode. Access Denied!", show_alert=True)
            query.stop_propagation()
            return

    # 4. Force Subscribe
    fsub = await _safe(db.get_fsub_settings(), default={"channel": Config.FORCE_SUB, "mode": "normal", "enabled": bool(Config.FORCE_SUB)})
    if fsub.get("enabled", True) and fsub.get("channel") and bot_mode != "private":
        channel = fsub.get("channel")
        mode = fsub.get("mode", "normal")
        chat_id_val = int(channel) if str(channel).startswith("-100") else channel
        if mode == "request":
            is_mem = await is_subscribed(client, user_id, channel)
            has_req = False
            if isinstance(chat_id_val, int):
                has_req = await _safe(db.has_fsub_request(chat_id_val, user_id), default=False)
            if not is_mem and not has_req:
                await query.answer("⚠️ Please request to join the channel first!", show_alert=True)
                query.stop_propagation()
                return
        else:
            if not await is_subscribed(client, user_id, channel):
                await query.answer("⚠️ Please join the updates channel first!", show_alert=True)
                query.stop_propagation()
                return


@Client.on_callback_query(filters.regex(r"^check_sub$"))
async def check_sub_callback_handler(client, query: CallbackQuery):
    user_id = query.from_user.id

    is_maint = await _safe(db.get_maintenance(), default=False)
    if is_maint:
        return await query.answer("🛠️ Bot is currently under maintenance!", show_alert=True)

    is_banned = await _safe(db.is_banned(user_id), default=False)
    if is_banned:
        return await query.answer("🚫 You are banned from using this bot.", show_alert=True)

    bot_mode = await _safe(db.get_bot_mode(), default="private" if Config.OWNER_ONLY else "public")
    if bot_mode == "private" and not await _safe(db.is_auth_user(user_id), default=False):
        return await query.answer("🔒 The bot is currently in Private Mode. Contact owner!", show_alert=True)

    fsub = await _safe(db.get_fsub_settings(), default={"channel": Config.FORCE_SUB, "mode": "normal", "enabled": bool(Config.FORCE_SUB)})
    channel = fsub.get("channel")
    mode = fsub.get("mode", "normal")
    chat_id_val = int(channel) if (channel and str(channel).startswith("-100")) else channel

    passed = True
    if fsub.get("enabled", True) and channel:
        if mode == "request":
            is_mem = await is_subscribed(client, user_id, channel)
            has_req = False
            if isinstance(chat_id_val, int):
                has_req = await _safe(db.has_fsub_request(chat_id_val, user_id), default=False)
            passed = is_mem or has_req
        else:
            passed = await is_subscribed(client, user_id, channel)

    if passed:
        try:
            await query.message.delete()
        except Exception:
            pass
        await client.send_message(
            chat_id=user_id,
            text=(
                "✅ <b>Thank you for joining / requesting!</b>\n\n"
                "Your subscription is verified. You now have full access to <b>NeX 4GB Rename Bot</b>!\n\n"
                "⚡ @Nex_bots"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
                 InlineKeyboardButton("📖 Help", callback_data="help")]
            ])
        )
    else:
        await query.answer("❌ Verification pending! Please join or request to join first.", show_alert=True)
