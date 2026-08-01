from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, sudo_users
from shivu.database import grant_character_to_user
from shivu.cache import characters_by_id


async def give(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask My Owner...')
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("You need to reply to a user's message to give them a character!")
        return

    target_user = update.message.reply_to_message.from_user

    if not target_user or target_user.is_bot:
        await update.message.reply_text("You can't give a character to a bot!")
        return

    if len(context.args) != 1:
        await update.message.reply_text('Please use: /give character_id (reply to the user)')
        return

    try:
        character_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text('Character ID must be a number!')
        return

    if character_id not in characters_by_id:
        await update.message.reply_text('This character ID does not exist.')
        return

    character = characters_by_id[character_id]

    await grant_character_to_user(
        target_user.id, character_id,
        target_user.username, target_user.first_name,
        is_new_catch=False,
    )

    await update.message.reply_text(
        f'Gave <b>{escape(character["name"])}</b> to '
        f'<a href="tg://user?id={target_user.id}">{escape(target_user.first_name)}</a>!',
        parse_mode='HTML',
    )


application.add_handler(CommandHandler('give', give, block=False))
