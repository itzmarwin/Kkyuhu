import re
import time
import random
from html import escape
from collections import Counter

from telegram import Update, InlineQueryResultPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import InlineQueryHandler, CallbackContext, ChosenInlineResultHandler

from shivu import user_collection, collection, application, db
from shivu.cache import characters_by_id
from shivu.rarity import format_rarity_html, format_rarity_plain_html


# Telegram only allows <tg-emoji> in messages the bot sends/edits directly
# (sendMessage/sendPhoto/editMessageCaption...) - never in the *initial*
# content of an answerInlineQuery result, no matter who owns the bot.
# So: send the plain-emoji caption first, then use chosen_inline_result +
# edit_message_caption to swap in the premium version once the result has
# actually been sent into a chat.
#
# result_id -> premium (tg-emoji) caption, filled in by inlinequery() and
# consumed by on_chosen_inline_result(). In-memory like shivu's other pending_*
# dicts (see trade.py) - if the bot restarts in between, the message just
# stays on the plain-emoji caption, which is a safe fallback either way.
pending_premium_captions = {}
MAX_PENDING_CAPTIONS = 1000


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
    """Diye gaye anime names ke liye catalog mein kitne total unique characters hain."""
    if not anime_names:
        return {}
    cursor = await collection.aggregate([
        {"$match": {"anime": {"$in": anime_names}}},
        {"$group": {"_id": "$anime", "count": {"$sum": 1}}}
    ])
    result_list = await cursor.to_list(length=None)
    return {item['_id']: item['count'] for item in result_list}


def _build_captions(character, c_id, c_anime, is_collection_search, user=None,
                     user_character_count=0, user_anime_characters=0,
                     anime_total=0, global_count=0):
    """Returns (plain_caption, premium_caption) - identical text, only the
    rarity line differs (plain unicode emoji vs <tg-emoji> markup)."""
    if is_collection_search:
        template = (
            f"<b> Look At <a href='tg://user?id={user['id']}'>{escape(user.get('first_name', user['id']))}</a>'s Character</b>\n\n"
            f"🌸: <b>{character['name']} (x{user_character_count})</b>\n"
            f"🏖️: <b>{c_anime} ({user_anime_characters}/{anime_total})</b>\n"
            f"<b>{{rarity}}</b>\n\n<b>🆔️:</b> {c_id}"
        )
    else:
        template = (
            f"<b>Look At This Character !!</b>\n\n🌸:<b> {character['name']}</b>\n🏖️: <b>{c_anime}</b>\n"
            f"<b>{{rarity}}</b>\n🆔️: <b>{c_id}</b>\n\n<b>Globally Guessed {global_count} Times...</b>"
        )

    plain_caption = template.format(rarity=format_rarity_plain_html(character['rarity']))
    premium_caption = template.format(rarity=format_rarity_html(character['rarity']))
    return plain_caption, premium_caption


async def inlinequery(update: Update, context: CallbackContext) -> None:
    query = update.inline_query.query
    offset = int(update.inline_query.offset) if update.inline_query.offset else 0
    limit = 50

    is_collection_search = query.startswith('collection.')
    search_terms = []
    user = None

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
            plain_caption, premium_caption = _build_captions(
                character, c_id, c_anime, True, user=user,
                user_character_count=user_character_count,
                user_anime_characters=user_anime_characters,
                anime_total=anime_total,
            )
            keyboard = [[InlineKeyboardButton("📂 View Collection", switch_inline_query_current_chat=f"collection.{user['id']}")]]
        else:
            plain_caption, premium_caption = _build_captions(
                character, c_id, c_anime, False, global_count=global_count,
            )
            keyboard = [[InlineKeyboardButton("🔎 Search More", switch_inline_query_current_chat="")]]

        # Random suffix (not just time.time()) because result_id now doubles as
        # our cache key - two results generated in the same millisecond must
        # never collide.
        result_id = f"{c_id}_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        pending_premium_captions[result_id] = premium_caption

        results.append(
            InlineQueryResultPhoto(
                thumbnail_url=character['img_url'],
                id=result_id,
                photo_url=character['img_url'],
                caption=plain_caption,
                parse_mode='HTML',
                # Required even though it's not otherwise needed: Telegram only
                # fills in inline_message_id on chosen_inline_result when an
                # inline keyboard is attached, and we need that id to edit the
                # premium emoji in afterwards.
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        )

    if len(pending_premium_captions) > MAX_PENDING_CAPTIONS:
        for stale_id in list(pending_premium_captions.keys())[:-MAX_PENDING_CAPTIONS // 2]:
            pending_premium_captions.pop(stale_id, None)

    await update.inline_query.answer(results, next_offset=next_offset, cache_time=5)


async def on_chosen_inline_result(update: Update, context: CallbackContext) -> None:
    chosen = update.chosen_inline_result

    # Only present when an inline keyboard was attached to the result - see
    # the comment on reply_markup above.
    if not chosen.inline_message_id:
        return

    premium_caption = pending_premium_captions.pop(chosen.result_id, None)
    if not premium_caption:
        # Bot restarted since this result was sent, or it's stale - leave the
        # message on its plain-emoji caption rather than fail loudly.
        return

    try:
        await context.bot.edit_message_caption(
            inline_message_id=chosen.inline_message_id,
            caption=premium_caption,
            parse_mode='HTML',
        )
    except Exception:
        pass


application.add_handler(InlineQueryHandler(inlinequery, block=False))
# NOTE: this handler only ever fires if Inline Feedback is turned on for the
# bot in @BotFather (/setinlinefeedback -> pick this bot -> 100%). Without
# that, Telegram never sends chosen_inline_result updates at all, and this
# whole file silently does nothing beyond the plain-emoji caption.
application.add_handler(ChosenInlineResultHandler(on_chosen_inline_result, block=False))
