"""
SaaS Configuration & License Manager
StainlessMax production-grade licensing and feature management
"""

import json
import hashlib
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# ===== PLAN TANIMLARI =====
PLANS = {
    "trial": {
        "name": "Trial",
        "max_videos_per_day": 5,
        "max_accounts": 2,
        "features": ["video_generation", "manual_upload"],
        "duration_days": 7,
        "price": 0
    },
    "starter": {
        "name": "Starter",
        "max_videos_per_day": 25,
        "max_accounts": 5,
        "features": ["video_generation", "manual_upload", "auto_upload", "analytics", "telegram_bot"],
        "duration_days": 30,
        "price": 29
    },
    "pro": {
        "name": "Professional",
        "max_videos_per_day": 100,
        "max_accounts": 20,
        "features": ["video_generation", "manual_upload", "auto_upload", "analytics", 
                     "telegram_bot", "ai_suggestions", "scheduled_posting", "multi_platform",
                     "affiliate_links", "priority_support"],
        "duration_days": 30,
        "price": 79
    },
    "enterprise": {
        "name": "Enterprise",
        "max_videos_per_day": 500,
        "max_accounts": 100,
        "features": ["*"],  # Tüm özellikler
        "duration_days": 365,
        "price": 299
    }
}

# Varsayılan: Pro (kendi kullanımı için sınırsız)
DEFAULT_PLAN = "enterprise"


@dataclass
class License:
    """Lisans bilgisi"""
    plan: str = DEFAULT_PLAN
    license_key: str = ""
    activated_at: str = ""
    expires_at: str = ""
    machine_id: str = ""
    owner: str = "Enes"
    videos_today: int = 0
    last_reset_date: str = ""


class SaaSConfig:
    """Merkezi SaaS yapılandırma yöneticisi"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.config_path = Path("config/license.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.license = self._load_license()
        self._initialized = True
        
        logger.info(f"✅ SaaS Config: Plan={self.license.plan}, Owner={self.license.owner}")
    
    def _load_license(self) -> License:
        """Lisans dosyasını yükle veya varsayılan oluştur"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return License(**data)
            except Exception as e:
                logger.error(f"Lisans yükleme hatası: {e}")
        
        # Varsayılan lisans oluştur (Enterprise - kendi kullanımı)
        license = License(
            plan=DEFAULT_PLAN,
            license_key=self._generate_key(),
            activated_at=datetime.now().isoformat(),
            expires_at=(datetime.now() + timedelta(days=3650)).isoformat(),  # 10 yıl
            machine_id=self._get_machine_id(),
            owner="Enes"
        )
        self._save_license(license)
        return license
    
    def _save_license(self, license: License):
        """Lisansı kaydet"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(license), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Lisans kaydetme hatası: {e}")
    
    def _generate_key(self) -> str:
        """Unique lisans anahtarı oluştur"""
        seed = f"{os.getlogin()}_{datetime.now().isoformat()}"
        return f"SM-{hashlib.sha256(seed.encode()).hexdigest()[:16].upper()}"
    
    def _get_machine_id(self) -> str:
        """Makine ID'si al"""
        try:
            import uuid
            return str(uuid.getnode())
        except:
            return "unknown"
    
    # ===== FEATURE KONTROL =====
    
    def get_plan(self) -> Dict:
        """Mevcut plan bilgisini döndür"""
        return PLANS.get(self.license.plan, PLANS[DEFAULT_PLAN])
    
    def get_plan_name(self) -> str:
        """Plan adını döndür"""
        return self.get_plan()["name"]
    
    def has_feature(self, feature: str) -> bool:
        """Özellik erişimi kontrol et"""
        plan = self.get_plan()
        return "*" in plan["features"] or feature in plan["features"]
    
    def can_generate_video(self) -> bool:
        """Günlük video limitini kontrol et"""
        plan = self.get_plan()
        
        # Gün değişti mi kontrol et
        today = datetime.now().strftime("%Y-%m-%d")
        if self.license.last_reset_date != today:
            self.license.videos_today = 0
            self.license.last_reset_date = today
            self._save_license(self.license)
        
        return self.license.videos_today < plan["max_videos_per_day"]
    
    def increment_video_count(self):
        """Video sayacını artır"""
        self.license.videos_today += 1
        self._save_license(self.license)
    
    def get_remaining_videos(self) -> int:
        """Kalan video hakkı"""
        plan = self.get_plan()
        return max(0, plan["max_videos_per_day"] - self.license.videos_today)
    
    def get_max_accounts(self) -> int:
        """Maksimum hesap sayısı"""
        return self.get_plan()["max_accounts"]
    
    def is_expired(self) -> bool:
        """Lisans süresi dolmuş mu?"""
        if not self.license.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.license.expires_at)
            return datetime.now() > expires
        except:
            return False
    
    def get_status(self) -> Dict:
        """Tam durum bilgisi"""
        plan = self.get_plan()
        return {
            "plan": self.license.plan,
            "plan_name": plan["name"],
            "owner": self.license.owner,
            "license_key": self.license.license_key,
            "videos_today": self.license.videos_today,
            "max_videos_per_day": plan["max_videos_per_day"],
            "remaining_videos": self.get_remaining_videos(),
            "max_accounts": plan["max_accounts"],
            "features": plan["features"],
            "expired": self.is_expired(),
            "expires_at": self.license.expires_at,
            "version": "3.0"
        }


# Singleton accessor
def get_saas_config() -> SaaSConfig:
    return SaaSConfig()
