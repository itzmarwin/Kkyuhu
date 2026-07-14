import importlib
import time
import random
import asyncio
from html import escape

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters

from shivu import application, SUPPORT_CHAT, UPDATE_CHAT, shivuu, LOGGER
from shivu.modules import ALL_MODULES
from shivu.rarity import RARITY_WEIGHTS, format_rarity_html
from shivu.database import (
    ensure_indexes,
    get_all_characters,
    iter_all_pm_user_ids,
    get_users_ranked_by_character_count,
    get_groups_ranked_by_count,
    grant_character_to_user,
    remove_character_from_user,
    record_group_guess,
    get_user,
    set_favorite_character,
    get_group_message_frequency,
)
from shivu.cache import (
    all_characters_cache,
    characters_by_id,
    group_freq_cache,
    locks,
    message_counts,
    last_characters,
    sent_characters,
    first_correct_guesses,
    last_user,
    warned_users,
    global_users_cache,
    global_groups_cache,
    started_users_cache,
)


async def load_characters_into_memory():
    LOGGER.info("Loading all characters into memory...")
    fresh_data = await get_all_characters()

    all_characters_cache.clear()
    all_characters_cache.extend(fresh_data)

    characters_by_id.clear()
    characters_by_id.update({c['id']: c for c in fresh_data})

    LOGGER.info(f"Loaded {len(all_characters_cache)} characters into memory!")

async def load_started_users_into_memory():
    LOGGER.info("Loading started users into memory...")
    started_users_cache.clear()
    async for user_id in iter_all_pm_user_ids():
        started_users_cache.add(user_id)

    LOGGER.info(f"Loaded {len(started_users_cache)} started users into memory!")

async def refresh_global_leaderboards():
    users_ranked_list = await get_users_ranked_by_character_count()
    groups_ranked_list = await get_groups_ranked_by_count()

    now = time.time()
    global_users_cache['ranked_list'] = users_ranked_list
    global_users_cache['refreshed_at'] = now
    global_groups_cache['ranked_list'] = groups_ranked_list
    global_groups_cache['refreshed_at'] = now

    LOGGER.info(f"Refreshed global leaderboards: {len(users_ranked_list)} users, {len(groups_ranked_list)} groups.")



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
            if last_user[chat_id]['count'] >= 50:
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
            group_freq_cache[chat_id] = await get_group_message_frequency(chat_id)

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
        caption=f"""A New {format_rarity_html(character['rarity'])} Character Appeared...\n/guess Character Name and add in Your Harem""",
        parse_mode='HTML')

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

        await asyncio.gather(
            grant_character_to_user(
                user_id, character['id'],
                update.effective_user.username, update.effective_user.first_name,
            ),
            record_group_guess(
                chat_id, update.effective_chat.title,
                user_id, update.effective_user.username, update.effective_user.first_name,
            ),
        )

        keyboard = [[InlineKeyboardButton(f"See Harem", switch_inline_query_current_chat=f"collection.{user_id}")]]

        await update.message.reply_text(
            f'<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> You Guessed a New Character ✅️ \n\n'
            f'𝗡𝗔𝗠𝗘: <b>{character["name"]}</b> \n'
            f'𝗔𝗡𝗜𝗠𝗘: <b>{character["anime"]}</b> \n'
            f'𝗥𝗔𝗜𝗥𝗧𝗬: <b>{format_rarity_html(character["rarity"])}</b>\n\n'
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

    user = await get_user(user_id)
    
    if not user:
        await update.message.reply_text('You have not Guessed any characters yet....')
        return

    if not any(c['id'] == character_id for c in user.get('characters', [])):
        await update.message.reply_text('This Character is Not In your collection')
        return

    await set_favorite_character(user_id, character_id)
    await update.message.reply_text(f'Character added to your favorite...')

async def post_init(app) -> None:
    await load_characters_into_memory()
    await load_started_users_into_memory()
    await ensure_indexes()
    await refresh_global_leaderboards()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_global_leaderboards, 'interval', minutes=10)
    scheduler.start()

def main() -> None:
    application.post_init = post_init

    application.add_handler(CommandHandler(["guess", "protecc", "collect", "grab", "hunt"], guess, block=False))
    application.add_handler(CommandHandler("fav", fav, block=False))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter, block=False))

    application.run_polling(drop_pending_updates=True)
    
if __name__ == "__main__":
    shivuu.start()
    LOGGER.info("Bot started")
    main()
