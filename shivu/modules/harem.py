from telegram import Update
from itertools import groupby
import math
from html import escape 
import random
from collections import Counter

from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from shivu import application, BOT_USERNAME
from shivu.database import get_user, get_anime_totals
from shivu.cache import characters_by_id, started_users_cache, harem_mode_cache
from shivu.rarity import format_rarity_emoji_only_html, RARITY_MAP, get_rarity_name, is_valid_rarity

PAGE_SIZE = 15
RARITY_ORDER = [1, 2, 3, 4, 5, 6]

NOT_STARTED_TEXT = "You need to start the bot in private first before using /harem."

_SMALL_CAPS_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘqʀsᴛᴜᴠᴡxʏᴢ",
)


def _to_small_caps(text: str) -> str:
    return text.lower().translate(_SMALL_CAPS_MAP)


async def _load_owned_characters(user):
    """Builds the same per-character dict shape used everywhere in this
    file, from a user_collection document's 'characters' array."""
    owned_characters = []
    for entry in user['characters']:
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
            'tag': info.get('tag'),
        })
    owned_characters.sort(key=lambda x: (x['anime'], x['id']))
    return owned_characters


async def _build_full_harem_view(user, user_id, display_name, page):
    owned_characters = await _load_owned_characters(user)

    total_pages = max(1, math.ceil(len(owned_characters) / PAGE_SIZE))
    if page < 0 or page >= total_pages:
        page = 0

    header_line = f"<b>{escape(display_name)}'s Harem • Page {page+1}/{total_pages}</b>\n"

    current_characters = owned_characters[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    anime_names = list(set(c['anime'] for c in current_characters))
    anime_counts = await get_anime_totals(anime_names)

    owned_anime_counts = Counter(c['anime'] for c in owned_characters)

    continuing_same_anime = False
    if page > 0 and current_characters:
        prev_last_char = owned_characters[page * PAGE_SIZE - 1]
        if current_characters[0]['anime'] == prev_last_char['anime']:
            continuing_same_anime = True

    current_grouped_characters = {k: list(v) for k, v in groupby(current_characters, key=lambda x: x['anime'])}

    harem_message = header_line
    for i, (anime, characters) in enumerate(current_grouped_characters.items()):
        if not (i == 0 and continuing_same_anime):
            anime_total = anime_counts.get(anime, 0)
            harem_message += f'\n✦ {anime} • {owned_anime_counts[anime]}/{anime_total}\n'
        for character in characters:
            tag_part = f' [{character["tag"]}]' if character.get('tag') else ''
            harem_message += (
                f'╰ {character["id"]:04d} • {format_rarity_emoji_only_html(character["rarity"])} • '
                f'{character["name"]}{tag_part} ×{character["count"]}\n'
            )

    total_count = sum(c['count'] for c in owned_characters)
    keyboard = [[InlineKeyboardButton(f"See Collection ({total_count})", switch_inline_query_current_chat=f"collection.{user_id}")]]

    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"harem:page:{page-1}:{user_id}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"harem:page:{page+1}:{user_id}"))
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("Filter by Rarity", callback_data=f"harem:filtermenu:{user_id}")])
    keyboard.append([InlineKeyboardButton("Close", callback_data=f"harem:close:{user_id}")])

    return harem_message, InlineKeyboardMarkup(keyboard), owned_characters


def _build_rarity_menu_view(owned_characters, user_id, header_name):
    """Same caption the user was already looking at stays useful context;
    we just swap the keyboard to the 6 rarity buttons + Back."""
    rarity_counts = Counter(c['rarity'] for c in owned_characters)

    menu_message = f"<b>{escape(header_name)}'s Harem</b>\nSelect a rarity to filter by:\n"

    keyboard = []
    for i in range(0, len(RARITY_ORDER), 2):
        row = []
        for rarity_key in RARITY_ORDER[i:i+2]:
            entry = RARITY_MAP[rarity_key]
            count = rarity_counts.get(rarity_key, 0)
            row.append(InlineKeyboardButton(
                f"{entry['name']} ({count})",
                callback_data=f"harem:rarity:{rarity_key}:0:{user_id}",
                icon_custom_emoji_id=entry['premium_id'],
            ))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅️ Back to Harem", callback_data=f"harem:page:0:{user_id}")])

    return menu_message, InlineKeyboardMarkup(keyboard)


async def _build_rarity_filtered_view(owned_characters, user_id, header_name, rarity_key, page, empty_state_is_saved_mode=False):
    filtered = [c for c in owned_characters if c['rarity'] == rarity_key]
    rarity_name = get_rarity_name(rarity_key)

    if not filtered:
        if empty_state_is_saved_mode:
            message = (
                f"<b>{escape(header_name)}'s Harem</b>\n\n"
                f"You don't have any {rarity_name} characters in your collection yet. "
                f"Keep guessing to catch some, or use /hmode to change your default view."
            )
            keyboard = [[InlineKeyboardButton("See Collection", switch_inline_query_current_chat=f"collection.{user_id}")]]
        else:
            message = (
                f"<b>{escape(header_name)}'s Harem • {rarity_name}</b>\n\n"
                f"You don't have any {rarity_name} characters yet."
            )
            keyboard = [[InlineKeyboardButton("⬅️ Back to Rarity Menu", callback_data=f"harem:filtermenu:{user_id}")]]
        return message, InlineKeyboardMarkup(keyboard)

    total_pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
    if page < 0 or page >= total_pages:
        page = 0

    current_characters = filtered[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    anime_names = list(set(c['anime'] for c in current_characters))
    anime_counts = await get_anime_totals(anime_names)

    owned_anime_counts_for_rarity = Counter(c['anime'] for c in filtered)

    continuing_same_anime = False
    if page > 0 and current_characters:
        prev_last_char = filtered[page * PAGE_SIZE - 1]
        if current_characters[0]['anime'] == prev_last_char['anime']:
            continuing_same_anime = True

    current_grouped_characters = {k: list(v) for k, v in groupby(current_characters, key=lambda x: x['anime'])}

    message = f"<b>{escape(header_name)}'s Harem • {rarity_name} • Page {page+1}/{total_pages}</b>\n"
    for i, (anime, characters) in enumerate(current_grouped_characters.items()):
        if not (i == 0 and continuing_same_anime):
            anime_total = anime_counts.get(anime, 0)
            message += f'\n✦ {anime} • {owned_anime_counts_for_rarity[anime]}/{anime_total}\n'
        for character in characters:
            tag_part = f' [{character["tag"]}]' if character.get('tag') else ''
            message += (
                f'╰ {character["id"]:04d} • {format_rarity_emoji_only_html(character["rarity"])} • '
                f'{character["name"]}{tag_part} ×{character["count"]}\n'
            )

    keyboard = []
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"harem:rarity:{rarity_key}:{page-1}:{user_id}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"harem:rarity:{rarity_key}:{page+1}:{user_id}"))
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("⬅️ Back to Rarity Menu", callback_data=f"harem:filtermenu:{user_id}")])

    return message, InlineKeyboardMarkup(keyboard)


async def _send_or_edit(update, message, reply_markup, owned_characters, user):
    """Picks an image the same way the old code did (favorite first, else a
    random owned character), and either sends a fresh message (/harem
    command) or edits the existing one (any button press)."""
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
            await update.message.reply_photo(photo=image_url, parse_mode='HTML', caption=message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
    else:
        query = update.callback_query
        try:
            if image_url:
                if query.message.caption != message:
                    await query.edit_message_caption(caption=message, reply_markup=reply_markup, parse_mode='HTML')
                else:
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
            else:
                if query.message.text != message:
                    await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
                else:
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass


def _build_hmode_home_view(user_id):
    message = "ʏᴏᴜ ᴄᴀɴ ᴄʜᴀɴɢᴇ ʜᴏᴡ ʏᴏᴜʀ ʜᴀʀᴇᴍ ɪs sʜᴏᴡɴ ᴜsɪɴɢ ᴛʜᴇsᴇ ʙᴜᴛᴛᴏɴs"

    keyboard = [
        [
            InlineKeyboardButton("Default", callback_data=f"hmode:setdefault:{user_id}"),
            InlineKeyboardButton("✨ By Rarity", callback_data=f"hmode:submenu:{user_id}"),
        ],
        [InlineKeyboardButton("🔄 Reset", callback_data=f"hmode:reset:{user_id}")],
    ]

    return message, InlineKeyboardMarkup(keyboard)


def _build_hmode_rarity_submenu(user_id):
    message = "ᴄʜᴏᴏsᴇ ᴀ ʀᴀʀɪᴛʏ ʏᴏᴜʀ ʜᴀʀᴇᴍ ᴡɪʟʟ ᴀʟᴡᴀʏs ᴏᴘᴇɴ ғɪʟᴛᴇʀᴇᴅ ᴛᴏ ɪᴛ"

    keyboard = []
    for i in range(0, len(RARITY_ORDER), 2):
        row = []
        for rarity_key in RARITY_ORDER[i:i+2]:
            entry = RARITY_MAP[rarity_key]
            row.append(InlineKeyboardButton(
                entry['name'],
                callback_data=f"hmode:set:{rarity_key}:{user_id}",
                icon_custom_emoji_id=entry['premium_id'],
            ))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"hmode:main:{user_id}")])

    return message, InlineKeyboardMarkup(keyboard)


async def _send_or_edit_hmode(update, message, reply_markup):
    """Text-only version of _send_or_edit for the /hmode settings menu --
    there's no character photo involved here, just a plain message."""
    if update.message:
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
    else:
        query = update.callback_query
        try:
            if reply_markup is None:
                await query.edit_message_text(message, parse_mode='HTML')
            elif query.message.text != message:
                await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await query.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass


async def harem(update: Update, context: CallbackContext, page=0) -> None:
    user_id = update.effective_user.id
    display_name = update.effective_user.first_name

    if update.message and user_id not in started_users_cache:
        keyboard = [[InlineKeyboardButton("Start Me", url=f'https://t.me/{BOT_USERNAME}?start=harem')]]
        await update.message.reply_text(NOT_STARTED_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    user = await get_user(user_id)
    if not user or 'characters' not in user or not user['characters']:
        if update.message:
            await update.message.reply_text('You Have Not Guessed any Characters Yet..')
        else:
            await update.callback_query.edit_message_text('You Have Not Guessed any Characters Yet..')
        return

    saved_rarity = harem_mode_cache.get(user_id)
    if saved_rarity and is_valid_rarity(saved_rarity):
        owned_characters = await _load_owned_characters(user)
        harem_message, reply_markup = await _build_rarity_filtered_view(
            owned_characters, user_id, display_name, saved_rarity, page,
            empty_state_is_saved_mode=True,
        )
    else:
        harem_message, reply_markup, owned_characters = await _build_full_harem_view(user, user_id, display_name, page)

    await _send_or_edit(update, harem_message, reply_markup, owned_characters, user)


async def harem_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data
    parts = data.split(':')
    mode = parts[1]

    if mode == 'close':
        user_id = int(parts[2])
        if query.from_user.id != user_id:
            await query.answer("its Not Your Harem", show_alert=True)
            return
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if mode == 'page':
        page, user_id = int(parts[2]), int(parts[3])
        if query.from_user.id != user_id:
            await query.answer("its Not Your Harem", show_alert=True)
            return
        await query.answer()
        await harem(update, context, page)
        return

    if mode == 'filtermenu':
        user_id = int(parts[2])
        if query.from_user.id != user_id:
            await query.answer("its Not Your Harem", show_alert=True)
            return
        await query.answer()

        user = await get_user(user_id)
        if not user or 'characters' not in user or not user['characters']:
            return
        owned_characters = await _load_owned_characters(user)

        menu_message, reply_markup = _build_rarity_menu_view(owned_characters, user_id, update.effective_user.first_name)
        await _send_or_edit(update, menu_message, reply_markup, owned_characters, user)
        return

    if mode == 'rarity':
        rarity_key, page, user_id = int(parts[2]), int(parts[3]), int(parts[4])
        if query.from_user.id != user_id:
            await query.answer("its Not Your Harem", show_alert=True)
            return
        await query.answer()

        user = await get_user(user_id)
        if not user or 'characters' not in user or not user['characters']:
            return
        owned_characters = await _load_owned_characters(user)

        message, reply_markup = await _build_rarity_filtered_view(
            owned_characters, user_id, update.effective_user.first_name, rarity_key, page
        )
        await _send_or_edit(update, message, reply_markup, owned_characters, user)
        return

    await query.answer()


async def hmode(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    message, reply_markup = _build_hmode_home_view(user_id)
    await _send_or_edit_hmode(update, message, reply_markup)


async def hmode_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data
    parts = data.split(':')
    action = parts[1]
    user_id = int(parts[-1])

    if query.from_user.id != user_id:
        await query.answer("its Not Your Settings", show_alert=True)
        return

    await query.answer()

    if action == 'main':
        message, reply_markup = _build_hmode_home_view(user_id)
        await _send_or_edit_hmode(update, message, reply_markup)
        return

    if action == 'submenu':
        message, reply_markup = _build_hmode_rarity_submenu(user_id)
        await _send_or_edit_hmode(update, message, reply_markup)
        return

    if action in ('setdefault', 'reset'):
        harem_mode_cache.pop(user_id, None)
        message = "ʜᴀʀᴇᴍ ᴍᴏᴅᴇ sᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ"
        await _send_or_edit_hmode(update, message, None)
        return

    if action == 'set':
        rarity_key = int(parts[2])
        if is_valid_rarity(rarity_key):
            harem_mode_cache[user_id] = rarity_key
            rarity_name = get_rarity_name(rarity_key)
            message = f"ʜᴀʀᴇᴍ ᴍᴏᴅᴇ ᴄʜᴀɴɢᴇᴅ ᴛᴏ {_to_small_caps(rarity_name)}"
            await _send_or_edit_hmode(update, message, None)
        return


application.add_handler(CommandHandler(["harem", "collection"], harem, block=False))
harem_handler = CallbackQueryHandler(harem_callback, pattern='^harem', block=False)
application.add_handler(harem_handler)

application.add_handler(CommandHandler(["hmode", "haremmode"], hmode, block=False))
hmode_handler = CallbackQueryHandler(hmode_callback, pattern='^hmode', block=False)
application.add_handler(hmode_handler)
