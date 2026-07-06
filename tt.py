"""
Standalone, READ-ONLY diagnostic. Does not modify anything.

Run on your server, from the project root (where the shivu/ folder is):

    python3 sequence_debug.py

Prints:
  1. The raw 'sequences' document for 'character_id'
  2. Every character currently in `collection`, sorted by id, so we can see
     if any ids are duplicated or missing
"""

import asyncio
from shivu import db, collection


async def main():
    seq_doc = await db.sequences.find_one({'_id': 'character_id'})
    print("sequences collection, character_id doc:")
    print(seq_doc)
    print()

    print("All characters currently in `collection`, sorted by id:")
    cursor = collection.find({}).sort('id', 1)
    all_chars = await cursor.to_list(length=None)

    if not all_chars:
        print("  (no characters found)")

    seen_ids = {}
    for c in all_chars:
        cid = c.get('id')
        print(f"  id={cid!r} name={c.get('name')!r} rarity={c.get('rarity')!r}")
        seen_ids.setdefault(cid, []).append(c.get('name'))

    print()
    duplicates = {cid: names for cid, names in seen_ids.items() if len(names) > 1}
    if duplicates:
        print("DUPLICATE ids found:")
        for cid, names in duplicates.items():
            print(f"  id={cid} is used by: {names}")
    else:
        print("No duplicate ids found.")


if __name__ == "__main__":
    asyncio.run(main())
