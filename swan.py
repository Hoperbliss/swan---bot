import os
import sqlite3
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =========================
# SWAN CONFIG
# =========================

TOKEN = os.getenv("BOT_TOKEN")
DATABASE = "swan_data.db"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# DATABASE
# =========================

def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL
            )
        """)


def get_group():
    with sqlite3.connect(DATABASE) as db:
        result = db.execute(
            "SELECT value FROM settings WHERE key='group_id'"
        ).fetchone()
    return int(result[0]) if result else None


def save_group(group_id):
    with sqlite3.connect(DATABASE) as db:
        db.execute(
            "INSERT OR REPLACE INTO settings VALUES (?, ?)",
            ("group_id", str(group_id))
        )


# =========================
# ADMIN CHECK
# =========================

async def is_admin(update, context):
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in ("administrator", "creator")


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦢 Welcome to Swan!\n\n"
        "Send your message here. "
        "Our team will receive it shortly."
    )


# =========================
# CONNECT ADMIN GROUP
# =========================

async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ("group", "supergroup"):
        return

    if not await is_admin(update, context):
        await update.message.reply_text(
            "Only group administrators can connect Swan."
        )
        return

    save_group(update.effective_chat.id)
    await update.message.reply_text(
        "🦢 Swan Admin connected successfully!"
    )


# =========================
# USER MESSAGE
# =========================

async def receive_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    group_id = get_group()

    if not group_id:
        await update.message.reply_text(
            "Swan is currently unavailable. Please try again later."
        )
        return

    user = update.effective_user
    full_name = user.full_name or "Tidak tersedia"
    username = f"@{user.username}" if user.username else "Tidak ada username"
    user_id = user.id
    received_at = update.message.date.strftime("%d-%m-%Y %H:%M:%S UTC")

    sender_info = (
        "📩 PESAN BARU MASUK\n\n"
        f"👤 Nama: {full_name}\n"
        f"🔖 Username: {username}\n"
        f"🆔 User ID: {user_id}\n"
        f"🕒 Waktu: {received_at}"
    )

    try:
        # Salinan pesan tetap menjadi pesan yang di-reply admin,
        # sehingga mekanisme balasan lama tidak berubah.
        copied = await context.bot.copy_message(
            chat_id=group_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )

        with sqlite3.connect(DATABASE) as db:
            db.execute(
                "INSERT OR REPLACE INTO messages VALUES (?, ?)",
                (copied.message_id, user_id)
            )

        # Identitas dikirim sebagai pesan terpisah di grup admin.
        await context.bot.send_message(
            chat_id=group_id,
            text=sender_info
        )

    except Exception:
        logging.exception("Message delivery failed")
        await update.message.reply_text(
            "Sorry, message delivery failed."
        )


# =========================
# ADMIN REPLY
# =========================

async def admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.message

    if not message.reply_to_message:
        return

    if not await is_admin(update, context):
        return

    with sqlite3.connect(DATABASE) as db:
        result = db.execute(
            "SELECT user_id FROM messages WHERE message_id = ?",
            (message.reply_to_message.message_id,)
        ).fetchone()

    if not result:
        return

    user_id = result[0]

    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        await message.reply_text("✅ Message delivered!")

    except Exception:
        logging.exception("Reply delivery failed")
        await message.reply_text(
            "❌ Failed to deliver reply."
        )


# =========================
# MAIN
# =========================

def main():
    if not TOKEN:
        raise ValueError(
            "BOT_TOKEN is missing. Set your bot token first."
        )

    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setgroup", setgroup))

    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.REPLY,
            admin_reply
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            receive_message
        )
    )

    print("🦢 SWAN BOT IS RUNNING!")
    app.run_polling()


if __name__ == "__main__":
    main()
