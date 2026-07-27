RARITY_MAP = {
    1: {"name": "Common",   "emoji": "🟢", "premium_id": "6282749538650300945"},
    2: {"name": "Rare",     "emoji": "🟠", "premium_id": "6282994824232574941"},
    3: {"name": "Legendary","emoji": "🟡", "premium_id": "6282812653194715792"},
    4: {"name": "Mythic",   "emoji": "💠", "premium_id": "6283045144069418520"},
    5: {"name": "Astral",  "emoji": "🌌", "premium_id": "6282794356634035796"},
    6: {"name": "Seraphic", "emoji": "🪽", "premium_id": "6282707254697271319"},
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
    entry = RARITY_MAP.get(rarity_key)
    if not entry:
        return "Unknown"
    return f'{entry["emoji"]} {entry["name"]}'


def format_rarity_emoji_only_html(rarity_key: int) -> str:
    entry = RARITY_MAP.get(rarity_key)
    if not entry:
        return ""

    emoji = entry["emoji"]
    premium_id = entry["premium_id"]

    if premium_id:
        return f'<tg-emoji emoji-id="{premium_id}">{emoji}</tg-emoji>'
    return emoji


def is_valid_rarity(rarity_key: int) -> bool:
    return rarity_key in RARITY_MAP
