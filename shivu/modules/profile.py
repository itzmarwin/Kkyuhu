import time
from collections import Counter
from datetime import datetime

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application
from shivu.database import get_user, unlock_new_achievements
from shivu.cache import (
    characters_by_id,
    all_characters_cache,
    global_users_cache,
    profile_cooldowns,
    profile_data_cache,
)
from shivu.rarity import format_rarity_html
from shivu.achievements import evaluate_all, AchievementContext, TOTAL_ACHIEVEMENTS

COOLDOWN_SECONDS = 4
PROFILE_CACHE_TTL = 30
PROGRESS_BAR_LENGTH = 10
MAX_TRACKED_USERS = 2000

LOADING_TEXT = "⌬ Loading your profile..."
NOT_STARTED_TEXT = 'You Have Not Guessed any Characters Yet..'

TITLE_THRESHOLDS = [
    (1500, "Mythic Collector"),
    (700, "Legend Collector"),
    (350, "Master Collector"),
    (150, "Elite Collector"),
    (50, "Skilled Collector"),
    (0, "Rookie Collector"),
]


def _cooldown_remaining(user_id: int) -> float:
    last_request = profile_cooldowns.get(user_id)
    if last_request is None:
        return 0.0
    elapsed = time.monotonic() - last_request
    remaining = COOLDOWN_SECONDS - elapsed
    return remaining if remaining > 0 else 0.0


def _get_title(character_count: int) -> str:
    for threshold, title in TITLE_THRESHOLDS:
        if character_count >= threshold:
            return title
    return "Rookie Collector"


def _build_progress_bar(percentage: float) -> str:
    filled = round((percentage / 100) * PROGRESS_BAR_LENGTH)
    filled = max(0, min(PROGRESS_BAR_LENGTH, filled))
    return '■' * filled + '▱' * (PROGRESS_BAR_LENGTH - filled)


def _format_join_date(first_collected_at) -> str:
    if not first_collected_at:
        return "N/A"
    if isinstance(first_collected_at, datetime):
        return first_collected_at.strftime('%d %b %Y')
    return "N/A"


def _get_global_rank(user_id: int):
    ranked_list = global_users_cache.get('ranked_list', [])
    for index, entry in enumerate(ranked_list, start=1):
        if entry.get('user_id') == user_id:
            return index
    return None


async def _compute_completed_anime_count(owned_character_ids: set) -> int:
    anime_totals = Counter(c['anime'] for c in all_characters_cache)
    anime_owned = Counter()
    for char_id in owned_character_ids:
        info = characters_by_id.get(char_id)
        if info:
            anime_owned[info['anime']] += 1

    completed = 0
    for anime, total in anime_totals.items():
        if total > 0 and anime_owned.get(anime, 0) >= total:
            completed += 1
    return completed


def _find_favorite_name(user, owned_character_ids) -> str:
    favorites = user.get('favorites') or []
    if not favorites:
        return "None"
    fav_id = favorites[0]
    if fav_id not in owned_character_ids:
        return "None"
    info = characters_by_id.get(fav_id)
    return info['name'] if info else "None"


async def _gather_profile_data(user_id: int, user: dict) -> dict:
    owned = user.get('characters', [])
    owned_character_ids = {c['id'] for c in owned}
    unique_count = len(owned_character_ids)
    character_count = user.get('character_count', 0)

    total_characters = len(all_characters_cache)
    completion_pct = (unique_count / total_characters * 100) if total_characters else 0.0

    highest_rarity = None
    for entry in owned:
        info = characters_by_id.get(entry['id'])
        if info and info.get('rarity') is not None:
            if highest_rarity is None or info['rarity'] > highest_rarity:
                highest_rarity = info['rarity']

    completed_anime_count = await _compute_completed_anime_count(owned_character_ids)
    global_rank = _get_global_rank(user_id)
    streak_count = user.get('streak_count', 0)

    ctx = AchievementContext(
        character_count=character_count,
        unique_count=unique_count,
        highest_rarity=highest_rarity,
        completed_anime_count=completed_anime_count,
        global_rank=global_rank,
        streak_count=streak_count,
        has_favorite=bool(user.get('favorites')),
    )
    achievement_results = evaluate_all(ctx)

    previously_unlocked_ids = set(user.get('unlocked_achievements', []))
    newly_unlocked_ids = [
        a['id'] for a in achievement_results
        if a['unlocked'] and a['id'] not in previously_unlocked_ids
    ]
    if newly_unlocked_ids:
        await unlock_new_achievements(user_id, newly_unlocked_ids)

    permanently_unlocked_ids = previously_unlocked_ids | set(newly_unlocked_ids)
    for a in achievement_results:
        a['unlocked'] = a['id'] in permanently_unlocked_ids

    unlocked_count = len(permanently_unlocked_ids)

    return {
        'character_count': character_count,
        'unique_count': unique_count,
        'total_characters': total_characters,
        'completion_pct': completion_pct,
        'highest_rarity': highest_rarity,
        'completed_anime_count': completed_anime_count,
        'global_rank': global_rank,
        'streak_count': streak_count,
        'favorite_name': _find_favorite_name(user, owned_character_ids),
        'first_collected_at': user.get('first_collected_at'),
        'achievement_results': achievement_results,
        'unlocked_count': unlocked_count,
    }


async def _get_or_compute_profile_data(user_id: int, user: dict) -> dict:
    cached = profile_data_cache.get(user_id)
    if cached and (time.monotonic() - cached['cached_at']) < PROFILE_CACHE_TTL:
        return cached['data']

    data = await _gather_profile_data(user_id, user)
    profile_data_cache[user_id] = {'data': data, 'cached_at': time.monotonic()}
    if len(profile_data_cache) > MAX_TRACKED_USERS:
        for stale_id in list(profile_data_cache.keys())[:-MAX_TRACKED_USERS // 2]:
            profile_data_cache.pop(stale_id, None)
    return data


def _render_profile_text(display_name: str, user_id: int, data: dict) -> str:
    title = _get_title(data['character_count'])
    joined = _format_join_date(data['first_collected_at'])

    progress_bar = _build_progress_bar(data['completion_pct'])

    if data['highest_rarity'] is not None:
        highest_rarity_display = format_rarity_html(data['highest_rarity'])
    else:
        highest_rarity_display = "None"

    rank_display = f"#{data['global_rank']:,}" if data['global_rank'] else "Unranked"
    streak_display = f"{data['streak_count']} Days" if data['streak_count'] else "0 Days"

    return f"""⌬ <b>Collector Profile</b>

<b>Name</b>             • {display_name}
<b>Title</b>            • {title}
<b>User ID</b>          • {user_id}
<b>Joined</b>           • {joined}

<b>Collected</b>        • {data['character_count']:,}
<b>Completion</b>       • {data['unique_count']} / {data['total_characters']:,} ({data['completion_pct']:.2f}%)

<b>Progress</b>
{progress_bar}

<b>Highest Rarity</b>   • {highest_rarity_display}
<b>Global Rank</b>      • {rank_display}

<b>Favorite</b>         • {data['favorite_name']}
<b>Catch Streak</b>     • {streak_display}
<b>Achievements</b>     • {data['unlocked_count']}/{TOTAL_ACHIEVEMENTS}"""


async def profile(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    display_name = update.effective_user.first_name

    remaining = _cooldown_remaining(user_id)
    if remaining > 0:
        return
    profile_cooldowns[user_id] = time.monotonic()
    if len(profile_cooldowns) > MAX_TRACKED_USERS:
        for stale_id in list(profile_cooldowns.keys())[:-MAX_TRACKED_USERS // 2]:
            profile_cooldowns.pop(stale_id, None)

    user = await get_user(user_id)
    if not user or not user.get('characters'):
        await update.message.reply_text(NOT_STARTED_TEXT)
        return

    loading_message = await update.message.reply_text(LOADING_TEXT)

    data = await _get_or_compute_profile_data(user_id, user)
    profile_text = _render_profile_text(display_name, user_id, data)

    await loading_message.edit_text(profile_text, parse_mode='HTML')


def _render_achievements_text(data: dict) -> str:
    lines = ["⌬ <b>Achievements</b>\n"]
    for a in data['achievement_results']:
        if a['unlocked']:
            mark = "✅"
            progress = f"{a['target']}/{a['target']}"
        else:
            mark = "▫️"
            progress = f"{min(a['current'], a['target'])}/{a['target']}"
        lines.append(
            f"{mark} <b>{a['name']}</b> — {a['description']}\n"
            f"    {progress}"
        )
    lines.append(f"\n<b>Total</b> • {data['unlocked_count']}/{TOTAL_ACHIEVEMENTS}")
    return '\n'.join(lines)


async def achievements(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    remaining = _cooldown_remaining(user_id)
    if remaining > 0:
        return
    profile_cooldowns[user_id] = time.monotonic()
    if len(profile_cooldowns) > MAX_TRACKED_USERS:
        for stale_id in list(profile_cooldowns.keys())[:-MAX_TRACKED_USERS // 2]:
            profile_cooldowns.pop(stale_id, None)

    user = await get_user(user_id)
    if not user or not user.get('characters'):
        await update.message.reply_text(NOT_STARTED_TEXT)
        return

    loading_message = await update.message.reply_text("⌬ Loading your achievements...")

    data = await _get_or_compute_profile_data(user_id, user)
    achievements_text = _render_achievements_text(data)

    await loading_message.edit_text(achievements_text, parse_mode='HTML')


application.add_handler(CommandHandler('profile', profile, block=False))
application.add_handler(CommandHandler('achievements', achievements, block=False))
