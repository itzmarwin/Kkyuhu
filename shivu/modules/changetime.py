from pyrogram.enums import ChatMemberStatus, ChatType
from shivu import shivuu
from shivu.database import set_group_message_frequency
from pyrogram import Client, filters
from pyrogram.types import Message
from shivu.cache import group_freq_cache

ADMINS = [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]

@shivuu.on_message(filters.command("changetime"))
async def change_time(client: Client, message: Message):
    
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

        await set_group_message_frequency(str(chat_id), new_frequency)

        group_freq_cache[str(chat_id)] = new_frequency

        await message.reply_text(f'Successfully changed drop frequency to {new_frequency} messages. Next cycle will use this new limit!')
    except Exception as e:
        await message.reply_text(f'Failed to change {str(e)}')
