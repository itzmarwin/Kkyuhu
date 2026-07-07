import re
from html import escape
from collections import Counter

from telegram import Update, InlineQueryResultPhoto
from telegram.ext import InlineQueryHandler, CallbackContext

from shivu import user_collection, collection, application, db
from shivu.cache import characters_by_id
from shivu.rarity import format_rarity_html


async def get_global_guess_counts(char_ids):
    if not char_ids:
        return {}
    cursor = await user_collection.aggregate([
        {"$match": {"characters.id": {"$in": char_ids}}},
        {"$project": {"matched": {"$filter": {
            "input": "$characters",
            "cond": {"$in": ["$$this.id", char_ids]}
        }}}},
        {"$unwind": "$matched"},
        {"$group": {"_id": "$matched.id", "count": {"$sum": "$matched.count"}}}
    ])
    result_list = await cursor.to_list(length=None)
    return {item['_id']: item['count'] for item in result_list}


async def get_anime_totals(anime_names):
    if not anime_names:
        return {}
    cursor = await collection.aggregate([
        {"$match": {"anime": {"$in": anime_names}}},
        {"$group": {"_id": "$anime", "count": {"$sum": 1}}}
    ])
    result_list = await cursor.to_list(length=None)
    return {item['_id']: item['count'] for item in result_list}


async def inlinequery(update: Update, context: CallbackContext) -> None:
    query = update.inline_query.query
    offset = int(update.inline_query.offset) if update.inline_query.offset else 0
    limit = 50

    is_collection_search = query.startswith('collection.')
    search_terms = []

    if is_collection_search:
        parts = query.split(' ', 1)
        user_id = parts[0].split('.')[1]
        if len(parts) > 1:
            search_terms = parts[1].split()

        if not user_id.isdigit():
            await update.inline_query.answer([], cache_time=5)
            return

        user = await user_collection.find_one({'id': int(user_id)}, {'characters': 1, 'first_name': 1, 'id': 1})
        if not user or 'characters' not in user:
            await update.inline_query.answer([], cache_time=5)
            return

        owned_characters = []
        char_count_map = {}
        for entry in user['characters']:
            info = characters_by_id.get(entry['id'])
            if info is None:
                continue
            owned_characters.append({
                'id': entry['id'],
                'name': info['name'],
                'anime': info['anime'],
                'rarity': info.get('rarity'),
                'img_url': info.get('img_url'),
            })
            char_count_map[entry['id']] = entry['count']

        if search_terms:
            regex = re.compile(' '.join(search_terms), re.IGNORECASE)
            owned_characters = [c for c in owned_characters if regex.search(c['name']) or regex.search(c['anime'])]

        owned_characters.sort(key=lambda c: c['id'])

        characters = owned_characters[offset:offset+limit]

        anime_count_map = Counter(c['anime'] for c in owned_characters)

        char_ids = [c['id'] for c in characters]
        global_counts = await get_global_guess_counts(char_ids)

        anime_names = list(set(c['anime'] for c in characters))
        anime_counts = await get_anime_totals(anime_names)

    else:
        if query:
            regex = re.compile(query, re.IGNORECASE)
            db_query = {"$or": [{"name": regex}, {"anime": regex}]}
        else:
            db_query = {}

        cursor = collection.find(db_query).sort('id', 1).skip(offset).limit(limit)
        characters = await cursor.to_list(length=limit)

        char_ids = [c['id'] for c in characters]
        global_counts = await get_global_guess_counts(char_ids)

        anime_names = list(set(c['anime'] for c in characters))
        anime_counts = await get_anime_totals(anime_names)

    next_offset = str(offset + limit) if len(characters) == limit else ""

    results = []
    for character in characters:
        c_id = character['id']
        c_anime = character['anime']

        global_count = global_counts.get(c_id, 0)
        anime_total = anime_counts.get(c_anime, 0)

        if is_collection_search:
            user_character_count = char_count_map.get(c_id, 0)
            user_anime_characters = anime_count_map.get(c_anime, 0)
            caption = f"<b> Look At <a href='tg://user?id={user['id']}'>{escape(user.get('first_name', user['id']))}</a>'s Character</b>\n\n🌸: <b>{character['name']} (x{user_character_count})</b>\n🏖️: <b>{c_anime} ({user_anime_characters}/{anime_total})</b>\n<b>{format_rarity_html(character['rarity'])}</b>\n\n<b>🆔️:</b> {c_id}"
        else:
            caption = f"<b>Look At This Character !!</b>\n\n🌸:<b> {character['name']}</b>\n🏖️: <b>{c_anime}</b>\n<b>{format_rarity_html(character['rarity'])}</b>\n🆔️: <b>{c_id}</b>\n\n<b>Globally Guessed {global_count} Times...</b>"

        results.append(
            InlineQueryResultPhoto(
                thumbnail_url=character['img_url'],
                id=f"{c_id}_{offset}_{len(results)}",
                photo_url=character['img_url'],
                caption=caption,
                parse_mode='HTML',
            )
        )

    await update.inline_query.answer(results, next_offset=next_offset, cache_time=5)


application.add_handler(InlineQueryHandler(inlinequery, block=False))
