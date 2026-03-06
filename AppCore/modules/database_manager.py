"""
Database Manager - SQLite Entegrasyonu
Video, hesap, log ve istatistik yönetimi
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class VideoRecord:
    id: int
    account_id: str
    platform: str
    title: str
    video_path: str
    status: str  # pending, approved, rejected, uploaded, failed
    created_at: str
    published_at: Optional[str]
    views: int
    likes: int
    error_message: Optional[str]


class DatabaseManager:
    """SQLite veritabanı yöneticisi"""
    
    def __init__(self, db_path: str = "database/app.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Veritabanı şemasını oluştur"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Videos tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL,
                    video_path TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    published_at TEXT,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    error_message TEXT,
                    metadata TEXT
                )
            """)
            
            # Account stats tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT UNIQUE NOT NULL,
                    platform TEXT NOT NULL,
                    total_videos INTEGER DEFAULT 0,
                    successful_uploads INTEGER DEFAULT 0,
                    failed_uploads INTEGER DEFAULT 0,
                    last_upload_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # System logs tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    component TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            """)
            
            # IP rotations tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ip_rotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    old_ip TEXT,
                    new_ip TEXT,
                    success BOOLEAN,
                    account_id TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Queue tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    script TEXT,
                    status TEXT DEFAULT 'waiting',  -- waiting, processing, completed, failed
                    priority INTEGER DEFAULT 5,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    processed_at TEXT,
                    error_message TEXT
                )
            """)
            
            # Analytics tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    videos_created INTEGER DEFAULT 0,
                    videos_uploaded INTEGER DEFAULT 0,
                    total_views INTEGER DEFAULT 0,
                    total_likes INTEGER DEFAULT 0,
                    accounts_used INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0
                )
            """)
            
            conn.commit()
    
    def add_video(self, account_id: str, platform: str, title: str, 
                  video_path: str = None, metadata: dict = None) -> int:
        """Yeni video ekle"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO videos (account_id, platform, title, video_path, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (account_id, platform, title, video_path, 
                  json.dumps(metadata) if metadata else None))
            conn.commit()
            return cursor.lastrowid
    
    def update_video_status(self, video_id: int, status: str, 
                           error_message: str = None, **kwargs):
        """Video durumunu güncelle"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            fields = ["status = ?"]
            values = [status]
            
            if error_message:
                fields.append("error_message = ?")
                values.append(error_message)
            
            if status == "uploaded":
                fields.append("published_at = CURRENT_TIMESTAMP")
            
            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)
            
            values.append(video_id)
            
            query = f"UPDATE videos SET {', '.join(fields)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
    
    def get_pending_videos(self) -> List[VideoRecord]:
        """Bekleyen videoları getir"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM videos 
                WHERE status IN ('pending', 'processing')
                ORDER BY created_at DESC
            """)
            return [VideoRecord(**dict(row)) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict:
        """Genel istatistikler"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Toplam video
            cursor.execute("SELECT COUNT(*) FROM videos")
            total = cursor.fetchone()[0]
            
            # Yayınlanan
            cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'uploaded'")
            published = cursor.fetchone()[0]
            
            # Başarısız
            cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'failed'")
            failed = cursor.fetchone()[0]
            
            # Bekleyen
            cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'pending'")
            pending = cursor.fetchone()[0]
            
            # Bugün
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT COUNT(*) FROM videos 
                WHERE DATE(created_at) = ?
            """, (today,))
            today_count = cursor.fetchone()[0]
            
            return {
                "total": total,
                "published": published,
                "failed": failed,
                "pending": pending,
                "today": today_count
            }
    
    def add_log(self, level: str, component: str, message: str, details: str = None):
        """Sistem logu ekle"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_logs (level, component, message, details)
                VALUES (?, ?, ?, ?)
            """, (level, component, message, details))
            conn.commit()
    
    def get_logs(self, limit: int = 100) -> List[Dict]:
        """Son logları getir"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM system_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def add_to_queue(self, account_id: str, title: str, script: str = None, 
                     priority: int = 5) -> int:
        """Video kuyruğa ekle"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO video_queue (account_id, title, script, priority)
                VALUES (?, ?, ?, ?)
            """, (account_id, title, script, priority))
            conn.commit()
            return cursor.lastrowid
    
    def get_queue(self, status: str = "waiting") -> List[Dict]:
        """Kuyruktaki videoları getir"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM video_queue
                WHERE status = ?
                ORDER BY priority ASC, created_at ASC
            """, (status,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_queue_status(self, queue_id: int, status: str, error: str = None):
        """Kuyruk durumunu güncelle"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if status == "completed":
                cursor.execute("""
                    UPDATE video_queue 
                    SET status = ?, processed_at = CURRENT_TIMESTAMP, error_message = ?
                    WHERE id = ?
                """, (status, error, queue_id))
            else:
                cursor.execute("""
                    UPDATE video_queue 
                    SET status = ?, error_message = ?
                    WHERE id = ?
                """, (status, error, queue_id))
            conn.commit()
    
    def update_analytics(self, date: str = None, **kwargs):
        """Analytics güncelle"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if exists
            cursor.execute("SELECT id FROM analytics WHERE date = ?", (date,))
            if cursor.fetchone():
                # Update
                fields = [f"{k} = {k} + ?" for k in kwargs.keys()]
                values = list(kwargs.values()) + [date]
                query = f"UPDATE analytics SET {', '.join(fields)} WHERE date = ?"
                cursor.execute(query, values)
            else:
                # Insert
                keys = ["date"] + list(kwargs.keys())
                values = [date] + list(kwargs.values())
                placeholders = ", ".join(["?"] * len(keys))
                query = f"INSERT INTO analytics ({', '.join(keys)}) VALUES ({placeholders})"
                cursor.execute(query, values)
            
            conn.commit()
    
    def get_analytics(self, days: int = 30) -> List[Dict]:
        """Analytics verilerini getir"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM analytics
                ORDER BY date DESC
                LIMIT ?
            """, (days,))
            return [dict(row) for row in cursor.fetchall()]


# Global instance
db_manager = DatabaseManager()
