"""
Standalone, READ-ONLY diagnostic. Does not touch the bot or modify any data.

Run directly on your server (bot can be running or stopped, doesn't matter):

    python3 harem_debug.py <your_telegram_user_id> <character_id>

Example, based on what you described:
    python3 harem_debug.py 123456789 1

This will print:
  1. The raw user document from user_collection (so we see exactly what
     'characters' list looks like - field names, types, everything)
  2. The raw character document from `collection` for the given character_id
     (so we see if 'id' is stored as int or string, and what 'rarity' is)
  3. Whether the two 'id' values actually match in type
"""

import sys
import asyncio

sys.path.insert(0, ".")

from shivu import collection, user_collection


async def main():
    if len(sys.argv) != 3:
        print("Usage: python3 harem_debug.py <telegram_user_id> <character_id>")
        return

    user_id_raw = sys.argv[1]
    character_id_raw = sys.argv[2]

    print(f"Looking up user with id = {user_id_raw} (as int)")
    user_id = int(user_id_raw)
    user_doc = await user_collection.find_one({'id': user_id})

    if not user_doc:
        print("NO USER DOCUMENT FOUND with id =", user_id)
        print("Trying as string just in case...")
        user_doc = await user_collection.find_one({'id': user_id_raw})
        if user_doc:
            print("FOUND when queried as STRING - this means 'id' is stored as a string in this doc, not int!")
        else:
            print("Still nothing. This user has no record in user_collection at all.")
    else:
        print("User document found:")
        print(user_doc)

    print()

    if user_doc and 'characters' in user_doc:
        print("Raw 'characters' list on this user:")
        for entry in user_doc['characters']:
            print(f"  entry = {entry!r}  (id type = {type(entry.get('id')).__name__})")

    print()

    character_id = int(character_id_raw)
    print(f"Looking up character with id = {character_id} (as int) in `collection`")
    char_doc = await collection.find_one({'id': character_id})

    if not char_doc:
        print("NO CHARACTER DOCUMENT FOUND with id =", character_id)
        print("Trying as string just in case...")
        char_doc = await collection.find_one({'id': character_id_raw})
        if char_doc:
            print("FOUND when queried as STRING - this means 'id' is stored as a string on the character doc, not int!")
    else:
        print("Character document found:")
        print(char_doc)
        print(f"  id type = {type(char_doc.get('id')).__name__}")
        print(f"  rarity value = {char_doc.get('rarity')!r} (type = {type(char_doc.get('rarity')).__name__})")


if __name__ == "__main__":
    asyncio.run(main())
