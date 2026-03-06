"""
Automation Engine - Otomatik Video Üretim ve Zamanlama Motoru
"""

import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Testlerin patchleyebilmesi için sembolü modül seviyesinde tanımlı tut.
HesaplarParser = None

try:
    from lib.error_handler import handle_error
except Exception:
    def handle_error(error: Exception, context: Optional[Dict] = None):
        logger.error(f"AutomationEngine error: {error}")


_engine_instance = None


class AutomationEngine:
    """Otomatik video üretim ve zamanlama motoru"""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else Path(".")
        self.running = False
        self.auto_mode = False
        self.queue_dir = self.base_dir / "upload_queue"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_path = self.base_dir / "config" / "jobs.json"
        self.jobs_path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs: List[Dict] = self._load_jobs()
        self.stats: Dict[str, int] = {
            "total_produced": 0,
            "total_uploaded": 0,
            "total_failed": 0,
            "today_produced": 0,
        }
        self._thread = None
        self._generator = None
        self._socketio = None
        
        logger.info(f"🤖 AutomationEngine başlatıldı ({len(self.jobs)} iş)")
    
    def set_generator(self, generator_func, socketio=None):
        """Video üretim fonksiyonunu ve socketio referansını ayarla"""
        self._generator = generator_func
        self._socketio = socketio
        logger.info("✅ Generator linked to AutomationEngine")
    
    def _load_jobs(self) -> List[Dict]:
        """İşleri yükle"""
        try:
            if self.jobs_path.exists():
                with open(self.jobs_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Jobs yükleme hatası: {e}")
        return []
    
    def _save_jobs(self):
        """İşleri kaydet"""
        try:
            with open(self.jobs_path, 'w', encoding='utf-8') as f:
                json.dump(self.jobs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Jobs kaydetme hatası: {e}")
    
    def add_job(self, job: Dict) -> bool:
        """Yeni iş ekle"""
        job['id'] = f"job_{int(time.time())}_{len(self.jobs)}"
        job['status'] = 'pending'
        job['created_at'] = datetime.now().isoformat()
        self.jobs.append(job)
        self._save_jobs()
        logger.info(f"📌 İş eklendi: {job['id']}")
        return True
    
    def get_pending_jobs(self) -> List[Dict]:
        """Bekleyen işleri al"""
        return [j for j in self.jobs if j.get('status') == 'pending']
    
    def _queue_counts(self) -> Dict[str, int]:
        statuses = [j.get("status") for j in self.jobs]
        queue = {
            "pending": sum(1 for s in statuses if s == "pending"),
            "generating": sum(1 for s in statuses if s == "generating"),
            "ready": sum(1 for s in statuses if s == "ready"),
            "uploading": sum(1 for s in statuses if s == "uploading"),
            "uploaded": sum(1 for s in statuses if s in {"uploaded", "completed"}),
            "failed": sum(1 for s in statuses if s == "failed"),
        }
        queue["total"] = len(self.jobs)
        return queue

    def get_status(self) -> Dict:
        """Motor durumu"""
        current_stats = self.stats if isinstance(self.stats, dict) else {}
        return {
            "active": self.running,
            "running": self.running,
            "auto_mode": self.auto_mode,
            "queue": self._queue_counts(),
            "stats": {
                "total_produced": current_stats.get("total_produced", 0),
                "total_uploaded": current_stats.get("total_uploaded", 0),
                "total_failed": current_stats.get("total_failed", 0),
                "today_produced": current_stats.get("today_produced", 0),
            },
            "accounts": [],
            "target": {},
            "recent_jobs": self.jobs[-10:],
            "total_jobs": len(self.jobs),
            "pending": sum(1 for j in self.jobs if j.get("status") == "pending"),
            "completed": sum(1 for j in self.jobs if j.get("status") == "completed"),
            "failed": sum(1 for j in self.jobs if j.get("status") == "failed"),
        }
    
    def start(self):
        """Motoru başlat"""
        if self.running:
            logger.warning("Motor zaten çalışıyor")
            return
        self.running = True
        self.auto_mode = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("🚀 Automation Engine başlatıldı")
    
    def stop(self):
        """Motoru durdur"""
        self.running = False
        self.auto_mode = False
        logger.info("🛑 Automation Engine durduruldu")
    
    def _run_loop(self):
        """Ana döngü"""
        while self.running:
            try:
                pending = self.get_pending_jobs()
                if pending:
                    job = pending[0]
                    logger.info(f"⚙️ İş işleniyor: {job.get('id')}")
                    self._process_job(job)
                time.sleep(30)  # 30 saniye aralıklarla kontrol
            except Exception as e:
                handle_error(e, {"component": "automation_engine", "phase": "run_loop"})
                time.sleep(60)
    
    def _process_job(self, job: Dict):
        """Tek bir işi işle"""
        try:
            job['status'] = 'processing'
            job['started_at'] = datetime.now().isoformat()
            self._save_jobs()
            
            # Video üretim burada tetiklenecek
            # Bu, main.py'deki create_real_video ile entegre edilecek
            
            job['status'] = 'completed'
            job['completed_at'] = datetime.now().isoformat()
            self._save_jobs()
            logger.info(f"✅ İş tamamlandı: {job.get('id')}")
            
        except Exception as e:
            job['status'] = 'failed'
            job['error'] = str(e)
            self._save_jobs()
            self.stats["total_failed"] = self.stats.get("total_failed", 0) + 1
            handle_error(e, {"component": "automation_engine", "phase": "process_job", "job_id": job.get("id")})
    
    def generate_daily_schedule(self, target_date: str = None) -> List[Dict]:
        """Günlük zamanlama oluştur - her hesap için 3 video"""
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")
        
        from AppCore.lib.config_manager import get_config_manager
        config = get_config_manager()
        
        videos_per_account = 3  # Sabit olarak her hesap için 3 video
        
        # Tüm hesapları al
        accounts = []
        try:
            from AppCore.modules.account_manager import AccountManager
            manager = AccountManager()
            all_accounts = manager.get_all_accounts()
            accounts = [a for a in all_accounts if getattr(a, 'active', True)]
        except Exception as e:
            logger.warning(f"Hesaplar yüklenemedi: {e}")
        
        if not accounts:
            logger.info("Hiç hesap bulunamadı, varsayılan zamanlama oluşturuluyor")
            return []
        
        schedule = []
        base_time = datetime.strptime(target_date, "%Y-%m-%d").replace(hour=8)
        total_videos = len(accounts) * videos_per_account
        
        # Videoları gün içine eşit dağıt (08:00 - 22:00 arası = 14 saat)
        interval_minutes = (14 * 60) / max(total_videos, 1)
        
        video_index = 0
        for account in accounts:
            platform = getattr(account, 'platform', 'youtube')
            account_id = getattr(account, 'id', 'unknown')
            account_name = getattr(account, 'name', account_id)
            niche = getattr(account, 'niche', getattr(account, 'theme', 'general'))
            
            for i in range(videos_per_account):
                scheduled_time = base_time + timedelta(minutes=video_index * interval_minutes)
                schedule.append({
                    "account_id": account_id,
                    "account_name": account_name,
                    "platform": platform,
                    "niche": niche,
                    "scheduled_time": scheduled_time.isoformat(),
                    "status": "pending",
                    "video_number": i + 1,
                })
                video_index += 1
        
        logger.info(f"📅 Günlük plan: {len(accounts)} hesap × {videos_per_account} video = {len(schedule)} video")
        return schedule

    def force_generate_all(self) -> Dict:
        """Hızlı Üretim Tetikle - Günde max 30 video limiti eklendi"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # O gün oluşturulan işleri say
        today_force_jobs = sum(1 for j in self.jobs if j.get('id', '').startswith('force_') and today_str in j.get('created_at', ''))
        
        if today_force_jobs >= 30:
            return {"error": "Günlük 30 hızlı üretim limitine ulaşıldı.", "added": 0}
            
        accounts = []
        try:
            from AppCore.modules.account_manager import AccountManager
            manager = AccountManager()
            all_accounts = manager.get_all_accounts()
            accounts = [a for a in all_accounts if getattr(a, 'active', True)]
        except Exception as e:
            logger.error(f"AccountManager import error in force_generate_all: {e}")
            return {"error": "Hesaplar yüklenemedi", "added": 0}
            
        if not accounts:
            return {"error": "Hiç hesap bulunamadı", "added": 0}
            
        added_count = 0
        now_dt = datetime.now()
        
        # Kalan limiti hesapla
        remaining = 30 - today_force_jobs
        
        # Her hesaba eşit veya en az 1 video eklenecek şekilde
        for account in accounts:
            if remaining <= 0:
                break
                
            platform = getattr(account, 'platform', 'youtube')
            account_id = getattr(account, 'id', 'unknown')
            account_name = getattr(account, 'name', account_id)
            niche = getattr(account, 'niche', getattr(account, 'theme', 'general'))
            
            job = {
                "id": f"force_{int(time.time())}_{added_count}",
                "account_id": account_id,
                "account_name": account_name,
                "platform": platform,
                "niche": niche,
                "scheduled_time": now_dt.isoformat(),
                "status": "pending",
                "video_number": 1,
                "created_at": now_dt.isoformat()
            }
            self.jobs.append(job)
            added_count += 1
            remaining -= 1
            
        self._save_jobs()
        return {"added": added_count, "remaining_limit": remaining}

    def force_generate(self, specific_platform: str = None) -> Dict:
        """Belirli bir platform veya genel için hızlı üretim tetikle (alias)"""
        if not specific_platform:
            return self.force_generate_all()
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_force_jobs = sum(1 for j in self.jobs if j.get('id', '').startswith('force_') and today_str in j.get('created_at', ''))
        
        if today_force_jobs >= 30:
            return {"error": "Günlük 30 hızlı üretim limitine ulaşıldı.", "added": 0}
            
        accounts = []
        try:
            from AppCore.modules.account_manager import AccountManager
            manager = AccountManager()
            all_accounts = manager.get_all_accounts()
            accounts = [a for a in all_accounts if getattr(a, 'active', True) and getattr(a, 'platform', '') == specific_platform]
        except Exception as e:
            return {"error": "Hesaplar yüklenemedi", "added": 0}
            
        if not accounts:
            return {"error": "Belirtilen platform için hesap bulunamadı", "added": 0}
            
        added_count = 0
        now_dt = datetime.now()
        remaining = 30 - today_force_jobs
        
        for account in accounts:
            if remaining <= 0:
                break
            
            job = {
                "id": f"force_{int(time.time())}_{added_count}",
                "account_id": getattr(account, 'id', 'unknown'),
                "account_name": getattr(account, 'name', 'unknown'),
                "platform": specific_platform,
                "niche": getattr(account, 'niche', 'general'),
                "scheduled_time": now_dt.isoformat(),
                "status": "pending",
                "video_number": 1,
                "created_at": now_dt.isoformat()
            }
            self.jobs.append(job)
            added_count += 1
            remaining -= 1
            
        self._save_jobs()
        return {"added": added_count, "remaining_limit": remaining}



def get_automation_engine() -> AutomationEngine:
    """Global AutomationEngine instance'ını al veya oluştur"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = AutomationEngine()
    return _engine_instance


def start_automation():
    """Otomasyonu başlat"""
    engine = get_automation_engine()
    engine.start()
    return engine.get_status()


def stop_automation():
    """Otomasyonu durdur"""
    engine = get_automation_engine()
    engine.stop()
    return engine.get_status()


def get_automation_status() -> Dict:
    """Otomasyon durumunu al"""
    engine = get_automation_engine()
    return engine.get_status()
