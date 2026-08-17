from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, sudo_users, CHARA_CHANNEL_ID, SUPPORT_CHAT
from shivu.database import (
    get_next_sequence_number,
    insert_character,
    get_character,
    delete_character,
    cascade_delete_character_from_users,
    update_character_field,
)
from shivu.cache import all_characters_cache, characters_by_id
from shivu.rarity import format_rarity_plain_html, is_valid_rarity
from shivu.events import is_valid_event, format_event_tag, format_event_footer, list_event_codes

WRONG_FORMAT_TEXT = """Wrong ❌️ format...  eg. /upload Img_url muzan-kibutsuji Demon-slayer 3

img_url character-name anime-name rarity-number [event_code]

use rarity number accordingly rarity Map

rarity_map = 1 (🔵 Common), 2 (🟠 Rare), 3 (🟡 Legendary), 4 (💠 Mythic), 5 (🌌 Astral), 6 (🪽 Seraphic)

[event_code] is optional - only needed for event characters (e.g. valentine). Leave it out for a normal character."""


def _build_channel_caption(character: dict, action_word: str, user) -> str:
    event_code = character.get('event')
    event_tag = format_event_tag(event_code) if event_code else ''
    event_footer = format_event_footer(event_code) if event_code else ''

    caption = (
        f'<b>Character Name:</b> {character["name"]}{event_tag}\n'
        f'<b>Anime Name:</b> {character["anime"]}\n'
        f'<b>Rarity:</b> {format_rarity_plain_html(character["rarity"])}\n'
        f'<b>ID:</b> {character["id"]}\n'
        f'{action_word} <a href="tg://user?id={user.id}">{user.first_name}</a>'
        f'{event_footer}'
    )
    return caption


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

        event_code = args[4] if len(args) == 5 else None
        if event_code and not is_valid_event(event_code):
            available = ', '.join(list_event_codes()) or 'none configured yet'
            await update.message.reply_text(f'Invalid event. Available: {available}')
            return

        id = await get_next_sequence_number('character_id')

        character = {
            'img_url': args[0],
            'name': character_name,
            'anime': anime,
            'rarity': rarity,
            'id': id
        }
        if event_code:
            character['event'] = event_code

        try:
            caption = _build_channel_caption(character, 'Added by', update.effective_user)
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=args[0],
                caption=caption,
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

            affected_count = await cascade_delete_character_from_users(character_id)

            try:
                await context.bot.delete_message(chat_id=CHARA_CHANNEL_ID, message_id=character['message_id'])
            except:
                pass

            if affected_count > 0:
                await update.message.reply_text(
                    f'DONE — Character deleted from the database.\n'
                    f'It was owned by {affected_count} user(s), and has been removed from all of their collections.'
                )
            else:
                await update.message.reply_text('DONE — Character deleted from the database.')
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

        valid_fields = ['img_url', 'name', 'anime', 'rarity', 'event']
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
        elif args[1] == 'event':
            if args[2].lower() in ('none', 'remove', 'clear'):
                new_value = None
            else:
                if not is_valid_event(args[2]):
                    available = ', '.join(list_event_codes()) or 'none configured yet'
                    await update.message.reply_text(f'Invalid event. Available: {available}')
                    return
                new_value = args[2]
        else:
            new_value = args[2]

        await update_character_field(character_id, args[1], new_value)
        character[args[1]] = new_value
        for i, c in enumerate(all_characters_cache):
            if c['id'] == character_id:
                all_characters_cache[i][args[1]] = new_value
                break
        if character_id in characters_by_id:
            characters_by_id[character_id][args[1]] = new_value

        if args[1] == 'img_url':
            try:
                await context.bot.delete_message(chat_id=CHARA_CHANNEL_ID, message_id=character['message_id'])
                caption = _build_channel_caption(character, 'Updated by', update.effective_user)
                message = await context.bot.send_photo(
                    chat_id=CHARA_CHANNEL_ID,
                    photo=new_value,
                    caption=caption,
                    parse_mode='HTML'
                )
                await update_character_field(character_id, 'message_id', message.message_id)
            except:
                pass
        else:
            try:
                caption = _build_channel_caption(character, 'Updated by', update.effective_user)
                await context.bot.edit_message_caption(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character['message_id'],
                    caption=caption,
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
