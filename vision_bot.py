import os
import logging
import asyncio
import base64
import re
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PicklePersistence

from app.config import VISION_BOT_TOKEN, GROQ_API_KEY
from app.services.history import create_user, DB_PATH
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
        context.user_data['vision_model'] = 'qwen/qwen3.6-27b'

    return user_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for the username instead of requesting a phone number."""
    context.user_data['awaiting_username'] = True
    await update.message.reply_text(
        "Welcome to the Vision Assistant!\n"
        "Please send your username to continue.\n"
        "After registering, you can send me an image and then ask questions about it!"
    )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image uploads and save them as base64 in session."""
    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and send your username first.")
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
    """Handle username registration and text questions regarding the uploaded image."""
    if context.user_data.get('awaiting_username'):
        username = update.message.text.strip() if update.message.text else ""
        if not username:
            return

        user_id = register_user(context, username)
        if user_id:
            await update.message.reply_text(
                "Successfully registered! \n\n"
                "Send me any image, and then ask me a question about it."
            )
        else:
            await update.message.reply_text("Could not register that username. Please try again.")
        return

    user_id = context.user_data.get('user_id')
    if not user_id:
        await update.message.reply_text("Please use /start and send your username first.")
        return

    question = update.message.text
    base64_img = context.user_data.get('last_image')

    if not base64_img:
        await update.message.reply_text("Please send an image first.")
        return

    await process_vision_question(update, context, question, base64_img)


async def process_vision_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str, base64_img: str):
    """Stream the Groq Vision response and update the same message as the answer appears."""
    await update.message.chat.send_action(action="typing")

    model_name = context.user_data.get('vision_model', 'qwen/qwen3.6-27b')
    thinking_message = await update.message.reply_text("Thinking...")

    def call_groq_stream():
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        return client.chat.completions.create(
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
            stream=True,
        )

    try:
        stream = await asyncio.to_thread(call_groq_stream)
        buffer = ""
        answer_buffer = ""
        post_thinking = False

        for chunk in stream:
            content = None
            if getattr(chunk, "choices", None):
                delta = chunk.choices[0].delta if hasattr(chunk.choices[0], "delta") else None
                if delta is not None and hasattr(delta, "content"):
                    content = delta.content
            if not content:
                continue

            if not post_thinking:
                buffer += content
                if "</thinking>" in buffer:
                    post_thinking = True
                    remainder = buffer.split("</thinking>", 1)[1].lstrip()
                    if remainder:
                        answer_buffer = remainder
                        await thinking_message.edit_text(answer_buffer)
                        await asyncio.sleep(0)
            else:
                answer_buffer += content
                await thinking_message.edit_text(answer_buffer)
                await asyncio.sleep(0)

        if not answer_buffer:
            cleaned = re.sub(r'<thinking>.*?</thinking>', '', buffer, flags=re.DOTALL).strip()
            answer_buffer = cleaned if cleaned else "Sorry, I couldn't generate a response."

        if answer_buffer:
            await thinking_message.edit_text(answer_buffer)
        else:
            await thinking_message.edit_text("Sorry, I couldn't generate a response.")
    except Exception as e:
        logger.error(f"Vision API error: {e}")
        await thinking_message.edit_text("Sorry, an error occurred while analyzing the image.")


def main() -> None:
    """Start the Vision bot."""
    if not VISION_BOT_TOKEN:
        logger.error("VISION_BOT_TOKEN is not set in config.")
        return

    persistence = PicklePersistence(filepath="vision_bot_data.pickle")
    application = Application.builder().token(VISION_BOT_TOKEN).persistence(persistence).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
