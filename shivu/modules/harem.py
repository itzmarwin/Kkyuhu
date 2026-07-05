from telegram import Update
from itertools import groupby
import math
from html import escape 
import random
from collections import Counter

from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from shivu import collection, user_collection, application
from shivu.__main__ import characters_by_id

async def harem(update: Update, context: CallbackContext, page=0) -> None:
    user_id = update.effective_user.id

    user = await user_collection.find_one({'id': user_id})
    if not user or 'characters' not in user or not user['characters']:
        if update.message:
            await update.message.reply_text('You Have Not Guessed any Characters Yet..')
        else:
            await update.callback_query.edit_message_text('You Have Not Guessed any Characters Yet..')
        return

    owned = user['characters']
    owned_characters = []
    for entry in owned:
        info = characters_by_id.get(entry['id'])
        if info is None:
            continue
        owned_characters.append({
            'id': entry['id'],
            'count': entry['count'],
            'name': info['name'],
            'anime': info['anime'],
            'rarity': info.get('rarity'),
            'img_url': info.get('img_url'),
        })

    owned_characters.sort(key=lambda x: (x['anime'], x['id']))

    owned_anime_counts = Counter(c['anime'] for c in owned_characters)

    total_pages = math.ceil(len(owned_characters) / 15)

    if page < 0 or page >= total_pages:
        page = 0

    harem_message = f"<b>{escape(update.effective_user.first_name)}'s Harem - Page {page+1}/{total_pages}</b>\n"

    current_characters = owned_characters[page*15:(page+1)*15]

    anime_names = list(set(c['anime'] for c in current_characters))
    anime_counts = {}
    if anime_names:
        cursor = await collection.aggregate([
            {"$match": {"anime": {"$in": anime_names}}},
            {"$group": {"_id": "$anime", "count": {"$sum": 1}}}
        ])
        async for doc in cursor:
            anime_counts[doc['_id']] = doc['count']

    continuing_same_anime = False
    if page > 0 and current_characters:
        prev_last_char = owned_characters[page*15 - 1]
        if current_characters[0]['anime'] == prev_last_char['anime']:
            continuing_same_anime = True

    current_grouped_characters = {k: list(v) for k, v in groupby(current_characters, key=lambda x: x['anime'])}

    for i, (anime, characters) in enumerate(current_grouped_characters.items()):
        if not (i == 0 and continuing_same_anime):
            anime_total = anime_counts.get(anime, 0)
            harem_message += f'\n<b>{anime} {owned_anime_counts[anime]}/{anime_total}</b>\n'

        for character in characters:
            harem_message += f'{character["id"]} {character["name"]} ×{character["count"]}\n'

    total_count = sum(c['count'] for c in owned_characters)
    keyboard = [[InlineKeyboardButton(f"See Collection ({total_count})", switch_inline_query_current_chat=f"collection.{user_id}")]]

    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"harem:{page-1}:{user_id}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"harem:{page+1}:{user_id}"))
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    image_url = None
    if user.get('favorites'):
        fav_character_id = user['favorites'][0]
        fav_entry = next((c for c in owned_characters if c['id'] == fav_character_id), None)
        if fav_entry and fav_entry.get('img_url'):
            image_url = fav_entry['img_url']

    if not image_url and owned_characters:
        random_character = random.choice(owned_characters)
        if random_character.get('img_url'):
            image_url = random_character['img_url']

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

    await query.answer()
    await harem(update, context, page)

application.add_handler(CommandHandler(["harem", "collection"], harem, block=False))
harem_handler = CallbackQueryHandler(harem_callback, pattern='^harem', block=False)
application.add_handler(harem_handler)
