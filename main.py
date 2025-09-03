import os
import time
import secrets
import telebot
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://xxx-etbu.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Admin IDs list (add your Telegram user_id here)
ADMIN_IDS = [7357160729,7810231866]  # apna Telegram user_id daalna

# Temporary store: token -> {file_id, expiry}
video_store = {}
TOKEN_EXPIRY = 24 * 3600  # 1 day


# ---------------- Webhook Routes ----------------
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_str = request.stream.read().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    return "Webhook set", 200


# ---------------- Handlers ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()
    if len(args) > 1:
        token = args[1]
        data = video_store.get(token)

        if not data:
            bot.reply_to(message, "❌ Invalid or expired link.")
            return

        # Expiry check
        if time.time() > data["expiry"]:
            bot.reply_to(message, "⏰ Link expired.")
            del video_store[token]
            return

        # Send video
        bot.send_chat_action(message.chat.id, "upload_video")
        bot.send_video(message.chat.id, data["file_id"])
        if data.get("single_use"):
            del video_store[token]
    else:
        bot.reply_to(message, "👋 Send me a video (admin only) and I'll generate a link.")


@bot.message_handler(content_types=['video', 'document'])
def handle_video(message):
    user_id = message.from_user.id

    # Admin check
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admin can upload videos.")
        return

    video = message.video or (message.document if message.document.mime_type.startswith("video/") else None)
    if not video:
        bot.reply_to(message, "⚠️ Please send a valid video file.")
        return

    file_id = video.file_id
    token = secrets.token_urlsafe(8)
    video_store[token] = {
        "file_id": file_id,
        "expiry": int(time.time()) + TOKEN_EXPIRY,
        "single_use": False
    }

    link = f"https://t.me/{bot.get_me().username}?start={token}"
    bot.reply_to(
        message,
        f"✅ Link generated:\n{link}\n\nValid till: {time.ctime(video_store[token]['expiry'])}"
    )


@bot.message_handler(commands=['id'])
def get_id(message):
    bot.reply_to(message, f"Your Telegram user_id: `{message.from_user.id}`", parse_mode="Markdown")


# ---------------- Run Flask ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
