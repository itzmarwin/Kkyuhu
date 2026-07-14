import random
from html import escape 

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from shivu import application, PHOTO_URL, SUPPORT_CHAT, UPDATE_CHAT, BOT_USERNAME, GROUP_ID
from shivu.database import sync_pm_user
from shivu.cache import started_users_cache


async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username

    is_new_user = await sync_pm_user(user_id, first_name, username)

    if is_new_user:
        started_users_cache.add(user_id)

        await context.bot.send_message(chat_id=GROUP_ID,
                                       text=f"New user Started The Bot..\n User: <a href='tg://user?id={user_id}'>{escape(first_name)}</a>",
                                       parse_mode='HTML')

    

    if update.effective_chat.type== "private":
        
        
        caption = f"""
<tg-emoji emoji-id="5846154572434772316">🙋‍♀️</tg-emoji><b>✨ Welcome to Character Grabber!</b>
━━━━━━━━━━━━━━━━━━━━━━

<tg-emoji emoji-id="5850203446694646751">✨</tg-emoji>Every message brings the next character.
<tg-emoji emoji-id="5850203446694646751">✨</tg-emoji>Every guess expands your collection.
<tg-emoji emoji-id="5850203446694646751">✨</tg-emoji>Every rarity brings a new challenge.

<tg-emoji emoji-id="5845736169605698028">🥳</tg-emoji><b>Add me to your group and start your journey today!</b>
        """
        
        keyboard = [
            [InlineKeyboardButton("Add Me In Your Group", url=f'http://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("Help And Commands", callback_data='help')],
            [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'),
            InlineKeyboardButton("Updates", url=f'https://t.me/{UPDATE_CHAT}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        photo_url = random.choice(PHOTO_URL)

        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')

    else:
        photo_url = random.choice(PHOTO_URL)
        keyboard = [
            [InlineKeyboardButton("Add Me In Your Group", url=f'http://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("Help and Commands", callback_data='help')],
            [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'),
            InlineKeyboardButton("Updates", url=f'https://t.me/{UPDATE_CHAT}')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_url, caption="<b>Looking for more?</b>\n\nEverything you need is waiting in my private chat.", reply_markup=reply_markup, parse_mode='HTML')

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'help':
        help_text = """
<b>❖ Character Commands</b>

/guess - Catch the spawned character. (Groups only)
/collection - View your character collection.
/fav - Set a character as your favorite.
/gift - Gift a character to another collector. (Groups only)
/trade - Trade characters with another collector.

/topusers - View the Global Top Collectors.
/ctop - View this Group's Top Collectors.
/topgroups - View the Global Top Groups.

/changetime - Change the character spawn interval. (Admins only).
   """
        help_keyboard = [[InlineKeyboardButton("Bᴀᴄᴋ", callback_data='back')]]
        reply_markup = InlineKeyboardMarkup(help_keyboard)
        
        await context.bot.edit_message_caption(chat_id=update.effective_chat.id, message_id=query.message.message_id, caption=help_text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data == 'back':

        caption = f"""
<tg-emoji emoji-id="5846154572434772316">🙋‍♀️</tg-emoji><b>✨ Welcome to Character Grabber!</b>
━━━━━━━━━━━━━━━━━━━━━━

<tg-emoji emoji-id="5850203446694646751">✨</tg-emoji>Every message brings the next character.
<tg-emoji emoji-id="5850203446694646751">✨</tg-emoji>Every guess expands your collection.
<tg-emoji emoji-id="5850203446694646751">✨</tg-emoji>Every rarity brings a new challenge.

<tg-emoji emoji-id="5845736169605698028">🥳</tg-emoji><b>Add me to your group and start your journey today!</b>
        """

        
        keyboard = [
            [InlineKeyboardButton("Add Me In Your Group", url=f'http://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("Help And Commands", callback_data='help')],
            [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'),
            InlineKeyboardButton("Updates", url=f'https://t.me/{UPDATE_CHAT}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.edit_message_caption(chat_id=update.effective_chat.id, message_id=query.message.message_id, caption=caption, reply_markup=reply_markup, parse_mode='HTML')


application.add_handler(CallbackQueryHandler(button, pattern='^help$|^back$', block=False))
start_handler = CommandHandler('start', start, block=False)
application.add_handler(start_handler)
