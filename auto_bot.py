from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)
import datetime
import pytz
import json
import os

TOKEN = os.getenv("BOT_TOKEN")  # Replace with your bot token
IST = pytz.timezone("Asia/Kolkata")

CHANNEL_NAME, MESSAGE, TIME, DAILY = range(4)
SCHEDULE_FILE = "scheduled.json"
CONFIG_FILE = "config.json"

# ---------------- Load / Save Data ----------------
if os.path.exists(SCHEDULE_FILE):
    with open(SCHEDULE_FILE, "r") as f:
        scheduled_messages = json.load(f)
else:
    scheduled_messages = []

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = {}

def save_schedules():
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(scheduled_messages, f, indent=4, default=str)

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# ---------------- Conversation ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "channel" in config:
        await update.message.reply_text(
            f"✅ Using saved channel: {config['channel']}\nNow send me the message to post (text/photo/doc/sticker/link/emoji):"
        )
        context.user_data["channel"] = config["channel"]
        return MESSAGE
    else:
        await update.message.reply_text("Hi! 👋 Please enter your channel username or ID (e.g. @mychannel or -100xxxx):")
        return CHANNEL_NAME

async def get_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = update.message.text.strip()
    config["channel"] = channel
    save_config()
    context.user_data["channel"] = channel
    await update.message.reply_text(f"✅ Channel saved as {channel}\nNow send me the message to post:")
    return MESSAGE

async def get_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text:
        context.user_data["msg_type"] = "text"
        context.user_data["content"] = msg.text
    elif msg.photo:
        context.user_data["msg_type"] = "photo"
        context.user_data["content"] = msg.photo[-1].file_id
        context.user_data["caption"] = msg.caption or ""
    else:
        await msg.reply_text("⚠️ Unsupported message type. Send text or photo.")
        return MESSAGE

    await msg.reply_text("⏰ Great! Now send the time(s) (HH:MM, 24hr IST). You can give multiple times separated by commas:")
    return TIME

async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    times_text = update.message.text
    try:
        times = [datetime.datetime.strptime(t.strip(), "%H:%M").time() for t in times_text.split(",")]
        context.user_data["times"] = times
        await update.message.reply_text("📅 Do you want this to repeat daily? (yes/no)")
        return DAILY
    except ValueError:
        await update.message.reply_text("⚠️ Invalid format! Use HH:MM or multiple like 09:00,13:30,20:00")
        return TIME

async def get_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    daily = update.message.text.lower() in ["yes", "y"]
    data = context.user_data
    for t in data["times"]:
        job_data = {
            "channel": data["channel"],
            "msg_type": data["msg_type"],
            "content": data["content"],
            "caption": data.get("caption", ""),
            "time": t.strftime("%H:%M"),
            "daily": daily,
        }
        scheduled_messages.append(job_data)
        schedule_job(context.application, job_data)
    save_schedules()
    await update.message.reply_text(f"✅ Message scheduled for {', '.join([t.strftime('%H:%M') for t in data['times']])} IST {'(daily)' if daily else ''}!")
    return ConversationHandler.END

# ---------------- Scheduler ----------------
def schedule_job(app, msg):
    now = datetime.datetime.now(IST)
    msg_time = datetime.datetime.strptime(msg["time"], "%H:%M").time()
    send_time = now.replace(hour=msg_time.hour, minute=msg_time.minute, second=0, microsecond=0)
    if send_time < now:
        send_time += datetime.timedelta(days=1)
    delay = (send_time - now).total_seconds()

    app.job_queue.run_once(send_scheduled_message, when=delay, data=msg)

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data
    try:
        if msg["msg_type"] == "text":
            await context.bot.send_message(msg["channel"], msg["content"])
        elif msg["msg_type"] == "photo":
            await context.bot.send_photo(msg["channel"], msg["content"], caption=msg["caption"])
        print(f"✅ Sent message to {msg['channel']} at {msg['time']}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")

    if msg["daily"]:
        context.job_queue.run_once(send_scheduled_message, when=24*3600, data=msg)

# ---------------- Commands ----------------
async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not scheduled_messages:
        await update.message.reply_text("📭 No scheduled messages.")
        return
    msg = "🗓️ *Scheduled Messages:*\n\n"
    for i, s in enumerate(scheduled_messages, start=1):
        msg += f"{i}. 🕒 {s['time']} | {'Daily' if s['daily'] else 'One-time'} | {s['channel']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        index = int(context.args[0]) - 1
        if 0 <= index < len(scheduled_messages):
            removed = scheduled_messages.pop(index)
            save_schedules()
            await update.message.reply_text(f"🗑️ Canceled schedule for {removed['time']} on {removed['channel']}")
        else:
            await update.message.reply_text("⚠️ Invalid schedule number.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /cancel <schedule_number>")

async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        channel = context.args[0]
        config["channel"] = channel
        save_config()
        await update.message.reply_text(f"✅ Default channel updated to: {channel}")
    else:
        await update.message.reply_text("Usage: /setchannel <@channelusername> or <-100id>")

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHANNEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel)],
            MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, get_message)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
            DAILY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_daily)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("list", list_schedules))
    app.add_handler(CommandHandler("cancel", cancel_schedule))
    app.add_handler(CommandHandler("setchannel", set_channel))

    for s in scheduled_messages:
        schedule_job(app, s)

    app.run_polling()

if __name__ == "__main__":
    main()

