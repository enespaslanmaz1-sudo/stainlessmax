"""
Config Manager - Merkezi Yapılandırma Yönetimi
"""

import os

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_config_instance = None


class _CompatNamespace:
    """SimpleNamespace benzeri yapı; legacy kod için model_dump desteği sağlar."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class ConfigManager:
    """Merkezi yapılandırma yöneticisi (Singleton)"""
    
    def __init__(self):
        self.config_path = Path("settings.json")
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """settings.json'u yükle"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Config yükleme hatası: {e}")
        return {}
    
    def save(self) -> bool:
        """Yapılandırmayı kaydet"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Config kaydetme hatası: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Ayar oku (dot notation: 'youtube.daily_limit')"""
        keys = key.split('.')
        val = self.config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default
    
    def set(self, key: str, value: Any) -> bool:
        """Ayar yaz (dot notation)"""
        keys = key.split('.')
        obj = self.config
        for k in keys[:-1]:
            if k not in obj:
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value
        return self.save()
    
    def get_api_key(self, service: str) -> Optional[str]:
        """API anahtarı al"""
        return self.get(f"api_keys.{service}", "")
    
    @property
    def api_keys(self):
        """Telegram bot ve diğer modüller için api_keys erişimi"""
        keys = self.config.get("api_keys", {})
        return _CompatNamespace(
            telegram_token=keys.get("telegram_token", os.getenv("TELEGRAM_BOT_TOKEN", "")),
            telegram_admin=keys.get("telegram_admin", os.getenv("TELEGRAM_ADMIN_ID", "")),
            pexels=keys.get("pexels", os.getenv("PEXELS_API_KEY", "")),
            pixabay=keys.get("pixabay", os.getenv("PIXABAY_API_KEY", "")),
            gemini=keys.get("gemini", os.getenv("GEMINI_API_KEY", "")),
        )
    
    @property
    def api_config(self):
        """Settings route uyumu için api_config erişimi"""
        return self.api_keys
    
    @property
    def youtube_config(self):
        """YouTube config erişimi"""
        yt = self.config.get("youtube", {})
        return _CompatNamespace(
            client_id=yt.get("client_id", ""),
            client_secret=yt.get("client_secret", ""),
        )
    
    @property
    def tiktok_config(self):
        """TikTok config erişimi"""
        tt = self.config.get("tiktok", {})
        return _CompatNamespace(
            client_id=tt.get("client_key", ""),
            client_secret=tt.get("client_secret", ""),
        )

    @property
    def n8n_config(self):
        """n8n config erişimi (legacy model_dump uyumlu)."""
        n8n = self.config.get("n8n", {})
        return _CompatNamespace(
            webhook_url=n8n.get("webhook_url", ""),
            api_key=n8n.get("api_key", ""),
            enabled=bool(n8n.get("enabled", False)),
        )
    
    def update_settings(self, data: Dict):
        """Ayarları güncelle"""
        for key, value in data.items():
            if isinstance(value, dict):
                if key not in self.config:
                    self.config[key] = {}
                self.config[key].update(value)
            else:
                self.config[key] = value
        self.save()
    
    def get_daily_limit(self, platform: str) -> int:
        """Günlük limit al (hesap başına)"""
        return self.get(f"{platform}.daily_limit", 3)
    
    def get_interval(self, platform: str) -> int:
        """Üretim aralığını al (saat)"""
        return self.get(f"{platform}.interval_hours", 8)


def get_config_manager() -> ConfigManager:
    """Global ConfigManager instance'ını al veya oluştur"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance
