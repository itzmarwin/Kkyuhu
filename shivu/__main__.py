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

# --- GLOBAL CACHES (Tumhara Plan) ---
all_characters_cache = []   # Stores all characters in memory
characters_by_id = {}       # id -> full character dict, O(1) lookup. Abhi is file mein use
                             # nahi hota, harem.py/inlinequery.py isko import karenge.
group_freq_cache = {}       # Stores drop frequency per group
# -----------------------------------

locks = {}
message_counts = {}
last_characters = {}
sent_characters = {}
first_correct_guesses = {}

last_user = {}
warned_users = {}

# NOTE: ye weights naam dekh kar guess kiye hain (Common sabse zyada milega, Special edition
# sabse kam). upload.py ke rarity_map (1-5) ki numbering rank-order nahi darshati (Legendary=3
# hai Medium=4 se pehle), isliye rank order khud decide kiya hai -- confirm/adjust kar lena.
RARITY_WEIGHTS = {
    "⚪ Common": 100,
    "🟢 Medium": 50,
    "🟣 Rare": 25,
    "🟡 Legendary": 10,
    "💮 Special edition": 3,
}

for module_name in ALL_MODULES:
    imported_module = importlib.import_module("shivu.modules." + module_name)

def escape_markdown(text):
    escape_chars = r'\*_`\\~>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)

async def ensure_indexes():
    """
    Saare zaroori indexes yahan ek jagah, startup pe ek baar banate hain.

    FIX: inlinequery.py mein pehle ye calls the (module-level, bina await ke) --
    lekin PyMongo ke naye async client mein create_index() khud ek COROUTINE hai
    (find_one/update_one/aggregate jaisa hi), matlab bina await ke wo call sirf ek
    coroutine object banata hai jo kabhi chalta hi nahi -- index kabhi bana hi nahi
    (chahe collection sahi ho ya galat). Isliye ab proper async context mein, yahan
    par await ke saath.
    """
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

    # FIX: rebind (all_characters_cache = ...) ki jagah in-place mutate. Rebind karne se
    # upload.py jaisa module jo isse import kar chuka hai, PURANE (stale) list-object par
    # atka reh jaata -- naye /upload live drop nahi hote the jab tak bot restart na ho.
    all_characters_cache.clear()
    all_characters_cache.extend(fresh_data)

    characters_by_id.clear()
    characters_by_id.update({c['id']: c for c in fresh_data})

    LOGGER.info(f"Loaded {len(all_characters_cache)} characters into memory!")

async def grant_character_to_user(user_id: int, character_id: int, username=None, first_name=None) -> None:
    """
    User ko character 'de do': pehle se 1+ copy hai to sirf count +1, warna naya
    {id, count: 1} entry push karo. character_count (leaderboard ke liye) bhi
    saath mein maintain karta hai. guess() abhi ise use karta hai; trade.py/gift.py
    bhi isi ko reuse karte hain.

    username/first_name OPTIONAL hain: guess() jaisa live-update context ho to pass karo
    (fresh info $set ho jaayegi), trade.py jaisa context ho jahan doosre party ka fresh
    naam haath mein nahi hota, to None chhod do -- warna unki existing username/first_name
    galti se null ho jaati.
    """
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
        # is user ke liye pehli baar (ya document hi nahi tha) -- naya entry push karo
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
    """
    User se character ki 1 copy hatao: count -1, aur count 0 pe pahunch jaaye to poora
    {id,count} entry hata do. character_count bhi -1. trade.py/gift.py (sender side)
    yahan se import karke use karte hain -- calling code pehle confirm kar chuka hona
    chahiye ki user ke paas ye character hai.
    """
    await user_collection.update_one(
        {'id': user_id, 'characters.id': character_id},
        {'$inc': {'characters.$.count': -1, 'character_count': -1}},
    )
    await user_collection.update_one(
        {'id': user_id},
        {'$pull': {'characters': {'id': character_id, 'count': {'$lte': 0}}}},
    )

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

        # Jab count current frequency tak pahuchega, tab flag lagao (bhejna lock ke bahar hoga)
        if message_counts[chat_id] >= current_cycle_freq:
            message_counts[chat_id] = 0  # Cycle reset
            should_send = True
            # NOTE: pehle yahan DB se group_freq_cache dobara fetch hota tha cycle-reset pe --
            # hataya, kyunki changetime.py admin ke /changetime chalate hi cache turant update
            # kar deta hai, ye re-fetch hamesha ek redundant extra DB round-trip tha.

    # send_image (Telegram photo-send + cache scan) jaan-boojh kar lock ke BAHAR -- taaki isi
    # chat ke doosre messages photo-send poora hone tak block na hon
    if should_send:
        await send_image(update, context)

async def send_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if not all_characters_cache:
        await context.bot.send_message(chat_id=chat_id, text="No characters found in database!")
        return

    if chat_id not in sent_characters:
        sent_characters[chat_id] = {}   # dict as ordered-set: id -> True (O(1) 'in' check)

    available_chars = [c for c in all_characters_cache if c['id'] not in sent_characters[chat_id]]

    # Agar sab characters already sent ho chuke hain, toh list reset karo
    if not available_chars:
        sent_characters[chat_id] = {}
        available_chars = all_characters_cache

    # Rarity-weighted pick -- pehle uniform random.choice tha, ab rarer characters kam milenge
    weights = [RARITY_WEIGHTS.get(c['rarity'], 1) for c in available_chars]
    character = random.choices(available_chars, weights=weights, k=1)[0]

    # Dict ko chota rakho taaki RAM leak na ho (last 20 rakhte hain, jaisa pehle tha)
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

        # Teeno collections independent hain -- parallel chalao. Pehle 6-9 sequential
        # round-trips the (find + set + push, teen collections ke liye); ab 3 parallel calls.
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

    # OPTIMIZATION: Check without iterating whole array if possible
    if not any(c['id'] == character_id for c in user.get('characters', [])):
        await update.message.reply_text('This Character is Not In your collection')
        return

    await user_collection.update_one({'id': user_id}, {'$set': {'favorites': [character_id]}})
    await update.message.reply_text(f'Character added to your favorite...')

def main() -> None:
    # Bot start hone pe characters load karo + indexes ensure karo
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
