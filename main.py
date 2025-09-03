import os
import secrets
import telebot
from flask import Flask, request

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://media-share-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Admins: set of user_ids
ADMIN_IDS = {
    7900116525,
    7810231866
}

# Video store: token -> {file_id, single_use}
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
    try:
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        return "✅ Webhook set", 200
    except Exception as e:
        return f"❌ Error setting webhook: {str(e)}", 500

# ---------------- Bot Handlers ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    args = message.text.split()

    # Admin greeting
    if user_id in ADMIN_IDS:
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

    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admin can upload videos. Please contact admin.")
        return

    video = message.video or (message.document if message.document.mime_type.startswith("video/") else None)
    if not video:
        bot.reply_to(message, "⚠️ Please send a valid video file.")
        return

    token = secrets.token_urlsafe(8)
    video_store[token] = {
        "file_id": video.file_id,
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
        bot.reply_to(message, "⚠️ Usage: /addadmin <user_id>")
        return

    try:
        new_id = int(args[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid user_id.")
        return

    if new_id in ADMIN_IDS:
        bot.reply_to(message, "ℹ️ This user is already an admin.")
        return

    ADMIN_IDS.add(new_id)
    bot.reply_to(message, f"✅ Added new admin: `{new_id}`", parse_mode="Markdown")

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

    ADMIN_IDS.remove(remove_id)
    bot.reply_to(message, f"✅ Removed admin: `{remove_id}`", parse_mode="Markdown")

@bot.message_handler(commands=['listadmins'])
def list_admins(message):
    text = "👑 Current Admins:\n"
    for uid in ADMIN_IDS:
        try:
            user = bot.get_chat(uid)
            username = f"@{user.username}" if user.username else user.first_name
        except:
            username = "N/A"
        text += f"- `{uid}` {username}\n"
    bot.reply_to(message, text, parse_mode="Markdown")

# ---------------- Help ----------------
@bot.message_handler(commands=['help'])
def help_command(message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        help_text = (
            "👑 Admin Commands:\n"
            "/start - Start bot\n"
            "/addadmin <user_id> - Add a new admin\n"
            "/removeadmin <user_id> - Remove an admin (cannot remove self)\n"
            "/listadmins - List all admins with usernames\n"
            "Send videos - Upload video to generate permanent link"
        )
    else:
        help_text = "👋 You are a normal user. Only admins can upload videos."
    bot.reply_to(message, help_text)

# ---------------- Run Flask ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
