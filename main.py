import os
import secrets
import telebot
from flask import Flask, request

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://media-share-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Admins: store dict user_id -> username (username may be None)
ADMIN_IDS = {
    7900116525: None,
    7810231866: None
}

# Store videos: token -> {file_id, single_use}
video_store = {}

# ---------------- Webhook Routes ----------------
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_str = request.stream.read().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def webhook():
    if not BOT_TOKEN or not WEBHOOK_URL:
        return "❌ BOT_TOKEN or WEBHOOK_URL not set", 500
    try:
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        return "✅ Webhook set", 200
    except Exception as e:
        return f"❌ Error setting webhook: {str(e)}", 500

# ---------------- Bot Handlers ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.text.split()

    # Update admin username if admin
    if user_id in ADMIN_IDS:
        ADMIN_IDS[user_id] = username
        bot.reply_to(message, "👋 Hello Admin! You can send videos to generate permanent links.\nUse /help to see all admin commands.")
        return

    # Normal users
    if len(args) > 1:  # token link
        token = args[1]
        data = video_store.get(token)
        if not data:
            bot.reply_to(message, "❌ Invalid link.")
            return
        bot.send_chat_action(message.chat.id, "upload_video")
        bot.send_video(message.chat.id, data["file_id"])
    else:
        bot.reply_to(message, "👋 Hello! I am Normal Media Sharing Bot.")

# ---------------- Video Upload ----------------
@bot.message_handler(content_types=['video', 'document'])
def handle_video(message):
    user_id = message.from_user.id
    username = message.from_user.username

    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admin can upload videos. Please contact admin.")
        return

    ADMIN_IDS[user_id] = username  # update username

    video = message.video or (message.document if message.document.mime_type.startswith("video/") else None)
    if not video:
        bot.reply_to(message, "⚠️ Please send a valid video file.")
        return

    file_id = video.file_id
    token = secrets.token_urlsafe(8)
    video_store[token] = {
        "file_id": file_id,
        "single_use": False
    }

    link = f"https://t.me/{bot.get_me().username}?start={token}"
    bot.reply_to(message, f"✅ Permanent link generated:\n{link}\n\nNo expiry.")

# ---------------- Admin Commands ----------------
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can add other admins.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: /addadmin <user_id> [@username]")
        return

    try:
        new_id = int(args[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid user_id.")
        return

    username = args[2] if len(args) > 2 else None

    if new_id in ADMIN_IDS:
        bot.reply_to(message, "ℹ️ This user is already an admin.")
        return

    ADMIN_IDS[new_id] = username
    bot.reply_to(message, f"✅ Added new admin: `{new_id}` @{username if username else ''}", parse_mode="Markdown")

@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can remove other admins.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: /removeadmin <user_id>")
        return

    try:
        remove_id = int(args[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid user_id.")
        return

    if remove_id not in ADMIN_IDS:
        bot.reply_to(message, "ℹ️ This user is not an admin.")
        return

    if remove_id == user_id:
        bot.reply_to(message, "⚠️ You cannot remove yourself!")
        return

    ADMIN_IDS.pop(remove_id)
    bot.reply_to(message, f"✅ Removed admin: `{remove_id}`", parse_mode="Markdown")

@bot.message_handler(commands=['listadmins'])
def list_admins(message):
    admin_list = "\n".join([f"- `{uid}` @{uname if uname else 'N/A'}" for uid, uname in ADMIN_IDS.items()])
    bot.reply_to(message, f"👑 Current Admins:\n{admin_list}", parse_mode="Markdown")

# ---------------- Help ----------------
@bot.message_handler(commands=['help'])
def help_command(message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        help_text = (
            "👑 Admin Commands:\n"
            "/start - Start bot\n"
            "/id - Get your user ID\n"
            "/addadmin <user_id> [@username] - Add a new admin\n"
            "/removeadmin <user_id> - Remove an admin (cannot remove self)\n"
            "/listadmins - List all admins\n"
            "Send videos - Upload video to generate permanent link"
        )
    else:
        help_text = "👋 You are a normal user. Only admins can upload videos."
    bot.reply_to(message, help_text)

# ---------------- Get User ID ----------------
@bot.message_handler(commands=['id'])
def get_id(message):
    bot.reply_to(message, f"Your Telegram user_id: `{message.from_user.id}`", parse_mode="Markdown")

# ---------------- Run Flask ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
