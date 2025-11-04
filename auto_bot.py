import asyncio
from datetime import datetime, timedelta
import pytz
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import nest_asyncio

# Apply nest_asyncio for Render compatibility
nest_asyncio.apply()

# --- SETTINGS ---
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHANNEL_ID = "@your_channel_id"  # e.g. @myupdateschannel
IST = pytz.timezone("Asia/Kolkata")

# Conversation states
WAITING_FOR_MESSAGE, WAITING_FOR_TIME = range(2)


# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me the message you want to schedule:")
    return WAITING_FOR_MESSAGE


# Receive message to send later
async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["message_to_send"] = update.message.text
    await update.message.reply_text("Now send the time(s) (e.g., 08:00, 09:00, 14:30):")
    return WAITING_FOR_TIME


# Receive time(s) and schedule jobs
async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    times_input = update.message.text
    msg = context.user_data.get("message_to_send")

    if not msg:
        await update.message.reply_text("Error: No message found. Please start again with /start.")
        return ConversationHandler.END

    times = [t.strip() for t in times_input.split(",")]

    for t in times:
        try:
            hour, minute = map(int, t.split(":"))
            now = datetime.now(IST)
            scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if scheduled_time < now:
                scheduled_time += timedelta(days=1)

            delay = (scheduled_time - now).total_seconds()
            context.job_queue.run_once(send_scheduled_message, when=delay, data=msg)

            await update.message.reply_text(f"✅ Message scheduled for {t} IST")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Invalid time format: {t}. Use HH:MM (e.g., 09:00)")

    return ConversationHandler.END


# Send message to channel
async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data
    await context.bot.send_message(chat_id=CHANNEL_ID, text=msg)


# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Scheduling cancelled.")
    return ConversationHandler.END


# Main function
async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message)],
            WAITING_FOR_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    await application.initialize()
    await application.start()
    print("🚀 Bot running on Render...")
    await application.updater.start_polling()
    await asyncio.Event().wait()  # keep alive


# Safe startup for Render
if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
