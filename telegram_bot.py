import os
import uuid
import logging
import asyncio
from typing import Optional

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
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

def get_user_by_phone(phone: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (phone,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message with a button to share contact."""
    contact_keyboard = KeyboardButton(text="Share Phone Number 📱", request_contact=True)
    custom_keyboard = [[contact_keyboard]]
    reply_markup = ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Welcome to the RAG Assistant!\nPlease share your phone number to continue.",
        reply_markup=reply_markup
    )

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle shared contact."""
    contact = update.message.contact
    phone = contact.phone_number
    
    # Check or create user
    user_id = get_user_by_phone(phone)
    if not user_id:
        user_id = create_user(phone, "dummy_password_for_telegram")
        if not user_id:
            # Fallback if created concurrently
            user_id = get_user_by_phone(phone)
            
    context.user_data['user_id'] = user_id
    
    await update.message.reply_text(
        "Successfully registered! You can now send me PDF documents (limit 10) and ask questions about them."
    )

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle PDF uploads."""
    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and share your contact first.")
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
    """Handle text messages for querying."""
    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and share your contact first.")
        return

    question = update.message.text
    if not question:
        return
        
    await update.message.chat.send_action(action="typing")
    
    try:
        # We pass None for session_id. The RAG pipeline will need to handle this.
        # However, answer_question_stream requires a session_id. Let's create a single session for the telegram chat.
        from app.services.history import get_chat_sessions, create_chat_session
        
        sessions = get_chat_sessions(user_id)
        if not sessions:
            session_id = create_chat_session(user_id, "Telegram Chat")
        else:
            session_id = sessions[-1]['id']  # use latest session
            
        def get_full_response():
            stream = answer_question_stream(question, user_id, session_id)
            full_resp = ""
            for chunk in stream:
                # The chunks from answer_question_stream are SSE JSON strings
                import json
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:])
                        if data.get("type") == "token":
                            full_resp += data.get("content", "")
                        elif data.get("type") == "error":
                            return data.get("content", "")
                    except Exception:
                        pass
            return full_resp
            
        full_response = await asyncio.to_thread(get_full_response)
        
        if not full_response:
            full_response = "I couldn't find an answer in your documents."
            
        await update.message.reply_text(full_response)
        
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
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
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
