import os
import logging
import asyncio
import base64
from typing import Optional

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PicklePersistence

from app.config import VISION_BOT_TOKEN, GROQ_API_KEY
from app.services.history import create_user, DB_PATH
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
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
        "Welcome to the Vision Assistant!\n"
        "Please share your phone number to continue.\n"
        "After registering, you can send me an image and then ask questions about it!",
        reply_markup=reply_markup
    )

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle shared contact."""
    contact = update.message.contact
    phone = contact.phone_number
    
    user_id = get_user_by_phone(phone)
    if not user_id:
        user_id = create_user(phone, "dummy_password_for_telegram")
        if not user_id:
            user_id = get_user_by_phone(phone)
            
    context.user_data['user_id'] = user_id
    context.user_data['vision_model'] = 'qwen/qwen3.6-27b'
    
    await update.message.reply_text(
        "Successfully registered! \n\n"
        "Send me any image, and then ask me a question about it."
    )

# Removed model_command since only one model is allowed

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image uploads and save them as base64 in session."""
    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and share your contact first.")
        return

    # Telegram sends multiple sizes. Grab the largest one (last in the array).
    photo_file = update.message.photo[-1]
    file = await context.bot.get_file(photo_file.file_id)
    
    # Download as bytes
    byte_array = await file.download_as_bytearray()
    
    # Encode as base64
    base64_img = base64.b64encode(byte_array).decode('utf-8')
    context.user_data['last_image'] = base64_img
    
    # If the user included a caption, we can treat it as a question immediately
    caption = update.message.caption
    if caption:
        await process_vision_question(update, context, caption, base64_img)
    else:
        await update.message.reply_text("Image saved! What would you like to know about it?")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text questions regarding the uploaded image."""
    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and share your contact first.")
        return

    question = update.message.text
    base64_img = context.user_data.get('last_image')
    
    if not base64_img:
        await update.message.reply_text("Please send an image first.")
        return

    await process_vision_question(update, context, question, base64_img)

async def process_vision_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str, base64_img: str):
    """Run the Groq Vision model in a background thread."""
    await update.message.chat.send_action(action="typing")
    
    model_name = context.user_data.get('vision_model', 'qwen/qwen3.6-27b')
    
    def call_groq():
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_img}",
                            },
                        },
                    ],
                }
            ],
            model=model_name,
        )
        return chat_completion.choices[0].message.content

    try:
        answer = await asyncio.to_thread(call_groq)
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(f"Vision API error: {e}")
        await update.message.reply_text("Sorry, an error occurred while analyzing the image.")

def main() -> None:
    """Start the Vision bot."""
    if not VISION_BOT_TOKEN:
        logger.error("VISION_BOT_TOKEN is not set in config.")
        return

    persistence = PicklePersistence(filepath="vision_bot_data.pickle")
    application = Application.builder().token(VISION_BOT_TOKEN).persistence(persistence).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
