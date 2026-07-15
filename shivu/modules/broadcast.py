from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from shivu import application, OWNER_ID, LOGGER
from shivu.database import iter_all_group_ids, iter_all_pm_user_ids


async def broadcast(update: Update, context: CallbackContext) -> None:

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    message_to_broadcast = update.message.reply_to_message
    if message_to_broadcast is None:
        await update.message.reply_text("Please reply to a message to broadcast.")
        return

    all_chats = [chat_id async for chat_id in iter_all_group_ids()]
    all_users = [user_id async for user_id in iter_all_pm_user_ids()]
    all_targets = list(set(all_chats + all_users))

    failed_sends = 0
    for chat_id in all_targets:
        try:
            await context.bot.forward_message(chat_id=chat_id,
                                              from_chat_id=message_to_broadcast.chat_id,
                                              message_id=message_to_broadcast.message_id)
        except Exception as e:
            LOGGER.warning("Failed to broadcast to %s: %s", chat_id, e)
            failed_sends += 1

    await update.message.reply_text(f"Broadcast complete. Failed to send to {failed_sends} chats/users.")


application.add_handler(CommandHandler("broadcast", broadcast, block=False))
