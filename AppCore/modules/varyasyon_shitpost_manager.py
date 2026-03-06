"""
VaryasyonMedia Shitpost Manager
Günde 6 video, viral saatlerde, assets/varyasyonmedia_shitpost klasöründen rastgele seçerek paylaşır
"""
import os
import json
import random
import logging
from pathlib import Path
from datetime import datetime, time
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

class VaryasyonShitpostManager:
    """VaryasyonMedia için özel shitpost video yöneticisi"""
    
    # Sabit açıklama metni
    DESCRIPTION = """Dün akşam sadece bir paket cips ve "Le Cola" almak için markete girdim. Kasiyere "Hayırlı işler" dedim, bana dönüp "Kod adı ne?" diye sordu. Şaka yapıyor sandım, gülerek "Peynirli Doritos" dedim.

Birden mağazadaki tüm ışıklar kırmızıya döndü. Arkadaki yaşlı teyze telsizini çıkarıp "Hedef doğrulandı, paket hazır" dedi. Raflardaki tüm süt kutuları kendi kendine yere düştü ve içlerinden süt yerine Matrix kodları akmaya başladı. Panikleyip kaçmaya çalıştım ama otomatik kapı bana "Yetersiz Bakiye" uyarısı verdi.

O sırada mağaza müdürü (ki kendisi 3 bacaklı bir NPC'ye benziyordu) yanıma gelip elime bir USB bellek tutuşturdu ve "Bunu Elon Musk'a ver, insanlığın son umudu sensin" dedi. Dışarı çıktığımda elimde USB yerine yarım yenmiş bir kaşarlı tost vardı.

Sizce bu bir rüya mıydı yoksa beni gerçekten göreve mi çağırdılar? Tostu yedim bu arada.

.
.
.
#varyasyonmedia #komikvideolar #shitpostturkey #simülasyon #bimanıları"""
    
    # Viral saatler (Instagram Reels için optimal)
    VIRAL_HOURS = [9, 12, 15, 18, 20, 22]  # 6 saat = günde 6 video
    
    def __init__(self, base_dir: Path = None):
        """Initialize manager"""
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent.parent
        self.videos_dir = self.base_dir / "assets" / "varyasyonmedia_shitpost"
        self.history_file = self.base_dir / "db" / "varyasyon_history.json"
        
        # Klasörleri oluştur
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"VaryasyonShitpostManager initialized: {self.videos_dir}")
    
    def get_available_videos(self) -> List[Path]:
        """Klasördeki tüm video dosyalarını getir"""
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv']
        videos = []
        
        if not self.videos_dir.exists():
            logger.warning(f"Videos directory not found: {self.videos_dir}")
            return videos
        
        for ext in video_extensions:
            videos.extend(self.videos_dir.glob(f"*{ext}"))
        
        logger.debug(f"Found {len(videos)} videos in {self.videos_dir}")
        return videos
    
    def load_history(self) -> Dict:
        """Paylaşım geçmişini yükle"""
        if not self.history_file.exists():
            return {"posted_videos": [], "last_post_date": None}
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            return {"posted_videos": [], "last_post_date": None}
    
    def save_history(self, history: Dict):
        """Paylaşım geçmişini kaydet"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            logger.info("History saved successfully")
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def get_next_video(self) -> Optional[Path]:
        """Paylaşılacak bir sonraki videoyu seç (daha önce paylaşılmamış)"""
        available_videos = self.get_available_videos()
        
        if not available_videos:
            logger.warning("No videos available in directory")
            return None
        
        history = self.load_history()
        posted_videos = set(history.get("posted_videos", []))
        
        # Daha önce paylaşılmamış videoları filtrele
        unposted_videos = [v for v in available_videos if v.name not in posted_videos]
        
        # Eğer tüm videolar paylaşıldıysa, geçmişi sıfırla
        if not unposted_videos:
            logger.info("All videos posted, resetting history")
            history["posted_videos"] = []
            self.save_history(history)
            unposted_videos = available_videos
        
        # Rastgele bir video seç
        selected_video = random.choice(unposted_videos)
        logger.info(f"Selected video: {selected_video.name}")
        
        return selected_video
    
    def mark_as_posted(self, video_path: Path):
        """Videoyu paylaşıldı olarak işaretle"""
        history = self.load_history()
        
        if "posted_videos" not in history:
            history["posted_videos"] = []
        
        if video_path.name not in history["posted_videos"]:
            history["posted_videos"].append(video_path.name)
        
        history["last_post_date"] = datetime.now().isoformat()
        
        self.save_history(history)
        logger.info(f"Marked as posted: {video_path.name}")
    
    def get_next_post_time(self) -> Optional[datetime]:
        """Bir sonraki paylaşım zamanını hesapla"""
        now = datetime.now()
        current_hour = now.hour
        
        # Bugün için kalan viral saatleri bul
        remaining_hours = [h for h in self.VIRAL_HOURS if h > current_hour]
        
        if remaining_hours:
            next_hour = remaining_hours[0]
            next_time = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        else:
            # Yarın ilk viral saate ayarla
            from datetime import timedelta
            next_time = (now + timedelta(days=1)).replace(
                hour=self.VIRAL_HOURS[0], 
                minute=0, 
                second=0, 
                microsecond=0
            )
        
        return next_time
    
    def should_post_now(self) -> bool:
        """Şu an paylaşım zamanı mı kontrol et"""
        now = datetime.now()
        current_hour = now.hour
        
        # Viral saatlerden birinde miyiz?
        if current_hour not in self.VIRAL_HOURS:
            return False
        
        # Bu saatte daha önce paylaşım yapıldı mı?
        history = self.load_history()
        last_post = history.get("last_post_date")
        
        if last_post:
            last_post_time = datetime.fromisoformat(last_post)
            # Aynı saat içinde paylaşım yapıldıysa, tekrar paylaşma
            if last_post_time.hour == current_hour and last_post_time.date() == now.date():
                return False
        
        return True
    
    def create_post_data(self, video_path: Path) -> Dict:
        """Instagram Reels için post verisi oluştur"""
        return {
            "video_path": str(video_path),
            "description": self.DESCRIPTION,
            "platform": "instagram",
            "post_type": "reel",
            "account": "varyasyonmedia",
            "scheduled_time": datetime.now().isoformat()
        }
    
    def get_stats(self) -> Dict:
        """İstatistikleri getir"""
        available_videos = self.get_available_videos()
        history = self.load_history()
        posted_count = len(history.get("posted_videos", []))
        
        return {
            "total_videos": len(available_videos),
            "posted_videos": posted_count,
            "remaining_videos": len(available_videos) - posted_count,
            "last_post_date": history.get("last_post_date"),
            "next_post_time": self.get_next_post_time().isoformat() if self.get_next_post_time() else None,
            "viral_hours": self.VIRAL_HOURS,
            "posts_per_day": len(self.VIRAL_HOURS)
        }


# Test fonksiyonu
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    manager = VaryasyonShitpostManager()
    
    print("=" * 60)
    print("VaryasyonMedia Shitpost Manager - Test")
    print("=" * 60)
    
    # İstatistikleri göster
    stats = manager.get_stats()
    print(f"\n📊 İstatistikler:")
    print(f"  Toplam Video: {stats['total_videos']}")
    print(f"  Paylaşılan: {stats['posted_videos']}")
    print(f"  Kalan: {stats['remaining_videos']}")
    print(f"  Günlük Post: {stats['posts_per_day']}")
    print(f"  Viral Saatler: {stats['viral_hours']}")
    
    # Bir sonraki video
    next_video = manager.get_next_video()
    if next_video:
        print(f"\n🎬 Sıradaki Video: {next_video.name}")
        post_data = manager.create_post_data(next_video)
        print(f"\n📝 Post Verisi:")
        print(f"  Platform: {post_data['platform']}")
        print(f"  Tip: {post_data['post_type']}")
        print(f"  Hesap: {post_data['account']}")
        print(f"\n📄 Açıklama:")
        print(post_data['description'][:200] + "...")
    else:
        print("\n⚠️ Video bulunamadı!")
    
    print("\n" + "=" * 60)
