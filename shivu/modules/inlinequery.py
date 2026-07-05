import re
import time
from html import escape
from collections import Counter
from pymongo import ASCENDING

from telegram import Update, InlineQueryResultPhoto
from telegram.ext import InlineQueryHandler, CallbackContext

from shivu import user_collection, collection, application, db

# Synchronous index creation
db.characters.create_index([('id', ASCENDING)])
db.characters.create_index([('anime', ASCENDING)])
db.user_collection.create_index([('characters.id', ASCENDING)])
db.user_collection.create_index([('characters.name', ASCENDING)])

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

        all_characters = user['characters']
        if search_terms:
            regex = re.compile(' '.join(search_terms), re.IGNORECASE)
            all_characters = [c for c in all_characters if regex.search(c.get('name', '')) or regex.search(c.get('anime', ''))]
        else:
            all_characters = list({v['id']:v for v in all_characters}.values())

        characters = all_characters[offset:offset+limit]
        total_count = len(all_characters)
        
        user_char_ids = [c['id'] for c in user['characters']]
        user_anime_names = [c['anime'] for c in user['characters']]
        
        char_count_map = Counter(user_char_ids)
        anime_count_map = Counter(user_anime_names)
        
        char_ids = [c['id'] for c in characters]
        
        # FIX: await lagaya gaya hai
        global_counts_cursor = await user_collection.aggregate([
            {"$match": {"characters.id": {"$in": char_ids}}},
            {"$project": {"_id": 0, "characters.id": 1}},
            {"$unwind": "$characters"},
            {"$match": {"characters.id": {"$in": char_ids}}},
            {"$group": {"_id": "$characters.id", "count": {"$sum": 1}}}
        ])
        global_counts_list = await global_counts_cursor.to_list(length=None)
        global_counts = {item['_id']: item['count'] for item in global_counts_list}
        
        anime_names = list(set(c['anime'] for c in characters))
        # FIX: await lagaya gaya hai
        anime_counts_cursor = await collection.aggregate([
            {"$match": {"anime": {"$in": anime_names}}},
            {"$group": {"_id": "$anime", "count": {"$sum": 1}}}
        ])
        anime_counts_list = await anime_counts_cursor.to_list(length=None)
        anime_counts = {item['_id']: item['count'] for item in anime_counts_list}

    else:
        # Global Search
        if query:
            regex = re.compile(query, re.IGNORECASE)
            db_query = {"$or": [{"name": regex}, {"anime": regex}]}
        else:
            db_query = {}

        cursor = collection.find(db_query).skip(offset).limit(limit)
        characters = await cursor.to_list(length=limit)
        
        total_count = await collection.count_documents(db_query)
        
        char_ids = [c['id'] for c in characters]
        if char_ids:
            # FIX: await lagaya gaya hai
            global_counts_cursor = await user_collection.aggregate([
                {"$match": {"characters.id": {"$in": char_ids}}},
                {"$project": {"_id": 0, "characters.id": 1}},
                {"$unwind": "$characters"},
                {"$match": {"characters.id": {"$in": char_ids}}},
                {"$group": {"_id": "$characters.id", "count": {"$sum": 1}}}
            ])
            global_counts_list = await global_counts_cursor.to_list(length=None)
            global_counts = {item['_id']: item['count'] for item in global_counts_list}
        else:
            global_counts = {}

        anime_names = list(set(c['anime'] for c in characters))
        if anime_names:
            # FIX: await lagaya gaya hai
            anime_counts_cursor = await collection.aggregate([
                {"$match": {"anime": {"$in": anime_names}}},
                {"$group": {"_id": "$anime", "count": {"$sum": 1}}}
            ])
            anime_counts_list = await anime_counts_cursor.to_list(length=None)
            anime_counts = {item['_id']: item['count'] for item in anime_counts_list}
        else:
            anime_counts = {}

    if offset + limit < total_count:
        next_offset = str(offset + limit)
    else:
        next_offset = ""

    results = []
    for character in characters:
        c_id = character['id']
        c_anime = character['anime']
        
        global_count = global_counts.get(c_id, 0)
        anime_total = anime_counts.get(c_anime, 0)

        if is_collection_search:
            user_character_count = char_count_map.get(c_id, 0)
            user_anime_characters = anime_count_map.get(c_anime, 0)
            caption = f"<b> Look At <a href='tg://user?id={user['id']}'>{escape(user.get('first_name', user['id']))}</a>'s Character</b>\n\n🌸: <b>{character['name']} (x{user_character_count})</b>\n🏖️: <b>{c_anime} ({user_anime_characters}/{anime_total})</b>\n<b>{character['rarity']}</b>\n\n<b>🆔️:</b> {c_id}"
        else:
            caption = f"<b>Look At This Character !!</b>\n\n🌸:<b> {character['name']}</b>\n🏖️: <b>{c_anime}</b>\n<b>{character['rarity']}</b>\n🆔️: <b>{c_id}</b>\n\n<b>Globally Guessed {global_count} Times...</b>"
            
        results.append(
            InlineQueryResultPhoto(
                thumbnail_url=character['img_url'],
                id=f"{c_id}_{time.time()}",
                photo_url=character['img_url'],
                caption=caption,
                parse_mode='HTML'
            )
        )

    await update.inline_query.answer(results, next_offset=next_offset, cache_time=5)

application.add_handler(InlineQueryHandler(inlinequery, block=False))
