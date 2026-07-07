import re
import time
import random
from html import escape
from collections import Counter

from telegram import Update, InlineQueryResultPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    InlineQueryHandler,
    CallbackContext,
    ChosenInlineResultHandler,
    CallbackQueryHandler,
)

from shivu import user_collection, collection, application, db, LOGGER
from shivu.cache import characters_by_id
from shivu.rarity import format_rarity_plain_html, format_rarity_emoji_only_html, get_rarity_name


# result_id -> premium caption (the version with <tg-emoji>), same as before.
# In-memory like shivu's other pending_* dicts (see trade.py) - if the bot
# restarts in between, the message just stays on the plain-emoji caption with
# its button, which is a safe (if slightly stale-looking) fallback.
pending_inline_updates = {}
MAX_PENDING_UPDATES = 1000

# inline_message_id -> current caption text, so on_top_collectors_click can
# read "what's on the message right now" and append to it.
#
# Why this second cache exists: a CallbackQuery from a button attached to an
# inline-mode message NEVER has .message populated - only .inline_message_id.
# (query.message and query.inline_message_id are mutually exclusive: message
# is set for buttons on messages the bot sent directly to a chat;
# inline_message_id is set for buttons on messages sent via inline mode. Ours
# is always the inline-mode case.) So there is no query.message.caption to
# read from inside on_top_collectors_click - we have to have cached it
# ourselves when we last wrote the caption.
current_captions = {}
MAX_CURRENT_CAPTIONS = 1000

# Why every result still needs SOME button attached, even though these two
# buttons serve very different purposes:
# Telegram only fills in inline_message_id on chosen_inline_result when an
# inline keyboard is attached to the result. Without that id we can never
# edit the message afterwards, so the <tg-emoji> premium swap becomes
# impossible. A button here is a hard technical requirement, not a style
# choice - see on_chosen_inline_result() below.
#
# - Global search results get "⌬ Top Collectors" from the very start, and it
#   STAYS after the emoji swap - it's genuinely clickable, see
#   on_top_collectors_click().
# - Collection search (harem) results get a neutral "✨ Details" button that
#   does nothing and is deleted the instant the emoji swap happens (exactly
#   like the old Converting button used to be for everything). It's neutral
#   on purpose: if it said "Top Collectors" here too, it would always vanish
#   without ever doing anything, which is itself a giveaway that something
#   mechanical is going on.
TOP_COLLECTORS_MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("⌬ Top Collectors", callback_data="noop")]])
DETAILS_MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("✨ Details", callback_data="noop")]])

# Unicode mathematical bold sans-serif "RARITY" - not an HTML tag, just a
# fixed run of special-codepoint characters. Telegram renders it as plain
# text in any chat type, no parse_mode trickery needed. Kept as one constant
# so the exact literal only appears in one place.
RARITY_LABEL = "𝙍𝘼𝙍𝙄𝙏𝙔"


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


async def get_top_collectors(character_id, limit=5):
    """Top `limit` users by how many times they've collected this specific
    character (not their overall collection size). Returns a list of dicts:
    [{'first_name': ..., 'count': ...}, ...] sorted highest first."""
    cursor = await user_collection.aggregate([
        {"$match": {"characters.id": character_id}},
        {"$project": {
            "first_name": 1,
            "matched_count": {
                "$first": {
                    "$map": {
                        "input": {"$filter": {
                            "input": "$characters",
                            "cond": {"$eq": ["$$this.id", character_id]}
                        }},
                        "as": "m",
                        "in": "$$m.count"
                    }
                }
            }
        }},
        {"$match": {"matched_count": {"$gt": 0}}},
        {"$sort": {"matched_count": -1}},
        {"$limit": limit}
    ])
    result_list = await cursor.to_list(length=limit)
    return [
        {'first_name': doc.get('first_name') or 'Unknown', 'count': doc.get('matched_count', 0)}
        for doc in result_list
    ]


def _build_rarity_line(rarity_key, premium):
    """(<emoji> RARITY: <Name>) - the fixed parenthesised rarity line used at
    the bottom of every caption in this file. premium=True gives the
    <tg-emoji> version (only valid once chosen_inline_result confirms the
    message was actually sent somewhere); premium=False gives the plain
    unicode-emoji version (required for the initial inline answer, and for
    anywhere else a <tg-emoji> entity isn't allowed)."""
    emoji = format_rarity_emoji_only_html(rarity_key) if premium else format_rarity_plain_html(rarity_key).split(' ', 1)[0]
    name = get_rarity_name(rarity_key)
    return f'({emoji} {RARITY_LABEL}: {name})'


def _build_captions(character, c_id, c_anime, is_collection_search, user=None,
                     user_character_count=0, user_anime_characters=0,
                     anime_total=0):
    """Returns (plain_caption, premium_caption) - identical text, only the
    rarity line differs (plain unicode emoji vs <tg-emoji> markup)."""
    char_name = escape(character['name'])
    anime_name = escape(c_anime)

    if is_collection_search:
        owner_name = escape(user.get('first_name', str(user['id'])))
        header = f"Look At {owner_name}'s Character!"
        body = (
            f"#{c_id:04d} • {char_name} ×{user_character_count}\n"
            f"{anime_name} ({user_anime_characters}/{anime_total})"
        )
    else:
        header = "Look At This Character!"
        body = f"#{c_id:04d} • {char_name}\n{anime_name}"

    plain_rarity = _build_rarity_line(character['rarity'], premium=False)
    premium_rarity = _build_rarity_line(character['rarity'], premium=True)

    plain_caption = f"{header}\n\n{body}\n\n{plain_rarity}"
    premium_caption = f"{header}\n\n{body}\n\n{premium_rarity}"
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

    next_offset = str(offset + limit) if len(characters) == limit else ""

    results = []
    for character in characters:
        c_id = character['id']
        c_anime = character['anime']

        if is_collection_search:
            user_character_count = char_count_map.get(c_id, 0)
            user_anime_characters = anime_count_map.get(c_anime, 0)
            anime_total = anime_counts.get(c_anime, 0)
            plain_caption, premium_caption = _build_captions(
                character, c_id, c_anime, True, user=user,
                user_character_count=user_character_count,
                user_anime_characters=user_anime_characters,
                anime_total=anime_total,
            )
            markup = DETAILS_MARKUP
        else:
            plain_caption, premium_caption = _build_captions(
                character, c_id, c_anime, False,
            )
            markup = TOP_COLLECTORS_MARKUP

        result_id = f"{c_id}_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        # Stash both the premium caption AND whether this result should keep
        # its button after the swap (collection search never does; global
        # search always does, so it can later become clickable).
        pending_inline_updates[result_id] = {
            'premium_caption': premium_caption,
            'keep_button_after_swap': not is_collection_search,
            'character_id': c_id,
        }

        results.append(
            InlineQueryResultPhoto(
                thumbnail_url=character['img_url'],
                id=result_id,
                photo_url=character['img_url'],
                caption=plain_caption,
                parse_mode='HTML',
                reply_markup=markup,
            )
        )

    if len(pending_inline_updates) > MAX_PENDING_UPDATES:
        for stale_id in list(pending_inline_updates.keys())[:-MAX_PENDING_UPDATES // 2]:
            pending_inline_updates.pop(stale_id, None)

    await update.inline_query.answer(results, next_offset=next_offset, cache_time=5)


async def on_chosen_inline_result(update: Update, context: CallbackContext) -> None:
    chosen = update.chosen_inline_result

    if not chosen.inline_message_id:
        LOGGER.warning(
            "chosen_inline_result had no inline_message_id (result_id=%s) - "
            "no inline keyboard was attached, so Telegram won't let us edit this message.",
            chosen.result_id,
        )
        return

    pending = pending_inline_updates.pop(chosen.result_id, None)
    if not pending:
        LOGGER.warning(
            "No cached premium caption for result_id=%s (bot restarted since it was sent, or it's stale).",
            chosen.result_id,
        )
        return

    if pending['keep_button_after_swap']:
        # Global search: keep the Top Collectors button alive so it can
        # still be clicked after the emoji swap.
        new_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⌬ Top Collectors", callback_data=f"topcol:{pending['character_id']}")]]
        )
    else:
        # Collection search: the Details button was only ever a vehicle for
        # getting inline_message_id - remove it now that its job is done.
        new_markup = InlineKeyboardMarkup([])

    try:
        await context.bot.edit_message_caption(
            inline_message_id=chosen.inline_message_id,
            caption=pending['premium_caption'],
            parse_mode='HTML',
            reply_markup=new_markup,
        )
        if pending['keep_button_after_swap']:
            # Only need to remember the caption if the button is still alive
            # (collection search's Details button is gone already, so there's
            # nothing left that could ever need to read this back).
            current_captions[chosen.inline_message_id] = pending['premium_caption']
            if len(current_captions) > MAX_CURRENT_CAPTIONS:
                for stale_key in list(current_captions.keys())[:-MAX_CURRENT_CAPTIONS // 2]:
                    current_captions.pop(stale_key, None)
    except Exception as e:
        LOGGER.error("Failed to swap in the premium emoji caption: %s", e)


async def on_top_collectors_click(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    try:
        character_id = int(query.data.split(':', 1)[1])
    except (IndexError, ValueError):
        return

    if not query.inline_message_id:
        # This button only ever lives on inline-mode messages, so this
        # shouldn't happen - but bail out cleanly rather than crash if it does.
        return

    current_caption = current_captions.pop(query.inline_message_id, None)
    if current_caption is None:
        LOGGER.warning(
            "No cached caption for inline_message_id=%s (bot restarted since the emoji swap, or it's stale).",
            query.inline_message_id,
        )
        return

    collectors = await get_top_collectors(character_id)

    if collectors:
        lines = "\n".join(
            f"#{i} {escape(c['first_name'])} ×{c['count']}"
            for i, c in enumerate(collectors, start=1)
        )
        addition = f"\n\n⌬ Top Collectors\n\n{lines}"
    else:
        addition = "\n\n⌬ Top Collectors\n\nNo one has collected this character yet."

    try:
        await context.bot.edit_message_caption(
            inline_message_id=query.inline_message_id,
            caption=current_caption + addition,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([]),
        )
    except Exception as e:
        LOGGER.error("Failed to append Top Collectors list: %s", e)


async def on_noop_callback(update: Update, context: CallbackContext) -> None:
    await update.callback_query.answer()


application.add_handler(InlineQueryHandler(inlinequery, block=False))
application.add_handler(ChosenInlineResultHandler(on_chosen_inline_result, block=False))
application.add_handler(CallbackQueryHandler(on_top_collectors_click, pattern='^topcol:', block=False))
application.add_handler(CallbackQueryHandler(on_noop_callback, pattern='^noop$', block=False))
