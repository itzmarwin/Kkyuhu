import os
import random
import html

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import (application, PHOTO_URL, OWNER_ID,
                    user_collection, top_global_groups_collection, 
                    group_user_totals_collection)

from shivu import sudo_users as SUDO_USERS 

async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    cursor = top_global_groups_collection.find(
        {}, 
        {'group_name': 1, 'count': 1, '_id': 0}
    ).sort('count', -1).limit(10)
    
    leaderboard_data = await cursor.to_list(length=10)

    leaderboard_message = "<b>TOP 10 GROUPS WHO GUESSED MOST CHARACTERS</b>\n\n"

    for i, group in enumerate(leaderboard_data, start=1):
        group_name = html.escape(group.get('group_name', 'Unknown'))

        if len(group_name) > 15:
            group_name = group_name[:15] + '...'
            
        count = group.get('count', 0)
        leaderboard_message += f'{i}. <b>{group_name}</b> ➾ <b>{count}</b>\n'
    
    photo_url = random.choice(PHOTO_URL) if PHOTO_URL else None
    if photo_url:
        await update.message.reply_photo(photo=photo_url, caption=leaderboard_message, parse_mode='HTML')
    else:
        await update.message.reply_text(leaderboard_message, parse_mode='HTML')

async def ctop(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    cursor = group_user_totals_collection.find(
        {'group_id': chat_id}, 
        {'username': 1, 'first_name': 1, 'count': 1, '_id': 0}
    ).sort('count', -1).limit(10)
    
    leaderboard_data = await cursor.to_list(length=10)

    leaderboard_message = "<b>TOP 10 USERS WHO GUESSED CHARACTERS MOST TIME IN THIS GROUP..</b>\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', '')
        first_name = html.escape(user.get('first_name', 'Unknown'))

        if len(first_name) > 15:
            first_name = first_name[:15] + '...'
            
        character_count = user.get('count', 0)
        
        if username:
            leaderboard_message += f'{i}. <a href="https://t.me/{username}"><b>{first_name}</b></a> ➾ <b>{character_count}</b>\n'
        else:
            leaderboard_message += f'{i}. <b>{first_name}</b> ➾ <b>{character_count}</b>\n'
    
    photo_url = random.choice(PHOTO_URL) if PHOTO_URL else None
    if photo_url:
        await update.message.reply_photo(photo=photo_url, caption=leaderboard_message, parse_mode='HTML')
    else:
        await update.message.reply_text(leaderboard_message, parse_mode='HTML')

async def leaderboard(update: Update, context: CallbackContext) -> None:
    cursor = user_collection.find(
        {'character_count': {'$gt': 0}},
        {'username': 1, 'first_name': 1, 'character_count': 1, '_id': 0}
    ).sort('character_count', -1).limit(10)

    leaderboard_data = await cursor.to_list(length=10)

    leaderboard_message = "<b>TOP 10 USERS WITH MOST CHARACTERS</b>\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', '')
        first_name = html.escape(user.get('first_name', 'Unknown'))

        if len(first_name) > 15:
            first_name = first_name[:15] + '...'
            
        character_count = user.get('character_count', 0)
        
        if username:
            leaderboard_message += f'{i}. <a href="https://t.me/{username}"><b>{first_name}</b></a> ➾ <b>{character_count}</b>\n'
        else:
            leaderboard_message += f'{i}. <b>{first_name}</b> ➾ <b>{character_count}</b>\n'
    
    photo_url = random.choice(PHOTO_URL) if PHOTO_URL else None
    if photo_url:
        await update.message.reply_photo(photo=photo_url, caption=leaderboard_message, parse_mode='HTML')
    else:
        await update.message.reply_text(leaderboard_message, parse_mode='HTML')

async def stats(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    user_count = await user_collection.estimated_document_count()
    group_count = await top_global_groups_collection.estimated_document_count()

    await update.message.reply_text(f'Total Users: {user_count}\nTotal groups: {group_count}')

async def send_users_document(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('only For Sudo users...')
        return
        
    filename = 'users.txt'
    with open(filename, 'w', encoding='utf-8') as f:
        async for user in user_collection.find({}, {'first_name': 1}):
            f.write(f"{user.get('first_name', 'Unknown')}\n")
            
    with open(filename, 'rb') as f:
        await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
    os.remove(filename)

async def send_groups_document(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('Only For Sudo users...')
        return
        
    filename = 'groups.txt'
    with open(filename, 'w', encoding='utf-8') as f:
        async for group in top_global_groups_collection.find({}, {'group_name': 1}):
            f.write(f"{group.get('group_name', 'Unknown')}\n\n")
            
    with open(filename, 'rb') as f:
        await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
    os.remove(filename)

application.add_handler(CommandHandler('ctop', ctop, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('TopGroups', global_leaderboard, block=False))

application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))

application.add_handler(CommandHandler('top', leaderboard, block=False))
