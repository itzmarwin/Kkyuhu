"""
Standalone test using python-telegram-bot itself (not raw HTTP this time).
This isolates whether PTB is the one breaking the tg-emoji tag.

Run from your project root:

    python3 ptb_emoji_test.py <your_telegram_user_id>

Compares 3 send methods:
  1. bot.send_message with parse_mode=HTML (plain string, like the raw test)
  2. bot.send_message with parse_mode=ParseMode.HTML (PTB's enum, in case the
     string "HTML" vs the enum behaves differently in this PTB version)
  3. bot.send_photo with a caption containing the tag (this matches exactly
     what upload.py / send_image / guess do in the real bot)

After running, check your Telegram DM with the bot - do any of the 3 test
messages show the actual premium emoji, or all fallback plain emoji?
Also paste the console output here, especially any errors.
"""

import sys
import os
import asyncio

from dotenv import load_dotenv
load_dotenv()

from telegram import Bot
from telegram.constants import ParseMode

TOKEN = os.getenv("TOKEN")
TEST_EMOJI_ID = "6224516447905783899"
TEST_FALLBACK_EMOJI = "💠"

# A small, known-public test image so send_photo has something to attach
TEST_PHOTO_URL = "https://telegra.ph/file/b925c3985f0f325e62e17.jpg"


async def main():
    if len(sys.argv) != 2:
        print("Usage: python3 ptb_emoji_test.py <your_telegram_user_id>")
        return

    if not TOKEN:
        print("Could not read TOKEN from .env")
        return

    chat_id = int(sys.argv[1])
    bot = Bot(token=TOKEN)

    tag_text = f'<tg-emoji emoji-id="{TEST_EMOJI_ID}">{TEST_FALLBACK_EMOJI}</tg-emoji> Mythic'

    print("=== Test 1: send_message, parse_mode='HTML' (string) ===")
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=f"Test 1: {tag_text}",
            parse_mode='HTML',
        )
        print("Sent. message_id =", msg.message_id)
        print("msg.entities =", msg.entities)
        print("msg.text =", repr(msg.text))
    except Exception as e:
        print("FAILED:", repr(e))
    print()

    print("=== Test 2: send_message, parse_mode=ParseMode.HTML (enum) ===")
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=f"Test 2: {tag_text}",
            parse_mode=ParseMode.HTML,
        )
        print("Sent. message_id =", msg.message_id)
        print("msg.entities =", msg.entities)
        print("msg.text =", repr(msg.text))
    except Exception as e:
        print("FAILED:", repr(e))
    print()

    print("=== Test 3: send_photo with caption containing the tag (matches real bot flow) ===")
    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=TEST_PHOTO_URL,
            caption=f"Test 3: {tag_text}",
            parse_mode='HTML',
        )
        print("Sent. message_id =", msg.message_id)
        print("msg.caption_entities =", msg.caption_entities)
        print("msg.caption =", repr(msg.caption))
    except Exception as e:
        print("FAILED:", repr(e))
    print()

    print("Done. Check your DM with the bot for these 3 messages, and paste this full console output.")


if __name__ == "__main__":
    asyncio.run(main())
