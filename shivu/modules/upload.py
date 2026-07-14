from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, sudo_users, CHARA_CHANNEL_ID, SUPPORT_CHAT
from shivu.database import (
    get_next_sequence_number,
    insert_character,
    get_character,
    delete_character,
    update_character_field,
)
from shivu.cache import all_characters_cache, characters_by_id
from shivu.rarity import format_rarity_plain_html, is_valid_rarity

WRONG_FORMAT_TEXT = """Wrong ❌️ format...  eg. /upload Img_url muzan-kibutsuji Demon-slayer 3

img_url character-name anime-name rarity-number [tag]

use rarity number accordingly rarity Map

rarity_map = 1 (🔵 Common), 2 (🟠 Rare), 3 (🟡 Legendary), 4 (💠 Mythic), 5 (🌌 Astral), 6 (🪽 Seraphic)

[tag] is optional - only needed for event characters (e.g. 🏖 for a summer event). Leave it out for a normal character."""

async def upload(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask My Owner...')
        return

    try:
        args = context.args
        if len(args) not in (4, 5):
            await update.message.reply_text(WRONG_FORMAT_TEXT)
            return

        character_name = args[1].replace('-', ' ').title()
        anime = args[2].replace('-', ' ').title()

        try:
            rarity = int(args[3])
        except ValueError:
            await update.message.reply_text('Invalid rarity. Please use 1, 2, 3, 4, 5, or 6.')
            return

        if not is_valid_rarity(rarity):
            await update.message.reply_text('Invalid rarity. Please use 1, 2, 3, 4, 5, or 6.')
            return
        tag = args[4] if len(args) == 5 else None

        id = await get_next_sequence_number('character_id')

        character = {
            'img_url': args[0],
            'name': character_name,
            'anime': anime,
            'rarity': rarity,
            'id': id
        }
        if tag:
            character['tag'] = tag

        try:
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=args[0],
                caption=f'<b>Character Name:</b> {character_name}\n<b>Anime Name:</b> {anime}\n<b>Rarity:</b> {format_rarity_plain_html(rarity)}\n<b>ID:</b> {id}\nAdded by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                parse_mode='HTML'
            )
            character['message_id'] = message.message_id
            await insert_character(character)
            
            all_characters_cache.append(character)
            characters_by_id[character['id']] = character
            
            await update.message.reply_text('CHARACTER ADDED....')
        except:
            await insert_character(character)
            all_characters_cache.append(character)
            characters_by_id[character['id']] = character
            await update.message.reply_text("Character Added but no Database Channel Found, Consider adding one.")
        
    except Exception as e:
        await update.message.reply_text(f'Character Upload Unsuccessful. Error: {str(e)}\nIf you think this is a source error, forward to: {SUPPORT_CHAT}')

async def delete(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask my Owner to use this Command...')
        return

    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('Incorrect format... Please use: /delete ID')
            return

        try:
            character_id = int(args[0])
        except ValueError:
            await update.message.reply_text('ID ek number hona chahiye.')
            return

        character = await delete_character(character_id)

        if character:
            all_characters_cache[:] = [c for c in all_characters_cache if c['id'] != character_id]
            characters_by_id.pop(character_id, None)
            
            try:
                await context.bot.delete_message(chat_id=CHARA_CHANNEL_ID, message_id=character['message_id'])
            except:
                pass
            
            await update.message.reply_text('DONE')
        else:
            await update.message.reply_text('Character not found in DB.')
    except Exception as e:
        await update.message.reply_text(f'{str(e)}')

async def update(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('You do not have permission to use this command.')
        return

    try:
        args = context.args
        if len(args) != 3:
            await update.message.reply_text('Incorrect format. Please use: /update id field new_value')
            return

        try:
            character_id = int(args[0])
        except ValueError:
            await update.message.reply_text('ID ek number hona chahiye.')
            return

        character = await get_character(character_id)
        if not character:
            await update.message.reply_text('Character not found.')
            return

        valid_fields = ['img_url', 'name', 'anime', 'rarity']
        if args[1] not in valid_fields:
            await update.message.reply_text(f'Invalid field. Please use one of the following: {", ".join(valid_fields)}')
            return

        if args[1] in ['name', 'anime']:
            new_value = args[2].replace('-', ' ').title()
        elif args[1] == 'rarity':
            try:
                new_value = int(args[2])
            except ValueError:
                await update.message.reply_text('Invalid rarity. Please use 1, 2, 3, 4, 5, or 6.')
                return

            if not is_valid_rarity(new_value):
                await update.message.reply_text('Invalid rarity. Please use 1, 2, 3, 4, 5, or 6.')
                return
        else:
            new_value = args[2]

        await update_character_field(character_id, args[1], new_value)

        for i, c in enumerate(all_characters_cache):
            if c['id'] == character_id:
                all_characters_cache[i][args[1]] = new_value
                break
        
        if args[1] == 'img_url':
            try:
                await context.bot.delete_message(chat_id=CHARA_CHANNEL_ID, message_id=character['message_id'])
                message = await context.bot.send_photo(
                    chat_id=CHARA_CHANNEL_ID,
                    photo=new_value,
                    caption=f'<b>Character Name:</b> {character["name"]}\n<b>Anime Name:</b> {character["anime"]}\n<b>Rarity:</b> {format_rarity_plain_html(character["rarity"])}\n<b>ID:</b> {character["id"]}\nUpdated by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                    parse_mode='HTML'
                )
                await update_character_field(character_id, 'message_id', message.message_id)
            except:
                pass
        else:
            try:
                await context.bot.edit_message_caption(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character['message_id'],
                    caption=f'<b>Character Name:</b> {character["name"]}\n<b>Anime Name:</b> {character["anime"]}\n<b>Rarity:</b> {format_rarity_plain_html(character["rarity"] if args[1] != "rarity" else new_value)}\n<b>ID:</b> {character["id"]}\nUpdated by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                    parse_mode='HTML'
                )
            except:
                pass

        await update.message.reply_text('Updated Done in Database and Memory!')
    except Exception as e:
        await update.message.reply_text(f'Failed to update: {str(e)}')

UPLOAD_HANDLER = CommandHandler('upload', upload, block=False)
application.add_handler(UPLOAD_HANDLER)
DELETE_HANDLER = CommandHandler('delete', delete, block=False)
application.add_handler(DELETE_HANDLER)
UPDATE_HANDLER = CommandHandler('update', update, block=False)
application.add_handler(UPDATE_HANDLER)
