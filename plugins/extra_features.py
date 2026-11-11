import os
import shutil
import psutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from helper.database import db
from helper.utils import humanbytes, get_readable_file_size, CANCEL_REQUESTS, edit_message_content
from config import Config

# NeX 4GB Rename Bot - Extra Features & Settings Dashboard
# Developed by @Nex_bots


async def build_settings_panel(user_id: int):
    settings = await db.get_user_settings(user_id)
    wm = await db.get_watermark(user_id)
    sample_set = await db.get_sample_settings(user_id)
    
    meta_status = "✅ ON" if settings["metadata_bool"] else "❌ OFF"
    wm_status = "✅ ON" if wm["enabled"] else "❌ OFF"
    thumb_status = "✅ Set" if settings["thumbnail"] else "❌ None"
    caption_status = "✅ Set" if settings["caption"] else "❌ None"
    
    prefix_val = settings["prefix"]
    prefix_status = f"<code>{prefix_val[:8]}..</code>" if prefix_val and len(prefix_val) > 8 else (f"<code>{prefix_val}</code>" if prefix_val else "None")
    suffix_val = settings["suffix"]
    suffix_status = f"<code>{suffix_val[:8]}..</code>" if suffix_val and len(suffix_val) > 8 else (f"<code>{suffix_val}</code>" if suffix_val else "None")
    
    sample_dur = sample_set["duration"]
    sample_status = f"{sample_dur}s ({sample_set['start_mode']})" if sample_dur > 0 else "OFF"
    ss_status = f"{settings['screenshots']} frames" if settings["screenshots"] > 0 else "OFF"
    cleaner_status = "Active" if (settings["clean_words"] or settings["replace_words"]) else "None"
    dump_status = "Set" if settings["dump_channel"] else "None"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   ⚙️ <b>NeX Control Panel & Settings</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>🏷️ Metadata :</b> {meta_status} (<code>{settings['metadata_code'][:18]}..</code>)\n"
        f"◈ <b>💧 Watermark :</b> {wm_status} (<code>{wm['text'][:12] or 'None'}</code>)\n"
        f"◈ <b>🎬 Sample Video :</b> <code>{sample_status}</code>\n"
        f"◈ <b>📸 Screenshots :</b> <code>{ss_status}</code>\n"
        f"◈ <b>🖼️ Thumbnail :</b> <code>{thumb_status}</code>\n"
        f"◈ <b>📑 Caption :</b> <code>{caption_status}</code>\n"
        f"◈ <b>🔤 Prefix / Suffix :</b> <code>{prefix_status}</code> / <code>{suffix_status}</code>\n"
        f"◈ <b>🧹 Cleaner :</b> <code>{cleaner_status}</code> | <b>Dump :</b> <code>{dump_status}</code>\n\n"
        "<i>Tap any feature below to customize your preferences:</i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    keyboard_buttons = [
        [
            InlineKeyboardButton(f"🏷️ Metadata: {meta_status}", callback_data="cb_metadata"),
            InlineKeyboardButton(f"💧 Watermark: {wm_status}", callback_data="cb_watermark")
        ],
        [
            InlineKeyboardButton(f"🎬 Sample: {sample_dur}s", callback_data="cb_sample_menu"),
            InlineKeyboardButton(f"📸 Screen: {settings['screenshots']}", callback_data="set_cycle_ss")
        ],
        [
            InlineKeyboardButton("🖼️ View Thumb", callback_data="set_view_thumb"),
            InlineKeyboardButton("🗑️ Delete Thumb", callback_data="set_del_thumb")
        ],
        [
            InlineKeyboardButton("🧹 Cleaner Rules", callback_data="set_view_cleaner"),
            InlineKeyboardButton("📦 Dump Channel", callback_data="set_view_dump")
        ],
        [
            InlineKeyboardButton("📊 My Usage & Plan", callback_data="my_plan_cb"),
            InlineKeyboardButton("🌍 Timezone", callback_data="open_timezone_menu")
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="open_settings"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ]
    if user_id in Config.ADMIN:
        keyboard_buttons.append([InlineKeyboardButton("👑 Owner Control Panel", callback_data="owner_panel")])

    return text, InlineKeyboardMarkup(keyboard_buttons)


# ==================== INTERACTIVE SETTINGS DASHBOARD ====================

@Client.on_message(filters.private & filters.command("settings"))
async def settings_command(client, message):
    user_id = message.from_user.id
    text, markup = await build_settings_panel(user_id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^open_settings$"))
async def open_settings_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    text, markup = await build_settings_panel(user_id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


# ==================== METADATA SUBMENU ====================

async def build_metadata_view(user_id: int):
    meta_bool = await db.get_metadata_bool(user_id)
    meta_code = await db.get_metadata_code(user_id)
    status_str = "ENABLED 🟢" if meta_bool else "DISABLED 🔴"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   🏷️ <b>NeX Metadata Engine</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Current Status :</b> <b>{status_str}</b>\n"
        f"◈ <b>Metadata Tag :</b> <code>{meta_code}</code>\n\n"
        "<b>Instructions:</b>\n"
        "• To change tag: <code>/set_metadata Encoded By @Nex_bots</code>\n"
        "• Losslessly injects into title, author, and audio/video/sub streams.\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Toggle: {'Disable ❌' if meta_bool else 'Enable ✅'}", callback_data="set_toggle_meta")],
        [InlineKeyboardButton("⬅️ Back", callback_data="open_settings"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_metadata$"))
async def cb_metadata_menu(client, query: CallbackQuery):
    text, markup = await build_metadata_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^set_toggle_meta$"))
async def set_toggle_meta_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    current = await db.get_metadata_bool(user_id)
    new_state = not current
    await db.set_metadata_bool(user_id, new_state)
    text, markup = await build_metadata_view(user_id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Metadata {'ENABLED 🟢' if new_state else 'DISABLED 🔴'}")


# ==================== VIDEO WATERMARK SUBMENU ====================

async def build_watermark_view(user_id: int):
    prem_info = await db.get_premium_info(user_id)
    is_prem = (prem_info.get("tier", 0) >= 1) or (user_id in Config.ADMIN)
    
    if not is_prem:
        text = (
            "╭━━━━━━━━━━━━━━━━━━━╮\n"
            "┃   💧 <b>Video Watermark (Premium)</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
            "⚠️ <b>Video Watermark is an exclusive Premium Feature!</b>\n\n"
            "Burn your channel tag or custom watermark text directly into video frames with ultrafast FFmpeg encoding.\n\n"
            "🚀 Upgrade to <b>Premium</b> to unlock Watermarks, 4GB Transfers, and Unlimited Renaming!"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Upgrade to Premium", callback_data="open_plans")],
            [InlineKeyboardButton("⬅️ Back", callback_data="open_settings"),
             InlineKeyboardButton("❌ Close", callback_data="close")]
        ])
        return text, markup

    wm = await db.get_watermark(user_id)
    status_str = "ENABLED 🟢" if wm["enabled"] else "DISABLED 🔴"
    wm_text = wm["text"] or "<i>Not Set (use /set_watermark)</i>"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   💧 <b>Video Watermark Settings</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Status :</b> <b>{status_str}</b>\n"
        f"◈ <b>Text :</b> <code>{wm_text}</code>\n"
        f"◈ <b>Position :</b> <code>{wm['position']}</code>\n"
        f"◈ <b>Font Size :</b> <code>{wm['size']}px</code> | <b>Color :</b> <code>{wm['color']}</code>\n\n"
        "<i>To change text: <code>/set_watermark @YourChannel</code></i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Toggle: {'Disable ❌' if wm['enabled'] else 'Enable ✅'}", callback_data="cb_wm_toggle")],
        [
            InlineKeyboardButton("↖️ Top-Left", callback_data="cb_wm_pos_top_left"),
            InlineKeyboardButton("↗️ Top-Right", callback_data="cb_wm_pos_top_right")
        ],
        [InlineKeyboardButton("🎯 Center", callback_data="cb_wm_pos_center")],
        [
            InlineKeyboardButton("↙️ Bot-Left", callback_data="cb_wm_pos_bottom_left"),
            InlineKeyboardButton("↘️ Bot-Right", callback_data="cb_wm_pos_bottom_right")
        ],
        [
            InlineKeyboardButton("🔉 Small (18)", callback_data="cb_wm_size_18"),
            InlineKeyboardButton("🔊 Med (28)", callback_data="cb_wm_size_28"),
            InlineKeyboardButton("📢 Large (40)", callback_data="cb_wm_size_40")
        ],
        [
            InlineKeyboardButton("⚪ White", callback_data="cb_wm_col_white"),
            InlineKeyboardButton("🟡 Yellow", callback_data="cb_wm_col_yellow"),
            InlineKeyboardButton("🔵 Cyan", callback_data="cb_wm_col_cyan")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="open_settings"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_message(filters.private & filters.command("watermark"))
async def watermark_cmd(client, message):
    text, markup = await build_watermark_view(message.from_user.id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("set_watermark"))
async def set_watermark_cmd(client, message):
    user_id = message.from_user.id
    prem_info = await db.get_premium_info(user_id)
    is_prem = (prem_info.get("tier", 0) >= 1) or (user_id in Config.ADMIN)
    if not is_prem:
        return await message.reply_text(
            "⚠️ <b>Video Watermark is a Premium-Only Feature!</b>\n\nUpgrade via <code>/plan</code> to unlock.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 View Plans", callback_data="open_plans")]])
        )
    if len(message.command) == 1:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/set_watermark @YourChannel</code>")
    text = message.text.split(" ", 1)[1].strip()
    await db.set_watermark(user_id, text=text, enabled=True)
    await message.reply_text(
        f"✅ <b>Watermark Text Saved!</b>\n\n💧 <b>Tag:</b> <code>{text}</code>\n🟢 <b>Status:</b> Enabled\n\n⚡ @Nex_bots"
    )


@Client.on_callback_query(filters.regex(r"^cb_watermark$"))
async def cb_watermark_menu(client, query: CallbackQuery):
    text, markup = await build_watermark_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_wm_toggle$"))
async def cb_wm_toggle(client, query: CallbackQuery):
    user_id = query.from_user.id
    wm = await db.get_watermark(user_id)
    new_state = not wm["enabled"]
    await db.set_watermark(user_id, enabled=new_state)
    text, markup = await build_watermark_view(user_id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Watermark {'Enabled ✅' if new_state else 'Disabled ❌'}")


@Client.on_callback_query(filters.regex(r"^cb_wm_pos_(top_left|top_right|center|bottom_left|bottom_right)$"))
async def cb_wm_pos(client, query: CallbackQuery):
    pos = query.matches[0].group(1)
    await db.set_watermark(query.from_user.id, position=pos)
    text, markup = await build_watermark_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Position set to {pos}! 🎯")


@Client.on_callback_query(filters.regex(r"^cb_wm_size_(\d+)$"))
async def cb_wm_size(client, query: CallbackQuery):
    size = int(query.matches[0].group(1))
    await db.set_watermark(query.from_user.id, size=size)
    text, markup = await build_watermark_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Size set to {size}px! 🔤")


@Client.on_callback_query(filters.regex(r"^cb_wm_col_(white|yellow|cyan)$"))
async def cb_wm_col(client, query: CallbackQuery):
    col = query.matches[0].group(1)
    await db.set_watermark(query.from_user.id, color=col)
    text, markup = await build_watermark_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Color set to {col}! 🎨")


# ==================== SAMPLE VIDEO & TIMELINE SUBMENU ====================

async def build_sample_view(user_id: int):
    sample_set = await db.get_sample_settings(user_id)
    dur = sample_set["duration"]
    mode = sample_set["start_mode"]
    status_str = f"ACTIVE ({dur}s)" if dur > 0 else "DISABLED 🔴"

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   🎬 <b>Sample Video Generator</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Status :</b> <b>{status_str}</b>\n"
        f"◈ <b>Duration :</b> <code>{dur} seconds</code>\n"
        f"◈ <b>Timeline Start :</b> <code>{mode}</code>\n\n"
        "<b>Instructions:</b>\n"
        "• Duration: <code>/set_sample &lt;sec&gt;</code> (0-120s)\n"
        "• Timeline: <code>/set_sample_time &lt;MM:SS&gt;</code> (e.g. 05:00)\n"
        "• Auto-generates a clip without your custom thumbnail.\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("OFF", callback_data="cb_sample_dur_0"),
            InlineKeyboardButton("15s", callback_data="cb_sample_dur_15"),
            InlineKeyboardButton("30s", callback_data="cb_sample_dur_30"),
            InlineKeyboardButton("60s", callback_data="cb_sample_dur_60")
        ],
        [
            InlineKeyboardButton("⚡ Auto (15%)", callback_data="cb_sample_mode_auto"),
            InlineKeyboardButton("▶️ 01:00", callback_data="cb_sample_mode_start")
        ],
        [
            InlineKeyboardButton("🎯 Middle (50%)", callback_data="cb_sample_mode_mid"),
            InlineKeyboardButton("🕙 10:00", callback_data="cb_sample_mode_ten")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="open_settings"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ])
    return text, markup


@Client.on_callback_query(filters.regex(r"^cb_sample_menu$"))
async def cb_sample_menu(client, query: CallbackQuery):
    text, markup = await build_sample_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^cb_sample_dur_(\d+)$"))
async def cb_sample_dur(client, query: CallbackQuery):
    dur = int(query.matches[0].group(1))
    await db.set_sample_duration(query.from_user.id, dur)
    text, markup = await build_sample_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Sample duration set to {dur}s! 🎬")


@Client.on_callback_query(filters.regex(r"^cb_sample_mode_(auto|start|mid|ten)$"))
async def cb_sample_mode(client, query: CallbackQuery):
    mode = query.matches[0].group(1)
    await db.set_sample_start_mode(query.from_user.id, mode)
    text, markup = await build_sample_view(query.from_user.id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Timeline start set to {mode}! ⏱️")


@Client.on_message(filters.private & filters.command("set_sample_time"))
async def set_sample_time_cmd(client, message):
    if len(message.command) == 1:
        return await message.reply_text("⚠️ <b>Usage:</b> <code>/set_sample_time MM:SS</code> (e.g. <code>/set_sample_time 03:30</code>)")
    t = message.command[1].strip()
    await db.set_sample_start_mode(message.from_user.id, t)
    await message.reply_text(f"✅ <b>Sample Video Start Time Set:</b> <code>{t}</code>\n\n⚡ @Nex_bots")


# ==================== OTHER SETTINGS CALLBACKS ====================

@Client.on_callback_query(filters.regex(r"^set_cycle_ss$"))
async def set_cycle_ss_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    current = await db.get_screenshots(user_id)
    next_val = 3 if current == 0 else (5 if current == 3 else (8 if current == 5 else (10 if current == 8 else 0)))
    await db.set_screenshots(user_id, next_val)
    text, markup = await build_settings_panel(user_id)
    await edit_message_content(query.message, text, reply_markup=markup)
    await query.answer(f"Screenshots: {next_val} frames 📸" if next_val > 0 else "Screenshots Disabled ❌")


@Client.on_callback_query(filters.regex(r"^set_view_thumb$"))
async def set_view_thumb_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    thumb = await db.get_thumbnail(user_id)
    if thumb:
        await query.answer()
        await client.send_photo(
            chat_id=user_id,
            photo=thumb,
            caption="🖼️ <b>Your Current Custom Thumbnail</b>\n\n⚡ @Nex_bots",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back to Settings", callback_data="open_settings"),
                InlineKeyboardButton("❌ Close", callback_data="close")
            ]])
        )
    else:
        await query.answer("❌ You don't have any custom thumbnail set!", show_alert=True)


@Client.on_callback_query(filters.regex(r"^set_del_thumb$"))
async def set_del_thumb_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    thumb = await db.get_thumbnail(user_id)
    if not thumb:
        return await query.answer("❌ You don't have any thumbnail to delete!", show_alert=True)
    await db.set_thumbnail(user_id, None)
    await query.answer("🗑️ Thumbnail Deleted Successfully!", show_alert=True)
    text, markup = await build_settings_panel(user_id)
    await edit_message_content(query.message, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^set_view_cleaner$"))
async def set_view_cleaner_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    clean_words = await db.get_clean_words(user_id)
    replace_words = await db.get_replace_words(user_id)
    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   🧹 <b>Word Cleaner & Replacer</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🗑️ <b>Words to Remove:</b> <code>{clean_words or 'None'}</code>\n"
        f"🔄 <b>Word Replacements:</b> <code>{replace_words or 'None'}</code>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/set_remove word1, word2</code>\n"
        "• <code>/set_replace old1:new1, old2:new2</code>\n"
        "• <code>/del_cleaner</code> (reset all rules)\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="open_settings"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await edit_message_content(query.message, text, reply_markup=btn)


@Client.on_callback_query(filters.regex(r"^set_view_dump$"))
async def set_view_dump_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    dump = await db.get_dump_channel(user_id)
    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   📦 <b>Private Dump Channel</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"◈ <b>Dump Channel :</b> <code>{dump or 'Not Set'}</code>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/set_dump -100xxxxxxxxxx</code>\n"
        "• <code>/set_dump off</code>\n\n"
        "<i>Note: Both the bot and your Premium Session account must be Admin in the dump channel!</i>\n\n"
        "⚡ @Nex_bots | 💬 Support: @NexCRSupportbot"
    )
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="open_settings"),
         InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await edit_message_content(query.message, text, reply_markup=btn)


# ==================== CANCEL TASK CALLBACK ====================

@Client.on_callback_query(filters.regex(r"^cancel_(\d+)$"))
async def cancel_task_cb(client, query: CallbackQuery):
    task_id = int(query.matches[0].group(1))
    CANCEL_REQUESTS.add(task_id)
    if query.message and query.message.chat:
        CANCEL_REQUESTS.add(f"{query.message.chat.id}_{task_id}")
    await query.answer("Cancelling active task... ✖️", show_alert=True)
    try:
        await query.message.edit_text("❌ <b>Operation Aborted by User!</b>\n\n⚡ @Nex_bots")
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^cancel_action$"))
async def cancel_action_cb(client, query: CallbackQuery):
    if query.message:
        CANCEL_REQUESTS.add(query.message.id)
        if query.message.chat:
            CANCEL_REQUESTS.add(f"{query.message.chat.id}_{query.message.id}")
    await query.answer("Cancelling operation... ✖️", show_alert=True)
    try:
        await query.message.edit_text("❌ <b>Operation Aborted by User!</b>\n\n⚡ @Nex_bots")
    except Exception:
        pass


@Client.on_message(filters.private & filters.command("cancel"))
async def cancel_command(client, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    CANCEL_REQUESTS.add(user_id)
    CANCEL_REQUESTS.add(chat_id)
    await message.reply_text(
        "🛑 <b>Cancellation Request Sent!</b>\n\n"
        "Any active file download, rename, or upload running in this chat will be aborted.\n\n"
        "⚡ @Nex_bots"
    )


# ==================== METADATA COMMANDS ====================

@Client.on_message(filters.private & filters.command("metadata"))
async def view_metadata(client, message):
    text, markup = await build_metadata_view(message.from_user.id)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.private & filters.command("set_metadata"))
async def set_metadata_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please provide a metadata tag!</b>\n\n"
            "<b>Example:</b> <code>/set_metadata Encoded By @Nex_bots</code>"
        )
    tag = message.text.split(" ", 1)[1].strip()
    await db.set_metadata_code(user_id, tag)
    await db.set_metadata_bool(user_id, True)
    await message.reply_text(
        f"✅ <b>Custom Metadata Tag Saved Successfully!</b>\n\n"
        f"🏷️ <b>Tag:</b> <code>{tag}</code>\n"
        f"🟢 <b>Status:</b> ENABLED\n\n"
        f"⚡ <i>This tag will be injected into streams.</i>\n📢 @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("toggle_metadata"))
async def toggle_metadata_cmd(client, message):
    user_id = message.from_user.id
    current = await db.get_metadata_bool(user_id)
    new_state = not current
    await db.set_metadata_bool(user_id, new_state)
    status_str = "ENABLED 🟢" if new_state else "DISABLED 🔴"
    await message.reply_text(f"🏷️ <b>Metadata has been {status_str}</b>\n\n⚡ @Nex_bots")


# ==================== WORD CLEANER & REPLACER COMMANDS ====================

@Client.on_message(filters.private & filters.command("set_remove"))
async def set_remove_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please provide comma-separated words to remove!</b>\n\n"
            "<b>Example:</b> <code>/set_remove [MkvCinemas], @OldChannel, [720p]</code>"
        )
    words = message.text.split(" ", 1)[1].strip()
    await db.set_clean_words(user_id, words)
    await message.reply_text(
        f"✅ <b>Clean Words Saved Successfully!</b>\n\n"
        f"🧹 <b>Words to remove:</b>\n<code>{words}</code>\n\n⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("set_replace"))
async def set_replace_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please provide comma-separated replacement pairs (old:new)!</b>\n\n"
            "<b>Example:</b> <code>/set_replace @OldChannel:@Nex_bots, 1080p:720p</code>"
        )
    pairs = message.text.split(" ", 1)[1].strip()
    if ":" not in pairs:
        return await message.reply_text(
            "❌ <b>Invalid format!</b> Each pair must have a colon (<code>old:new</code>)."
        )
    await db.set_replace_words(user_id, pairs)
    await message.reply_text(
        f"✅ <b>Word Replacements Saved Successfully!</b>\n\n"
        f"🔄 <b>Replacements:</b>\n<code>{pairs}</code>\n\n⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["see_cleaner", "clean_words"]))
async def see_cleaner_cmd(client, message):
    user_id = message.from_user.id
    clean_words = await db.get_clean_words(user_id)
    replace_words = await db.get_replace_words(user_id)

    text = (
        "╭━━━━━━━━━━━━━━━━━━━╮\n"
        "┃   🧹 <b>Active Word Cleaner Settings</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🗑️ <b>Words To Remove:</b> <code>{clean_words or 'None'}</code>\n"
        f"🔄 <b>Word Replacements:</b> <code>{replace_words or 'None'}</code>\n\n"
        "<i>To reset cleaner rules: /del_cleaner</i>\n⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]])
    await message.reply_text(text, reply_markup=btn)


@Client.on_message(filters.private & filters.command("add_clean"))
async def add_clean_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please provide word(s) to add to cleaner!</b>\n\n"
            "<b>Example:</b> <code>/add_clean [MkvCinemas]</code>"
        )
    new_words = message.text.split(" ", 1)[1].strip()
    current = await db.get_clean_words(user_id)
    combined = f"{current}, {new_words}" if current else new_words
    await db.set_clean_words(user_id, combined)
    await message.reply_text(
        f"✅ <b>Word Added to Cleaner!</b>\n\n"
        f"🧹 <b>Active Words:</b> <code>{combined}</code>\n\n⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("del_clean"))
async def del_clean_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please specify the word to remove from cleaner rules!</b>\n\n"
            "<b>Example:</b> <code>/del_clean [MkvCinemas]</code>"
        )
    target = message.text.split(" ", 1)[1].strip().lower()
    current = await db.get_clean_words(user_id)
    if not current:
        return await message.reply_text("❌ <b>You have no active cleaner rules!</b>")
    
    parts = [w.strip() for w in current.split(",") if w.strip()]
    remaining = [w for w in parts if w.lower() != target]
    
    if len(remaining) == len(parts):
        return await message.reply_text(f"⚠️ Word '<code>{target}</code>' not found in your cleaner rules.")
    
    new_val = ", ".join(remaining) if remaining else None
    await db.set_clean_words(user_id, new_val)
    await message.reply_text(
        f"✅ <b>Word Removed from Cleaner!</b>\n\n"
        f"🧹 <b>Remaining:</b> <code>{new_val or 'None'}</code>\n\n⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["clear_clean", "del_cleaner"]))
async def del_cleaner_cmd(client, message):
    user_id = message.from_user.id
    await db.set_clean_words(user_id, None)
    await db.set_replace_words(user_id, None)
    await message.reply_text(
        "🗑️ <b>Word Cleaner & Replacer Rules Cleared Successfully!</b>\n\n⚡ @Nex_bots"
    )


# ==================== SAMPLE VIDEO COMMAND ====================

@Client.on_message(filters.private & filters.command("set_sample"))
async def set_sample_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please specify sample duration in seconds!</b>\n\n"
            "<b>Example:</b> <code>/set_sample 30</code>\n"
            "<b>To Disable:</b> <code>/set_sample 0</code>"
        )
    try:
        duration = int(message.command[1].strip())
    except ValueError:
        return await message.reply_text("❌ Please enter a valid number of seconds.")

    if duration < 0 or duration > 120:
        return await message.reply_text("❌ Sample duration must be between 0 and 120 seconds.")

    await db.set_sample_duration(user_id, duration)
    if duration > 0:
        await message.reply_text(
            f"✅ <b>Sample Video Generator Enabled!</b>\n\n"
            f"🎬 <b>Clip Duration:</b> <code>{duration} seconds</code>\n\n⚡ @Nex_bots"
        )
    else:
        await message.reply_text("❌ <b>Sample Video Generator Disabled!</b>\n\n⚡ @Nex_bots")


# ==================== SCREENSHOT GENERATOR COMMAND ====================

@Client.on_message(filters.private & filters.command(["set_shots", "set_screenshots"]))
async def set_screenshots_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please specify the number of screenshots!</b>\n\n"
            "<b>Example:</b> <code>/set_screenshots 5</code> (Max: 10)\n"
            "<b>To Disable:</b> <code>/set_screenshots 0</code>"
        )
    try:
        count = int(message.command[1].strip())
    except ValueError:
        return await message.reply_text("❌ Please enter a valid number.")

    if count < 0 or count > 10:
        return await message.reply_text("❌ Screenshot count must be between 0 and 10.")

    await db.set_screenshots(user_id, count)
    if count > 0:
        await message.reply_text(
            f"✅ <b>Screenshot Generator Enabled!</b>\n\n"
            f"📸 <b>Screenshots:</b> <code>{count} frames</code>\n\n⚡ @Nex_bots"
        )
    else:
        await message.reply_text("❌ <b>Screenshot Generator Disabled!</b>\n\n⚡ @Nex_bots")


# ==================== DUMP CHANNEL COMMAND ====================

@Client.on_message(filters.private & filters.command("set_dump"))
async def set_dump_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        dump = await db.get_dump_channel(user_id)
        dump_txt = f"<code>{dump}</code>" if dump else "<i>Not Configured</i>"
        return await message.reply_text(
            f"📦 <b><u>Custom Private Dump Channel</u></b>\n\n"
            f"<b>Current Dump:</b> {dump_txt}\n\n"
            f"<b>To Set:</b> <code>/set_dump -100xxxxxxxxxx</code>\n"
            f"<b>To Disable:</b> <code>/set_dump off</code>"
        )
    arg = message.command[1].strip()
    if arg.lower() in ["off", "del", "delete", "disable", "none"]:
        await db.set_dump_channel(user_id, None)
        return await message.reply_text("❌ <b>Custom Dump Channel Disabled!</b>\n\n⚡ @Nex_bots")

    try:
        channel_id = int(arg)
    except ValueError:
        return await message.reply_text("❌ Invalid Channel ID! Must be in format <code>-100xxxxxxxxxx</code>.")

    await db.set_dump_channel(user_id, channel_id)
    await message.reply_text(
        f"✅ <b>Custom Dump Channel Saved!</b>\n\n"
        f"📦 <b>Channel ID:</b> <code>{channel_id}</code>\n\n⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command(["del_dump", "remove_dump"]))
async def del_dump_cmd(client, message):
    user_id = message.from_user.id
    await db.set_dump_channel(user_id, None)
    await message.reply_text("🗑️ <b>Custom Dump Channel Removed Successfully!</b>\n\n⚡ @Nex_bots")


# ==================== DISK / SERVER CACHE CLEANUP (ADMIN) ====================

@Client.on_message(filters.private & filters.command("clear_cache") & filters.user(Config.ADMIN))
async def clear_cache_cmd(client, message):
    ms = await message.reply_text("🧹 <b>Scanning and cleaning cache directory...</b>")
    downloads_dir = "downloads"
    cleaned_bytes = 0
    file_count = 0
    if os.path.exists(downloads_dir):
        for root, dirs, files in os.walk(downloads_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    cleaned_bytes += os.path.getsize(fp)
                    os.remove(fp)
                    file_count += 1
                except Exception:
                    pass
            for d in dirs:
                dp = os.path.join(root, d)
                try:
                    shutil.rmtree(dp)
                except Exception:
                    pass

    total, used, free = shutil.disk_usage(".")
    mem = psutil.virtual_memory()
    text = (
        f"🧹 <b><u>NeX Server Cache Cleanup Completed</u></b>\n\n"
        f"🗑️ <b>Files Deleted :</b> <code>{file_count}</code>\n"
        f"📦 <b>Space Freed :</b> <code>{humanbytes(cleaned_bytes)}</code>\n\n"
        f"💾 <b>Free Disk Space :</b> <code>{get_readable_file_size(free)}</code> / <code>{get_readable_file_size(total)}</code>\n"
        f"🧠 <b>Free RAM :</b> <code>{get_readable_file_size(mem.available)}</code> / <code>{get_readable_file_size(mem.total)}</code> (Usage: {mem.percent}%)\n\n"
        f"⚡ <b>NeX 4GB Rename Bot</b> | @Nex_bots"
    )
    await ms.edit(text)


# ==================== ALL COMMANDS LIST ====================

@Client.on_message(filters.private & filters.command(["commands", "cmds"]))
async def commands_list_cmd(client, message):
    text = (
        "📋 <b><u>NeX 4GB Rename Bot - All Commands</u></b> ⚡\n\n"
        "⚡ <b>Core Commands:</b>\n"
        "• <code>/start</code> - Start the bot & check status\n"
        "• <code>/settings</code> - Open interactive settings dashboard\n"
        "• <code>/commands</code> - View this copy-pasteable commands list\n\n"
        "🏷️ <b>Metadata (FFmpeg):</b>\n"
        "• <code>/metadata</code> - View current metadata settings\n"
        "• <code>/set_metadata &lt;tag&gt;</code> - Set custom metadata tag (e.g. <code>/set_metadata Encoded By @Nex_bots</code>)\n"
        "• <code>/toggle_metadata</code> - Turn metadata ON or OFF\n\n"
        "🧹 <b>Word Cleaner & Replacer:</b>\n"
        "• <code>/set_remove &lt;word1, word2&gt;</code> - Auto-remove words from filenames\n"
        "• <code>/set_replace &lt;old:new, old2:new2&gt;</code> - Auto-replace words\n"
        "• <code>/see_cleaner</code> - View active cleaner rules\n"
        "• <code>/del_cleaner</code> - Clear all cleaner rules\n\n"
        "🎬 <b>Sample Video & Screenshots:</b>\n"
        "• <code>/set_sample &lt;seconds&gt;</code> - Set sample duration (e.g. <code>/set_sample 30</code> or <code>0</code>)\n"
        "• <code>/set_screenshots &lt;count&gt;</code> - Set screenshot count (e.g. <code>/set_screenshots 5</code> or <code>0</code>)\n\n"
        "📦 <b>Dump Channel:</b>\n"
        "• <code>/set_dump &lt;-100channel_id or off&gt;</code> - Set private dump channel\n\n"
        "📝 <b>Caption & Thumbnail:</b>\n"
        "• <code>/set_caption &lt;text&gt;</code> - Set custom formatted caption\n"
        "• <code>/see_caption</code> - View current caption\n"
        "• <code>/del_caption</code> - Delete custom caption\n"
        "• <code>/view_thumb</code> - View current thumbnail\n"
        "• <code>/del_thumb</code> - Delete current thumbnail\n\n"
        "🏷️ <b>Prefix & Suffix:</b>\n"
        "• <code>/set_prefix &lt;text&gt;</code> - Set prefix before filename\n"
        "• <code>/see_prefix</code> - View current prefix\n"
        "• <code>/del_prefix</code> - Delete prefix\n"
        "• <code>/set_suffix &lt;text&gt;</code> - Set suffix after filename\n"
        "• <code>/see_suffix</code> - View current suffix\n"
        "• <code>/del_suffix</code> - Delete suffix\n\n"
        "🛠️ <b>Admin / Owner Commands:</b>\n"
        "• <code>/owner</code> | <code>/admin</code> - Open interactive Owner Control Panel\n"
        "• <code>/mode [private|public]</code> - Toggle or set bot access mode\n"
        "• <code>/add_user &lt;id&gt;</code> | <code>/rem_user &lt;id&gt;</code> - Manage authorized users\n"
        "• <code>/add_prem &lt;id&gt;</code> | <code>/rem_prem &lt;id&gt;</code> - Manage 4GB Premium users\n"
        "• <code>/ban &lt;id&gt;</code> | <code>/unban &lt;id&gt;</code> - Ban or unban users\n"
        "• <code>/set_global_meta &lt;tag&gt;</code> - Set bot default metadata\n"
        "• <code>/status</code> - View bot uptime, ping, and user count\n"
        "• <code>/clear_cache</code> - Clean temp downloads folder\n"
        "• <code>/restart</code> - Restart the bot\n"
        "• <code>/broadcast</code> - Broadcast message to all users (reply to msg)\n\n"
        "📢 <b>Powered by:</b> @Nex_bots"
    )
    btn = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings"),
            InlineKeyboardButton("✖️ Close", callback_data="close")
        ]
    ])
    await message.reply_text(text, reply_markup=btn)
