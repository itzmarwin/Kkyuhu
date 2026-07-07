"""
Standalone, minimal test - does NOT use pyrogram/PTB/the bot at all.
Calls Telegram's sendMessage HTTP API directly with a <tg-emoji> HTML tag,
then prints the FULL raw response Telegram sends back.

This tells us definitively whether Telegram is accepting the custom_emoji
entity or silently stripping it - by looking at the "entities" field in
the response.

Run from your project root (so it can read .env for the token):

    python3 tg_emoji_raw_test.py <your_own_telegram_user_id>

You must have started a DM with your bot at least once before running this
(so the bot is allowed to message you).
"""

import sys
import os
import json
import urllib.request
import urllib.parse

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")

# One of the ids you gave earlier - Mythic
TEST_EMOJI_ID = "6224516447905783899"
TEST_FALLBACK_EMOJI = "💠"


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tg_emoji_raw_test.py <your_telegram_user_id>")
        return

    if not TOKEN:
        print("Could not read TOKEN from .env - check the variable name matches what your bot uses.")
        return

    chat_id = sys.argv[1]

    text = f"Testing premium emoji: <tg-emoji emoji-id=\"{TEST_EMOJI_ID}\">{TEST_FALLBACK_EMOJI}</tg-emoji> Mythic"

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data)

    print("Sending raw HTTP request to Telegram...")
    print("Text sent:", text)
    print()

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode()
    except Exception as e:
        print("Request failed:", repr(e))
        return

    parsed = json.loads(body)
    print("FULL RAW RESPONSE FROM TELEGRAM:")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))

    print()
    if parsed.get("ok"):
        entities = parsed["result"].get("entities", [])
        custom_emoji_entities = [e for e in entities if e.get("type") == "custom_emoji"]
        if custom_emoji_entities:
            print("SUCCESS: Telegram accepted the custom_emoji entity:")
            print(custom_emoji_entities)
        else:
            print("Telegram returned entities =", entities)
            print("NO custom_emoji entity in the response - Telegram silently stripped it.")
    else:
        print("Telegram returned an ERROR:", parsed.get("description"))


if __name__ == "__main__":
    main()
