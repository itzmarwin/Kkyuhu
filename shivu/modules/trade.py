import asyncio
import itertools

from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from shivu import shivuu
from shivu.database import grant_character_to_user, remove_character_from_user, user_has_character

pending_trades = {}
_trade_id_counter = itertools.count(1)

@shivuu.on_message(filters.command("trade"))
async def trade(client, message):
    sender_id = message.from_user.id

    if not message.reply_to_message:
        await message.reply_text("You need to reply to a user's message to trade a character!")
        return

    if not message.reply_to_message.from_user:
        await message.reply_text("You can't trade with an unknown user!")
        return

    receiver_id = message.reply_to_message.from_user.id

    if sender_id == receiver_id:
        await message.reply_text("You can't trade a character with yourself!")
        return

    if len(message.command) != 3:
        await message.reply_text("You need to provide two character IDs! /trade your_id their_id")
        return

    try:
        sender_character_id = int(message.command[1])
        receiver_character_id = int(message.command[2])
    except ValueError:
        await message.reply_text("Character IDs must be numbers!")
        return

    if not await user_has_character(sender_id, sender_character_id):
        await message.reply_text("You don't have the character you're trying to trade!")
        return

    if not await user_has_character(receiver_id, receiver_character_id):
        await message.reply_text("The other user doesn't have the character they are trying to trade!")
        return

    trade_id = next(_trade_id_counter)
    pending_trades[trade_id] = {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'sender_character_id': sender_character_id,
        'receiver_character_id': receiver_character_id,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Trade", callback_data=f"confirm_trade:{trade_id}")],
            [InlineKeyboardButton("Cancel Trade", callback_data=f"cancel_trade:{trade_id}")]
        ]
    )

    await message.reply_text(f"{message.reply_to_message.from_user.mention}, do you accept this trade?", reply_markup=keyboard)


@shivuu.on_callback_query(filters.create(lambda _, __, query: query.data.startswith("confirm_trade:") or query.data.startswith("cancel_trade:")))
async def on_trade_callback(client, callback_query):
    action, _, trade_id_str = callback_query.data.partition(':')
    try:
        trade_id = int(trade_id_str)
    except ValueError:
        await callback_query.answer("This trade offer is no longer valid.", show_alert=True)
        return

    trade_info = pending_trades.get(trade_id)
    if not trade_info:
        await callback_query.answer("This trade offer is no longer valid.", show_alert=True)
        return

    if callback_query.from_user.id != trade_info['receiver_id']:
        await callback_query.answer("This is not for you!", show_alert=True)
        return

    sender_id = trade_info['sender_id']
    receiver_id = trade_info['receiver_id']
    sender_character_id = trade_info['sender_character_id']
    receiver_character_id = trade_info['receiver_character_id']

    if action == "confirm_trade":
        sender_check, receiver_check = await asyncio.gather(
            user_has_character(sender_id, sender_character_id),
            user_has_character(receiver_id, receiver_character_id),
        )

        if not sender_check or not receiver_check:
            del pending_trades[trade_id]
            await callback_query.message.edit_text("❌ Trade failed! Someone no longer has the character.")
            return

        await asyncio.gather(
            remove_character_from_user(sender_id, sender_character_id),
            remove_character_from_user(receiver_id, receiver_character_id),
            grant_character_to_user(sender_id, receiver_character_id),
            grant_character_to_user(receiver_id, sender_character_id),
        )

        del pending_trades[trade_id]
        
        await callback_query.message.edit_text(f"✅ Trade successful! {callback_query.from_user.mention} and the other user have exchanged characters.")

    else:
        del pending_trades[trade_id]
        await callback_query.message.edit_text("❌️ Sad Cancelled....")


pending_gifts = {}
_gift_id_counter = itertools.count(1)

@shivuu.on_message(filters.command("gift"))
async def gift(client, message):
    sender_id = message.from_user.id

    if not message.reply_to_message:
        await message.reply_text("You need to reply to a user's message to gift a character!")
        return

    if not message.reply_to_message.from_user:
        await message.reply_text("You can't gift to an unknown user!")
        return

    receiver_id = message.reply_to_message.from_user.id
    receiver_username = message.reply_to_message.from_user.username
    receiver_first_name = message.reply_to_message.from_user.first_name

    if sender_id == receiver_id:
        await message.reply_text("You can't gift a character to yourself!")
        return

    if len(message.command) != 2:
        await message.reply_text("You need to provide a character ID! /gift character_id")
        return

    try:
        character_id = int(message.command[1])
    except ValueError:
        await message.reply_text("Character ID must be a number!")
        return

    if not await user_has_character(sender_id, character_id):
        await message.reply_text("You don't have this character in your collection!")
        return

    gift_id = next(_gift_id_counter)
    pending_gifts[gift_id] = {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'character_id': character_id,
        'receiver_username': receiver_username,
        'receiver_first_name': receiver_first_name,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Gift", callback_data=f"confirm_gift:{gift_id}")],
            [InlineKeyboardButton("Cancel Gift", callback_data=f"cancel_gift:{gift_id}")]
        ]
    )

    await message.reply_text(f"Do You Really Want To Gift {message.reply_to_message.from_user.mention} ?", reply_markup=keyboard)


@shivuu.on_callback_query(filters.create(lambda _, __, query: query.data.startswith("confirm_gift:") or query.data.startswith("cancel_gift:")))
async def on_gift_callback(client, callback_query):
    action, _, gift_id_str = callback_query.data.partition(':')
    try:
        gift_id = int(gift_id_str)
    except ValueError:
        await callback_query.answer("This gift offer is no longer valid.", show_alert=True)
        return

    gift_info = pending_gifts.get(gift_id)
    if not gift_info:
        await callback_query.answer("This gift offer is no longer valid.", show_alert=True)
        return

    if callback_query.from_user.id != gift_info['sender_id']:
        await callback_query.answer("This is not for you!", show_alert=True)
        return

    sender_id = gift_info['sender_id']
    receiver_id = gift_info['receiver_id']
    character_id = gift_info['character_id']

    if action == "confirm_gift":
        sender_check = await user_has_character(sender_id, character_id)
        if not sender_check:
            del pending_gifts[gift_id]
            await callback_query.message.edit_text("❌ Gift failed! You no longer have this character.")
            return

        await asyncio.gather(
            remove_character_from_user(sender_id, character_id),
            grant_character_to_user(
                receiver_id, character_id,
                gift_info['receiver_username'], gift_info['receiver_first_name'],
            ),
        )

        del pending_gifts[gift_id]
        await callback_query.message.edit_text(f"✅ You have successfully gifted your character to [{gift_info['receiver_first_name']}](tg://user?id={receiver_id})!")

    else:
        del pending_gifts[gift_id]
        await callback_query.message.edit_text("❌️ Gift Cancelled....")
