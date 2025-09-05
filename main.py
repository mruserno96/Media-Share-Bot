import os import secrets import telebot from flask import Flask, request from supabase import create_client, Client from telebot import types

---------------- Config ----------------

BOT_TOKEN = os.getenv("BOT_TOKEN") WEBHOOK_URL = os.getenv("WEBHOOK_URL") SUPABASE_URL = os.getenv("SUPABASE_URL") SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(BOT_TOKEN) app = Flask(name)

Supabase client

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

Admins: dict user_id -> username

ADMIN_IDS = { 8356178010: None }

Conversation state: user_id -> action

pending_action = {}

---------------- Helpers ----------------

def escape_markdown(text: str) -> str: escape_chars = r'_*~`>#+-=|{}.!' return ''.join(['\' + c if c in escape_chars else c for c in text])

def get_admin_keyboard(): keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2) keyboard.add( types.KeyboardButton("➕ Add Admin"), types.KeyboardButton("❌ Remove Admin"), types.KeyboardButton("👑 List Admins"), types.KeyboardButton("📂 List Videos"), types.KeyboardButton("🔥 Destroy Video"), ) return keyboard

---------------- Webhook Routes ----------------

@app.route('/' + BOT_TOKEN, methods=['POST']) def getMessage(): json_str = request.stream.read().decode("utf-8") update = telebot.types.Update.de_json(json_str) bot.process_new_updates([update]) return "OK", 200

@app.route("/") def webhook(): try: bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}") return "✅ Webhook set", 200 except Exception as e: return f"❌ Error setting webhook: {str(e)}", 500

---------------- Bot Handlers ----------------

@bot.message_handler(commands=['start']) def handle_start(message): user_id = message.from_user.id username = message.from_user.username args = message.text.split()

# Token flow
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

# Admin greeting
if user_id in ADMIN_IDS:
    ADMIN_IDS[user_id] = username
    bot.send_message(
        message.chat.id,
        "👋 Hello Admin! Use the buttons below to manage the bot.",
        reply_markup=get_admin_keyboard()
    )
    return

# Normal user
bot.reply_to(message, "👋 Hello! Send me a valid link to get a video.")

---------------- Video Upload ----------------

@bot.message_handler(content_types=['video', 'document']) def handle_video(message): user_id = message.from_user.id username = message.from_user.username

if user_id not in ADMIN_IDS:
    bot.reply_to(message, "❌ Only admins can upload videos.")
    return

ADMIN_IDS[user_id] = username

video = message.video or (message.document if message.document.mime_type.startswith("video/") else None)
if not video:
    bot.reply_to(message, "⚠️ Please send a valid video file.")
    return

token = secrets.token_urlsafe(8)
supabase.table("videos").insert({"token": token, "file_id": video.file_id}).execute()

link = f"https://t.me/{bot.get_me().username}?start={token}"
bot.reply_to(message, f"✅ Permanent link generated:\n{link}\n\nNo expiry.")

---------------- Admin Button Actions ----------------

@bot.message_handler(func=lambda m: m.text in ["➕ Add Admin", "❌ Remove Admin", "👑 List Admins", "📂 List Videos", "🔥 Destroy Video"]) def handle_admin_buttons(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return

if message.text == "➕ Add Admin":
    pending_action[user_id] = "addadmin"
    bot.reply_to(message, "👉 Please enter user ID to add as admin")
elif message.text == "❌ Remove Admin":
    pending_action[user_id] = "removeadmin"
    bot.reply_to(message, "👉 Please enter user ID to remove")
elif message.text == "👑 List Admins":
    list_admins(message)
elif message.text == "📂 List Videos":
    list_videos(message)
elif message.text == "🔥 Destroy Video":
    pending_action[user_id] = "destroy"
    bot.reply_to(message, "👉 Please enter token to destroy")

---------------- Handle Pending Actions ----------------

@bot.message_handler(func=lambda m: m.from_user.id in pending_action) def handle_pending(message): user_id = message.from_user.id action = pending_action[user_id] arg = message.text.strip()

if action == "addadmin":
    try:
        new_id = int(arg)
        if new_id in ADMIN_IDS:
            bot.reply_to(message, "ℹ️ This user is already an admin.")
        else:
            ADMIN_IDS[new_id] = None
            bot.reply_to(message, f"✅ Added new admin: `{new_id}`", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Invalid user_id.")

elif action == "removeadmin":
    try:
        remove_id = int(arg)
        if remove_id not in ADMIN_IDS:
            bot.reply_to(message, "ℹ️ This user is not an admin.")
        elif remove_id == user_id:
            bot.reply_to(message, "⚠️ You cannot remove yourself!")
        else:
            ADMIN_IDS.pop(remove_id)
            bot.reply_to(message, f"✅ Removed admin: `{remove_id}`", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Invalid user_id.")

elif action == "destroy":
    token = arg
    response = supabase.table("videos").delete().eq("token", token).execute()
    if response.data:
        bot.reply_to(message, f"✅ Destroyed video with token `{token}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Token not found.")

# Clear action
del pending_action[user_id]

---------------- Admin Commands ----------------

@bot.message_handler(commands=['listadmins']) def list_admins(message): text = "👑 Current Admins:\n" for uid, uname in ADMIN_IDS.items(): text += f"- {uid} @{uname if uname else 'N/A'}\n" bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['listvideos']) def list_videos(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return try: response = supabase.table("videos").select("token, created_at").execute() videos = response.data if not videos: bot.reply_to(message, "ℹ️ No videos found.") return text = "📂 All Video Links:\n\n" for v in videos: link = f"https://t.me/{bot.get_me().username}?start={v['token']}" token = escape_markdown(v['token']) created = escape_markdown(v['created_at']) safe_link = escape_markdown(link) text += f"🎬 Token: {token}\n🔗 Link: {safe_link}\n🕒 Created: {created}\n\n" bot.reply_to(message, text, parse_mode="MarkdownV2") except Exception as e: bot.reply_to(message, f"❌ Error fetching videos:\n{str(e)}")

---------------- Run Flask ----------------

if name == "main": port = int(os.environ.get("PORT", 5000)) app.run(host="0.0.0.0", port=port)

