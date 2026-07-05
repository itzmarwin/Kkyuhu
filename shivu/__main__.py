import importlib
import time
import random
import re
import asyncio
from html import escape 

from pymongo import ASCENDING
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters

from shivu import collection, top_global_groups_collection, group_user_totals_collection, user_collection, user_totals_collection, shivuu
from shivu import application, SUPPORT_CHAT, UPDATE_CHAT, db, LOGGER
from shivu.modules import ALL_MODULES


all_characters_cache = []   
characters_by_id = {}       
group_freq_cache = {}       


locks = {}
message_counts = {}
last_characters = {}
sent_characters = {}
first_correct_guesses = {}

last_user = {}
warned_users = {}

RARITY_WEIGHTS = {
    "⚪ Common": 100,
    "🟢 Medium": 50,
    "🟣 Rare": 25,
    "🟡 Legendary": 10,
    "💮 Special edition": 3,
}



async def ensure_indexes():
    await collection.create_index([('id', ASCENDING)])
    await collection.create_index([('anime', ASCENDING)])
    await user_collection.create_index([('id', ASCENDING)])
    await user_collection.create_index([('characters.id', ASCENDING)])
    await user_collection.create_index([('character_count', -1)])
    LOGGER.info("Indexes ensured.")

async def load_characters_into_memory():
    """Fetch all characters (startup pe, aur upload/delete/update ke baad re-sync ke liye reusable)"""
    LOGGER.info("Loading all characters into memory...")
    fresh_data = await collection.find({}).to_list(length=None)

    all_characters_cache.clear()
    all_characters_cache.extend(fresh_data)

    characters_by_id.clear()
    characters_by_id.update({c['id']: c for c in fresh_data})

    LOGGER.info(f"Loaded {len(all_characters_cache)} characters into memory!")

async def grant_character_to_user(user_id: int, character_id: int, username=None, first_name=None) -> None:
    inc_fields = {'characters.$.count': 1, 'character_count': 1}
    set_fields = {}
    if username is not None:
        set_fields['username'] = username
    if first_name is not None:
        set_fields['first_name'] = first_name

    update_doc = {'$inc': inc_fields}
    if set_fields:
        update_doc['$set'] = set_fields

    result = await user_collection.update_one(
        {'id': user_id, 'characters.id': character_id},
        update_doc,
    )
    if result.matched_count == 0:
        push_doc = {
            '$push': {'characters': {'id': character_id, 'count': 1}},
            '$inc': {'character_count': 1},
        }
        if set_fields:
            push_doc['$set'] = set_fields
        await user_collection.update_one(
            {'id': user_id},
            push_doc,
            upsert=True,
        )

async def remove_character_from_user(user_id: int, character_id: int) -> None:
    await user_collection.update_one(
        {'id': user_id, 'characters.id': character_id},
        {'$inc': {'characters.$.count': -1, 'character_count': -1}},
    )
    await user_collection.update_one(
        {'id': user_id},
        {'$pull': {'characters': {'id': character_id, 'count': {'$lte': 0}}}},
    )

def escape_markdown(text):
    escape_chars = r'\*_`\\~>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)



for module_name in ALL_MODULES:
    imported_module = importlib.import_module("shivu.modules." + module_name)

async def message_counter(update: Update, context: CallbackContext) -> None:
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id

    if update.message is None or update.message.text is None:
        return

    if chat_id not in locks:
        locks[chat_id] = asyncio.Lock()
    lock = locks[chat_id]

    should_send = False

    async with lock:
        if chat_id in last_user and last_user[chat_id]['user_id'] == user_id:
            last_user[chat_id]['count'] += 1
            if last_user[chat_id]['count'] >= 10:
                if user_id in warned_users and time.time() - warned_users[user_id] < 600:
                    return
                else:
                    await update.message.reply_text(f"Don't Spam {update.effective_user.first_name}...\nYour Messages Will be ignored for 10 Minutes...")
                    warned_users[user_id] = time.time()
                    return
        else:
            last_user[chat_id] = {'user_id': user_id, 'count': 1}

        if chat_id not in message_counts:
            message_counts[chat_id] = 0

        if chat_id not in group_freq_cache:
            chat_frequency = await user_totals_collection.find_one({'chat_id': chat_id})
            freq = chat_frequency.get('message_frequency', 100) if chat_frequency else 100
            group_freq_cache[chat_id] = freq

        current_cycle_freq = group_freq_cache[chat_id]

        message_counts[chat_id] += 1

        if message_counts[chat_id] >= current_cycle_freq:
            message_counts[chat_id] = 0
            should_send = True

    if should_send:
        await send_image(update, context)

async def send_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if not all_characters_cache:
        await context.bot.send_message(chat_id=chat_id, text="No characters found in database!")
        return

    if chat_id not in sent_characters:
        sent_characters[chat_id] = {}

    available_chars = [c for c in all_characters_cache if c['id'] not in sent_characters[chat_id]]

    if not available_chars:
        sent_characters[chat_id] = {}
        available_chars = all_characters_cache

    weights = [RARITY_WEIGHTS.get(c['rarity'], 1) for c in available_chars]
    character = random.choices(available_chars, weights=weights, k=1)[0]

    if len(sent_characters[chat_id]) > 50:
        sent_characters[chat_id] = dict(list(sent_characters[chat_id].items())[-20:])

    sent_characters[chat_id][character['id']] = True
    last_characters[chat_id] = character

    if chat_id in first_correct_guesses:
        del first_correct_guesses[chat_id]

    await context.bot.send_photo(
        chat_id=chat_id,
        photo=character['img_url'],
        caption=f"""A New {character['rarity']} Character Appeared...\n/guess Character Name and add in Your Harem""",
        parse_mode='Markdown')

async def guess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in last_characters:
        return

    if chat_id in first_correct_guesses:
        await update.message.reply_text('❌️ Already Guessed By Someone.. Try Next Time Bruhh ')
        return

    guess_text = ' '.join(context.args).lower() if context.args else ''
    
    if "()" in guess_text or "&" in guess_text.lower():
        await update.message.reply_text("Nahh You Can't use This Types of words in your guess..❌️")
        return

    name_parts = last_characters[chat_id]['name'].lower().split()

    if sorted(name_parts) == sorted(guess_text.split()) or any(part == guess_text for part in name_parts):
        first_correct_guesses[chat_id] = user_id

        character = last_characters[chat_id]

        user_update = grant_character_to_user(
            user_id, character['id'],
            update.effective_user.username, update.effective_user.first_name,
        )

        group_user_update = group_user_totals_collection.update_one(
            {'user_id': user_id, 'group_id': chat_id},
            {
                '$set': {
                    'username': update.effective_user.username,
                    'first_name': update.effective_user.first_name,
                },
                '$inc': {'count': 1},
            },
            upsert=True,
        )

        group_update = top_global_groups_collection.update_one(
            {'group_id': chat_id},
            {
                '$set': {'group_name': update.effective_chat.title},
                '$inc': {'count': 1},
            },
            upsert=True,
        )

        await asyncio.gather(user_update, group_user_update, group_update)

        keyboard = [[InlineKeyboardButton(f"See Harem", switch_inline_query_current_chat=f"collection.{user_id}")]]

        await update.message.reply_text(
            f'<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> You Guessed a New Character ✅️ \n\n'
            f'𝗡𝗔𝗠𝗘: <b>{character["name"]}</b> \n'
            f'𝗔𝗡𝗜𝗠𝗘: <b>{character["anime"]}</b> \n'
            f'𝗥𝗔𝗜𝗥𝗧𝗬: <b>{character["rarity"]}</b>\n\n'
            f'This Character added in Your harem.. use /harem To see your harem',
            parse_mode='HTML', 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text('Please Write Correct Character Name... ❌️')
   

async def fav(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text('Please provide Character id...')
        return

    try:
        character_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text('Character id ek number hona chahiye.')
        return

    user = await user_collection.find_one({'id': user_id})
    
    if not user:
        await update.message.reply_text('You have not Guessed any characters yet....')
        return

    if not any(c['id'] == character_id for c in user.get('characters', [])):
        await update.message.reply_text('This Character is Not In your collection')
        return

    await user_collection.update_one({'id': user_id}, {'$set': {'favorites': [character_id]}})
    await update.message.reply_text(f'Character added to your favorite...')

def main() -> None:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(load_characters_into_memory())
    loop.run_until_complete(ensure_indexes())

    application.add_handler(CommandHandler(["guess", "protecc", "collect", "grab", "hunt"], guess, block=False))
    application.add_handler(CommandHandler("fav", fav, block=False))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter, block=False))

    application.run_polling(drop_pending_updates=True)
    
if __name__ == "__main__":
    shivuu.start()
    LOGGER.info("Bot started")
    main()
