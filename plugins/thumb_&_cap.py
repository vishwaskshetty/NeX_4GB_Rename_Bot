from pyrogram import Client, filters 
from helper.database import db

# NeX 4GB Rename Bot - Thumbnail & Caption Manager
# Developed by @Nex_bots


@Client.on_message(filters.private & filters.command('set_caption'))
async def add_caption(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            "<b>Please provide a custom caption!</b>\n\n"
            "<b>Available Format Tags:</b>\n"
            "• <code>{filename}</code> - Renamed file name\n"
            "• <code>{filesize}</code> - Human-readable file size\n"
            "• <code>{duration}</code> - Video/audio duration\n\n"
            "<b>Example:</b>\n"
            "<code>/set_caption 📕 <b>Name :</b> {filename}\n🔗 <b>Size :</b> {filesize}\n⏰ <b>Duration :</b> {duration}\n\n⚡ @Nex_bots</code>"
        )
    caption = message.text.split(" ", 1)[1]
    await db.set_caption(message.from_user.id, caption=caption)
    await message.reply_text("✅ <b>Your Custom Caption has been saved successfully!</b>\n\n⚡ @Nex_bots")
   

@Client.on_message(filters.private & filters.command('del_caption'))
async def delete_caption(client, message):
    caption = await db.get_caption(message.from_user.id)  
    if not caption:
        return await message.reply_text("❌ <b>You do not have any active custom caption!</b>")
    await db.set_caption(message.from_user.id, caption=None)
    await message.reply_text("🗑️ <b>Custom Caption Deleted Successfully!</b>\n\n⚡ @Nex_bots")
                                        

@Client.on_message(filters.private & filters.command(['see_caption', 'view_caption']))
async def see_caption(client, message):
    caption = await db.get_caption(message.from_user.id)  
    if caption:
        await message.reply_text(f"📑 <b><u>Your Current Custom Caption</u>:</b>\n\n<code>{caption}</code>\n\n⚡ @Nex_bots")
    else:
        await message.reply_text("❌ <b>You do not have any custom caption set!</b>\n\nUse <code>/set_caption &lt;text&gt;</code> to set one.")


@Client.on_message(filters.private & filters.command(['view_thumb', 'viewthumb']))
async def viewthumb(client, message):    
    thumb = await db.get_thumbnail(message.from_user.id)
    if thumb:
        await client.send_photo(
            chat_id=message.chat.id,
            photo=thumb,
            caption="🖼️ <b>Your Active Custom Thumbnail</b>\n\n<i>This image will be attached to all renamed files.</i>\n\n⚡ @Nex_bots"
        )
    else:
        await message.reply_text("❌ <b>You do not have any custom thumbnail set!</b>\n\n<i>Send any photo to set it as your thumbnail.</i>") 
		

@Client.on_message(filters.private & filters.command(['del_thumb', 'delthumb']))
async def removethumb(client, message):
    thumb = await db.get_thumbnail(message.from_user.id)
    if not thumb:
        return await message.reply_text("❌ <b>You do not have any custom thumbnail to delete!</b>")
    await db.set_thumbnail(message.from_user.id, file_id=None)
    await message.reply_text("🗑️ <b>Custom Thumbnail Deleted Successfully!</b>\n\n⚡ @Nex_bots")
	

@Client.on_message(filters.private & filters.photo)
async def addthumbs(client, message):
    ms = await message.reply_text("⏳ <i>Processing and saving thumbnail...</i>")
    await db.set_thumbnail(message.from_user.id, file_id=message.photo.file_id)                
    await ms.edit("✅ <b>Custom Thumbnail Saved Successfully!</b>\n\n<i>Aspect ratio will be preserved automatically.</i>\n\n⚡ @Nex_bots")
