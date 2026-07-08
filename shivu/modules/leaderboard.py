import os
import time
import asyncio
import random
import html

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import (application, PHOTO_URL, OWNER_ID,
                    user_collection, top_global_groups_collection,
                    group_user_totals_collection)

from shivu import sudo_users as SUDO_USERS
from shivu.cache import (
    global_users_cache,
    global_groups_cache,
    group_leaderboard_cache,
    group_leaderboard_locks,
)

GROUP_CACHE_TTL = 600

GROUPS_ONLY_TEXT = 'This command only works in groups.'


def format_count(count: int) -> str:
    return f'{count:,}'


async def build_group_ranked_list(chat_id: int):
    cursor = group_user_totals_collection.find(
        {'group_id': chat_id},
        {'user_id': 1, 'username': 1, 'first_name': 1, 'count': 1, '_id': 0}
    ).sort('count', -1)

    return await cursor.to_list(length=None)


async def get_group_leaderboard(chat_id: int):
    entry = group_leaderboard_cache.get(chat_id)
    now = time.time()

    if entry and now - entry['refreshed_at'] < GROUP_CACHE_TTL:
        return entry

    if chat_id not in group_leaderboard_locks:
        group_leaderboard_locks[chat_id] = asyncio.Lock()
    lock = group_leaderboard_locks[chat_id]

    async with lock:
        entry = group_leaderboard_cache.get(chat_id)
        now = time.time()
        if entry and now - entry['refreshed_at'] < GROUP_CACHE_TTL:
            return entry

        ranked_list = await build_group_ranked_list(chat_id)
        entry = {'ranked_list': ranked_list, 'refreshed_at': now}
        group_leaderboard_cache[chat_id] = entry
        return entry


def find_user_rank(ranked_list, user_id):
    for index, entry in enumerate(ranked_list, start=1):
        if entry.get('user_id') == user_id:
            return index, entry.get('count', 0)
    return None, 0


def build_top_users_block(ranked_list, count_field):
    lines = []
    for i, user in enumerate(ranked_list[:10], start=1):
        username = user.get('username', '')
        first_name = html.escape(user.get('first_name', 'Unknown'))

        if len(first_name) > 15:
            first_name = first_name[:15] + '...'

        count = format_count(user.get(count_field, 0))

        if username:
            lines.append(f'#{i} <a href="https://t.me/{username}"><b>{first_name}</b></a> • <b>{count}</b>')
        else:
            lines.append(f'#{i} <b>{first_name}</b> • <b>{count}</b>')

    return '\n'.join(lines)


async def ctop(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.type == 'private':
        await update.message.reply_text(GROUPS_ONLY_TEXT)
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    entry = await get_group_leaderboard(chat_id)
    ranked_list = entry['ranked_list']

    group_name = html.escape(update.effective_chat.title or 'This Group')

    leaderboard_message = f'<b>⌬ {group_name} • Top Collectors</b>\n\n'
    leaderboard_message += build_top_users_block(ranked_list, 'count')

    rank, count = find_user_rank(ranked_list, user_id)
    leaderboard_message += '\n\n<b>Your Rank</b>\n'
    if rank:
        leaderboard_message += f'#{rank} • {format_count(count)}'
    else:
        leaderboard_message += 'Not Ranked Yet'

    photo_url = random.choice(PHOTO_URL) if PHOTO_URL else None
    if photo_url:
        await update.message.reply_photo(photo=photo_url, caption=leaderboard_message, parse_mode='HTML')
    else:
        await update.message.reply_text(leaderboard_message, parse_mode='HTML')


async def topusers(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.type == 'private':
        await update.message.reply_text(GROUPS_ONLY_TEXT)
        return

    user_id = update.effective_user.id

    ranked_list = global_users_cache.get('ranked_list', [])

    leaderboard_message = '<b>⌬ Global Top Collectors</b>\n\n'
    leaderboard_message += build_top_users_block(ranked_list, 'character_count')

    rank, count = find_user_rank(ranked_list, user_id)
    leaderboard_message += '\n\n<b>Your Rank</b>\n'
    if rank:
        first_name = html.escape(update.effective_user.first_name or 'Unknown')
        leaderboard_message += f'#{rank} {first_name} • {format_count(count)}'
    else:
        leaderboard_message += 'Not Ranked Yet'

    photo_url = random.choice(PHOTO_URL) if PHOTO_URL else None
    if photo_url:
        await update.message.reply_photo(photo=photo_url, caption=leaderboard_message, parse_mode='HTML')
    else:
        await update.message.reply_text(leaderboard_message, parse_mode='HTML')


async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.type == 'private':
        await update.message.reply_text(GROUPS_ONLY_TEXT)
        return

    chat_id = update.effective_chat.id

    ranked_list = global_groups_cache.get('ranked_list', [])

    leaderboard_message = '<b>⌬ Global Top Groups</b>\n\n'

    lines = []
    for i, group in enumerate(ranked_list[:10], start=1):
        group_name = html.escape(group.get('group_name', 'Unknown'))

        if len(group_name) > 15:
            group_name = group_name[:15] + '...'

        count = format_count(group.get('count', 0))
        lines.append(f'#{i} <b>{group_name}</b> • <b>{count}</b>')

    leaderboard_message += '\n'.join(lines)

    rank = None
    count = 0
    for index, group in enumerate(ranked_list, start=1):
        if group.get('group_id') == chat_id:
            rank = index
            count = group.get('count', 0)
            break

    leaderboard_message += '\n\n<b>Your Group Rank</b>\n'
    if rank:
        group_name = html.escape(update.effective_chat.title or 'This Group')
        leaderboard_message += f'#{rank} {group_name} • {format_count(count)}'
    else:
        leaderboard_message += 'Not Ranked Yet'

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

application.add_handler(CommandHandler(['ctop', 'gtop', 'chattop', 'grouptop'], ctop, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('TopGroups', global_leaderboard, block=False))

application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))

application.add_handler(CommandHandler('topusers', topusers, block=False))
