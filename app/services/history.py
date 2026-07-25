"""
Lightweight SQLite-based Chat History Manager.
"""
import sqlite3
import os
import json
from datetime import datetime
from app.config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "chat_history.db")

def init_db():
    """Create the messages table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_id ON messages(session_id)')
    conn.commit()
    conn.close()

def add_message(session_id: str, role: str, content: str):
    """Save a single message to the history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (session_id, role, content)
        VALUES (?, ?, ?)
    ''', (session_id, role, content))
    conn.commit()
    conn.close()

def get_history(session_id: str, limit: int = 10) -> list:
    """Retrieve the last N messages for a given session."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # We fetch the last N messages, ordered by descending id to get the latest,
    # then reverse them to return in chronological order.
    cursor.execute('''
        SELECT role, content, timestamp 
        FROM messages 
        WHERE session_id = ? 
        ORDER BY id DESC 
        LIMIT ?
    ''', (session_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Return chronologically
    return [dict(row) for row in reversed(rows)]

def clear_history(session_id: str):
    """Delete all messages for a session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()
