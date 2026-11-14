from pyrogram import Client, filters
from helper.database import db

# NeX 4GB Rename Bot - Prefix & Suffix Engine
# Developed by @Nex_bots


# ==================== PREFIX COMMANDS ====================

@Client.on_message(filters.private & filters.command('set_prefix'))
async def add_prefix(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "<b>Please provide a prefix!</b>\n\n"
            "<b>Example:</b> <code>/set_prefix @Nex_bots</code>\n"
            "<i>This tag will be prepended to your filename.</i>"
        )
    prefix = message.text.split(" ", 1)[1].strip()
    ms = await message.reply_text("⏳ <i>Saving prefix...</i>")
    await db.set_prefix(message.from_user.id, prefix)
    await ms.edit(f"✅ <b>Prefix Saved Successfully!</b>\n\n🔤 <b>Prefix:</b> <code>{prefix}</code>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command('del_prefix'))
async def delete_prefix(client, message):
    ms = await message.reply_text("⏳ <i>Deleting prefix...</i>")
    prefix = await db.get_prefix(message.from_user.id)
    if not prefix:
        return await ms.edit("❌ <b>You do not have any prefix configured!</b>")
    await db.set_prefix(message.from_user.id, None)
    await ms.edit("🗑️ <b>Prefix Deleted Successfully!</b>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command('see_prefix'))
async def see_prefix(client, message):
    ms = await message.reply_text("⏳ <i>Fetching prefix...</i>")
    prefix = await db.get_prefix(message.from_user.id)
    if prefix:
        await ms.edit(f"🔤 <b><u>Your Current Prefix</u>:</b>\n\n<code>{prefix}</code>\n\n⚡ @Nex_bots")
    else:
        await ms.edit("❌ <b>You do not have any prefix configured!</b>\n\nUse <code>/set_prefix &lt;prefix&gt;</code> to set one.")


# ==================== SUFFIX COMMANDS ====================

@Client.on_message(filters.private & filters.command('set_suffix'))
async def add_suffix(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "<b>Please provide a suffix!</b>\n\n"
            "<b>Example:</b> <code>/set_suffix @Nex_bots</code>\n"
            "<i>This tag will be appended right before the file extension.</i>"
        )
    suffix = message.text.split(" ", 1)[1].strip()
    ms = await message.reply_text("⏳ <i>Saving suffix...</i>")
    await db.set_suffix(message.from_user.id, suffix)
    await ms.edit(f"✅ <b>Suffix Saved Successfully!</b>\n\n🔡 <b>Suffix:</b> <code>{suffix}</code>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command('del_suffix'))
async def delete_suffix(client, message):
    ms = await message.reply_text("⏳ <i>Deleting suffix...</i>")
    suffix = await db.get_suffix(message.from_user.id)
    if not suffix:
        return await ms.edit("❌ <b>You do not have any suffix configured!</b>")
    await db.set_suffix(message.from_user.id, None)
    await ms.edit("🗑️ <b>Suffix Deleted Successfully!</b>\n\n⚡ @Nex_bots")


@Client.on_message(filters.private & filters.command('see_suffix'))
async def see_suffix(client, message):
    ms = await message.reply_text("⏳ <i>Fetching suffix...</i>")
    suffix = await db.get_suffix(message.from_user.id)
    if suffix:
        await ms.edit(f"🔡 <b><u>Your Current Suffix</u>:</b>\n\n<code>{suffix}</code>\n\n⚡ @Nex_bots")
    else:
        await ms.edit("❌ <b>You do not have any suffix configured!</b>\n\nUse <code>/set_suffix &lt;suffix&gt;</code> to set one.")
