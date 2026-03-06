"""
Video PRO AI - Extended Modules
Stainless PC Farm Integration + hesaplar.txt Support + Viral Video AI
"""

from .account_manager import AccountManager
from .network_controller import NetworkController
from .multi_uploader import MultiUploader
from .telegram_manager import TelegramManager
from .hesaplar_parser import HesaplarParser
from .youtube_uploader import YouTubeUploader
from .unified_uploader import UnifiedUploader

# Viral Video Modülleri
from .tts_generator import TTSGenerator
from .scenario_generator import ScenarioGenerator
from .content_fetcher import ContentFetcher  # Eski modül (backward compatibility)
from .multi_stock_fetcher import MultiStockFetcher  # Yeni modül (Pexels + Pixabay + Gemini)
from .viral_video_producer import ViralVideoProducer
from .video_assembler import VideoAssembler
from .video_scheduler import VideoScheduler
from .affiliate_manager import AffiliateManager

# Utilities
from .asset_downloader import AssetDownloader, ensure_assets_ready

# Analytics (Cash Flow Engine)
from .video_tracker import VideoTracker
from .analytics_scraper import get_scraper, TikTokAnalyticsScraper, YouTubeShortsAnalytics
from .viral_detector import ViralDetector
from .analytics_manager import AnalyticsManager

# Whisper Captions
from .whisper_captioner import WhisperCaptioner

# Humanization (Anti-Ban) - optional (selenium paketlenmemiş olabilir)
try:
    from .humanized_browser import HumanizedBrowser
    _HUMANIZED_BROWSER_AVAILABLE = True
except Exception:
    HumanizedBrowser = None
    _HUMANIZED_BROWSER_AVAILABLE = False

__all__ = [
    # Hesap ve Yükleme
    'AccountManager', 
    'NetworkController', 
    'MultiUploader', 
    'TelegramManager',
    'YouTubeUploader',
    'UnifiedUploader',
    
    # Viral Video AI
    'TTSGenerator',
    'ScenarioGenerator',
    'ContentFetcher',  # Eski modül (backward compatibility)
    'MultiStockFetcher',  # Yeni modül (Pexels + Pixabay + Gemini)
    'ViralVideoProducer',
    'VideoAssembler',
    'VideoScheduler',
    'AffiliateManager',
    
    # Analytics (Cash Flow Engine)
    'VideoTracker',
    'get_scraper',
    'TikTokAnalyticsScraper',
    'YouTubeShortsAnalytics',
    'ViralDetector',
    'AnalyticsManager',
    
    # Whisper Captions
    'WhisperCaptioner',
    
    # Utilities
    'AssetDownloader',
    'ensure_assets_ready'
]

if _HUMANIZED_BROWSER_AVAILABLE:
    __all__.append('HumanizedBrowser')
