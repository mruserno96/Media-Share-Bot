import os
import secrets
import sqlite3
import telebot
from flask import Flask, request

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://media-share-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Admins
ADMIN_IDS = {7900116525, 7810231866}

# ---------------- Database ----------------
DB_FILE = "videos.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            token TEXT PRIMARY KEY,
            file_id TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_video(token, file_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO videos (token, file_id) VALUES (?, ?)", (token, file_id))
    conn.commit()
    conn.close()

def delete_video(token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM videos WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def get_video(token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT file_id FROM videos WHERE token = ?", (token,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def list_videos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT token FROM videos")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

# Init database
init_db()

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

    if user_id in ADMIN_IDS:
        bot.reply_to(message, "👋 Hello Admin! Use /help for commands.")
        return

    if len(args) > 1:  # token
        token = args[1]
        file_id = get_video(token)
        if not file_id:
            bot.reply_to(message, "❌ Invalid link.")
            return
        bot.send_chat_action(message.chat.id, "upload_video")
        bot.send_video(message.chat.id, file_id)
    else:
        bot.reply_to(message, "👋 Hello! I am Media Sharing Bot.")

# ---------------- Video Upload ----------------
@bot.message_handler(content_types=['video', 'document'])
def handle_video(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can upload.")
        return

    video = message.video or (message.document if message.document.mime_type.startswith("video/") else None)
    if not video:
        bot.reply_to(message, "⚠️ Please send a valid video file.")
        return

    token = secrets.token_urlsafe(8)
    save_video(token, video.file_id)

    link = f"https://t.me/{bot.get_me().username}?start={token}"
    bot.reply_to(message, f"✅ Permanent link:\n{link}")

# ---------------- Admin Commands ----------------
@bot.message_handler(commands=['listlinks'])
def list_links(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can view links.")
        return

    tokens = list_videos()
    if not tokens:
        bot.reply_to(message, "ℹ️ No active links.")
        return

    text = "🎬 Active Links:\n"
    for token in tokens:
        link = f"https://t.me/{bot.get_me().username}?start={token}"
        text += f"- `{token}` → {link}\n"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['deletelink'])
def delete_link_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can delete.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: /deletelink <token>")
        return

    token = args[1]
    if not get_video(token):
        bot.reply_to(message, "❌ Invalid token.")
        return

    delete_video(token)
    bot.reply_to(message, f"✅ Link `{token}` deleted.", parse_mode="Markdown")

# ---------------- Help ----------------
@bot.message_handler(commands=['help'])
def help_command(message):
    if message.from_user.id in ADMIN_IDS:
        help_text = (
            "👑 Admin Commands:\n"
            "/listlinks - Show all video links\n"
            "/deletelink <token> - Delete a link\n"
            "Send videos - Upload and generate permanent link"
        )
    else:
        help_text = "👋 Only admins can upload videos."
    bot.reply_to(message, help_text)

# ---------------- Run Flask ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
