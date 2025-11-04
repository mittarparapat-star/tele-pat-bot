import os
import pytz
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ======================
# Load Token from Environment
# ======================
TOKEN = os.getenv("BOT_TOKEN")

# States for ConversationHandler
CHANNEL_NAME, MESSAGE, TIME, DAILY = range(4)

# To store scheduled messages in memory
scheduled_messages = []
default_channel = None


# ======================
# Start Command
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I can schedule messages for your Telegram channel.\n\n"
        "Commands:\n"
        "/setchannel – Set your default channel\n"
        "/list – View scheduled messages\n"
        "/cancel – Cancel all\n\n"
        "Let’s begin — send me your *channel username* (e.g. @mychannel)."
    )
    return CHANNEL_NAME


# ======================
# Get Channel
# ======================
async def get_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global default_channel
    default_channel = update.message.text.strip()
    await update.message.reply_text(f"✅ Channel set to {default_channel}\nNow send me the message text.")
    return MESSAGE


# ======================
# Get Message
# ======================
async def get_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["message"] = update.message.text
    await update.message.reply_text("🕒 When do you want to send it? (Format: HH:MM 24hr)")
    return TIME


# ======================
# Get Time
# ======================
async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        send_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        await update.message.reply_text("⚠️ Invalid time format. Please use HH:MM (24hr).")
        return TIME

    context.user_data["time"] = send_time
    await update.message.reply_text("📆 Do you want to send this *daily*? (yes/no)")
    return DAILY


# ======================
# Daily / One-Time Message
# ======================
async def get_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = context.user_data["message"]
    send_time = context.user_data["time"]
    is_daily = update.message.text.strip().lower().startswith("y")

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    send_datetime = datetime.combine(now.date(), send_time).replace(tzinfo=ist)
    if send_datetime < now:
        send_datetime += timedelta(days=1)

    delay = (send_datetime - now).total_seconds()

    data = {
        "channel": default_channel,
        "msg": msg,
        "time": send_time.strftime("%H:%M"),
        "daily": is_daily,
    }
    scheduled_messages.append(data)

    await update.message.reply_text(
        f"✅ Scheduled message:\n\n"
        f"🗨️ {msg}\n🕒 {send_time.strftime('%H:%M')} IST\n📅 {'Daily' if is_daily else 'Once'}"
    )

    schedule_job(context.application, data, delay)
    return ConversationHandler.END


# ======================
# Schedule Job Function
# ======================
def schedule_job(app, data, delay=None):
    async def send_message(ctx: ContextTypes.DEFAULT_TYPE):
        await ctx.bot.send_message(chat_id=data["channel"], text=data["msg"])
        if data["daily"]:
            # Reschedule for next day
            schedule_job(app, data, delay=24 * 3600)

    # Ensure job_queue exists
    if not app.job_queue:
        from telegram.ext import JobQueue
        job_queue = JobQueue()
        job_queue.set_application(app)
        job_queue.start()
        app.job_queue = job_queue

    app.job_queue.run_once(send_message, when=delay or 1, data=data)


# ======================
# List Scheduled Messages
# ======================
async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not scheduled_messages:
        await update.message.reply_text("📭 No scheduled messages.")
        return
    text = "\n\n".join(
        [f"🗨️ {m['msg']}\n🕒 {m['time']} IST\n📅 {'Daily' if m['daily'] else 'Once'}" for m in scheduled_messages]
    )
    await update.message.reply_text(f"📋 Scheduled Messages:\n\n{text}")


# ======================
# Cancel All
# ======================
async def cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scheduled_messages.clear()
    if context.application.job_queue:
        context.application.job_queue.jobs().clear()
    await update.message.reply_text("❌ All scheduled messages cleared.")


# ======================
# Set Channel Command
# ======================
async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global default_channel
    if context.args:
        default_channel = context.args[0]
        await update.message.reply_text(f"✅ Default channel set to {default_channel}")
    else:
        await update.message.reply_text("Usage: /setchannel @yourchannel")


# ======================
# Main Function
# ======================
def main():
    print("🚀 Starting Telegram Scheduler Bot...")

    app = ApplicationBuilder().token(TOKEN).build()

    # Ensure JobQueue exists
    if not app.job_queue:
        from telegram.ext import JobQueue
        job_queue = JobQueue()
        job_queue.set_application(app)
        job_queue.start()
        app.job_queue = job_queue

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHANNEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel)],
            MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_message)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
            DAILY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_daily)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("list", list_schedules))
    app.add_handler(CommandHandler("cancel", cancel_schedule))
    app.add_handler(CommandHandler("setchannel", set_channel))

    print("🤖 Bot is running 24x7 on Render...")
    app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
