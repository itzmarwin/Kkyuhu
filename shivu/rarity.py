
RARITY_MAP = {
    1: {"name": "Common",   "emoji": "🔵", "premium_id": "6219726962370289232"},
    2: {"name": "Rare",     "emoji": "🟠", "premium_id": "6224452757835752311"},
    3: {"name": "Legendary","emoji": "🟡", "premium_id": "6219595845608677184"},
    4: {"name": "Mythic",   "emoji": "💠", "premium_id": "6224516447905783899"},
    5: {"name": "Astral",  "emoji": "🌌", "premium_id": "6221737208928281346"},
    6: {"name": "Seraphic", "emoji": "🪽", "premium_id": "6224022079990146834"},
}

# Drop weights used by send_image()'s random.choices(). Higher = more common.
# Roughly halves at each step so rarity feels like it's actually getting rarer.
RARITY_WEIGHTS = {
    1: 100,  # 🔵 Common
    2: 50,   # 🟠 Rare
    3: 25,   # 🟡 Legendary
    4: 12,   # 💠 Mythic
    5: 5,    # 🌌 Astral
    6: 2,    # 🪽 Seraphic
}


def get_rarity_name(rarity_key: int) -> str:
    """Plain name only, e.g. 'Mythic'. Use where no emoji/HTML is wanted."""
    entry = RARITY_MAP.get(rarity_key)
    return entry["name"] if entry else "Unknown"


def get_rarity_emoji(rarity_key: int) -> str:
    """Plain fallback emoji only, e.g. '💠'."""
    entry = RARITY_MAP.get(rarity_key)
    return entry["emoji"] if entry else ""


def format_rarity_html(rarity_key: int) -> str:
    """
    HTML-ready rarity string for captions sent with parse_mode='HTML'.

    If a premium_id is set, wraps the fallback emoji in a <tg-emoji> tag so
    Telegram Premium accounts see the custom emoji. If premium_id is None
    (not filled in yet), just returns the plain emoji + name - completely
    safe to use before the premium emoji ids are added.

    Example output once premium_id is filled in:
        '<tg-emoji emoji-id="5368324170671202286">💠</tg-emoji> Mythic'
    Example output while premium_id is still None:
        '💠 Mythic'
    """
    entry = RARITY_MAP.get(rarity_key)
    if not entry:
        return "Unknown"

    name = entry["name"]
    emoji = entry["emoji"]
    premium_id = entry["premium_id"]

    if premium_id:
        return f'<tg-emoji emoji-id="{premium_id}">{emoji}</tg-emoji> {name}'
    return f'{emoji} {name}'


def is_valid_rarity(rarity_key: int) -> bool:
    return rarity_key in RARITY_MAP
