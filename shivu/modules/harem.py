from telegram import Update
from itertools import groupby
import math
from html import escape 
import random
from collections import Counter

from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from shivu import collection, user_collection, application

async def harem(update: Update, context: CallbackContext, page=0) -> None:
    user_id = update.effective_user.id

    # Fetch user
    user = await user_collection.find_one({'id': user_id})
    if not user or 'characters' not in user or not user['characters']:
        if update.message:
            await update.message.reply_text('You Have Not Guessed any Characters Yet..')
        else:
            await update.callback_query.edit_message_text('You Have Not Guessed any Characters Yet..')
        return

    # Sort characters
    all_chars = user['characters']
    all_chars_sorted = sorted(all_chars, key=lambda x: (x['anime'], x['id']))

    # OPTIMIZATION: Use Counter for instant duplicate counting in memory
    character_counts = Counter(c['id'] for c in all_chars_sorted)

    # Extract unique characters while maintaining sort order
    seen_ids = set()
    unique_characters = []
    for c in all_chars_sorted:
        if c['id'] not in seen_ids:
            seen_ids.add(c['id'])
            unique_characters.append(c)

    total_pages = math.ceil(len(unique_characters) / 15)  

    if page < 0 or page >= total_pages:
        page = 0  

    harem_message = f"<b>{escape(update.effective_user.first_name)}'s Harem - Page {page+1}/{total_pages}</b>\n"

    # Pagination slice
    current_characters = unique_characters[page*15:(page+1)*15]

    # OPTIMIZATION: Batch fetch anime counts to prevent N+1 DB queries
    anime_names = list(set(c['anime'] for c in current_characters))
    anime_counts = {}
    if anime_names:
        # FIX: await lagaya gaya hai
        cursor = await collection.aggregate([
            {"$match": {"anime": {"$in": anime_names}}},
            {"$group": {"_id": "$anime", "count": {"$sum": 1}}}
        ])
        async for doc in cursor:
            anime_counts[doc['_id']] = doc['count']

    # Group current page characters by anime
    current_grouped_characters = {k: list(v) for k, v in groupby(current_characters, key=lambda x: x['anime'])}

    for anime, characters in current_grouped_characters.items():
        anime_total = anime_counts.get(anime, 0)
        harem_message += f'\n<b>{anime} {len(characters)}/{anime_total}</b>\n'

        for character in characters:
            count = character_counts[character['id']]  
            harem_message += f'{character["id"]} {character["name"]} ×{count}\n'

    total_count = len(all_chars)
    keyboard = [[InlineKeyboardButton(f"See Collection ({total_count})", switch_inline_query_current_chat=f"collection.{user_id}")]]

    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"harem:{page-1}:{user_id}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"harem:{page+1}:{user_id}"))
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Image selection logic (Favorite or Random)
    image_url = None
    if 'favorites' in user and user['favorites']:
        fav_character_id = user['favorites'][0]
        fav_character = next((c for c in all_chars if c['id'] == fav_character_id), None)
        if fav_character and 'img_url' in fav_character:
            image_url = fav_character['img_url']
    
    if not image_url and all_chars:
        random_character = random.choice(all_chars)
        if 'img_url' in random_character:
            image_url = random_character['img_url']

    # Send or Edit Message
    if update.message:
        if image_url:
            await update.message.reply_photo(photo=image_url, parse_mode='HTML', caption=harem_message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(harem_message, parse_mode='HTML', reply_markup=reply_markup)
    else:
        query = update.callback_query
        try:
            if image_url:
                if query.message.caption != harem_message:
                    await query.edit_message_caption(caption=harem_message, reply_markup=reply_markup, parse_mode='HTML')
            else:
                if query.message.text != harem_message:
                    await query.edit_message_text(harem_message, parse_mode='HTML', reply_markup=reply_markup)
        except Exception:
            # Ignore "Message is not modified" errors
            pass

async def harem_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data

    _, page, user_id = data.split(':')

    page = int(page)
    user_id = int(user_id)

    if query.from_user.id != user_id:
        await query.answer("its Not Your Harem", show_alert=True)
        return

    await query.answer() # Acknowledge the callback to remove loading icon
    await harem(update, context, page)

application.add_handler(CommandHandler(["harem", "collection"], harem, block=False))
harem_handler = CallbackQueryHandler(harem_callback, pattern='^harem', block=False)
application.add_handler(harem_handler)
