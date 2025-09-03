import os
import telebot
from supabase import create_client, Client
from flask import Flask, request
import requests

# ==============================
# CONFIG
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_IDS = [7900116525,7810231866]  # <-- apna telegram user id daalna

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
server = Flask(__name__)

# ==============================
# HELPERS
# ==============================
def escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars"""
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + c if c in escape_chars else c for c in text])

def get_file_url(file_id: str):
    """Get permanent Telegram download URL for file_id"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    r = requests.get(url).json()
    if "result" in r:
        file_path = r["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    return None

# ==============================
# COMMANDS
# ==============================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    args = message.text.split()
    if len(args) > 1:
        token = args[1]
        data = supabase.table("videos").select("*").eq("token", token).execute()
        if data.data:
            video = data.data[0]
            file_id = video["file_id"]

            try:
                # Send video using stored file_id
                bot.send_video(message.chat.id, file_id, caption="Here is your video 🎬")
            except:
                # If file_id invalid, fallback to download_url
                if "download_url" in video and video["download_url"]:
                    bot.send_message(message.chat.id, f"🔗 Download here:\n{video['download_url']}")
                else:
                    url = get_file_url(file_id)
                    if url:
                        bot.send_message(message.chat.id, f"🔗 Download here:\n{url}")
                    else:
                        bot.send_message(message.chat.id, "❌ Video not found!")
        else:
            bot.send_message(message.chat.id, "❌ Invalid link.")
    else:
        bot.send_message(message.chat.id, "👋 Welcome! Send me a video if you're admin.")

@bot.message_handler(content_types=['video'])
def handle_video(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can upload videos.")
        return

    file_id = message.video.file_id
    token = os.urandom(6).hex()

    # Get permanent file URL
    download_url = get_file_url(file_id)

    supabase.table("videos").insert({
        "token": token,
        "file_id": file_id,
        "download_url": download_url
    }).execute()

    bot.reply_to(
        message,
        f"✅ Video saved!\n\n🔗 Link: https://t.me/{bot.get_me().username}?start={token}"
    )

@bot.message_handler(commands=['listvideos'])
def list_videos(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can list videos.")
        return

    videos = supabase.table("videos").select("token, created_at").execute().data

    if not videos:
        bot.reply_to(message, "ℹ️ No videos found.")
        return

    text = "📂 *All Video Links:*\n\n"
    for v in videos:
        link = f"https://t.me/{bot.get_me().username}?start={v['token']}"
        text += f"🎬 Token: `{escape_md(v['token'])}`\n🔗 {escape_md(link)}\n🕒 {escape_md(v['created_at'])}\n\n"

    bot.reply_to(message, text, parse_mode="MarkdownV2")

@bot.message_handler(commands=['destroy'])
def destroy_video(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can destroy links.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: /destroy <token>")
        return

    token = args[1]
    supabase.table("videos").delete().eq("token", token).execute()
    bot.reply_to(message, f"🗑️ Video with token `{escape_md(token)}` deleted.", parse_mode="MarkdownV2")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "ℹ️ Just send a valid link to get your video.")
        return

    help_text = """
⚙️ *Admin Commands:*
/listvideos – Show all saved links
/destroy <token> – Delete a video
"""
    bot.reply_to(message, help_text, parse_mode="MarkdownV2")

# ==============================
# FLASK SERVER
# ==============================
@server.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "ok", 200

@server.route("/")
def index():
    return "Bot is running!", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{os.getenv('RENDER_URL')}/{BOT_TOKEN}")
    server.run(host="0.0.0.0", port=10000)
