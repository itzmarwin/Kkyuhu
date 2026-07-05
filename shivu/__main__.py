import importlib
import time
import random
import re
import asyncio
from html import escape 

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters

from shivu import collection, top_global_groups_collection, group_user_totals_collection, user_collection, user_totals_collection, shivuu
from shivu import application, SUPPORT_CHAT, UPDATE_CHAT, db, LOGGER
from shivu.modules import ALL_MODULES

# --- GLOBAL CACHES (Tumhara Plan) ---
all_characters_cache = []  # Stores all characters in memory
group_freq_cache = {}      # Stores drop frequency per group
# -----------------------------------

locks = {}
message_counts = {}
last_characters = {}
sent_characters = {}
first_correct_guesses = {}

last_user = {}
warned_users = {}

for module_name in ALL_MODULES:
    imported_module = importlib.import_module("shivu.modules." + module_name)

def escape_markdown(text):
    escape_chars = r'\*_`\\~>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)

async def load_characters_into_memory():
    """Fetch all characters once on startup"""
    global all_characters_cache
    LOGGER.info("Loading all characters into memory...")
    all_characters_cache = list(await collection.find({}).to_list(length=None))
    LOGGER.info(f"Loaded {len(all_characters_cache)} characters into memory!")

async def message_counter(update: Update, context: CallbackContext) -> None:
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id

    if update.message is None or update.message.text is None:
        return

    if chat_id not in locks:
        locks[chat_id] = asyncio.Lock()
    lock = locks[chat_id]

    async with lock:
        # Spam protection
        if chat_id in last_user and last_user[chat_id]['user_id'] == user_id:
            last_user[chat_id]['count'] += 1
            if last_user[chat_id]['count'] >= 10:
                if user_id in warned_users and time.time() - warned_users[user_id] < 600:
                    return
                else:
                    await update.message.reply_text(f"⚠️ Don't Spam {update.effective_user.first_name}...\nYour Messages Will be ignored for 10 Minutes...")
                    warned_users[user_id] = time.time()
                    return
        else:
            last_user[chat_id] = {'user_id': user_id, 'count': 1}

        # Agar group memory me nahi hai, toh default 0 se shuru karo
        if chat_id not in message_counts:
            message_counts[chat_id] = 0
            
        # Agar group ki frequency memory me nahi hai, toh DB se laao
        if chat_id not in group_freq_cache:
            chat_frequency = await user_totals_collection.find_one({'chat_id': chat_id})
            freq = chat_frequency.get('message_frequency', 100) if chat_frequency else 100
            group_freq_cache[chat_id] = freq

        # Current cycle ki frequency (Beech me change hone par bhi purani wahi chalegi)
        current_cycle_freq = group_freq_cache[chat_id]

        message_counts[chat_id] += 1

        # Jab count current frequency tak pahuchega, tab image bhejo
        if message_counts[chat_id] >= current_cycle_freq:
            await send_image(update, context)
            message_counts[chat_id] = 0 # Cycle reset
            
            # Cycle reset hone pe DB se latest frequency laao taaki next cycle naye time se chale
            chat_frequency = await user_totals_collection.find_one({'chat_id': chat_id})
            group_freq_cache[chat_id] = chat_frequency.get('message_frequency', 100) if chat_frequency else 100
            
async def send_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if not all_characters_cache:
        await context.bot.send_message(chat_id=chat_id, text="No characters found in database!")
        return

    if chat_id not in sent_characters:
        sent_characters[chat_id] = []

    # Memory se random choice (0.001 seconds)
    available_chars = [c for c in all_characters_cache if c['id'] not in sent_characters[chat_id]]
    
    # Agar sab characters already sent ho chuke hain, toh list reset karo
    if not available_chars:
        sent_characters[chat_id] = []
        available_chars = all_characters_cache

    character = random.choice(available_chars)

    # Memory list ko chota rakho taaki RAM leak na ho
    if len(sent_characters[chat_id]) > 50:
        sent_characters[chat_id] = sent_characters[chat_id][-20:]
        
    sent_characters[chat_id].append(character['id'])
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
        
        # User Collection Update
        user = await user_collection.find_one({'id': user_id})
        if user:
            update_fields = {}
            if hasattr(update.effective_user, 'username') and update.effective_user.username != user.get('username'):
                update_fields['username'] = update.effective_user.username
            if update.effective_user.first_name != user.get('first_name'):
                update_fields['first_name'] = update.effective_user.first_name
            if update_fields:
                await user_collection.update_one({'id': user_id}, {'$set': update_fields})
            
            await user_collection.update_one({'id': user_id}, {'$push': {'characters': character}})
        elif hasattr(update.effective_user, 'username'):
            await user_collection.insert_one({
                'id': user_id,
                'username': update.effective_user.username,
                'first_name': update.effective_user.first_name,
                'characters': [character],
            })

        # Group User Total Update
        group_user_total = await group_user_totals_collection.find_one({'user_id': user_id, 'group_id': chat_id})
        if group_user_total:
            update_fields = {}
            if hasattr(update.effective_user, 'username') and update.effective_user.username != group_user_total.get('username'):
                update_fields['username'] = update.effective_user.username
            if update.effective_user.first_name != group_user_total.get('first_name'):
                update_fields['first_name'] = update.effective_user.first_name
            if update_fields:
                await group_user_totals_collection.update_one({'user_id': user_id, 'group_id': chat_id}, {'$set': update_fields})
            
            await group_user_totals_collection.update_one({'user_id': user_id, 'group_id': chat_id}, {'$inc': {'count': 1}})
        else:
            await group_user_totals_collection.insert_one({
                'user_id': user_id,
                'group_id': chat_id,
                'username': update.effective_user.username,
                'first_name': update.effective_user.first_name,
                'count': 1,
            })

        # Global Group Update
        group_info = await top_global_groups_collection.find_one({'group_id': chat_id})
        if group_info:
            update_fields = {}
            if update.effective_chat.title != group_info.get('group_name'):
                update_fields['group_name'] = update.effective_chat.title
            if update_fields:
                await top_global_groups_collection.update_one({'group_id': chat_id}, {'$set': update_fields})
            
            await top_global_groups_collection.update_one({'group_id': chat_id}, {'$inc': {'count': 1}})
        else:
            await top_global_groups_collection.insert_one({
                'group_id': chat_id,
                'group_name': update.effective_chat.title,
                'count': 1,
            })

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

    character_id = context.args[0]
    user = await user_collection.find_one({'id': user_id})
    
    if not user:
        await update.message.reply_text('You have not Guessed any characters yet....')
        return

    # OPTIMIZATION: Check without iterating whole array if possible
    if not any(c['id'] == character_id for c in user.get('characters', [])):
        await update.message.reply_text('This Character is Not In your collection')
        return

    await user_collection.update_one({'id': user_id}, {'$set': {'favorites': [character_id]}})
    await update.message.reply_text(f'Character added to your favorite...')

def main() -> None:
    # Bot start hone pe characters load karo
    loop = asyncio.get_event_loop()
    loop.run_until_complete(load_characters_into_memory())

    application.add_handler(CommandHandler(["guess", "protecc", "collect", "grab", "hunt"], guess, block=False))
    application.add_handler(CommandHandler("fav", fav, block=False))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter, block=False))

    application.run_polling(drop_pending_updates=True)
    
if __name__ == "__main__":
    shivuu.start()
    LOGGER.info("Bot started")
    main()
