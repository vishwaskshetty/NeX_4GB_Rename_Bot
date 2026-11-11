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
    
    meta_status = "✅ ON" if settings["metadata_bool"] else "❌ OFF"
    thumb_status = "✅ Set" if settings["thumbnail"] else "❌ None"
    caption_status = "✅ Set" if settings["caption"] else "❌ None"
    prefix_val = settings["prefix"]
    prefix_status = f"✅ <code>{prefix_val[:10]}..</code>" if prefix_val and len(prefix_val) > 10 else (f"✅ <code>{prefix_val}</code>" if prefix_val else "❌ None")
    suffix_val = settings["suffix"]
    suffix_status = f"✅ <code>{suffix_val[:10]}..</code>" if suffix_val and len(suffix_val) > 10 else (f"✅ <code>{suffix_val}</code>" if suffix_val else "❌ None")
    
    sample_status = f"{settings['sample_duration']}s" if settings["sample_duration"] > 0 else "OFF"
    ss_status = str(settings['screenshots']) if settings["screenshots"] > 0 else "OFF"
    cleaner_status = "✅ Active" if (settings["clean_words"] or settings["replace_words"]) else "❌ None"
    dump_status = f"<code>{settings['dump_channel']}</code>" if settings["dump_channel"] else "❌ None"

    text = (
        f"⚙️ <b><u>NeX 4GB Control Panel & Settings</u></b>\n\n"
        f"◈ <b>🏷️ Metadata Engine :</b> {meta_status} (<code>{settings['metadata_code']}</code>)\n"
        f"◈ <b>🖼️ Custom Thumbnail :</b> {thumb_status}\n"
        f"◈ <b>📑 Custom Caption :</b> {caption_status}\n"
        f"◈ <b>🔤 Prefix :</b> {prefix_status}\n"
        f"◈ <b>🔡 Suffix :</b> {suffix_status}\n"
        f"◈ <b>🎬 Sample Video :</b> <code>{sample_status}</code>\n"
        f"◈ <b>📸 Screenshots :</b> <code>{ss_status}</code>\n"
        f"◈ <b>🧹 Word Cleaner :</b> {cleaner_status}\n"
        f"◈ <b>📦 Dump Channel :</b> {dump_status}\n\n"
        f"<i>💡 Tap any button below to toggle or cycle your preferences instantly!</i>\n\n"
        f"⚡ <b>Powered by:</b> @Nex_bots"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🏷️ Metadata: {meta_status}", callback_data="set_toggle_meta")
        ],
        [
            InlineKeyboardButton(f"🎬 Sample Video: {sample_status}", callback_data="set_cycle_sample"),
            InlineKeyboardButton(f"📸 Screenshots: {ss_status}", callback_data="set_cycle_ss")
        ],
        [
            InlineKeyboardButton("🖼️ View Thumbnail", callback_data="set_view_thumb"),
            InlineKeyboardButton("🗑️ Delete Thumbnail", callback_data="set_del_thumb")
        ],
        [
            InlineKeyboardButton("🧹 Cleaner Info", callback_data="set_view_cleaner"),
            InlineKeyboardButton("🔄 Refresh", callback_data="open_settings"),
            InlineKeyboardButton("✖️ Close", callback_data="close")
        ]
    ])
    return text, keyboard


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
    try:
        await edit_message_content(query.message, text, reply_markup=markup)
    except Exception:
        pass
    await query.answer("Settings refreshed! ⚙️")


@Client.on_callback_query(filters.regex(r"^set_toggle_meta$"))
async def set_toggle_meta_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    current = await db.get_metadata_bool(user_id)
    new_state = not current
    await db.set_metadata_bool(user_id, new_state)
    text, markup = await build_settings_panel(user_id)
    try:
        await edit_message_content(query.message, text, reply_markup=markup)
    except Exception:
        pass
    await query.answer(f"Metadata is now {'ENABLED 🟢' if new_state else 'DISABLED 🔴'}")


@Client.on_callback_query(filters.regex(r"^set_cycle_sample$"))
async def set_cycle_sample_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    current = await db.get_sample_duration(user_id)
    # Cycle: OFF (0) -> 15s -> 30s -> 60s -> OFF (0)
    next_val = 15 if current == 0 else (30 if current == 15 else (60 if current == 30 else 0))
    await db.set_sample_duration(user_id, next_val)
    text, markup = await build_settings_panel(user_id)
    try:
        await edit_message_content(query.message, text, reply_markup=markup)
    except Exception:
        pass
    await query.answer(f"Sample Video: {next_val}s 🎬" if next_val > 0 else "Sample Video Disabled ❌")


@Client.on_callback_query(filters.regex(r"^set_cycle_ss$"))
async def set_cycle_ss_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    current = await db.get_screenshots(user_id)
    # Cycle: OFF (0) -> 3 -> 5 -> 8 -> 10 -> OFF (0)
    next_val = 3 if current == 0 else (5 if current == 3 else (8 if current == 5 else (10 if current == 8 else 0)))
    await db.set_screenshots(user_id, next_val)
    text, markup = await build_settings_panel(user_id)
    try:
        await edit_message_content(query.message, text, reply_markup=markup)
    except Exception:
        pass
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
            caption="🖼️ <b>Your Current Custom Thumbnail</b>\n\n⚡ @Nex_bots"
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
    try:
        await edit_message_content(query.message, text, reply_markup=markup)
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^set_view_cleaner$"))
async def set_view_cleaner_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    clean_words = await db.get_clean_words(user_id)
    replace_words = await db.get_replace_words(user_id)
    text = (
        "🧹 <b><u>Word Cleaner & Replacer Rules</u></b>\n\n"
        f"🗑️ <b>Words to Remove:</b> <code>{clean_words or 'None'}</code>\n"
        f"🔄 <b>Word Replacements:</b> <code>{replace_words or 'None'}</code>\n\n"
        "<b>Commands to manage:</b>\n"
        "• <code>/set_remove word1, word2</code>\n"
        "• <code>/set_replace old1:new1, old2:new2</code>\n"
        "• <code>/del_cleaner</code> (reset rules)\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="open_settings")]])
    await edit_message_content(query.message, text, reply_markup=btn)


@Client.on_callback_query(filters.regex(r"^set_view_dump$"))
async def set_view_dump_cb(client, query: CallbackQuery):
    user_id = query.from_user.id
    dump = await db.get_dump_channel(user_id)
    text = (
        "📦 <b><u>Custom Private Dump Channel</u></b>\n\n"
        f"<b>Current Dump Channel:</b> <code>{dump or 'Not Set'}</code>\n\n"
        "<b>Commands to configure:</b>\n"
        "• <code>/set_dump -100xxxxxxxxxx</code> (set channel)\n"
        "• <code>/set_dump off</code> (disable dump)\n\n"
        "<i>Note: Both the bot and your Premium Session account must be Admin in the dump channel!</i>\n\n"
        "⚡ @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="open_settings")]])
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


# ==================== METADATA COMMANDS ====================

@Client.on_message(filters.private & filters.command("metadata"))
async def view_metadata(client, message):
    user_id = message.from_user.id
    meta_bool = await db.get_metadata_bool(user_id)
    meta_code = await db.get_metadata_code(user_id)
    
    status = "ENABLED 🟢" if meta_bool else "DISABLED 🔴"
    text = (
        f"🏷️ <b><u>NeX 4GB Metadata Engine</u></b>\n\n"
        f"<b>Status:</b> {status}\n"
        f"<b>Current Tag:</b> <code>{meta_code}</code>\n\n"
        f"<i>To change tag:</i> <code>/set_metadata &lt;your text&gt;</code>\n"
        f"<i>To toggle ON/OFF:</i> <code>/toggle_metadata</code>\n\n"
        f"⚡ <b>Powered by:</b> @Nex_bots"
    )
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Toggle Status", callback_data="set_toggle_meta"),
        InlineKeyboardButton("✖️ Close", callback_data="close")
    ]])
    await message.reply_text(text, reply_markup=btn)


@Client.on_message(filters.private & filters.command("set_metadata"))
async def set_metadata_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please provide a metadata tag!</b>\n\n"
            "<b>Example:</b> <code>/set_metadata Encoded By @Nex_bots</code>\n"
            "<b>Example:</b> <code>/set_metadata Telegram : @Nex_bots</code>"
        )
    tag = message.text.split(" ", 1)[1].strip()
    await db.set_metadata_code(user_id, tag)
    await db.set_metadata_bool(user_id, True)
    await message.reply_text(
        f"✅ <b>Custom Metadata Tag Saved Successfully!</b>\n\n"
        f"🏷️ <b>Tag:</b> <code>{tag}</code>\n"
        f"🟢 <b>Status:</b> ENABLED\n\n"
        f"⚡ <i>This tag will be injected into title, author, artist, and audio/video/subtitle streams.</i>\n"
        f"📢 @Nex_bots"
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
            "<b>Example:</b> <code>/set_remove [MkvCinemas], @OldChannel, [720p]</code>\n\n"
            "<i>These words/phrases will be automatically stripped from your filenames when using Auto Clean & Rename.</i>"
        )
    words = message.text.split(" ", 1)[1].strip()
    await db.set_clean_words(user_id, words)
    await message.reply_text(
        f"✅ <b>Clean Words Saved Successfully!</b>\n\n"
        f"🧹 <b>Words to remove:</b>\n<code>{words}</code>\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("set_replace"))
async def set_replace_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please provide comma-separated replacement pairs (old:new)!</b>\n\n"
            "<b>Example:</b> <code>/set_replace @OldChannel:@Nex_bots, 1080p:720p</code>\n\n"
            "<i>Format: old_word:new_word, separated by commas.</i>"
        )
    pairs = message.text.split(" ", 1)[1].strip()
    if ":" not in pairs:
        return await message.reply_text(
            "❌ <b>Invalid format!</b> Each pair must have a colon (<code>old:new</code>).\n\n"
            "<b>Example:</b> <code>/set_replace @Old:@Nex_bots, 1080p:720p</code>"
        )
    await db.set_replace_words(user_id, pairs)
    await message.reply_text(
        f"✅ <b>Word Replacements Saved Successfully!</b>\n\n"
        f"🔄 <b>Replacements:</b>\n<code>{pairs}</code>\n\n"
        f"⚡ @Nex_bots"
    )


@Client.on_message(filters.private & filters.command("see_cleaner"))
async def see_cleaner_cmd(client, message):
    user_id = message.from_user.id
    clean_words = await db.get_clean_words(user_id)
    replace_words = await db.get_replace_words(user_id)

    text = "🧹 <b><u>Your Active Word Cleaner Settings</u></b>\n\n"
    if clean_words:
        text += f"🗑️ <b>Words To Remove:</b>\n<code>{clean_words}</code>\n\n"
    else:
        text += "🗑️ <b>Words To Remove:</b> <i>None configured</i>\n\n"

    if replace_words:
        text += f"🔄 <b>Word Replacements:</b>\n<code>{replace_words}</code>\n\n"
    else:
        text += "🔄 <b>Word Replacements:</b> <i>None configured</i>\n\n"

    text += "<i>To reset cleaner rules: /del_cleaner</i>\n⚡ @Nex_bots"
    await message.reply_text(text)


@Client.on_message(filters.private & filters.command("del_cleaner"))
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
            "<b>Example:</b> <code>/set_sample 30</code> (for a 30-second sample clip)\n"
            "<b>To Disable:</b> <code>/set_sample 0</code>"
        )
    try:
        duration = int(message.command[1].strip())
    except ValueError:
        return await message.reply_text("❌ Please enter a valid number of seconds (e.g. <code>/set_sample 30</code>).")

    if duration < 0 or duration > 120:
        return await message.reply_text("❌ Sample duration must be between 0 and 120 seconds.")

    await db.set_sample_duration(user_id, duration)
    if duration > 0:
        await message.reply_text(
            f"✅ <b>Sample Video Generator Enabled!</b>\n\n"
            f"🎬 <b>Clip Duration:</b> <code>{duration} seconds</code>\n\n"
            f"<i>A sample clip will be automatically generated and sent whenever you rename a video.</i>\n"
            f"⚡ @Nex_bots"
        )
    else:
        await message.reply_text("❌ <b>Sample Video Generator Disabled!</b>\n\n⚡ @Nex_bots")


# ==================== SCREENSHOT GENERATOR COMMAND ====================

@Client.on_message(filters.private & filters.command("set_screenshots"))
async def set_screenshots_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) == 1:
        return await message.reply_text(
            "⚠️ <b>Please specify the number of screenshots!</b>\n\n"
            "<b>Example:</b> <code>/set_screenshots 5</code> (generates 5 evenly spaced screenshots)\n"
            "<b>To Disable:</b> <code>/set_screenshots 0</code> (Max: 10)"
        )
    try:
        count = int(message.command[1].strip())
    except ValueError:
        return await message.reply_text("❌ Please enter a valid number (e.g. <code>/set_screenshots 5</code>).")

    if count < 0 or count > 10:
        return await message.reply_text("❌ Screenshot count must be between 0 and 10.")

    await db.set_screenshots(user_id, count)
    if count > 0:
        await message.reply_text(
            f"✅ <b>Screenshot Generator Enabled!</b>\n\n"
            f"📸 <b>Screenshots:</b> <code>{count} frames</code>\n\n"
            f"<i>{count} evenly spaced screenshots will be captured and sent as an album whenever you rename a video.</i>\n"
            f"⚡ @Nex_bots"
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
            f"<b>To Disable:</b> <code>/set_dump off</code>\n\n"
            f"⚠️ <b>Important:</b> Ensure both this bot and your 4GB Premium Account are added as <b>Admin</b> to the channel!"
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
        f"📦 <b>Channel ID:</b> <code>{channel_id}</code>\n\n"
        f"⚡ <i>Your renamed files will be backed up here.</i>\n"
        f"📢 @Nex_bots"
    )


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
        "🛠️ <b>Admin Commands:</b>\n"
        "• <code>/status</code> - View bot uptime, ping, and user count\n"
        "• <code>/clear_cache</code> - Clean temp downloads folder & show RAM/Disk\n"
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
