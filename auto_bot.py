from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)
import datetime, pytz, json, os, asyncio
###temp solution###
import threading, http.server, socketserver

def keep_alive_server():
    port = int(os.environ.get("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"⚡ Keep-alive server running on port {port}")
        httpd.serve_forever()

threading.Thread(target=keep_alive_server, daemon=True).start()


##end tem sol##
# --- Secure Bot Token ---
TOKEN = os.getenv("BOT_TOKEN")  # Set in Render Environment Variables
IST = pytz.timezone("Asia/Kolkata")

# --- Constants ---
CHANNEL_NAME, MESSAGE, TIME, DAILY, ADD_MORE = range(5)
SCHEDULE_FILE = "scheduled.json"
CONFIG_FILE = "config.json"

# --- Load / Save Data ---
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

# --- Conversation Flow ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "channel" in config:
        await update.message.reply_text(
            f"✅ Using saved channel: {config['channel']}\nNow send me the message (text, image, gif, video, sticker, poll, doc, etc):"
        )
        context.user_data["channel"] = config["channel"]
        context.user_data["messages"] = []
        return MESSAGE
    else:
        await update.message.reply_text("Hi! 👋 Please enter your channel username or ID (e.g. @mychannel or -100xxxx):")
        return CHANNEL_NAME

async def get_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = update.message.text.strip()
    config["channel"] = channel
    save_config()
    context.user_data["channel"] = channel
    context.user_data["messages"] = []
    await update.message.reply_text(f"✅ Channel saved as {channel}\nNow send me the message to post:")
    return MESSAGE

async def get_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    msg_data = None

    if msg.text:
        msg_data = {"type": "text", "content": msg.text}
    elif msg.photo:
        msg_data = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    elif msg.video:
        msg_data = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
    elif msg.animation:
        msg_data = {"type": "animation", "file_id": msg.animation.file_id, "caption": msg.caption or ""}
    elif msg.document:
        msg_data = {"type": "document", "file_id": msg.document.file_id, "caption": msg.caption or ""}
    elif msg.sticker:
        msg_data = {"type": "sticker", "file_id": msg.sticker.file_id}
    elif msg.poll:
        msg_data = {
            "type": "poll",
            "question": msg.poll.question,
            "options": [o.text for o in msg.poll.options],
            "is_anonymous": msg.poll.is_anonymous,
            "allows_multiple_answers": msg.poll.allows_multiple_answers,
        }
    else:
        await msg.reply_text("⚠️ Unsupported message type. Try text, photo, video, gif, doc, sticker, or poll.")
        return MESSAGE

    context.user_data["messages"].append(msg_data)
    await msg.reply_text("✅ Message added.\nSend another message for the same schedule or type 'done' to continue:")
    return ADD_MORE

async def add_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.lower() == "done":
        await update.message.reply_text("⏰ Now send the time(s) (HH:MM, 24hr IST). You can give multiple times separated by commas:")
        return TIME
    return await get_message(update, context)

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
            "messages": data["messages"],
            "time": t.strftime("%H:%M"),
            "daily": daily,
        }
        scheduled_messages.append(job_data)
        schedule_job(context.application, job_data)
    save_schedules()
    await update.message.reply_text(f"✅ Scheduled for {', '.join([t.strftime('%H:%M') for t in data['times']])} IST {'(daily)' if daily else ''}")
    return ConversationHandler.END

# --- Scheduler ---
def schedule_job(app, job):
    now = datetime.datetime.now(IST)
    msg_time = datetime.datetime.strptime(job["time"], "%H:%M").time()
    send_time = now.replace(hour=msg_time.hour, minute=msg_time.minute, second=0, microsecond=0)
    if send_time < now:
        send_time += datetime.timedelta(days=1)
    delay = (send_time - now).total_seconds()
    app.job_queue.run_once(send_scheduled_message, when=delay, data=job)

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job.data
    bot = context.bot
    try:
        for m in job["messages"]:
            t = m["type"]
            if t == "text":
                await bot.send_message(job["channel"], m["content"])
            elif t == "photo":
                await bot.send_photo(job["channel"], m["file_id"], caption=m.get("caption", ""))
            elif t == "video":
                await bot.send_video(job["channel"], m["file_id"], caption=m.get("caption", ""))
            elif t == "animation":
                await bot.send_animation(job["channel"], m["file_id"], caption=m.get("caption", ""))
            elif t == "document":
                await bot.send_document(job["channel"], m["file_id"], caption=m.get("caption", ""))
            elif t == "sticker":
                await bot.send_sticker(job["channel"], m["file_id"])
            elif t == "poll":
                await bot.send_poll(
                    job["channel"],
                    question=m["question"],
                    options=m["options"],
                    is_anonymous=m["is_anonymous"],
                    allows_multiple_answers=m["allows_multiple_answers"],
                )
        print(f"✅ Sent scheduled messages to {job['channel']} at {job['time']}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")

    if job["daily"]:
        context.job_queue.run_once(send_scheduled_message, when=24*3600, data=job)

# --- Commands ---
async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not scheduled_messages:
        await update.message.reply_text("📭 No scheduled messages.")
        return
    msg = "🗓️ *Scheduled Messages:*\n\n"
    for i, s in enumerate(scheduled_messages, start=1):
        msg += f"{i}. 🕒 {s['time']} | {'Daily' if s['daily'] else 'One-time'} | {s['channel']}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /cancel <schedule_number>")
        return
    try:
        index = int(context.args[0]) - 1
        if 0 <= index < len(scheduled_messages):
            removed = scheduled_messages.pop(index)
            save_schedules()
            await update.message.reply_text(f"🗑️ Canceled schedule for {removed['time']} on {removed['channel']}")
        else:
            await update.message.reply_text("⚠️ Invalid number.")
    except ValueError:
        await update.message.reply_text("Usage: /cancel <schedule_number>")

async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        channel = context.args[0]
        config["channel"] = channel
        save_config()
        await update.message.reply_text(f"✅ Default channel updated to: {channel}")
    else:
        await update.message.reply_text("Usage: /setchannel <@channelusername> or <-100id>")

# --- Main ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHANNEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel)],
            MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, get_message)],
            ADD_MORE: [MessageHandler(filters.ALL & ~filters.COMMAND, add_more)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
            DAILY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_daily)],
        },
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("list", list_schedules))
    app.add_handler(CommandHandler("cancel", cancel_schedule))
    app.add_handler(CommandHandler("setchannel", set_channel))

    # reload all scheduled jobs
    for s in scheduled_messages:
        schedule_job(app, s)

    app.run_polling()

if __name__ == "__main__":
    main()


