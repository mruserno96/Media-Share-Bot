import os
import secrets
from flask import Flask, request
import telebot

# ---- Supabase ----
from supabase import create_client, Client

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://example.onrender.com")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://jvfnjzvgojnmedjidchj.supabase.co")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    # NOTE: put your key in Render env vars; hardcoding is unsafe.
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2Zm5qenZnb2pubWVkamlkY2hqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY5MTA0NDcsImV4cCI6MjA3MjQ4NjQ0N30.LdPTAmtkxz3ECmXiPVmaY2X_FuBF_sL8aoKP6ltdGgo"
)

# safety checks
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL/KEY missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

# Admins: set of user_ids
ADMIN_IDS = {7900116525, 7810231866}

# ---------------- Supabase helpers ----------------
TABLE = "videos"  # columns: token (pk text), file_id (text), created_at (timestamp default now())

def save_video(token: str, file_id: str) -> bool:
    try:
        supabase.table(TABLE).insert({"token": token, "file_id": file_id}).execute()
        return True
    except Exception as e:
        print("Supabase insert error:", e)
        return False

def get_video(token: str) -> str | None:
    try:
        res = supabase.table(TABLE).select("file_id").eq("token", token).limit(1).execute()
        if res.data:
            return res.data[0]["file_id"]
    except Exception as e:
        print("Supabase select error:", e)
    return None

def delete_video(token: str) -> bool:
    try:
        res = supabase.table(TABLE).delete().eq("token", token).execute()
        return bool(res.data) or True  # some clients return empty data on success
    except Exception as e:
        print("Supabase delete error:", e)
        return False

def list_tokens() -> list[dict]:
    try:
        res = supabase.table(TABLE).select("token, created_at").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        print("Supabase list error:", e)
        return []

def generate_unique_token() -> str:
    # ensure token not already used
    for _ in range(5):
        t = secrets.token_urlsafe(8)
        if not get_video(t):
            return t
    # extremely unlikely fallback
    return secrets.token_urlsafe(12)

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
        return f"❌ Error setting webhook: {e}", 500

# ---------------- Bot Handlers ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    # Admin greeting
    if user_id in ADMIN_IDS and (len(args) == 1):
        bot.reply_to(message, "👋 *Hello Admin!* Send a video to generate a permanent link.\nUse /help for commands.")
        return

    # Normal user or deep-link open
    if len(args) > 1:
        token = args[1].strip()
        file_id = get_video(token)
        if not file_id:
            bot.reply_to(message, "❌ Invalid link.")
            return
        bot.send_chat_action(message.chat.id, "upload_video")
        # Optional: protect_content=True to prevent forwarding/downloading
        bot.send_video(message.chat.id, file_id)
    else:
        bot.reply_to(message, "👋 Hello! I am *Media Sharing Bot*.\nSend a valid link to receive the video.")

# ---------------- Video Upload ----------------
@bot.message_handler(content_types=['video', 'document'])
def handle_video(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can upload videos.")
        return

    # accept video or video document
    video = message.video
    if not video and message.document and (message.document.mime_type or "").startswith("video/"):
        video = message.document
    if not video:
        bot.reply_to(message, "⚠️ Please send a *video* file.")
        return

    token = generate_unique_token()
    ok = save_video(token, video.file_id)
    if not ok:
        bot.reply_to(message, "❌ Could not save link (DB error).")
        return

    link = f"https://t.me/{bot.get_me().username}?start={token}"
    bot.reply_to(
        message,
        f"✅ *Permanent link generated:*\n{link}\n\nUse `/listlinks` to see all links."
    )

# ---------------- Admin Commands ----------------
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can add admins.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: `/addadmin <user_id>`")
        return
    try:
        new_id = int(args[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid user_id.")
        return
    if new_id in ADMIN_IDS:
        bot.reply_to(message, "ℹ️ Already an admin.")
        return
    ADMIN_IDS.add(new_id)
    bot.reply_to(message, f"✅ Added admin: `{new_id}`")

@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can remove admins.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: `/removeadmin <user_id>`")
        return
    try:
        rem_id = int(args[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid user_id.")
        return
    if rem_id not in ADMIN_IDS:
        bot.reply_to(message, "ℹ️ Not an admin.")
        return
    if rem_id == uid:
        bot.reply_to(message, "⚠️ You cannot remove yourself.")
        return
    ADMIN_IDS.remove(rem_id)
    bot.reply_to(message, f"✅ Removed admin: `{rem_id}`")

@bot.message_handler(commands=['listadmins'])
def list_admins(message):
    text = "👑 *Current Admins:*\n"
    for uid in ADMIN_IDS:
        try:
            u = bot.get_chat(uid)
            username = f"@{u.username}" if u.username else (u.first_name or "N/A")
        except Exception:
            username = "N/A"
        text += f"- `{uid}` {username}\n"
    bot.reply_to(message, text)

# -------- Link Management --------
@bot.message_handler(commands=['listlinks'])
def list_links(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can view links.")
        return

    rows = list_tokens()
    if not rows:
        bot.reply_to(message, "ℹ️ No active links.")
        return

    me = bot.get_me().username
    lines = ["🎬 *Active Links:*"]
    for r in rows:
        token = r["token"]
        link = f"https://t.me/{me}?start={token}"
        created = r.get("created_at", "") or ""
        lines.append(f"- `{token}` → {link}  _{created}_")
    bot.reply_to(message, "\n".join(lines))

@bot.message_handler(commands=['deletelink'])
def delete_link_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Only admins can delete links.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: `/deletelink <token>`")
        return
    token = args[1].strip()
    file_id = get_video(token)
    if not file_id:
        bot.reply_to(message, "❌ Invalid token.")
        return
    if delete_video(token):
        bot.reply_to(message, f"✅ Link `{token}` deleted permanently.")
    else:
        bot.reply_to(message, "❌ Delete failed (DB error).")

# ---------------- Help ----------------
@bot.message_handler(commands=['help'])
def help_command(message):
    if message.from_user.id in ADMIN_IDS:
        help_text = (
            "👑 *Admin Commands*\n"
            "/start – Greet\n"
            "/addadmin `<user_id>` – Add admin\n"
            "/removeadmin `<user_id>` – Remove admin (not self)\n"
            "/listadmins – List admins\n"
            "/listlinks – Show all active links\n"
            "/deletelink `<token>` – Destroy a link\n"
            "➕ Send a *video* to generate a permanent link"
        )
    else:
        help_text = "👋 Only admins can upload videos. Use a valid link to receive a video."
    bot.reply_to(message, help_text)

# ---------------- Run Flask ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
