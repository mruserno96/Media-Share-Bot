import os
import sqlite3
import secrets
import time
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://xxx-etbu.onrender.com")
TOKEN_EXPIRY_SECONDS = 24 * 3600  # link 1 din tak valid
SINGLE_USE = False                # True karne par link ek hi baar chalega
DB_PATH = "videos.db"

# ✅ Sirf ye users video bhej sakte hain (Admin IDs)
ADMIN_IDS = [7357160729, 7810231866]   # <-- apna Telegram user_id daalna
# ============================================

bot = Bot(BOT_TOKEN)
app = Flask(__name__)

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE,
        file_id TEXT,
        owner_user_id INTEGER,
        created_at INTEGER,
        expires_at INTEGER,
        used INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def save_video(token, file_id, owner_user_id, expires_at):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO videos (token, file_id, owner_user_id, created_at, expires_at) VALUES (?,?,?,?,?)",
              (token, file_id, owner_user_id, int(time.time()), int(expires_at)))
    conn.commit()
    conn.close()

def get_video(token):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, token, file_id, owner_user_id, expires_at, used FROM videos WHERE token=?", (token,))
    row = c.fetchone()
    conn.close()
    return row

def mark_used(video_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE videos SET used=1 WHERE id=?", (video_id,))
    conn.commit()
    conn.close()

# ---------- HANDLERS ----------
def start(update: Update, context: CallbackContext):
    args = context.args
    if not args:
        update.message.reply_text("Mujhe video bhejo (sirf admin) → main ek shareable link dunga.")
        return

    token = args[0]
    row = get_video(token)
    if not row:
        update.message.reply_text("❌ Invalid ya expire link.")
        return

    vid_id, token_db, file_id, owner_id, expires_at, used = row
    now = int(time.time())

    if expires_at and now > expires_at:
        update.message.reply_text("⏳ Ye link expire ho chuka hai.")
        return
    if SINGLE_USE and used:
        update.message.reply_text("❌ Ye link pehle use ho chuka hai.")
        return

    context.bot.send_video(chat_id=update.effective_chat.id, video=file_id,
                           caption=f"🎥 Shared by Admin {owner_id}")
    if SINGLE_USE:
        mark_used(vid_id)

def handle_video(update: Update, context: CallbackContext):
    msg = update.message
    user_id = msg.from_user.id

    # ✅ Admin check
    if user_id not in ADMIN_IDS:
        msg.reply_text("❌ Sirf admin hi video bhej sakta hai.")
        return

    video = msg.video or (msg.document if msg.document and msg.document.mime_type.startswith("video/") else None)
    if not video:
        msg.reply_text("⚠️ Please send a valid video file.")
        return

    file_id = video.file_id
    token = secrets.token_urlsafe(8)
    expiry = int(time.time()) + TOKEN_EXPIRY_SECONDS
    save_video(token, file_id, msg.from_user.id, expiry)

    link = f"https://t.me/{context.bot.username}?start={token}"
    msg.reply_text(f"✅ Link generated:\n{link}\n\n⏳ Valid till: {time.ctime(expiry)}")

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text("📌 Sirf admin hi video bhej kar link generate kar sakte hain.\n"
                              "Koi bhi user link open karega to video dekh sakta hai.")

# ---------- DISPATCHER ----------
dispatcher = Dispatcher(bot, None, workers=0)
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_cmd))
dispatcher.add_handler(MessageHandler(Filters.video | Filters.document.category("video"), handle_video))

# ---------- FLASK ROUTES ----------
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok", 200

@app.route("/setwebhook", methods=["GET"])
def set_webhook():
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    return "Webhook set!", 200

# ---------- INIT ----------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
