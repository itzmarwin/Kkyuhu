from collections import namedtuple

AchievementContext = namedtuple('AchievementContext', [
    'character_count',
    'unique_count',
    'highest_rarity',
    'completed_anime_count',
    'global_rank',
    'streak_count',
    'has_favorite',
])


def _simple(current, target):
    return current >= target, current, target


ACHIEVEMENTS = [
    {
        'id': 'first_character',
        'name': 'First Character',
        'description': 'Collect your very first character',
        'check': lambda ctx: _simple(ctx.character_count, 1),
    },
    {
        'id': 'collect_10',
        'name': 'Getting Started',
        'description': 'Collect 10 characters',
        'check': lambda ctx: _simple(ctx.character_count, 10),
    },
    {
        'id': 'collect_50',
        'name': 'Building a Collection',
        'description': 'Collect 50 characters',
        'check': lambda ctx: _simple(ctx.character_count, 50),
    },
    {
        'id': 'collect_100',
        'name': 'Century Club',
        'description': 'Collect 100 characters',
        'check': lambda ctx: _simple(ctx.character_count, 100),
    },
    {
        'id': 'collect_250',
        'name': 'Serious Collector',
        'description': 'Collect 250 characters',
        'check': lambda ctx: _simple(ctx.character_count, 250),
    },
    {
        'id': 'collect_500',
        'name': 'Half a Thousand',
        'description': 'Collect 500 characters',
        'check': lambda ctx: _simple(ctx.character_count, 500),
    },
    {
        'id': 'collect_1000',
        'name': 'Four Digits',
        'description': 'Collect 1,000 characters',
        'check': lambda ctx: _simple(ctx.character_count, 1000),
    },
    {
        'id': 'unique_100',
        'name': 'Variety Seeker',
        'description': 'Own 100 unique characters',
        'check': lambda ctx: _simple(ctx.unique_count, 100),
    },
    {
        'id': 'unique_500',
        'name': 'Dedicated Archivist',
        'description': 'Own 500 unique characters',
        'check': lambda ctx: _simple(ctx.unique_count, 500),
    },

    {
        'id': 'first_rare',
        'name': 'A Bit Lucky',
        'description': 'Collect your first Rare character',
        'check': lambda ctx: _simple(1 if ctx.highest_rarity and ctx.highest_rarity >= 2 else 0, 1),
    },
    {
        'id': 'first_legendary',
        'name': 'Legendary Find',
        'description': 'Collect your first Legendary character',
        'check': lambda ctx: _simple(1 if ctx.highest_rarity and ctx.highest_rarity >= 3 else 0, 1),
    },
    {
        'id': 'first_mythic',
        'name': 'Mythic Encounter',
        'description': 'Collect your first Mythic character',
        'check': lambda ctx: _simple(1 if ctx.highest_rarity and ctx.highest_rarity >= 4 else 0, 1),
    },
    {
        'id': 'first_astral',
        'name': 'Reaching the Stars',
        'description': 'Collect your first Astral character',
        'check': lambda ctx: _simple(1 if ctx.highest_rarity and ctx.highest_rarity >= 5 else 0, 1),
    },
    {
        'id': 'first_seraphic',
        'name': 'Touched by Seraphim',
        'description': 'Collect your first Seraphic character',
        'check': lambda ctx: _simple(1 if ctx.highest_rarity and ctx.highest_rarity >= 6 else 0, 1),
    },

    {
        'id': 'complete_first_anime',
        'name': 'Series Complete',
        'description': 'Fully collect every character from one anime',
        'check': lambda ctx: _simple(min(ctx.completed_anime_count, 1), 1),
    },
    {
        'id': 'complete_5_anime',
        'name': 'Genre Master',
        'description': 'Fully collect 5 different anime series',
        'check': lambda ctx: _simple(ctx.completed_anime_count, 5),
    },
    {
        'id': 'complete_10_anime',
        'name': 'Encyclopedia',
        'description': 'Fully collect 10 different anime series',
        'check': lambda ctx: _simple(ctx.completed_anime_count, 10),
    },

    {
        'id': 'top_1000_global',
        'name': 'Making Moves',
        'description': 'Reach Top 1,000 on the Global Leaderboard',
        'check': lambda ctx: _simple(
            1 if ctx.global_rank and ctx.global_rank <= 1000 else 0, 1,
        ),
    },
    {
        'id': 'top_100_global',
        'name': 'Elite Ranks',
        'description': 'Reach Top 100 on the Global Leaderboard',
        'check': lambda ctx: _simple(
            1 if ctx.global_rank and ctx.global_rank <= 100 else 0, 1,
        ),
    },
    {
        'id': 'top_10_global',
        'name': 'Best of the Best',
        'description': 'Reach Top 10 on the Global Leaderboard',
        'check': lambda ctx: _simple(
            1 if ctx.global_rank and ctx.global_rank <= 10 else 0, 1,
        ),
    },
    {
        'id': 'set_favorite',
        'name': 'Close to the Heart',
        'description': 'Set a character as your favorite',
        'check': lambda ctx: _simple(1 if ctx.has_favorite else 0, 1),
    },

    {
        'id': 'streak_3',
        'name': 'Warming Up',
        'description': 'Reach a 3-Day Catch Streak',
        'check': lambda ctx: _simple(ctx.streak_count, 3),
    },
    {
        'id': 'streak_7',
        'name': 'One Week Strong',
        'description': 'Reach a 7-Day Catch Streak',
        'check': lambda ctx: _simple(ctx.streak_count, 7),
    },
    {
        'id': 'streak_14',
        'name': 'Two Weeks Running',
        'description': 'Reach a 14-Day Catch Streak',
        'check': lambda ctx: _simple(ctx.streak_count, 14),
    },
    {
        'id': 'streak_30',
        'name': 'Unstoppable',
        'description': 'Reach a 30-Day Catch Streak',
        'check': lambda ctx: _simple(ctx.streak_count, 30),
    },
]

ACHIEVEMENTS_BY_ID = {a['id']: a for a in ACHIEVEMENTS}
TOTAL_ACHIEVEMENTS = len(ACHIEVEMENTS)


def evaluate_all(ctx: AchievementContext):
    results = []
    for achievement in ACHIEVEMENTS:
        unlocked, current, target = achievement['check'](ctx)
        results.append({
            'id': achievement['id'],
            'name': achievement['name'],
            'description': achievement['description'],
            'unlocked': unlocked,
            'current': current,
            'target': target,
        })
    return results
