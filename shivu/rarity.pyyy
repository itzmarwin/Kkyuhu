RARITY_MAP = {
    1: {"name": "Common",   "emoji": "🔵", "premium_id": "6219726962370289232"},
    2: {"name": "Rare",     "emoji": "🟠", "premium_id": "6224452757835752311"},
    3: {"name": "Legendary","emoji": "🟡", "premium_id": "6219595845608677184"},
    4: {"name": "Mythic",   "emoji": "💠", "premium_id": "6224516447905783899"},
    5: {"name": "Astral",  "emoji": "🌌", "premium_id": "6221737208928281346"},
    6: {"name": "Seraphic", "emoji": "🪽", "premium_id": "6224022079990146834"},
}

RARITY_WEIGHTS = {
    1: 100,
    2: 50,
    3: 25,
    4: 12,
    5: 5,
    6: 2,
}


def get_rarity_name(rarity_key: int) -> str:
    entry = RARITY_MAP.get(rarity_key)
    return entry["name"] if entry else "Unknown"


def get_rarity_emoji(rarity_key: int) -> str:
    entry = RARITY_MAP.get(rarity_key)
    return entry["emoji"] if entry else ""


def format_rarity_html(rarity_key: int) -> str:
    entry = RARITY_MAP.get(rarity_key)
    if not entry:
        return "Unknown"

    name = entry["name"]
    emoji = entry["emoji"]
    premium_id = entry["premium_id"]

    if premium_id:
        return f'<tg-emoji emoji-id="{premium_id}">{emoji}</tg-emoji> {name}'
    return f'{emoji} {name}'


def format_rarity_plain_html(rarity_key: int) -> str:
    """Same output as format_rarity_html but WITHOUT the <tg-emoji> wrapper.

    Why this exists: Telegram will not render a custom/premium emoji inside the
    *initial* content of an answerInlineQuery result no matter what - not even
    if the bot owner has Telegram Premium. The entity is only allowed in
    messages the bot sends/edits directly (sendMessage, sendPhoto,
    editMessageCaption, etc.) to a private/group/supergroup chat.

    So inlinequery.py uses this plain version for the caption it first answers
    the inline query with, then swaps in format_rarity_html()'s version via
    edit_message_caption once chosen_inline_result confirms the result was
    actually sent into a chat. See inlinequery.py for the full flow.
    """
    entry = RARITY_MAP.get(rarity_key)
    if not entry:
        return "Unknown"
    return f'{entry["emoji"]} {entry["name"]}'


def is_valid_rarity(rarity_key: int) -> bool:
    return rarity_key in RARITY_MAP
