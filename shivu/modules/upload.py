import asyncio
import aiohttp
from pymongo import ReturnDocument

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, sudo_users, collection, db, CHARA_CHANNEL_ID, SUPPORT_CHAT
# Tumhara Plan: Memory cache import kar rahe hain
from shivu.__main__ import all_characters_cache, characters_by_id

WRONG_FORMAT_TEXT = """Wrong ❌️ format...  eg. /upload Img_url muzan-kibutsuji Demon-slayer 3

img_url character-name anime-name rarity-number

use rarity number accordingly rarity Map

rarity_map = 1 (⚪️ Common), 2 (🟣 Rare) , 3 (🟡 Legendary), 4 (🟢 Medium), 5 (💮 Special edition)"""

async def get_next_sequence_number(sequence_name):
    sequence_collection = db.sequences
    sequence_document = await sequence_collection.find_one_and_update(
        {'_id': sequence_name}, 
        {'$inc': {'sequence_value': 1}}, 
        return_document=ReturnDocument.AFTER
    )
    if not sequence_document:
        await sequence_collection.insert_one({'_id': sequence_name, 'sequence_value': 0})
        return 0
    return sequence_document['sequence_value']

async def check_url(url):
    """
    Async URL validator to prevent blocking.
    Returns (True, None) if reachable, (False, reason) otherwise.

    FIX: pehle HEAD request use hota tha -- kaafi image-hosts (graph.org/telegra.ph
    samet) HEAD ko GET jaisa reliably handle nahi karte, aur bina User-Agent ke
    kuch hosts non-browser client ko block/misbehave kar dete hain. Ab GET +
    browser-like User-Agent use karte hain. Reason bhi return karte hain ab,
    taaki 'Invalid URL' ke saath asli wajah (404, timeout, etc.) bhi dikh sake.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return True, None
                return False, f'server returned status {response.status}'
    except asyncio.TimeoutError:
        return False, 'request timed out'
    except Exception as e:
        return False, str(e)

async def upload(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask My Owner...')
        return

    try:
        args = context.args
        if len(args) != 4:
            await update.message.reply_text(WRONG_FORMAT_TEXT)
            return

        character_name = args[1].replace('-', ' ').title()
        anime = args[2].replace('-', ' ').title()

        # Aiohttp use karke URL check (Non-blocking)
        is_valid_url, invalid_reason = await check_url(args[0])
        if not is_valid_url:
            await update.message.reply_text(f'Invalid URL. ({invalid_reason})')
            return

        rarity_map = {1: "⚪ Common", 2: "🟣 Rare", 3: "🟡 Legendary", 4: "🟢 Medium", 5: "💮 Special edition"}
        try:
            rarity = rarity_map[int(args[3])]
        except KeyError:
            await update.message.reply_text('Invalid rarity. Please use 1, 2, 3, 4, or 5.')
            return

        # FIX: ab plain integer (pehle str().zfill(2) tha -- 100+ IDs pe same-anime ke andar
        # sort order todh deta, kyunki "100" string-compare mein "99" se PEHLE aa jaata hai)
        id = await get_next_sequence_number('character_id')

        character = {
            'img_url': args[0],
            'name': character_name,
            'anime': anime,
            'rarity': rarity,
            'id': id
        }

        try:
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=args[0],
                caption=f'<b>Character Name:</b> {character_name}\n<b>Anime Name:</b> {anime}\n<b>Rarity:</b> {rarity}\n<b>ID:</b> {id}\nAdded by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                parse_mode='HTML'
            )
            character['message_id'] = message.message_id
            await collection.insert_one(character)
            
            # Memory cache update -- dono containers ek hi object ko refer karte hain
            all_characters_cache.append(character)
            characters_by_id[character['id']] = character
            
            await update.message.reply_text('CHARACTER ADDED....')
        except:
            await collection.insert_one(character)
            all_characters_cache.append(character)
            characters_by_id[character['id']] = character
            await update.effective_message.reply_text("Character Added but no Database Channel Found, Consider adding one.")
        
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

        character = await collection.find_one_and_delete({'id': character_id})

        if character:
            # FIX: in-place mutation (rebind nahi karte) -- taaki __main__.py jaisa doosra
            # module isी list-object ko dekhta rahe, stale/purani copy pe na atke
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

        character = await collection.find_one({'id': character_id})
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
            rarity_map = {1: "⚪ Common", 2: "🟣 Rare", 3: "🟡 Legendary", 4: "🟢 Medium", 5: "💮 Special edition"}
            try:
                new_value = rarity_map[int(args[2])]
            except KeyError:
                await update.message.reply_text('Invalid rarity. Please use 1, 2, 3, 4, or 5.')
                return
        else:
            new_value = args[2]

        await collection.find_one_and_update({'id': character_id}, {'$set': {args[1]: new_value}})

        # Memory cache update -- all_characters_cache[i] aur characters_by_id[character_id]
        # dono SAME dict-object ko refer karte hain (load ke waqt ek hi object dono
        # containers mein gaya tha), isliye sirf yahan mutate karna kaafi hai; characters_by_id
        # se padhne par ye change turant khud-ba-khud dikhega, alag se sync nahi karna padta.
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
                    caption=f'<b>Character Name:</b> {character["name"]}\n<b>Anime Name:</b> {character["anime"]}\n<b>Rarity:</b> {character["rarity"]}\n<b>ID:</b> {character["id"]}\nUpdated by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                    parse_mode='HTML'
                )
                await collection.find_one_and_update({'id': character_id}, {'$set': {'message_id': message.message_id}})
            except:
                pass
        else:
            try:
                await context.bot.edit_message_caption(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character['message_id'],
                    caption=f'<b>Character Name:</b> {character["name"]}\n<b>Anime Name:</b> {character["anime"]}\n<b>Rarity:</b> {character["rarity"]}\n<b>ID:</b> {character["id"]}\nUpdated by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
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
