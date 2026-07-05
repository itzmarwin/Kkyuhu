from pymongo import ReturnDocument
from pyrogram.enums import ChatMemberStatus, ChatType  # Changed to pyrogram
from shivu import user_totals_collection, shivuu
from pyrogram import Client, filters  # Changed to pyrogram
from pyrogram.types import Message  # Changed to pyrogram

# Tumhara Plan: Memory cache import kar rahe hain taaki update kar saken
from shivu.__main__ import group_freq_cache

ADMINS = [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]

@shivuu.on_message(filters.command("changetime"))
async def change_time(client: Client, message: Message):
    
    # Crash fix: Agar anonymous admin ya channel post ho toh from_user None ho sakta hai
    if not message.from_user:
        await message.reply_text("Please use this command as a normal admin, not anonymous.")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        member = await shivuu.get_chat_member(chat_id, user_id)
    except Exception as e:
        await message.reply_text(f"Failed to check admin status: {str(e)}")
        return

    if member.status not in ADMINS:
        await message.reply_text('You are not an Admin.')
        return

    try:
        args = message.command
        if len(args) != 2:
            await message.reply_text('Please use: /changetime NUMBER')
            return

        new_frequency = int(args[1])
        if new_frequency < 100:
            await message.reply_text('The message frequency must be greater than or equal to 100.')
            return

        # MongoDB Update
        await user_totals_collection.find_one_and_update(
            {'chat_id': str(chat_id)},
            {'$set': {'message_frequency': new_frequency}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

        # TUMHARA PLAN: Memory Cache Update
        group_freq_cache[str(chat_id)] = new_frequency

        await message.reply_text(f'Successfully changed drop frequency to {new_frequency} messages. Next cycle will use this new limit!')
    except Exception as e:
        await message.reply_text(f'Failed to change {str(e)}')
