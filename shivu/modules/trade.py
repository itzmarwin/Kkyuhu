from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from shivu import user_collection, shivuu

pending_trades = {}

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

    sender_character_id, receiver_character_id = message.command[1], message.command[2]

    # OPTIMIZATION: Sirf wahi character fetch karo jo trade hone wala hai, poora array mat lo
    sender_char_doc = await user_collection.find_one(
        {'id': sender_id, 'characters.id': sender_character_id},
        {'characters.$': 1}
    )
    if not sender_char_doc:
        await message.reply_text("You don't have the character you're trying to trade!")
        return

    receiver_char_doc = await user_collection.find_one(
        {'id': receiver_id, 'characters.id': receiver_character_id},
        {'characters.$': 1}
    )
    if not receiver_char_doc:
        await message.reply_text("The other user doesn't have the character they are trying to trade!")
        return

    # Store actual character objects to avoid DB calls later on confirm
    sender_character = sender_char_doc['characters'][0]
    receiver_character = receiver_char_doc['characters'][0]

    pending_trades[(sender_id, receiver_id)] = (sender_character, receiver_character)

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Trade", callback_data="confirm_trade")],
            [InlineKeyboardButton("Cancel Trade", callback_data="cancel_trade")]
        ]
    )

    await message.reply_text(f"{message.reply_to_message.from_user.mention}, do you accept this trade?", reply_markup=keyboard)


@shivuu.on_callback_query(filters.create(lambda _, __, query: query.data in ["confirm_trade", "cancel_trade"]))
async def on_trade_callback(client, callback_query):
    receiver_id = callback_query.from_user.id

    trade_info = None
    sender_id = None
    for (s_id, r_id), trade_data in pending_trades.items():
        if r_id == receiver_id:
            trade_info = trade_data
            sender_id = s_id
            break
    
    if not trade_info:
        await callback_query.answer("This is not for you!", show_alert=True)
        return

    if callback_query.data == "confirm_trade":
        sender_character, receiver_character = trade_info

        # Double check if both still have the characters (in case they traded/gifted away meanwhile)
        sender_check = await user_collection.count_documents({'id': sender_id, 'characters.id': sender_character['id']})
        receiver_check = await user_collection.count_documents({'id': receiver_id, 'characters.id': receiver_character['id']})

        if not sender_check or not receiver_check:
            del pending_trades[(sender_id, receiver_id)]
            await callback_query.message.edit_text("❌ Trade failed! Someone no longer has the character.")
            return

        # ATOMIC OPERATIONS: $pull to remove, $push to add. No array overwriting!
        await user_collection.update_one(
            {'id': sender_id},
            {'$pull': {'characters': {'id': sender_character['id']}}}
        )
        await user_collection.update_one(
            {'id': receiver_id},
            {'$pull': {'characters': {'id': receiver_character['id']}}}
        )

        await user_collection.update_one(
            {'id': sender_id},
            {'$push': {'characters': receiver_character}}
        )
        await user_collection.update_one(
            {'id': receiver_id},
            {'$push': {'characters': sender_character}}
        )

        del pending_trades[(sender_id, receiver_id)]
        
        # Edit message text directly without relying on reply_to_message
        await callback_query.message.edit_text(f"✅ Trade successful! {callback_query.from_user.mention} and the other user have exchanged characters.")

    elif callback_query.data == "cancel_trade":
        del pending_trades[(sender_id, receiver_id)]
        await callback_query.message.edit_text("❌️ Sad Cancelled....")


pending_gifts = {}

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

    character_id = message.command[1]

    # Fetch only the specific character instead of the whole array
    char_doc = await user_collection.find_one(
        {'id': sender_id, 'characters.id': character_id},
        {'characters.$': 1}
    )
    
    if not char_doc:
        await message.reply_text("You don't have this character in your collection!")
        return

    character = char_doc['characters'][0]

    pending_gifts[(sender_id, receiver_id)] = {
        'character': character,
        'receiver_username': receiver_username,
        'receiver_first_name': receiver_first_name
    }

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Gift", callback_data="confirm_gift")],
            [InlineKeyboardButton("Cancel Gift", callback_data="cancel_gift")]
        ]
    )

    await message.reply_text(f"Do You Really Want To Gift {message.reply_to_message.from_user.mention} ?", reply_markup=keyboard)


@shivuu.on_callback_query(filters.create(lambda _, __, query: query.data in ["confirm_gift", "cancel_gift"]))
async def on_gift_callback(client, callback_query):
    sender_id = callback_query.from_user.id

    gift_info = None
    receiver_id = None
    for (s_id, r_id), gift_data in pending_gifts.items():
        if s_id == sender_id:
            gift_info = gift_data
            receiver_id = r_id
            break

    if not gift_info:
        await callback_query.answer("This is not for you!", show_alert=True)
        return

    if callback_query.data == "confirm_gift":
        character = gift_info['character']

        # Verify sender still has it
        sender_check = await user_collection.count_documents({'id': sender_id, 'characters.id': character['id']})
        if not sender_check:
            del pending_gifts[(sender_id, receiver_id)]
            await callback_query.message.edit_text("❌ Gift failed! You no longer have this character.")
            return

        # ATOMIC: $pull from sender
        await user_collection.update_one(
            {'id': sender_id},
            {'$pull': {'characters': {'id': character['id']}}}
        )

        # ATOMIC: $push to receiver (or create new user)
        receiver = await user_collection.find_one({'id': receiver_id})
        if receiver:
            await user_collection.update_one(
                {'id': receiver_id},
                {'$push': {'characters': character}}
            )
        else:
            await user_collection.insert_one({
                'id': receiver_id,
                'username': gift_info['receiver_username'],
                'first_name': gift_info['receiver_first_name'],
                'characters': [character],
            })

        del pending_gifts[(sender_id, receiver_id)]
        await callback_query.message.edit_text(f"✅ You have successfully gifted your character to [{gift_info['receiver_first_name']}](tg://user?id={receiver_id})!")

    elif callback_query.data == "cancel_gift":
        del pending_gifts[(sender_id, receiver_id)]
        await callback_query.message.edit_text("❌️ Gift Cancelled....")
