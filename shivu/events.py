EVENT_MAP = {
    "thingyan": {
        "emoji": "💦",
        "display_name": "💦𝑻𝒉𝒊𝒏𝒈𝒚𝒂𝒏💦",
    },
}


def is_valid_event(event_code: str) -> bool:
    return event_code in EVENT_MAP


def get_event_emoji(event_code: str) -> str:
    entry = EVENT_MAP.get(event_code)
    return entry["emoji"] if entry else ""


def get_event_display_name(event_code: str) -> str:
    entry = EVENT_MAP.get(event_code)
    return entry["display_name"] if entry else ""


def format_event_tag(event_code: str) -> str:
    emoji = get_event_emoji(event_code)
    return f" [{emoji}]" if emoji else ""


def format_event_footer(event_code: str) -> str:
    entry = EVENT_MAP.get(event_code)
    if not entry:
        return ""
    return f"\n\n{entry['display_name']}"


def list_event_codes() -> list:
    return list(EVENT_MAP.keys())
