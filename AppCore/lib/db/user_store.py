"""
STAINLESS MAX - User Database & Encryption Store
Handles SQLite databases for users, usage stats, promo codes, and AES API key encryption.
"""

import sqlite3
import json
import os
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import base64
from cryptography.fernet import Fernet
import bcrypt

class UserStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.data_dir / 'stainless.db'
        self.key_path = self.data_dir / 'app.key'
        
        self._init_encryption_key()
        self._init_db()
        
    def _init_encryption_key(self):
        """Uygulama başına benzersiz AES anahtarı oluştur veya yükle"""
        if not self.key_path.exists():
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
        
        with open(self.key_path, 'rb') as f:
            self.cipher = Fernet(f.read())
            
    def encrypt_json(self, data: dict) -> str:
        """Sözlüğü JSON'a çevirip şifreler"""
        if not data:
            return ""
        json_str = json.dumps(data)
        return self.cipher.encrypt(json_str.encode()).decode()
        
    def decrypt_json(self, encrypted_str: str) -> dict:
        """Şifreli veriyi çözüp sözlük döndürür"""
        if not encrypted_str:
            return {}
        try:
            json_str = self.cipher.decrypt(encrypted_str.encode()).decode()
            return json.loads(json_str)
        except Exception:
            return {}

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Veritabanı tablolarını oluştur (Yoksa)"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Users tablosu
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    surname TEXT,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    plan TEXT DEFAULT 'free',
                    promo_code TEXT,
                    api_keys_encrypted TEXT,
                    accounts_encrypted TEXT,
                    setup_complete BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            ''')
            
            # Geriye dönük uyumluluk (Mevcut tabloya accounts_encrypted sütununu ekle)
            try:
                c.execute("ALTER TABLE users ADD COLUMN accounts_encrypted TEXT")
            except sqlite3.OperationalError:
                pass # Sütun zaten varsa hata verir, yoksay
            
            # Daily Usage tablosu
            c.execute('''
                CREATE TABLE IF NOT EXISTS daily_usage (
                    user_id TEXT,
                    date TEXT,
                    videos_produced INTEGER DEFAULT 0,
                    videos_shared INTEGER DEFAULT 0,
                    platform_views INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                )
            ''')
            
            # Promo Codes tablosu
            c.execute('''
                CREATE TABLE IF NOT EXISTS promo_codes (
                    code TEXT PRIMARY KEY,
                    plan_grant TEXT,
                    expires_at TIMESTAMP,
                    max_uses INTEGER DEFAULT 0,
                    use_count INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Admin Logs
            c.execute('''
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT,
                    user_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            ''')
            
            conn.commit()
            
            # Varsayılan ADMIN promo kodunu ekge (Sadece 1 kez)
            self._ensure_default_promo(c)
            conn.commit()

    def _ensure_default_promo(self, cursor):
        """Sistemin ana promo kodunu (ardigilu5035) otomatik ekle"""
        code = "ardigilu5035"
        cursor.execute("SELECT code FROM promo_codes WHERE code = ?", (code,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO promo_codes (code, plan_grant, max_uses, active)
                VALUES (?, ?, ?, ?)
            ''', (code, 'ultra', 10000, 1))

    # --- KULLANICI İŞLEMLERİ ---

    def create_user(self, name: str, surname: str, email: str, password_hash: str, promo_code: str = "") -> str:
        with self.get_connection() as conn:
            c = conn.cursor()
            user_id = str(uuid.uuid4())
            
            plan = "free"
            
            # Eğer promo code geçerli ise planı yükselt
            if promo_code:
                c.execute("SELECT plan_grant, use_count, max_uses FROM promo_codes WHERE code = ? AND active = 1", (promo_code,))
                promo = c.fetchone()
                if promo and (promo['max_uses'] == 0 or promo['use_count'] < promo['max_uses']):
                    plan = promo['plan_grant']
                    c.execute("UPDATE promo_codes SET use_count = use_count + 1 WHERE code = ?", (promo_code,))
            
            c.execute('''
                INSERT INTO users (id, name, surname, email, password_hash, plan, promo_code, api_keys_encrypted, accounts_encrypted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, surname, email, password_hash, plan, promo_code, self.encrypt_json({}), self.encrypt_json({"accounts": []})))
            
            conn.commit()
            return user_id

    def get_user_by_email(self, email: str) -> Optional[dict]:
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            if row:
                d = dict(row)
                d['api_keys'] = self.decrypt_json(d.get('api_keys_encrypted', ''))
                d['accounts'] = self.decrypt_json(d.get('accounts_encrypted', ''))
                return d
            return None

    def update_user_api_keys(self, user_id: str, new_keys: dict):
        encrypted = self.encrypt_json(new_keys)
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET api_keys_encrypted = ?, setup_complete = 1 WHERE id = ?", (encrypted, user_id))
            conn.commit()
            
    def get_user_accounts(self, user_id: str) -> dict:
        """Kullanıcının platform hesaplarını JSON formatında getirir"""
        user = self.get_user_by_id(user_id)
        if user and user.get('accounts'):
            return user['accounts']
        return {"accounts": []}
        
    def update_user_accounts(self, user_id: str, accounts_data: dict):
        """Kullanıcının platform hesaplarını kaydeder"""
        encrypted = self.encrypt_json(accounts_data)
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET accounts_encrypted = ? WHERE id = ?", (encrypted, user_id))
            conn.commit()
            
    def update_user_password(self, user_id: str, new_password_hash: str):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
            conn.commit()

    def update_last_login(self, user_id: str):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            conn.commit()
            
    def update_user_plan(self, user_id: str, new_plan: str):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET plan = ? WHERE id = ?", (new_plan, user_id))
            conn.commit()

    def apply_promo_code(self, user_id: str, code: str) -> bool:
        """Promosyon kodu girilince planı yükselt"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT plan_grant, use_count, max_uses FROM promo_codes WHERE code = ? AND active = 1", (code,))
            promo = c.fetchone()
            if promo and (promo['max_uses'] == 0 or promo['use_count'] < promo['max_uses']):
                plan = promo['plan_grant']
                c.execute("UPDATE promo_codes SET use_count = use_count + 1 WHERE code = ?", (code,))
                c.execute("UPDATE users SET plan = ?, promo_code = ? WHERE id = ?", (plan, code, user_id))
                conn.commit()
                return True
        return False

    # --- KULLANIM (QUOTA) İŞLEMLERİ ---
    
    def get_today_usage(self, user_id: str) -> dict:
        today = datetime.now().strftime('%Y-%m-%d')
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM daily_usage WHERE user_id = ? AND date = ?", (user_id, today))
            row = c.fetchone()
            if row:
                return dict(row)
            return {'videos_produced': 0, 'videos_shared': 0, 'platform_views': 0}

    def increment_usage(self, user_id: str, field: str, amount: int = 1):
        if field not in ['videos_produced', 'videos_shared', 'platform_views']:
            return
            
        today = datetime.now().strftime('%Y-%m-%d')
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT user_id FROM daily_usage WHERE user_id = ? AND date = ?", (user_id, today))
            if not c.fetchone():
                c.execute("INSERT INTO daily_usage (user_id, date, videos_produced, videos_shared, platform_views) VALUES (?, ?, 0, 0, 0)", (user_id, today))
            
            c.execute(f"UPDATE daily_usage SET {field} = {field} + ? WHERE user_id = ? AND date = ?", (amount, user_id, today))
            conn.commit()

    # --- ADMIN İŞLEMLERİ ---
    
    def get_all_users(self) -> List[dict]:
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, surname, email, plan, promo_code, setup_complete, created_at, last_login FROM users ORDER BY created_at DESC")
            return [dict(r) for r in c.fetchall()]

    def log_admin_event(self, event: str, user_id: str, details: str):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO admin_logs (event, user_id, details) VALUES (?, ?, ?)", (event, user_id, details))
            conn.commit()

    def create_promo_code(self, code: str, target_plan: str, max_uses: int):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO promo_codes (code, plan_grant, max_uses, active) VALUES (?, ?, ?, 1)", (code, target_plan, max_uses))
            conn.commit()

