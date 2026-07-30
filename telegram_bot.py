import os
import uuid
import logging
import asyncio
import json
import re
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from app.config import TELEGRAM_BOT_TOKEN, DOCUMENTS_DIR
from app.services.history import create_user, DB_PATH
from app.services.queue_manager import document_queue, set_job
from app.services.rag import answer_question_stream

import sqlite3

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_user_by_username(username: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None


def register_user(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[int]:
    normalized_username = username.strip()
    if not normalized_username:
        return None

    user_id = get_user_by_username(normalized_username)
    if not user_id:
        user_id = create_user(normalized_username, "dummy_password_for_telegram")
        if not user_id:
            user_id = get_user_by_username(normalized_username)

    if user_id:
        context.user_data['user_id'] = user_id
        context.user_data['awaiting_username'] = False

    return user_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set up the conversation and tell the user that the first message will be used as registration."""
    context.user_data['awaiting_username'] = True
    await update.message.reply_text(
        "Welcome to the RAG Assistant!\nYour first message will be used to register your Telegram username."
    )


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle PDF uploads."""
    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and send your username first.")
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("Only PDF files are supported.")
        return

    # Check limits
    user_docs_dir = os.path.join(DOCUMENTS_DIR, str(user_id))
    os.makedirs(user_docs_dir, exist_ok=True)

    existing_files = [f for f in os.listdir(user_docs_dir) if f.endswith(".pdf")]
    if len(existing_files) >= 10:
        await update.message.reply_text("LIMIT_REACHED: You have reached the maximum number of 10 PDF uploads.")
        return

    file = await context.bot.get_file(doc.file_id)
    safe_name = "".join(c for c in doc.file_name if c.isalnum() or c in " ._-")
    file_path = os.path.join(user_docs_dir, safe_name)

    await file.download_to_drive(file_path)

    size_mb = doc.file_size / 1024 / 1024
    job_id = str(uuid.uuid4())
    set_job(job_id, {
        "status": "queued",
        "filename": safe_name,
        "size_mb": round(size_mb, 2),
    })
    document_queue.put((job_id, file_path, user_id))

    await update.message.reply_text(f"File '{safe_name}' queued for processing. It will take a few moments.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages for username registration and querying."""
    if context.user_data.get('awaiting_username'):
        username = update.effective_user.username or ""
        if not username:
            username = update.message.text.strip() if update.message.text else ""

        user_id = register_user(context, username)
        if user_id:
            await update.message.reply_text(
                f"Username: {username} registered. You can now send me PDF documents (limit 10) and ask questions about them."
            )
            context.user_data['awaiting_username'] = False
        else:
            await update.message.reply_text("Could not register that username. Please try again.")
        return

    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and send your username first.")
        return

    question = update.message.text
    if not question:
        return

    await update.message.chat.send_action(action="typing")

    try:
        from app.services.history import get_chat_sessions, create_chat_session

        sessions = get_chat_sessions(user_id)
        if not sessions:
            session_id = create_chat_session(user_id, "Telegram Chat")
        else:
            session_id = sessions[-1]['id']

        thinking_message = await update.message.reply_text("Thinking...")
        response_parts: list[str] = []
        buffer = ""
        post_thinking = False

        stream = answer_question_stream(question, user_id, session_id)
        for chunk in stream:
            if not chunk.startswith("data: "):
                continue
            try:
                data = json.loads(chunk[6:])
            except Exception:
                continue

            if data.get("type") == "token":
                token = data.get("content", "")
                if not token:
                    continue

                if not post_thinking:
                    buffer += token
                    if "</thinking>" in buffer:
                        post_thinking = True
                        remainder = buffer.split("</thinking>", 1)[1].lstrip()
                        if remainder:
                            response_parts = [remainder]
                            await thinking_message.edit_text("".join(response_parts))
                            await asyncio.sleep(0)
                else:
                    response_parts.append(token)
                    await thinking_message.edit_text("".join(response_parts))
                    await asyncio.sleep(0)
            elif data.get("type") == "error":
                error_message = data.get("content", "I couldn't find an answer in your documents.")
                await thinking_message.edit_text(error_message)
                return

        if response_parts:
            await thinking_message.edit_text("".join(response_parts))
        else:
            clean_buffer = re.sub(r'<thinking>.*', '', buffer, flags=re.DOTALL).strip()
            final_answer = clean_buffer if clean_buffer else "I couldn't find an answer in your documents."
            await thinking_message.edit_text(final_answer)

    except FileNotFoundError:
        await update.message.reply_text("You haven't uploaded any PDF documents yet. Please send a PDF first.")
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        await update.message.reply_text("An error occurred while answering your question.")


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in config.")
        return

    from telegram.ext import PicklePersistence
    persistence = PicklePersistence(filepath="telegram_bot_data.pickle")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Start background worker for document processing
    from threading import Thread
    from app.services.worker import process_documents
    worker_thread = Thread(target=process_documents, daemon=True, name="doc-worker")
    worker_thread.start()

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
