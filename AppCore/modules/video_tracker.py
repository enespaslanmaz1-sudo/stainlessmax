"""
Video Tracker - Upload edilen videoları takip et ve analiz et
SQLite database ile video metadata ve analytics storage
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class VideoTracker:
    """Upload edilen videoları track eden sistem"""
    
    def __init__(self, db_path: str = "data/video_analytics.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """SQLite veritabanını başlat"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            
            # Video tracking tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    url TEXT,
                    account_id TEXT,
                    upload_time DATETIME NOT NULL,
                    scenario_json TEXT,
                    title TEXT,
                    niche TEXT,
                    topic TEXT,
                    hook TEXT,
                    duration INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Analytics tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    check_time DATETIME NOT NULL,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    watch_time REAL DEFAULT 0,
                    engagement_rate REAL DEFAULT 0,
                    is_viral BOOLEAN DEFAULT 0,
                    FOREIGN KEY (video_id) REFERENCES videos(video_id)
                )
            """)
            
            # Analytics check schedule
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analytics_schedule (
                    video_id TEXT PRIMARY KEY,
                    scheduled_time DATETIME NOT NULL,
                    checked BOOLEAN DEFAULT 0,
                    FOREIGN KEY (video_id) REFERENCES videos(video_id)
                )
            """)
            
            # Viral patterns (öğrenilen hooklar)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS viral_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT,
                    niche TEXT,
                    hook TEXT,
                    avg_views INTEGER,
                    success_count INTEGER DEFAULT 1,
                    last_used DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            logger.info(f"✅ Video tracking database initialized: {self.db_path}")
        finally:
            conn.close()
    
    def track_upload(self, video_data: Dict) -> bool:
        """
        Video upload sonrası kayıt
        
        Args:
            video_data: {
                'video_id': 'xyz123',
                'platform': 'tiktok',
                'url': 'https://tiktok.com/@user/video/...',
                'account_id': 'tiktok_main',
                'scenario': {...},
                'title': 'Video başlığı',
                'niche': 'finance',
                'topic': 'zenginlik'
            }
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                # Scenario'dan hook çıkar
                scenario = video_data.get('scenario', {})
                hook = scenario.get('hook', '')
                duration = sum(scene.get('duration', 10) for scene in scenario.get('scenes', []))
                
                # Video kaydı
                cursor.execute("""
                    INSERT OR REPLACE INTO videos 
                    (video_id, platform, url, account_id, upload_time, scenario_json, 
                     title, niche, topic, hook, duration)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    video_data['video_id'],
                    video_data['platform'],
                    video_data.get('url', ''),
                    video_data.get('account_id', ''),
                    video_data.get('upload_time', datetime.now()),
                    json.dumps(scenario, ensure_ascii=False),
                    video_data.get('title', ''),
                    video_data.get('niche', ''),
                    video_data.get('topic', ''),
                    hook,
                    duration
                ))
                
                # 48 saat sonrası için schedule
                scheduled_time = datetime.now() + timedelta(hours=48)
                cursor.execute("""
                    INSERT OR REPLACE INTO analytics_schedule
                    (video_id, scheduled_time, checked)
                    VALUES (?, ?, 0)
                """, (video_data['video_id'], scheduled_time))
                
                conn.commit()
                logger.info(f"✅ Video tracked: {video_data['video_id']} ({video_data['platform']})")
                return True
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Video tracking error: {e}")
            return False
    
    def get_pending_checks(self, hours_ago: int = 48) -> List[Dict]:
        """
        Analytics check bekleyen videoları al
        
        Args:
            hours_ago: Kaç saat önce yüklenmiş videoları al (default: 48)
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cutoff_time = datetime.now() - timedelta(hours=hours_ago)
                
                cursor.execute("""
                    SELECT v.*, s.scheduled_time
                    FROM videos v
                    JOIN analytics_schedule s ON v.video_id = s.video_id
                    WHERE s.checked = 0 
                    AND s.scheduled_time <= ?
                    ORDER BY s.scheduled_time ASC
                """, (datetime.now(),))
                
                rows = cursor.fetchall()
                
                videos = []
                for row in rows:
                    videos.append({
                        'video_id': row['video_id'],
                        'platform': row['platform'],
                        'url': row['url'],
                        'account_id': row['account_id'],
                        'upload_time': row['upload_time'],
                        'scenario': json.loads(row['scenario_json']) if row['scenario_json'] else {},
                        'title': row['title'],
                        'niche': row['niche'],
                        'topic': row['topic'],
                        'hook': row['hook']
                    })
                
                return videos
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Get pending checks error: {e}")
            return []
    
    def save_analytics(self, video_id: str, stats: Dict) -> bool:
        """
        Video analytics kaydet
        
        Args:
            stats: {
                'views': 15000,
                'likes': 1200,
                'comments': 45,
                'shares': 30,
                'watch_time': 0.85
            }
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                # Engagement rate hesapla
                views = stats.get('views', 0)
                likes = stats.get('likes', 0)
                engagement_rate = (likes / views) if views > 0 else 0
                
                # Analytics kaydet
                cursor.execute("""
                    INSERT INTO analytics
                    (video_id, check_time, views, likes, comments, shares, 
                     watch_time, engagement_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    video_id,
                    datetime.now(),
                    views,
                    likes,
                    stats.get('comments', 0),
                    stats.get('shares', 0),
                    stats.get('watch_time', 0),
                    engagement_rate
                ))
                
                # Schedule'ı checked olarak işaretle
                cursor.execute("""
                    UPDATE analytics_schedule
                    SET checked = 1
                    WHERE video_id = ?
                """, (video_id,))
                
                conn.commit()
                logger.info(f"✅ Analytics saved: {video_id} - {views} views")
                return True
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Save analytics error: {e}")
            return False
    
    def mark_as_viral(self, video_id: str) -> bool:
        """Video'yu viral olarak işaretle"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE analytics
                    SET is_viral = 1
                    WHERE video_id = ?
                    ORDER BY check_time DESC
                    LIMIT 1
                """, (video_id,))
                
                conn.commit()
                logger.info(f"🔥 Marked as VIRAL: {video_id}")
                return True
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Mark viral error: {e}")
            return False
    
    def save_viral_pattern(self, platform: str, niche: str, hook: str, views: int) -> bool:
        """Viral hook pattern'i kaydet"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                # Aynı hook daha önce var mı?
                cursor.execute("""
                    SELECT id, success_count, avg_views
                    FROM viral_patterns
                    WHERE platform = ? AND niche = ? AND hook = ?
                """, (platform, niche, hook))
                
                existing = cursor.fetchone()
                
                if existing:
                    # Güncelle
                    pattern_id, old_count, old_avg = existing
                    new_count = old_count + 1
                    new_avg = ((old_avg * old_count) + views) // new_count
                    
                    cursor.execute("""
                        UPDATE viral_patterns
                        SET success_count = ?, avg_views = ?, last_used = ?
                        WHERE id = ?
                    """, (new_count, new_avg, datetime.now(), pattern_id))
                else:
                    # Yeni kayıt
                    cursor.execute("""
                        INSERT INTO viral_patterns
                        (platform, niche, hook, avg_views, last_used)
                        VALUES (?, ?, ?, ?, ?)
                    """, (platform, niche, hook, views, datetime.now()))
                
                conn.commit()
                logger.info(f"💎 Viral pattern saved: '{hook}' ({views} views)")
                return True
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Save viral pattern error: {e}")
            return False
    
    def get_viral_patterns(self, platform: str = None, niche: str = None, limit: int = 10) -> List[Dict]:
        """
        Öğrenilen viral pattern'leri al
        
        Returns:
            [{
                'hook': 'Zenginlerin gizlediği 3 sır!',
                'avg_views': 25000,
                'success_count': 3,
                'platform': 'tiktok',
                'niche': 'finance'
            }]
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = """
                    SELECT platform, niche, hook, avg_views, success_count, last_used
                    FROM viral_patterns
                    WHERE 1=1
                """
                params = []
                
                if platform:
                    query += " AND platform = ?"
                    params.append(platform)
                
                if niche:
                    query += " AND niche = ?"
                    params.append(niche)
                
                query += " ORDER BY avg_views DESC, success_count DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                patterns = []
                for row in rows:
                    patterns.append({
                        'platform': row['platform'],
                        'niche': row['niche'],
                        'hook': row['hook'],
                        'avg_views': row['avg_views'],
                        'success_count': row['success_count'],
                        'last_used': row['last_used']
                    })
                
                return patterns
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Get viral patterns error: {e}")
            return []
    
    def get_stats_summary(self) -> Dict:
        """Genel istatistikler"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                
                # Toplam video
                cursor.execute("SELECT COUNT(*) FROM videos")
                total_videos = cursor.fetchone()[0]
                
                # Viral video sayısı
                cursor.execute("SELECT COUNT(DISTINCT video_id) FROM analytics WHERE is_viral = 1")
                viral_count = cursor.fetchone()[0]
                
                # Ortalama views
                cursor.execute("SELECT AVG(views) FROM analytics")
                avg_views = cursor.fetchone()[0] or 0
                
                # En çok kullanılan niş
                cursor.execute("""
                    SELECT niche, COUNT(*) as count
                    FROM videos
                    WHERE niche != ''
                    GROUP BY niche
                    ORDER BY count DESC
                    LIMIT 1
                """)
                top_niche = cursor.fetchone()
                
                return {
                    'total_videos': total_videos,
                    'viral_count': viral_count,
                    'viral_rate': (viral_count / total_videos * 100) if total_videos > 0 else 0,
                    'avg_views': int(avg_views),
                    'top_niche': top_niche[0] if top_niche else 'N/A'
                }
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Stats summary error: {e}")
            return {}


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("VIDEO TRACKER TEST")
    print("="*60)
    
    tracker = VideoTracker()
    
    # Test video kaydet
    test_video = {
        'video_id': 'test123',
        'platform': 'tiktok',
        'url': 'https://tiktok.com/@test/video/123',
        'account_id': 'tiktok_main',
        'upload_time': datetime.now(),
        'scenario': {
            'hook': 'Zenginlerin 3 sırrı!',
            'scenes': [
                {'duration': 10, 'narration': 'Test'}
            ]
        },
        'title': 'Test Video',
        'niche': 'finance',
        'topic': 'zenginlik'
    }
    
    tracker.track_upload(test_video)
    
    # Stats summary
    stats = tracker.get_stats_summary()
    print(f"\n📊 Stats:")
    print(f"Total Videos: {stats['total_videos']}")
    print(f"Viral Count: {stats['viral_count']}")
    print(f"Viral Rate: {stats['viral_rate']:.1f}%")
    print(f"Avg Views: {stats['avg_views']}")
