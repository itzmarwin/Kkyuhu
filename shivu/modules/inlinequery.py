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

from shivu import application, LOGGER
from shivu.database import get_anime_totals, get_top_collectors, get_user_with_characters, search_characters
from shivu.cache import characters_by_id
from shivu.rarity import format_rarity_plain_html, format_rarity_emoji_only_html, get_rarity_name

pending_inline_updates = {}
MAX_PENDING_UPDATES = 1000
current_captions = {}
MAX_CURRENT_CAPTIONS = 1000


TOP_COLLECTORS_MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("⌬ Top Collectors", callback_data="noop")]])
DETAILS_MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("✨ Details", callback_data="noop")]])

RARITY_LABEL = "𝙍𝘼𝙍𝙄𝙏𝙔"


def _build_rarity_line(rarity_key, premium):
    emoji = format_rarity_emoji_only_html(rarity_key) if premium else format_rarity_plain_html(rarity_key).split(' ', 1)[0]
    name = get_rarity_name(rarity_key)
    return f'({emoji} {RARITY_LABEL}: {name})'


def _build_captions(character, c_id, c_anime, is_collection_search, user=None,
                     user_character_count=0, user_anime_characters=0,
                     anime_total=0):
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

        user = await get_user_with_characters(int(user_id))
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
            regex = re.compile(re.escape(' '.join(search_terms)), re.IGNORECASE)
            owned_characters = [c for c in owned_characters if regex.search(c['name']) or regex.search(c['anime'])]

        owned_characters.sort(key=lambda c: c['id'])

        characters = owned_characters[offset:offset+limit]

        anime_count_map = Counter(c['anime'] for c in owned_characters)

        anime_names = list(set(c['anime'] for c in characters))
        anime_counts = await get_anime_totals(anime_names)

    else:
        if query:
            regex = re.compile(re.escape(query), re.IGNORECASE)
            db_query = {"$or": [{"name": regex}, {"anime": regex}]}
        else:
            db_query = {}

        characters = await search_characters(db_query, offset, limit)

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
        new_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⌬ Top Collectors", callback_data=f"topcol:{pending['character_id']}")]]
        )
    else:
        new_markup = InlineKeyboardMarkup([])

    try:
        await context.bot.edit_message_caption(
            inline_message_id=chosen.inline_message_id,
            caption=pending['premium_caption'],
            parse_mode='HTML',
            reply_markup=new_markup,
        )
        if pending['keep_button_after_swap']:
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
