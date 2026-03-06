"""
VaryasyonMedia Scheduler
Otomatik olarak viral saatlerde video paylaşımı yapar
"""
import asyncio
import logging
import schedule
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .varyasyon_shitpost_manager import VaryasyonShitpostManager

logger = logging.getLogger(__name__)

class VaryasyonScheduler:
    """VaryasyonMedia için zamanlayıcı"""
    
    def __init__(self):
        """Initialize scheduler"""
        self.manager = VaryasyonShitpostManager()
        self.is_running = False
        self.instagram_uploader = None
        
        logger.debug("VaryasyonScheduler initialized")
    
    def set_instagram_uploader(self, uploader):
        """Instagram uploader'ı ayarla"""
        self.instagram_uploader = uploader
        logger.info("Instagram uploader set")
    
    async def post_video(self):
        """Video paylaş"""
        try:
            # Şu an paylaşım zamanı mı kontrol et
            if not self.manager.should_post_now():
                logger.info("Not time to post yet")
                return
            
            # Sıradaki videoyu al
            video_path = self.manager.get_next_video()
            
            if not video_path:
                logger.warning("No video available to post")
                return
            
            # Post verisini oluştur
            post_data = self.manager.create_post_data(video_path)
            
            logger.info(f"📱 Posting to Instagram: {video_path.name}")
            
            # Instagram'a yükle
            if self.instagram_uploader:
                try:
                    result = await self.instagram_uploader.upload_reel(
                        video_path=str(video_path),
                        caption=post_data['description'],
                        username="varyasyonmedia"
                    )
                    
                    if result.get("success"):
                        # Başarılı, videoyu işaretle
                        self.manager.mark_as_posted(video_path)
                        logger.info(f"✅ Successfully posted: {video_path.name}")
                    else:
                        logger.error(f"❌ Failed to post: {result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"❌ Upload error: {e}")
            else:
                # Test modu - sadece işaretle
                logger.warning("⚠️ Instagram uploader not set, marking as posted (TEST MODE)")
                self.manager.mark_as_posted(video_path)
            
        except Exception as e:
            logger.error(f"Error in post_video: {e}", exc_info=True)
    
    def schedule_posts(self):
        """Tüm viral saatler için paylaşımları zamanla"""
        schedule.clear()  # Önceki zamanlamaları temizle
        
        for hour in self.manager.VIRAL_HOURS:
            schedule_time = f"{hour:02d}:00"
            schedule.every().day.at(schedule_time).do(
                lambda: asyncio.create_task(self.post_video())
            )
            logger.debug(f"📅 Scheduled post at {schedule_time}")
        
        logger.debug(f"✅ Scheduled {len(self.manager.VIRAL_HOURS)} posts per day")
    
    def start(self):
        """Zamanlayıcıyı başlat"""
        if self.is_running:
            logger.warning("Scheduler already running")
            return
        
        self.is_running = True
        self.schedule_posts()
        
        logger.debug("🚀 VaryasyonScheduler started")
        
        # Zamanlayıcı döngüsü
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)  # Her dakika kontrol et
    
    def stop(self):
        """Zamanlayıcıyı durdur"""
        self.is_running = False
        schedule.clear()
        logger.info("⏹️ VaryasyonScheduler stopped")
    
    def get_status(self) -> dict:
        """Durum bilgisi getir"""
        stats = self.manager.get_stats()
        
        return {
            "is_running": self.is_running,
            "account": "varyasyonmedia",
            "platform": "instagram",
            "post_type": "reel",
            "stats": stats,
            "next_post": stats.get("next_post_time"),
            "viral_hours": self.manager.VIRAL_HOURS
        }


# Global instance
_scheduler_instance = None

def get_varyasyon_scheduler() -> VaryasyonScheduler:
    """Global scheduler instance'ı getir"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = VaryasyonScheduler()
    return _scheduler_instance


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    scheduler = VaryasyonScheduler()
    status = scheduler.get_status()
    
    print("=" * 60)
    print("VaryasyonMedia Scheduler - Status")
    print("=" * 60)
    print(f"\n📱 Account: {status['account']}")
    print(f"🎬 Platform: {status['platform']}")
    print(f"📹 Type: {status['post_type']}")
    print(f"\n📊 Stats:")
    print(f"  Total Videos: {status['stats']['total_videos']}")
    print(f"  Posted: {status['stats']['posted_videos']}")
    print(f"  Remaining: {status['stats']['remaining_videos']}")
    print(f"  Posts/Day: {status['stats']['posts_per_day']}")
    print(f"\n⏰ Viral Hours: {status['viral_hours']}")
    print(f"⏭️  Next Post: {status['next_post']}")
    print("\n" + "=" * 60)
