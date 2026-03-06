"""
System Initialization - StainlessMax Startup
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def initialize_system():
    """Sistem başlangıç kontrollerini yap ve gerekli dizinleri oluştur"""
    
    base_dir = Path(__file__).parent.parent.parent  # StainlessMax root
    
    # Gerekli dizinleri oluştur
    required_dirs = [
        base_dir / "System_Data" / "outputs",
        base_dir / "System_Data" / "clips_cache",
        base_dir / "System_Data" / "audio",
        base_dir / "System_Data" / "logs",
        base_dir / "config",
        base_dir / "temp",
    ]
    
    for d in required_dirs:
        d.mkdir(parents=True, exist_ok=True)
    
    # .env dosyasını yükle
    try:
        from dotenv import load_dotenv
        env_path = base_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("✅ .env dosyası yüklendi")
    except ImportError:
        logger.warning("⚠️ python-dotenv yüklü değil")
    
    # SaaS Config başlat
    try:
        from AppCore.lib.saas_config import get_saas_config
        config = get_saas_config()
        logger.info(f"✅ SaaS Config: {config.get_plan_name()} ({config.get_remaining_videos()} video hakkı)")
    except Exception as e:
        logger.warning(f"⚠️ SaaS Config yüklenemedi: {e}")
    
    # FFmpeg kontrolü
    ffmpeg_ok = _check_ffmpeg()
    
    logger.info("="*50)
    logger.info("  STAINLESS MAX - System Initialized")
    logger.info(f"  Base Dir: {base_dir}")
    logger.info(f"  FFmpeg: {'✅' if ffmpeg_ok else '❌'}")
    logger.info("="*50)
    
    return True


def _check_ffmpeg() -> bool:
    """FFmpeg kurulu mu kontrol et"""
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        logger.info(f"✅ FFmpeg bulundu: {ffmpeg_path}")
        return True
    else:
        logger.warning("⚠️ FFmpeg bulunamadı! Video üretimi yapılamayacak.")
        return False
