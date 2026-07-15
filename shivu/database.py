import asyncio
import logging

from pymongo import AsyncMongoClient, ASCENDING, ReturnDocument
from pymongo.errors import PyMongoError

from shivu.config import Development as Config

LOGGER = logging.getLogger(__name__)

client = AsyncMongoClient(Config.mongo_url)
db = client['Character_catcher']

collection                    = db['anime_characters_lol']      # all characters in the game
user_collection                = db['user_collection_lmaoooo']   # per-user owned characters
user_totals_collection         = db['user_totals_lmaoooo']       # per-group message_frequency setting
group_user_totals_collection   = db['group_user_totalsssssss']   # per-group per-user guess counts (/ctop)
top_global_groups_collection   = db['top_global_groups']         # per-group global guess totals (/TopGroups)
pm_users_collection            = db['total_pm_users']            # users who've /start'd in PM    (was "pm_users")
sequences_collection           = db['sequences']                 # auto-increment counters         (was inline "db.sequences")


async def _create_index_safely(coll, keys, **kwargs):
    """Wraps create_index so that a duplicate-data conflict on a brand-new
    unique index logs a clear, actionable error instead of crashing the
    whole bot on startup."""
    try:
        await coll.create_index(keys, **kwargs)
    except PyMongoError as e:
        LOGGER.error(
            "Could not create index %s on '%s' -- likely duplicate rows already "
            "exist that violate the new unique constraint. Dedupe the collection "
            "and restart to retry. Error: %s",
            keys, coll.name, e,
        )


async def ensure_indexes():
    """Called once at startup (see post_init in __main__.py)."""

    await collection.create_index([('id', ASCENDING)])
    await collection.create_index([('anime', ASCENDING)])
    await user_collection.create_index([('id', ASCENDING)])
    await user_collection.create_index([('characters.id', ASCENDING)])
    await user_collection.create_index([('character_count', -1)])
    await user_collection.create_index([('id', ASCENDING), ('characters.id', ASCENDING)])

    await _create_index_safely(
        group_user_totals_collection,
        [('group_id', ASCENDING), ('user_id', ASCENDING)],
        unique=True,
    )
    await group_user_totals_collection.create_index([('group_id', ASCENDING), ('count', -1)])

    await _create_index_safely(
        top_global_groups_collection,
        [('group_id', ASCENDING)],
        unique=True,
    )
    await top_global_groups_collection.create_index([('count', -1)])

    await _create_index_safely(
        user_totals_collection,
        [('chat_id', ASCENDING)],
        unique=True,
    )

    LOGGER.info("Indexes ensured.")

async def get_next_sequence_number(sequence_name: str) -> int:
    sequence_document = await sequences_collection.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'sequence_value': 1}},
        upsert=True,
        return_document=ReturnDocument.BEFORE,
    )
    if not sequence_document:
        return 0
    return sequence_document['sequence_value']


async def insert_character(character: dict) -> None:
    await collection.insert_one(character)


async def get_character(character_id: int):
    return await collection.find_one({'id': character_id})


async def delete_character(character_id: int):
    """Returns the deleted document, or None if no such character existed."""
    return await collection.find_one_and_delete({'id': character_id})


async def update_character_field(character_id: int, field: str, value):
    return await collection.find_one_and_update(
        {'id': character_id}, {'$set': {field: value}}
    )


async def get_all_characters() -> list:
    return await collection.find({}).to_list(length=None)


async def search_characters(query_filter: dict, offset: int, limit: int) -> list:
    cursor = collection.find(query_filter).sort('id', 1).skip(offset).limit(limit)
    return await cursor.to_list(length=limit)


async def get_anime_totals(anime_names: list) -> dict:
    """How many characters exist in the catalog for each of these anime."""
    if not anime_names:
        return {}
    cursor = await collection.aggregate([
        {"$match": {"anime": {"$in": anime_names}}},
        {"$group": {"_id": "$anime", "count": {"$sum": 1}}},
    ])
    result_list = await cursor.to_list(length=None)
    return {item['_id']: item['count'] for item in result_list}

async def get_user(user_id: int):
    return await user_collection.find_one({'id': user_id})


async def get_user_with_characters(user_id: int):
    return await user_collection.find_one(
        {'id': user_id}, {'characters': 1, 'first_name': 1, 'id': 1}
    )


async def user_has_character(user_id: int, character_id: int) -> bool:
    count = await user_collection.count_documents(
        {'id': user_id, 'characters.id': character_id}
    )
    return count > 0


async def grant_character_to_user(user_id: int, character_id: int, username=None, first_name=None) -> None:
    inc_fields = {'characters.$.count': 1, 'character_count': 1}
    set_fields = {}
    if username is not None:
        set_fields['username'] = username
    if first_name is not None:
        set_fields['first_name'] = first_name

    update_doc = {'$inc': inc_fields}
    if set_fields:
        update_doc['$set'] = set_fields

    result = await user_collection.update_one(
        {'id': user_id, 'characters.id': character_id},
        update_doc,
    )
    if result.matched_count == 0:
        push_doc = {
            '$push': {'characters': {'id': character_id, 'count': 1}},
            '$inc': {'character_count': 1},
        }
        if set_fields:
            push_doc['$set'] = set_fields
        await user_collection.update_one(
            {'id': user_id},
            push_doc,
            upsert=True,
        )


async def remove_character_from_user(user_id: int, character_id: int) -> None:
    await user_collection.update_one(
        {'id': user_id, 'characters.id': character_id},
        {'$inc': {'characters.$.count': -1, 'character_count': -1}},
    )
    await user_collection.update_one(
        {'id': user_id},
        {'$pull': {'characters': {'id': character_id, 'count': {'$lte': 0}}}},
    )


async def set_favorite_character(user_id: int, character_id: int) -> None:
    await user_collection.update_one({'id': user_id}, {'$set': {'favorites': [character_id]}})


async def get_top_collectors(character_id: int, limit: int = 5) -> list:
    cursor = await user_collection.aggregate([
        {"$match": {"characters.id": character_id}},
        {"$project": {
            "first_name": 1,
            "matched_count": {
                "$first": {
                    "$map": {
                        "input": {"$filter": {
                            "input": "$characters",
                            "cond": {"$eq": ["$$this.id", character_id]},
                        }},
                        "as": "m",
                        "in": "$$m.count",
                    }
                }
            },
        }},
        {"$match": {"matched_count": {"$gt": 0}}},
        {"$sort": {"matched_count": -1}},
        {"$limit": limit},
    ])
    result_list = await cursor.to_list(length=limit)
    return [
        {'first_name': doc.get('first_name') or 'Unknown', 'count': doc.get('matched_count', 0)}
        for doc in result_list
    ]


async def get_user_count() -> int:
    return await user_collection.estimated_document_count()


async def iter_all_user_first_names():
    async for user in user_collection.find({}, {'first_name': 1}):
        yield user.get('first_name', 'Unknown')


async def record_group_guess(chat_id: int, group_name: str, user_id: int, username, first_name) -> None:
    """Called once per successful /guess -- bumps this user's per-group
    guess count and this group's global guess count together."""
    await asyncio.gather(
        group_user_totals_collection.update_one(
            {'group_id': chat_id, 'user_id': user_id},
            {
                '$set': {
                    'user_id': user_id,
                    'username': username,
                    'first_name': first_name,
                },
                '$inc': {'count': 1},
            },
            upsert=True,
        ),
        top_global_groups_collection.update_one(
            {'group_id': chat_id},
            {
                '$set': {'group_name': group_name},
                '$inc': {'count': 1},
            },
            upsert=True,
        ),
    )


async def get_group_ranked_list(chat_id: int) -> list:
    cursor = group_user_totals_collection.find(
        {'group_id': chat_id},
        {'user_id': 1, 'username': 1, 'first_name': 1, 'count': 1, '_id': 0},
    ).sort('count', -1)
    return await cursor.to_list(length=None)


async def get_users_ranked_by_character_count() -> list:
    cursor = user_collection.find(
        {'character_count': {'$gt': 0}},
        {'id': 1, 'username': 1, 'first_name': 1, 'character_count': 1, '_id': 0},
    ).sort('character_count', -1)
    ranked_list = await cursor.to_list(length=None)
    for entry in ranked_list:
        entry['user_id'] = entry.pop('id')
    return ranked_list


async def get_groups_ranked_by_count() -> list:
    cursor = top_global_groups_collection.find(
        {}, {'group_id': 1, 'group_name': 1, 'count': 1, '_id': 0},
    ).sort('count', -1)
    return await cursor.to_list(length=None)


async def get_group_count() -> int:
    return await top_global_groups_collection.estimated_document_count()


async def iter_all_group_names():
    async for group in top_global_groups_collection.find({}, {'group_name': 1}):
        yield group.get('group_name', 'Unknown')


async def iter_all_group_ids():
    """Every group_id the bot has ever seen a guess in -- used for /broadcast."""
    async for group in top_global_groups_collection.find({}, {'group_id': 1, '_id': 0}):
        yield group['group_id']

async def sync_pm_user(user_id: int, first_name: str, username: str) -> bool:
    user_data = await pm_users_collection.find_one({"_id": user_id})

    if user_data is None:
        await pm_users_collection.insert_one(
            {"_id": user_id, "first_name": first_name, "username": username}
        )
        return True

    if user_data['first_name'] != first_name or user_data['username'] != username:
        await pm_users_collection.update_one(
            {"_id": user_id}, {"$set": {"first_name": first_name, "username": username}}
        )
    return False


async def iter_all_pm_user_ids():
    async for user in pm_users_collection.find({}, {'_id': 1}):
        yield user['_id']

async def get_group_message_frequency(chat_id: str, default: int = 100) -> int:
    doc = await user_totals_collection.find_one({'chat_id': chat_id})
    return doc.get('message_frequency', default) if doc else default


async def set_group_message_frequency(chat_id: str, frequency: int):
    return await user_totals_collection.find_one_and_update(
        {'chat_id': chat_id},
        {'$set': {'message_frequency': frequency}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
