"""
Lightweight SQLite-based Chat History and Authentication Manager.
"""
import sqlite3
import os
import json
import uuid
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "chat_history.db")

def init_db():
    """Initialize SQLite database with Auth and Chat tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Auth Sessions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Chat Sessions (Threads)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Messages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT DEFAULT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)')
    
    # Guest IP Usage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ip_usage (
            ip_address TEXT PRIMARY KEY,
            question_count INTEGER DEFAULT 0,
            last_used DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ── IP Usage Helpers ────────────────────────────────────────────────────────

def get_ip_usage(ip_address: str) -> int:
    """Get the number of questions asked by a guest IP."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT question_count FROM ip_usage WHERE ip_address = ?', (ip_address,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def increment_ip_usage(ip_address: str):
    """Increment the question count for a guest IP."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ip_usage (ip_address, question_count, last_used)
        VALUES (?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(ip_address) DO UPDATE SET 
            question_count = question_count + 1,
            last_used = CURRENT_TIMESTAMP
    ''', (ip_address,))
    conn.commit()
    conn.close()

# ── Auth Helpers ────────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    """Hash password using PBKDF2 (zero dependency)."""
    return hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    ).hex()

def create_user(username: str, password: str) -> Optional[int]:
    """Create a new user. Returns user_id or None if username exists."""
    salt = uuid.uuid4().hex
    password_hash = _hash_password(password, salt)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)',
            (username, password_hash, salt)
        )
        user_id = cursor.lastrowid
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def verify_user(username: str, password: str) -> Optional[int]:
    """Verify credentials and return user_id if valid."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, salt FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
        
    user_id, stored_hash, salt = row
    if _hash_password(password, salt) == stored_hash:
        return user_id
    return None

def create_session(user_id: int) -> str:
    """Create and return a new session token."""
    token = "sk_" + uuid.uuid4().hex + uuid.uuid4().hex
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO auth_sessions (token, user_id) VALUES (?, ?)', (token, user_id))
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """Get user details from an auth token."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username 
        FROM auth_sessions s 
        JOIN users u ON s.user_id = u.id 
        WHERE s.token = ?
    ''', (token,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def delete_session(token: str):
    """Log out by deleting the session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM auth_sessions WHERE token = ?', (token,))
    conn.commit()
    conn.close()

# ── Chat Helpers ────────────────────────────────────────────────────────────

def create_chat_session(user_id: int, title: str) -> str:
    """Create a new chat session and return its ID."""
    session_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO chat_sessions (id, user_id, title)
        VALUES (?, ?, ?)
    ''', (session_id, user_id, title))
    conn.commit()
    conn.close()
    return session_id

def get_chat_sessions(user_id: int) -> List[Dict[str, Any]]:
    """Retrieve all chat sessions for a user, newest first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, created_at
        FROM chat_sessions
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_message(session_id: str, role: str, content: str, metadata: list = None):
    """Save a message to the history with optional RAG metadata."""
    meta_json = json.dumps(metadata) if metadata else None
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (session_id, role, content, metadata)
        VALUES (?, ?, ?, ?)
    ''', (session_id, role, content, meta_json))
    conn.commit()
    conn.close()

def get_history(session_id: str, user_id: Any, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve the last N messages for a chat session, verifying ownership."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.role, m.content, m.metadata, m.timestamp 
        FROM messages m
        JOIN chat_sessions s ON m.session_id = s.id
        WHERE m.session_id = ? AND s.user_id = ?
        ORDER BY m.id DESC 
        LIMIT ?
    ''', (session_id, user_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in reversed(rows):
        d = dict(row)
        if d['metadata']:
            d['metadata'] = json.loads(d['metadata'])
        results.append(d)
        
    return results

def delete_chat_session(session_id: str, user_id: Any):
    """Delete a chat session and all its messages, verifying ownership."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM chat_sessions WHERE id = ? AND user_id = ?', (session_id, user_id))
    conn.commit()
    conn.close()

def verify_session_ownership(session_id: str, user_id: Any) -> bool:
    """Check if a session belongs to a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM chat_sessions WHERE id = ? AND user_id = ?', (session_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return bool(row)

# Initialize DB on import
init_db()

def migrate_chat_sessions(guest_id: str, new_user_id: int):
    """Migrate all chat sessions from a guest ID to a new permanent user ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE chat_sessions 
        SET user_id = ? 
        WHERE user_id = ?
    ''', (new_user_id, guest_id))
    conn.commit()
    conn.close()
