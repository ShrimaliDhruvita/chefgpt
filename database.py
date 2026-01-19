import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

class Database:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_recipes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    recipe_title TEXT NOT NULL,
                    recipe_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
    
    def hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, email: str, password: str, name: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
                    (email, self.hash_password(password), name)
                )
                return True
        except sqlite3.IntegrityError:
            return False
    
    def verify_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, email, name FROM users WHERE email = ? AND password_hash = ? AND is_active = 1",
                (email, self.hash_password(password))
            )
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "email": row[1], "name": row[2]}
        return None
    
    def create_session(self, user_id: int) -> str:
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(days=7)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
                (user_id, session_token, expires_at)
            )
        return session_token
    
    def get_user_by_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT u.id, u.email, u.name 
                FROM users u 
                JOIN sessions s ON u.id = s.user_id 
                WHERE s.session_token = ? AND s.expires_at > datetime('now') AND u.is_active = 1
            """, (session_token,))
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "email": row[1], "name": row[2]}
        return None
    
    def delete_session(self, session_token: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
    
    def save_recipe(self, user_id: int, recipe_title: str, recipe_data: str) -> int:
        """Save a recipe for user. Returns recipe id."""
        import json
        # Validate recipe_data is valid JSON
        try:
            json.loads(recipe_data)
        except json.JSONDecodeError:
            raise ValueError("Invalid recipe data format")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO saved_recipes (user_id, recipe_title, recipe_data) VALUES (?, ?, ?)",
                (user_id, recipe_title, recipe_data)
            )
            return cursor.lastrowid
    
    def get_user_recipes(self, user_id: int) -> list:
        """Get all saved recipes for a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, recipe_title, recipe_data, created_at FROM saved_recipes WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recipe(self, recipe_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific recipe if it belongs to the user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, recipe_title, recipe_data, created_at FROM saved_recipes WHERE id = ? AND user_id = ?",
                (recipe_id, user_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def delete_recipe(self, recipe_id: int, user_id: int) -> bool:
        """Delete a recipe if it belongs to the user. Returns True if deleted."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM saved_recipes WHERE id = ? AND user_id = ?",
                (recipe_id, user_id)
            )
            return cursor.rowcount > 0

db = Database()