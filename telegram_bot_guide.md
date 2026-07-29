# Telegram Bot Guide

This guide covers everything you need to know to run, maintain, and interact with the RAG Assistant Telegram Bot.

## 1. Prerequisites

Before running the bot, ensure you have the required dependencies and a valid Bot API Token.

1. **Install Dependencies:**
   Make sure you have installed all requirements, specifically the Telegram library:
   ```bash
   pip install -r requirements.txt
   ```
   *(Or run `pip install python-telegram-bot` if you haven't yet).*

2. **Get a Bot Token:**
   - Open Telegram and search for `@BotFather`.
   - Send the `/newbot` command and follow the prompts to name your bot.
   - BotFather will provide an HTTP API Token (e.g., `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`).

3. **Configure Environment:**
   Create or edit the `.env` file in the root of your project directory and add your token:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   ```

## 2. Running the Bot

Because the bot uses **long-polling**, it does not require Nginx or the FastAPI web server to be running. It handles its own internet traffic.

To start the bot, simply run:
```bash
python telegram_bot.py
```

### Running in the background
To ensure the bot continues running even after you close your SSH terminal, use a background process manager like `screen` or `tmux`.

**Using `screen`:**
1. Start a new session: `screen -S mybot`
2. Run the bot: `python telegram_bot.py`
3. Detach from the session: Press `Ctrl+A`, then press `D`.
4. (To reattach later, use `screen -r mybot`).

## 3. How Users Interact with the Bot

1. **Registration:**
   - Users send `/start` to the bot.
   - The bot replies with a keyboard button asking them to "Share Phone Number 📱".
   - Once clicked, Telegram securely passes their phone number to the bot.
   - The bot uses this number to create a unique user account in the internal database.

2. **Uploading Documents:**
   - Users can send any `.pdf` file directly to the chat.
   - The bot verifies the user hasn't exceeded the **10 PDF limit**.
   - If within the limit, it downloads the PDF and queues it for the background FAISS vector database processing.

3. **Asking Questions:**
   - Users just type a text message (e.g., "What are the main skills listed in my document?").
   - The bot retrieves the answer using the RAG pipeline and replies directly in the chat.
   - *Note: There are no hourly limits on questions.*

## 4. Architecture Notes

- **Concurrency**: The bot leverages `asyncio.to_thread()` when querying the LLM and FAISS database. This ensures that a heavy question from User A will not block User B from registering or asking a question at the same time.
- **Background Worker**: The script automatically starts the document ingestion worker thread (`process_documents`) in the background, so you do not need to run a separate ingestion script.
- **Webhooks vs Long-Polling**: Currently, the bot uses long-polling (`run_polling()`), which simplifies setup (no SSL certificates or open firewall ports required). If you scale to thousands of active users, you may eventually want to migrate to a Webhook architecture.
