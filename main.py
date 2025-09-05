import os import secrets import telebot from flask import Flask, request from supabase import create_client, Client from telebot import types

---------------- Config ----------------

BOT_TOKEN = os.getenv("BOT_TOKEN") WEBHOOK_URL = os.getenv("WEBHOOK_URL") SUPABASE_URL = os.getenv("SUPABASE_URL") SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(BOT_TOKEN) app = Flask(name)

Supabase client

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

Admins: dict user_id -> username

ADMIN_IDS = { 8356178010: None }

---------------- Helpers ----------------

def escape_markdown(text: str) -> str: escape_chars = r'\_*~`>#+-=|{}.!' return ''.join(['\' + c if c in escape_chars else c for c in text])

def get_admin_keyboard(): keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2) keyboard.add( types.KeyboardButton("➕ Add Admin"), types.KeyboardButton("❌ Remove Admin"), types.KeyboardButton("👑 List Admins"), types.KeyboardButton("📂 List Videos"), types.KeyboardButton("🔥 Destroy Video"), types.KeyboardButton("ℹ️ Help"), ) return keyboard

---------------- Webhook Routes ----------------

@app.route('/' + BOT_TOKEN, methods=['POST']) def getMessage(): json_str = request.stream.read().decode("utf-8") update = telebot.types.Update.de_json(json_str) bot.process_new_updates([update]) return "OK", 200

@app.route("/") def webhook(): try: bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}") return "✅ Webhook set", 200 except Exception as e: return f"❌ Error setting webhook: {str(e)}", 500

---------------- Bot Handlers ----------------

@bot.message_handler(commands=['start']) def handle_start(message): user_id = message.from_user.id username = message.from_user.username args = message.text.split()

# 1️⃣ Token flow
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

# 2️⃣ Admin greeting
if user_id in ADMIN_IDS:
    ADMIN_IDS[user_id] = username
    bot.send_message(
        message.chat.id,
        "👋 Hello Admin! Use the buttons below to manage the bot.",
        reply_markup=get_admin_keyboard()
    )
    return

# 3️⃣ Normal user without token
bot.reply_to(message, "👋 Hello! Send me a valid link to get a video.")

---------------- Video Upload ----------------

@bot.message_handler(content_types=['video', 'document']) def handle_video(message): user_id = message.from_user.id username = message.from_user.username

if user_id not in ADMIN_IDS:
    bot.reply_to(message, "❌ Unknown command.")
    return

ADMIN_IDS[user_id] = username

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
bot.reply_to(message, f"✅ Permanent link generated:\n{link}\n\nNo expiry.")

---------------- Admin Button Actions ----------------

@bot.message_handler(func=lambda m: m.text in ["➕ Add Admin", "❌ Remove Admin", "👑 List Admins", "📂 List Videos", "🔥 Destroy Video", "ℹ️ Help"]) def handle_admin_buttons(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return

if message.text == "➕ Add Admin":
    bot.reply_to(message, "Send user_id with /addadmin <user_id>")
elif message.text == "❌ Remove Admin":
    bot.reply_to(message, "Send user_id with /removeadmin <user_id>")
elif message.text == "👑 List Admins":
    list_admins(message)
elif message.text == "📂 List Videos":
    list_videos(message)
elif message.text == "🔥 Destroy Video":
    bot.reply_to(message, "Send token with /destroy <token>")
elif message.text == "ℹ️ Help":
    help_command(message)

---------------- Admin Commands ----------------

@bot.message_handler(commands=['addadmin']) def add_admin(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return args = message.text.split() if len(args) < 2: bot.reply_to(message, "⚠️ Usage: /addadmin <user_id>") return try: new_id = int(args[1]) except ValueError: bot.reply_to(message, "❌ Invalid user_id.") return if new_id in ADMIN_IDS: bot.reply_to(message, "ℹ️ This user is already an admin.") return ADMIN_IDS[new_id] = None bot.reply_to(message, f"✅ Added new admin: {new_id}", parse_mode="Markdown")

@bot.message_handler(commands=['removeadmin']) def remove_admin(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return args = message.text.split() if len(args) < 2: bot.reply_to(message, "⚠️ Usage: /removeadmin <user_id>") return try: remove_id = int(args[1]) except ValueError: bot.reply_to(message, "❌ Invalid user_id.") return if remove_id not in ADMIN_IDS: bot.reply_to(message, "ℹ️ This user is not an admin.") return if remove_id == user_id: bot.reply_to(message, "⚠️ You cannot remove yourself!") return ADMIN_IDS.pop(remove_id) bot.reply_to(message, f"✅ Removed admin: {remove_id}", parse_mode="Markdown")

@bot.message_handler(commands=['listadmins']) def list_admins(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return text = "👑 Current Admins:\n" for uid, uname in ADMIN_IDS.items(): text += f"- {uid} @{uname if uname else 'N/A'}\n" bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['listvideos']) def list_videos(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return try: response = supabase.table("videos").select("token, created_at").execute() videos = response.data if not videos: bot.reply_to(message, "ℹ️ No videos found.") return text = "📂 All Video Links:\n\n" for v in videos: link = f"https://t.me/{bot.get_me().username}?start={v['token']}" token = escape_markdown(v['token']) created = escape_markdown(v['created_at']) safe_link = escape_markdown(link) text += f"🎬 Token: {token}\n🔗 Link: {safe_link}\n🕒 Created: {created}\n\n" bot.reply_to(message, text, parse_mode="MarkdownV2") except Exception as e: bot.reply_to(message, f"❌ Error fetching videos:\n{str(e)}")

@bot.message_handler(commands=['destroy']) def destroy_video(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return args = message.text.split() if len(args) < 2: bot.reply_to(message, "⚠️ Usage: /destroy <token>") return token = args[1] response = supabase.table("videos").delete().eq("token", token).execute() if response.data: bot.reply_to(message, f"✅ Destroyed video with token {token}", parse_mode="Markdown") else: bot.reply_to(message, "❌ Token not found.")

@bot.message_handler(commands=['help']) def help_command(message): user_id = message.from_user.id if user_id not in ADMIN_IDS: bot.reply_to(message, "❌ Unknown command.") return help_text = ( "👑 Admin Help Menu:\n" "- ➕ Add Admin (/addadmin <user_id>)\n" "- ❌ Remove Admin (/removeadmin <user_id>)\n" "- 👑 List Admins (/listadmins)\n" "- 📂 List Videos (/listvideos)\n" "- 🔥 Destroy Video (/destroy <token>)\n" "- Send video to generate link" ) bot.reply_to(message, help_text)

---------------- Run Flask ----------------

if name == "main": port = int(os.environ.get("PORT", 5000)) app.run(host="0.0.0.0", port=port)

