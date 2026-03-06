"""
Analytics Manager - Geri Bildirim Döngüsü (Feedback Loop)
48 saat sonra viral videoların hookları kaydedilir ve yeni üretimlerde kullanılır
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AnalyticsManager:
    """
    Video performansını takip edip başarılı hookları öğrenen sistem
    
    VideoTracker'dan farklı olarak:
    - Daha basit yapı (uploads tablosu)
    - successful_hooks.json ile feedback
    - Gemini entegrasyonu için optimize
    """
    
    VIRAL_THRESHOLD = 10000  # 10K+ izlenme = viral
    
    def __init__(self, db_path: str = "data/uploads.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.hooks_file = Path("data/successful_hooks.json")
        self.hooks_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
    
    def _init_database(self):
        """SQLite veritabanını başlat ve sütunları kontrol et"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            
            # uploads tablosu oluştur
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT UNIQUE,
                    platform TEXT,
                    url TEXT,
                    upload_time DATETIME,
                    script_hook TEXT,
                    view_count INTEGER DEFAULT 0,
                    checked BOOLEAN DEFAULT 0
                )
            """)
            
            # Sütunları kontrol et ve eksikleri ekle
            cursor.execute("PRAGMA table_info(uploads)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # view_count yoksa ekle
            if 'view_count' not in columns:
                cursor.execute("ALTER TABLE uploads ADD COLUMN view_count INTEGER DEFAULT 0")
                logger.info("✅ view_count sütunu eklendi")
            
            # script_hook yoksa ekle
            if 'script_hook' not in columns:
                cursor.execute("ALTER TABLE uploads ADD COLUMN script_hook TEXT")
                logger.info("✅ script_hook sütunu eklendi")
            
            # checked yoksa ekle
            if 'checked' not in columns:
                cursor.execute("ALTER TABLE uploads ADD COLUMN checked BOOLEAN DEFAULT 0")
                logger.info("✅ checked sütunu eklendi")
            
            conn.commit()
            logger.info(f"✅ Analytics Manager database initialized: {self.db_path}")
        finally:
            conn.close()
    
    def track_upload(self, video_id: str, platform: str, url: str, script_hook: str):
        """
        Video upload kaydı
        
        Args:
            video_id: Unique video ID
            platform: tiktok, youtube, instagram
            url: Video URL
            script_hook: İlk 3 saniyedeki hook cümlesi
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO uploads 
                    (video_id, platform, url, upload_time, script_hook, view_count, checked)
                    VALUES (?, ?, ?, ?, ?, 0, 0)
                """, (video_id, platform, url, datetime.now(), script_hook))
                
                conn.commit()
                logger.info(f"✅ Upload tracked: {video_id} - '{script_hook[:30]}...'")
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Track upload error: {e}")
    
    def update_view_count(self, video_id: str, view_count: int):
        """Video izlenme sayısını güncelle"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE uploads 
                    SET view_count = ?, checked = 1
                    WHERE video_id = ?
                """, (view_count, video_id))
                
                conn.commit()
                logger.info(f"✅ View count updated: {video_id} → {view_count:,} views")
                
                # Viral ise hook'u kaydet
                if view_count >= self.VIRAL_THRESHOLD:
                    self._save_viral_hook(video_id)
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Update view count error: {e}")
    
    def _save_viral_hook(self, video_id: str):
        """Viral videonun hook'unu successful_hooks.json'a kaydet"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT script_hook, view_count, platform
                    FROM uploads
                    WHERE video_id = ?
                """, (video_id,))
                
                row = cursor.fetchone()
                
                if not row or not row[0]:
                    return
                
                script_hook, view_count, platform = row
                
                # Mevcut hookları oku
                if self.hooks_file.exists():
                    with open(self.hooks_file, 'r', encoding='utf-8') as f:
                        hooks_data = json.load(f)
                else:
                    hooks_data = {'hooks': []}
                
                # Yeni viral hook ekle
                hooks_data['hooks'].append({
                    'hook': script_hook,
                    'views': view_count,
                    'platform': platform,
                    'date': datetime.now().isoformat()
                })
                
                # Dosyaya kaydet
                with open(self.hooks_file, 'w', encoding='utf-8') as f:
                    json.dump(hooks_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"🔥 VIRAL HOOK SAVED: '{script_hook}' ({view_count:,} views)")
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Save viral hook error: {e}")
    
    def get_pending_checks(self, hours_ago: int = 48) -> List[Dict]:
        """48 saat geçmiş, henüz kontrol edilmemiş videoları al"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cutoff_time = datetime.now() - timedelta(hours=hours_ago)
                
                cursor.execute("""
                    SELECT *
                    FROM uploads
                    WHERE checked = 0
                    AND upload_time <= ?
                    ORDER BY upload_time ASC
                """, (cutoff_time,))
                
                rows = cursor.fetchall()
                
                videos = []
                for row in rows:
                    videos.append({
                        'video_id': row['video_id'],
                        'platform': row['platform'],
                        'url': row['url'],
                        'script_hook': row['script_hook']
                    })
                
                return videos
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Get pending checks error: {e}")
            return []
    
    def get_successful_hooks(self, limit: int = 10) -> List[str]:
        """
        Başarılı hook'ları al (Gemini'ye feedback için)
        
        Returns:
            En çok izlenen hook'lar
        """
        try:
            if not self.hooks_file.exists():
                return []
            
            with open(self.hooks_file, 'r', encoding='utf-8') as f:
                hooks_data = json.load(f)
            
            # View'a göre sırala
            sorted_hooks = sorted(
                hooks_data.get('hooks', []),
                key=lambda x: x.get('views', 0),
                reverse=True
            )
            
            # Sadece hook metinlerini döndür
            return [h['hook'] for h in sorted_hooks[:limit]]
            
        except Exception as e:
            logger.error(f"Get successful hooks error: {e}")
            return []
    
    def get_stats(self) -> Dict:
        """İstatistik özeti"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                # Toplam video
                cursor.execute("SELECT COUNT(*) FROM uploads")
                total = cursor.fetchone()[0]
                
                # Viral count (10K+)
                cursor.execute("SELECT COUNT(*) FROM uploads WHERE view_count >= ?", 
                              (self.VIRAL_THRESHOLD,))
                viral = cursor.fetchone()[0]
                
                # Ortalama views
                cursor.execute("SELECT AVG(view_count) FROM uploads WHERE view_count > 0")
                avg_views = cursor.fetchone()[0] or 0
                
                return {
                    'total_videos': total,
                    'viral_count': viral,
                    'viral_rate': (viral / total * 100) if total > 0 else 0,
                    'avg_views': int(avg_views)
                }
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return {}


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("ANALYTICS MANAGER TEST")
    print("="*60)
    
    manager = AnalyticsManager(db_path="test_uploads.db")
    
    # Test upload
    manager.track_upload(
        video_id="test123",
        platform="tiktok",
        url="https://tiktok.com/@test/video/123",
        script_hook="Zenginlerin gizlediği 3 sır!"
    )
    
    # Viral view count güncelle
    manager.update_view_count("test123", 25000)
    
    # Successful hooks al
    hooks = manager.get_successful_hooks()
    print(f"\n🔥 Successful Hooks: {hooks}")
    
    # Stats
    stats = manager.get_stats()
    print(f"\n📊 Stats: {stats}")
    
    # Cleanup
    import os
    if os.path.exists("test_uploads.db"):
        os.remove("test_uploads.db")
