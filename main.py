import os
import secrets
import telebot
from flask import Flask, request
from supabase import create_client, Client
from telebot import types

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- Owner / Admins ----------------
OWNER_ID = 8356178010  # replace with your real Telegram ID
ADMIN_IDS = {OWNER_ID: None}  # start with only owner

# ---------------- Helpers ----------------
def escape_markdown(text: str) -> str:
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + c if c in escape_chars else c for c in text])

def get_owner_keyboard():
    """Keyboard for owner"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("➕ Add Admin"),
        types.KeyboardButton("❌ Remove Admin"),
        types.KeyboardButton("👑 List Admins"),
        types.KeyboardButton("📂 List Videos"),
        types.KeyboardButton("🔥 Destroy Video"),
    )
    return kb

def get_admin_keyboard():
    """Keyboard for admins"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("📂 List Videos"),
        types.KeyboardButton("🔥 Destroy Video"),
    )
    return kb

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
pending_action = {}  # store user pending actions

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.text.split()

    # Token link flow
    if len(args) > 1:
        token = args[1]
        response = supabase.table("videos").select("file_id").eq("token", token).execute()
        if not response.data:
            bot.reply_to(message, "❌ Invalid or deleted link.")
            return
        file_id = response.data[0]["file_id"]
        bot.send_chat_action(message.chat.id, "upload_video")
        bot.send_video(message.chat.id, file_id)
        return

    # Owner
    if user_id == OWNER_ID:
        ADMIN_IDS[user_id] = username
        bot.send_message(
            message.chat.id,
            "👑 Welcome Owner! Use the buttons below:",
            reply_markup=get_owner_keyboard()
        )
        return

    # Admins
    if user_id in ADMIN_IDS:
        ADMIN_IDS[user_id] = username
        bot.send_message(
            message.chat.id,
            "👋 Welcome Admin! You can manage videos.",
            reply_markup=get_admin_keyboard()
        )
        return

    # Normal users
    bot.reply_to(message, "👋 Hello! Send me a valid video link to watch.")

# ---------------- Video Upload ----------------
@bot.message_handler(content_types=['video', 'document'])
def handle_video(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can upload videos.")
        return

    video = message.video or (message.document if message.document.mime_type.startswith("video/") else None)
    if not video:
        bot.reply_to(message, "⚠️ Please send a valid video file.")
        return

    token = secrets.token_urlsafe(8)
    supabase.table("videos").insert({
        "token": token,
        "file_id": video.file_id
    }).execute()

    link = f"https://t.me/{bot.get_me().username}?start={token}"
    bot.reply_to(message, f"✅ Permanent link generated:\n{link}")

# ---------------- Owner/Admin Button Actions ----------------
@bot.message_handler(func=lambda m: m.text in ["➕ Add Admin", "❌ Remove Admin", "👑 List Admins", "📂 List Videos", "🔥 Destroy Video"])
def handle_buttons(message):
    user_id = message.from_user.id

    if message.text == "➕ Add Admin":
        if user_id != OWNER_ID:
            bot.reply_to(message, "❌ Only the owner can add admins.")
            return
        pending_action[user_id] = "add_admin"
        bot.reply_to(message, "👉 Enter user_id to add as admin:")

    elif message.text == "❌ Remove Admin":
        if user_id != OWNER_ID:
            bot.reply_to(message, "❌ Only the owner can remove admins.")
            return
        pending_action[user_id] = "remove_admin"
        bot.reply_to(message, "👉 Enter user_id to remove from admins:")

    elif message.text == "👑 List Admins":
        if user_id != OWNER_ID:
            bot.reply_to(message, "❌ Only the owner can list admins.")
            return
        text = "👑 Current Admins:\n"
        for uid, uname in ADMIN_IDS.items():
            text += f"- `{uid}` @{uname if uname else 'N/A'}\n"
        bot.reply_to(message, text, parse_mode="Markdown")

    elif message.text == "📂 List Videos":
        if user_id not in ADMIN_IDS:
            bot.reply_to(message, "❌ Only admins can list videos.")
            return
        response = supabase.table("videos").select("token, created_at").execute()
        videos = response.data
        if not videos:
            bot.reply_to(message, "ℹ️ No videos found.")
            return
        text = "📂 All Video Links:\n\n"
        for v in videos:
            link = f"https://t.me/{bot.get_me().username}?start={v['token']}"
            token = escape_markdown(v['token'])
            created = escape_markdown(v['created_at'])
            safe_link = escape_markdown(link)
            text += f"🎬 Token: `{token}`\n🔗 Link: {safe_link}\n🕒 {created}\n\n"
        bot.reply_to(message, text, parse_mode="MarkdownV2")

    elif message.text == "🔥 Destroy Video":
        if user_id not in ADMIN_IDS:
            bot.reply_to(message, "❌ Only admins can destroy videos.")
            return
        pending_action[user_id] = "destroy_video"
        bot.reply_to(message, "👉 Enter token to destroy video:")

# ---------------- Handle Pending Actions ----------------
@bot.message_handler(func=lambda m: m.from_user.id in pending_action)
def handle_pending(message):
    user_id = message.from_user.id
    action = pending_action.get(user_id)

    if action == "add_admin":
        try:
            new_id = int(message.text.strip())
            if new_id in ADMIN_IDS:
                bot.reply_to(message, "ℹ️ Already an admin.")
            else:
                ADMIN_IDS[new_id] = None
                bot.reply_to(message, f"✅ Added new admin: `{new_id}`", parse_mode="Markdown")
        except:
            bot.reply_to(message, "❌ Invalid user_id.")
        pending_action.pop(user_id, None)

    elif action == "remove_admin":
        try:
            remove_id = int(message.text.strip())
            if remove_id not in ADMIN_IDS:
                bot.reply_to(message, "❌ Not an admin.")
            elif remove_id == OWNER_ID:
                bot.reply_to(message, "⚠️ Cannot remove owner.")
            else:
                ADMIN_IDS.pop(remove_id)
                bot.reply_to(message, f"✅ Removed admin: `{remove_id}`", parse_mode="Markdown")
        except:
            bot.reply_to(message, "❌ Invalid user_id.")
        pending_action.pop(user_id, None)

    elif action == "destroy_video":
        token = message.text.strip()
        response = supabase.table("videos").delete().eq("token", token).execute()
        if response.data:
            bot.reply_to(message, f"✅ Destroyed video with token `{token}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Token not found.")
        pending_action.pop(user_id, None)

# ---------------- Run Flask ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
