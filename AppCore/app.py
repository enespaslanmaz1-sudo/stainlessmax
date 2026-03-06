"""
Video PRO AI - Python Application
Flask Backend + Web UI
Windows 11 Optimized Version
"""
import os
import sys
import json
import subprocess
import threading
import socket
import time
import random
import webbrowser
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Windows 11 specific optimizations
if os.name == 'nt':
    # Enable UTF-8 mode for Windows 11
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Windows 11 DPI awareness
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception as e:
        print(f"Warning: Failed to set DPI awareness: {e}")
    # Windows 11 console improvements
    try:
        import ctypes.wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception as e:
        print(f"Warning: Failed to set console mode: {e}")

# Load environment variables
load_dotenv()

def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SAAS_MODE = _env_flag("SAAS_MODE", False)
DESKTOP_MODE = _env_flag("DESKTOP_MODE", not SAAS_MODE)
ENABLE_TELEGRAM_BOT = _env_flag("ENABLE_TELEGRAM_BOT", False)

from flask import Flask, render_template, jsonify, request, send_from_directory, g
from flask_socketio import SocketIO, emit

# Initialize Socket Manager
from lib.socket_manager import init_socket_manager, emit_safe

import core

try:
    from lib.db.auth import install_auth
    from lib.db.session import create_engine_from_env, create_session_factory
    from lib.db.tenant_context import reset_to_default_tenant
    from lib.billing.http import install_billing_routes
    from lib.billing.quotas import PlanLimitReachedError, consume_job_quota_or_raise
except Exception:
    install_auth = None
    create_engine_from_env = None
    create_session_factory = None
    reset_to_default_tenant = None
    install_billing_routes = None
    PlanLimitReachedError = Exception
    consume_job_quota_or_raise = None

# STAINLESS MAX Version
VERSION = "v2.1"

# Import Viral Producer - LAZY LOAD
producer_instance = None
def get_producer():
    global producer_instance
    if producer_instance is None:
        from modules.viral_video_producer import ViralVideoProducer
        try:
            producer_instance = ViralVideoProducer()
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to initialize ViralVideoProducer: {e}")
            producer_instance = None
    return producer_instance

# Import config manager and logger
try:
    from lib.config_manager import get_config_manager, ConfigManager
    from lib.logger import logger, SecureLogger
    from lib.error_handler import get_error_handler, handle_error, log_error
    from lib.gemini_oauth import get_gemini_oauth
    config_manager = get_config_manager()
    error_handler = get_error_handler()
    gemini_oauth = (
        config_manager.get_gemini_oauth_client()
        if config_manager and hasattr(config_manager, "get_gemini_oauth_client")
        else None
    )
except ImportError as e:
    print(f"Warning: Config manager not available: {e}")
    config_manager = None
    logger = None
    error_handler = None
    gemini_oauth = None

# pywebview/pythonnet, proje kökündeki "System" klasörü ile çakışabiliyor.
# (pythonnet "from System import ..." beklerken yerel klasör import edilebiliyor.)
_PYTHONNET_PATH_GUARD_ACTIVE = False

def _activate_pythonnet_path_guard() -> None:
    """Temel sys.path girdilerinde yerel 'System' klasörü çakışmasını engelle."""
    global _PYTHONNET_PATH_GUARD_ACTIVE
    if _PYTHONNET_PATH_GUARD_ACTIVE:
        return

    cleaned = []
    for p in list(sys.path):
        try:
            if not p:
                continue
            if os.path.isdir(os.path.join(p, "System")):
                # Bu path pythonnet için problemli (yerel System klasörü)
                continue
            cleaned.append(p)
        except Exception:
            cleaned.append(p)

    # Sıralamayı koruyarak sys.path'i güncelle
    sys.path[:] = cleaned
    _PYTHONNET_PATH_GUARD_ACTIVE = True


def _sanitize_system_module_for_pythonnet() -> None:
    """Yanlış yüklenmiş System modülünü temizle ve pythonnet tarafını ısıt."""
    try:
        mod = sys.modules.get("System")
        if mod is not None:
            mod_file = str(getattr(mod, "__file__", "") or "")
            # Gerçek CLR namespace'i dosya tabanlı olmaz; yerel System paketi ise temizle.
            if mod_file:
                sys.modules.pop("System", None)
        # pythonnet/clr import'u erken dene; başarısız olursa log akışı zaten yakalayacak.
        try:
            import clr  # noqa: F401
        except Exception:
            pass
    except Exception:
        pass


# Req 4: Missing imports
try:
    _activate_pythonnet_path_guard()
    _sanitize_system_module_for_pythonnet()
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    webview = None
    WEBVIEW_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

# Cross-platform support with Windows 11 optimizations
if os.name == 'nt':
    CREATE_NO_WINDOW = 0x08000000
    # Windows 11 specific subprocess flags
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    SUBPROCESS_FLAGS = CREATE_NO_WINDOW | DETACHED_PROCESS
else:
    CREATE_NO_WINDOW = 0
    SUBPROCESS_FLAGS = 0

try:
    import telebot
except ImportError:
    telebot = None

bot_instance = None # Global instance for notifications

# Helper function to send notifications to Telegram admin
def notify_admin(message, video_path=None):
    """Send a text message and optionally a video to the Telegram admin."""
    try:
        if config_manager:
            token = config_manager.get_api_key("telegram_token")
            admin_id = config_manager.get_api_key("telegram_admin")
        else:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            admin_id = os.getenv("TELEGRAM_ADMIN_ID", "")
        
        # Req 3: Basic check
        if not token or not admin_id:
            return

        # Initialize bot just-in-time if needed, or use global
        global bot_instance
        if not bot_instance and telebot:
             bot_instance = telebot.TeleBot(token)

        if not bot_instance: return

        if video_path:
            with open(video_path, "rb") as video:
                bot_instance.send_video(
                    admin_id,
                    video,
                    caption=message,
                    parse_mode="Markdown",
                )
        else:
            bot_instance.send_message(
                admin_id,
                message,
                parse_mode="Markdown",
            )

    except Exception as e:
        if error_handler:
            error_context = handle_error(e, {
                "context": "telegram_notification",
                "message": message,
                "video_path": video_path
            })
            file_log(f"[BOT-ERR] Bildirim gönderilemedi: {e}")
        else:
            file_log(f"[BOT-ERR] Bildirim gönderilemedi: {e}")


# Prefixes that trigger Telegram notifications
NOTIFY_PREFIXES = (
    "[START]",
    "[SUCCESS]",
    "[BATCH]",
    "[AUTO]",
    "[ONAY]",
    "[ERROR]",
    "[SYSTEM]",
)

# Windows specific flag to hide console windows
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

# Configuration
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    BASE_DIR = Path(sys.executable).parent
    # Templates/static PyInstaller datas içinde AppCore altında paketleniyor
    TEMPLATE_DIR = Path(sys._MEIPASS) / "AppCore" / "templates"
    STATIC_DIR = Path(sys._MEIPASS) / "AppCore" / "static"
else:
    # Running as script
    BASE_DIR = Path(__file__).parent
    TEMPLATE_DIR = "templates"
    STATIC_DIR = "static"

ASSETS_DIR = BASE_DIR / "assets"
OUTPUTS_DIR = BASE_DIR / "outputs"
TOKENS_DIR = BASE_DIR / "tokens"

# Create directories
for d in [ASSETS_DIR, OUTPUTS_DIR, TOKENS_DIR]:
    d.mkdir(exist_ok=True)

# Initialize configuration and logging
if logger:
    file_logger = logger
else:
    file_logger = None

# Log Buffer for UI Persistence
LOG_BUFFER = []
MAX_LOG_BUFFER = 100

def file_log(message):
    """Log message to file and console"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"

    # Print to console (pytest/no-disk-space gibi ortamlarda patlamasın)
    try:
        print(log_message)
    except OSError:
        pass

    # Write to log file
    try:
        log_file = BASE_DIR / "app.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
    except Exception as e:
        if error_handler:
            handle_error(e, {"context": "log_file_write", "log_file": str(log_file)})
        try:
            print(f"Failed to write to log file: {e}")
        except OSError:
            pass

    # Use structured logger if available
    if file_logger:
        file_logger.info(message)

    # Buffer for UI
    global LOG_BUFFER
    LOG_BUFFER.append(log_message)
    if len(LOG_BUFFER) > MAX_LOG_BUFFER:
        LOG_BUFFER.pop(0)

# ALIAS for log compatibility
log = file_log


def _log_template_diagnostics(context: str) -> None:
    """Template/static çözümleme durumunu runtime'da detaylı logla."""
    try:
        frozen = bool(getattr(sys, "frozen", False))
        meipass = str(getattr(sys, "_MEIPASS", "") or "")
        exe_path = str(getattr(sys, "executable", "") or "")
        cwd = os.getcwd()

        tf = str(getattr(app, "template_folder", "") or "") if "app" in globals() else ""
        sf = str(getattr(app, "static_folder", "") or "") if "app" in globals() else ""

        template_candidate = Path(tf) / "dashboard_v2.html" if tf else None
        template_exists = template_candidate.exists() if template_candidate else False

        file_log(
            "[STARTUP-TEMPLATE-DIAG] "
            f"context={context} frozen={frozen} cwd={cwd} "
            f"__file__={__file__} exe={exe_path} meipass={meipass} "
            f"BASE_DIR={BASE_DIR} TEMPLATE_DIR={TEMPLATE_DIR} STATIC_DIR={STATIC_DIR} "
            f"app.template_folder={tf} app.static_folder={sf} "
            f"dashboard_candidate={template_candidate} dashboard_exists={template_exists}"
        )
    except Exception as e:
        file_log(f"[STARTUP-TEMPLATE-DIAG] context={context} diag_failed={e}")

# Load settings and configuration
def load_settings():
    """Load settings from settings.json and environment variables"""
    settings_file = BASE_DIR / "settings.json"
    settings = {}
    
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception as e:
            if error_handler:
                handle_error(e, {"context": "settings_json_load", "file": str(settings_file)})
            file_log(f"Failed to load settings.json: {e}")
    
    # Use config manager if available
    if config_manager:
        try:
            return {
                "api_keys": config_manager.api_keys.model_dump(),
                "youtube": config_manager.youtube_config.model_dump(),
                "tiktok": config_manager.tiktok_config.model_dump(),
                "n8n": config_manager.n8n_config.model_dump()
            }
        except Exception as e:
            if error_handler:
                handle_error(e, {"context": "config_manager_load"})
            file_log(f"Config manager error: {e}")
    
    # Fallback to settings.json and environment variables
    return {
        "api_keys": {
            "pexels": os.getenv(
                "PEXELS_API_KEY",
                settings.get("api_keys", {}).get("pexels", ""),
            ),
            "pixabay": os.getenv(
                "PIXABAY_API_KEY",
                settings.get("api_keys", {}).get("pixabay", ""),
            ),
            "gemini": os.getenv(
                "GEMINI_API_KEY",
                settings.get("api_keys", {}).get("gemini", ""),
            ),
            "telegram_token": os.getenv(
                "TELEGRAM_BOT_TOKEN",
                settings.get("api_keys", {}).get("telegram_token", ""),
            ),
            "telegram_admin": os.getenv(
                "TELEGRAM_ADMIN_ID",
                settings.get("api_keys", {}).get("telegram_admin", ""),
            ),
            "apify": os.getenv(
                "APIFY_API_TOKEN",
                settings.get("api_keys", {}).get("apify", ""),
            ),
            "prototipal": os.getenv(
                "PROTOTIPAL_API_KEY",
                settings.get("api_keys", {}).get("prototipal", ""),
            ),
        },
        "youtube": settings.get("youtube", {}),
        "tiktok": settings.get("tiktok", {}),
        "n8n": settings.get("n8n", {}),
    }

def save_settings():
    """Save settings to file"""
    if config_manager:
        try:
            config_manager.save_config()
        except Exception as e:
            if error_handler:
                handle_error(e, {"context": "config_save"})
            file_log(f"Failed to save config: {e}")
    else:
        file_log("Config manager not available, settings not saved")

# Load configuration - Skip heavy operations on startup
try:
    config = load_settings()
    # Remove global state variables - use config_manager instead
    if config_manager:
        file_log("Using config manager for configuration")
    else:
        file_log("Config manager not available, using fallback configuration")
        # Keep minimal fallback for compatibility
        API_KEYS = config["api_keys"]
        YOUTUBE_CONFIG = config["youtube"]
        TIKTOK_CONFIG = config["tiktok"]
        N8N_CONFIG = config["n8n"]
except Exception as e:
    if error_handler:
        handle_error(e, {"context": "config_loading_startup"})
    file_log(f"Config loading error: {e}")
    # Use minimal fallback config for faster startup
    if not config_manager:
        API_KEYS = {}
        YOUTUBE_CONFIG = {}
        TIKTOK_CONFIG = {}
        N8N_CONFIG = {}

# Languages
LANGUAGES = [
    {
        "id": "tr",
        "name": "Türkçe",
        "flag": "🇹🇷",
        "voice": "tr-TR-AhmetNeural",
        "lang": "tr",
    },
    {
        "id": "en",
        "name": "English",
        "flag": "🇺🇸",
        "voice": "en-US-ChristopherNeural",
        "lang": "en",
    },
    {
        "id": "de",
        "name": "Deutsch",
        "flag": "🇩🇪",
        "voice": "de-DE-ConradNeural",
        "lang": "de",
    },
    {
        "id": "fr",
        "name": "Français",
        "flag": "🇫🇷",
        "voice": "fr-FR-HenriNeural",
        "lang": "fr",
    },
    {
        "id": "es",
        "name": "Español",
        "flag": "🇪🇸",
        "voice": "es-ES-AlvaroNeural",
        "lang": "es",
    },
    {
        "id": "pt",
        "name": "Português",
        "flag": "🇧🇷",
        "voice": "pt-BR-AntonioNeural",
        "lang": "pt",
    },
    {
        "id": "it",
        "name": "Italiano",
        "flag": "🇮🇹",
        "voice": "it-IT-DiegoNeural",
        "lang": "it",
    },
    {
        "id": "ru",
        "name": "Русский",
        "flag": "🇷🇺",
        "voice": "ru-RU-DmitryNeural",
        "lang": "ru",
    },
    {
        "id": "ar",
        "name": "العربية",
        "flag": "🇸🇦",
        "voice": "ar-SA-HamedNeural",
        "lang": "ar",
    },
    {
        "id": "hi",
        "name": "हिंदी",
        "flag": "🇮🇳",
        "voice": "hi-IN-MadhurNeural",
        "lang": "hi",
    },
    {
        "id": "ja",
        "name": "日本語",
        "flag": "🇯🇵",
        "voice": "ja-JP-KeitaNeural",
        "lang": "ja",
    },
    {
        "id": "ko",
        "name": "한국어",
        "flag": "🇰🇷",
        "voice": "ko-KR-InJoonNeural",
        "lang": "ko",
    },
    {
        "id": "zh",
        "name": "中文",
        "flag": "🇨🇳",
        "voice": "zh-CN-YunxiNeural",
        "lang": "zh-CN",
    },
    {
        "id": "nl",
        "name": "Nederlands",
        "flag": "🇳🇱",
        "voice": "nl-NL-MaartenNeural",
        "lang": "nl",
    },
    {
        "id": "pl",
        "name": "Polski",
        "flag": "🇵🇱",
        "voice": "pl-PL-MarekNeural",
        "lang": "pl",
    },
    {
        "id": "id",
        "name": "Indonesia",
        "flag": "🇮🇩",
        "voice": "id-ID-ArdiNeural",
        "lang": "id",
    },
]

STORY_DATA = Path(__file__).parent / "stock.json"
# Re-using stock json? No, SCENARIOS was hardcoded.
# For now keep SCENARIOS hardcoded or move to data file later.
SCENARIOS = {
    "mystery": [
        {
            "title": "Titanik'in Gerçek Hikayesi 🚢",
            "topic": "titanic ship iceberg",
            "script": (
                "14 Nisan 1912 gecesi Titanik buzdağına çarptığında aslında "
                "dev bir planın kurbanı mıydı? Batan gemi Titanik değil, ikiz "
                "kardeşi Olympic'ti."
            ),
        },
        {
            "title": "Piramitlerin Gizli Odası 🔺",
            "topic": "egypt pyramid mystery",
            "script": (
                "Keops Piramidi'nin kalbinde kozmik ışınlarla keşfedilen 30 "
                "metrelik devasa boşluk. Binlerce yıldır mühürlü bu oda neyi "
                "saklıyor?"
            ),
        },
        {
            "title": "Bermuda Şeytan Üçgeni 🌊",
            "topic": "bermuda triangle ocean",
            "script": (
                "Florida, Bermuda ve Porto Riko arasındaki bölgede onlarca "
                "uçak ve yüzlerce gemi kayboldu."
            ),
        },
        {
            "title": "Voynich El Yazması 📜",
            "topic": "voynich manuscript ancient",
            "script": (
                "600 yıldır kimsenin çözemediği kitap. Kimin yazdığı, hangi "
                "dilde olduğu bilinmiyor."
            ),
        },
        {
            "title": "Okyanusun Dibindeki Ses 🔊",
            "topic": "bloop underwater mystery",
            "script": (
                "1997'de Pasifik'in derinliklerinde kaydedilen The Bloop. "
                "5000 km öteden duyulan bu ses."
            ),
        },
        {
            "title": "Nazca Çizgileri 🛸",
            "topic": "nazca lines peru",
            "script": (
                "Peru çölündeki devasa figürler sadece havadan görülebiliyor. "
                "2000 yıl önce kim, neden yaptı?"
            ),
        },
        {
            "title": "Dyatlov Geçidi Faciası ❄️",
            "topic": "dyatlov pass incident",
            "script": (
                "1959'da 9 dağcı donarak öldü. Çadırı içeriden yırttılar, "
                "çıplak ayakla kaçtılar."
            ),
        },
        {
            "title": "Area 51'in Sırları 👽",
            "topic": "area 51 ufo secrets",
            "script": (
                "Nevada çölündeki gizli üste ne saklıyorlar? Roswell "
                "kazasından kalan dünya dışı teknoloji mi?"
            ),
        },
        {
            "title": "Atlantis Gerçek mi? 🏛️",
            "topic": "atlantis lost city",
            "script": (
                "Platon'un anlattığı gelişmiş uygarlık bir gecede battı."
            ),
        },
        {
            "title": "Zaman Yolculuğu Kanıtları ⏰",
            "topic": "time travel evidence",
            "script": (
                "1940 fotoğrafındaki modern gözlüklü adam, eski resimlerdeki "
                "dijital cihazlar."
            ),
        },
        {
            "title": "Stonehenge'in Gizemi 🪨",
            "topic": "stonehenge mystery",
            "script": "4500 yıl önce 25 tonluk taşlar 250 km taşındı.",
        },
        {
            "title": "Jack the Ripper Kimdi? 🔪",
            "topic": "jack ripper mystery",
            "script": (
                "1888 Londra'sında 5 kadını öldüren seri katil hiç "
                "yakalanmadı."
            ),
        },
        {
            "title": "Kayıp Koloni Roanoke 🏚️",
            "topic": "roanoke lost colony",
            "script": "1590'da 117 kişilik koloni iz bırakmadan kayboldu.",
        },
        {
            "title": "Taş Küreler Gizemli 🔮",
            "topic": "costa rica stone spheres",
            "script": "Kosta Rika'da yüzlerce mükemmel yuvarlak taş küre.",
        },
        {
            "title": "DB Cooper Nerede? 🪂",
            "topic": "db cooper hijack",
            "script": (
                "1971'de uçak kaçırıp 200.000 dolarla paraşütle atlayan adam."
            ),
        },
        {
            "title": "Wow! Sinyali 📡",
            "topic": "wow signal space",
            "script": "1977'de uzaydan gelen 72 saniyelik sinyal.",
        },
    ],
    "finance": [
        {
            "title": "Bileşik Faizin Gücü 💰",
            "topic": "compound interest wealth",
            "script": (
                "Einstein'ın 8. harikası dediği bileşik faiz. 25 yaşında ayda "
                "500 TL yatırsan, 65 yaşında milyoner olursun."
            ),
        },
        {
            "title": "50/30/20 Kuralı 📊",
            "topic": "budget money rule",
            "script": (
                "Gelirinin %50'si ihtiyaçlara, %30'u isteklere, %20'si "
                "tasarrufa."
            ),
        },
        {
            "title": "Pasif Gelir Kaynakları 🏦",
            "topic": "passive income streams",
            "script": (
                "Uyurken para kazanmanın 7 yolu: temettü hisseleri, "
                "kira geliri, dijital ürünler."
            ),
        },
        {
            "title": "Acil Durum Fonu 🆘",
            "topic": "emergency fund saving",
            "script": "6 aylık harcamanı kenara koy. İş kaybı, sağlık sorunu.",
        },
        {
            "title": "Borç Çığı Yöntemi ❄️",
            "topic": "debt avalanche method",
            "script": "En yüksek faizli borçtan başla, küçüklerden değil.",
        },
        {
            "title": "Emeklilik Hesabı 👴",
            "topic": "retirement savings account",
            "script": (
                "Bireysel emeklilik hesabına devam et. Devlet katkısı "
                "ve vergi avantajı."
            ),
        },
        {
            "title": "Enflasyonla Mücadele 📈",
            "topic": "inflation hedge investing",
            "script": (
                "Paranın değeri her yıl eriyor. Altın, hisse, gayrimenkul."
            ),
        },
        {
            "title": "Yatırım Piramidi 🔺",
            "topic": "investment pyramid strategy",
            "script": (
                "Temelde güvenli varlıklar, ortada dengeli, tepede riskli."
            ),
        },
        {
            "title": "Vergi Optimizasyonu 📋",
            "topic": "tax optimization legal",
            "script": "Yasal yollarla vergini azalt.",
        },
        {
            "title": "Side Hustle Fikirleri 💡",
            "topic": "side income ideas",
            "script": "Freelance, dropshipping, blog, YouTube, danışmanlık.",
        },
        {
            "title": "Kredi Puanını Yükselt 📊",
            "topic": "credit score improve",
            "script": (
                "Faturaları zamanında öde, kredi kullanım oranını düşür."
            ),
        },
        {
            "title": "Dolar Maliyet Ortalaması 💵",
            "topic": "dollar cost averaging",
            "script": "Her ay aynı miktarı yatır, fiyat ne olursa olsun.",
        },
        {
            "title": "Fire Movement 🔥",
            "topic": "financial independence retire",
            "script": "Gelirinin %50-70'ini biriktir, 40 yaşında emekli ol.",
        },
        {
            "title": "Zengin Baba Yoksul Baba 📚",
            "topic": "rich dad poor dad",
            "script": "Varlık ve yükümlülük farkını öğren.",
        },
        {
            "title": "Maaşını İkiye Katla 💼",
            "topic": "salary negotiation tips",
            "script": "Pazarlık yapmaktan korkma.",
        },
        {
            "title": "Kripto Temelleri ₿",
            "topic": "crypto basics blockchain",
            "script": "Bitcoin, Ethereum, blockchain.",
        },
    ],
    "health": [
        {
            "title": "Soğuk Duş Mucizesi 🚿",
            "topic": "cold shower benefits",
            "script": "30 saniye soğuk su metabolizmayı hızlandırır.",
        },
        {
            "title": "7 Saat Uyku Şart 😴",
            "topic": "sleep health importance",
            "script": (
                "Yetersiz uyku obezite, kalp hastalığı, bunama riskini "
                "artırır."
            ),
        },
        {
            "title": "Aralıklı Oruç 🍽️",
            "topic": "intermittent fasting",
            "script": "16 saat oruç, 8 saat yeme penceresi.",
        },
        {
            "title": "Bağırsak İkinci Beyin 🦠",
            "topic": "gut health microbiome",
            "script": "Bağırsakta 100 trilyon bakteri.",
        },
        {
            "title": "Günde 10.000 Adım 🚶",
            "topic": "walking steps daily",
            "script": "Yürümek en hafife alınan egzersiz.",
        },
        {
            "title": "Şeker Zehiri ⚠️",
            "topic": "sugar health effects",
            "script": "İşlenmiş şeker bağımlılık yapar.",
        },
        {
            "title": "Meditasyon 10 Dakika 🧘",
            "topic": "meditation benefits mind",
            "script": "Günde 10 dakika meditasyon kortizolü düşürür.",
        },
        {
            "title": "Su İç, 2 Litre 💧",
            "topic": "hydration water health",
            "script": "Vücudun %60'ı su.",
        },
        {
            "title": "Güneş Vitamini D ☀️",
            "topic": "vitamin d sunlight",
            "script": "Sabah 15 dakika güneş.",
        },
        {
            "title": "Protein Yetersizliği 🥩",
            "topic": "protein muscle health",
            "script": "Her öğünde protein.",
        },
        {
            "title": "Stres Öldürür 😰",
            "topic": "stress health chronic",
            "script": "Kronik stres kortizol yükseltir.",
        },
        {
            "title": "Omega-3 Gücü 🐟",
            "topic": "omega3 fish oil brain",
            "script": "Haftada 2 kez yağlı balık.",
        },
        {
            "title": "Otur Kalk Testi 🧎",
            "topic": "sit rise test longevity",
            "script": "Yere otur, elleri kullanmadan kalk.",
        },
        {
            "title": "Sigara Bırakmanın Faydaları 🚭",
            "topic": "quit smoking benefits",
            "script": "20 dakikada kalp atışı normale döner.",
        },
        {
            "title": "Alkol Gerçekleri 🍺",
            "topic": "alcohol health effects",
            "script": "Güvenli alkol miktarı yok.",
        },
        {
            "title": "Postur Düzelt 🧍",
            "topic": "posture spine health",
            "script": "Kambur duruş sırt ağrısı yapar.",
        },
    ],
}

# Account Manager Integration - LAZY LOAD
account_manager_instance = None
YOUTUBE_CHANNELS = []
TIKTOK_ACCOUNTS = []
INSTAGRAM_ACCOUNTS = []

def get_account_manager():
    global account_manager_instance
    if account_manager_instance is None:
        try:
            from modules.account_manager import AccountManager
            account_manager_instance = AccountManager()
        except ImportError as e:
            file_log(f"[SYSTEM] AccountManager import failed: {e}")
            account_manager_instance = None
    return account_manager_instance

def refresh_accounts():
    """Load accounts from AccountManager into global lists"""
    global YOUTUBE_CHANNELS, TIKTOK_ACCOUNTS, INSTAGRAM_ACCOUNTS
    
    mgr = get_account_manager()
    if not mgr:
        # Fallback/Hardcoded (kept for safety if module fails)
        YOUTUBE_CHANNELS = [
             {"id": "UC_TEST_1", "name": "Future Lab", "theme": "mystery"},
             {"id": "UC_TEST_2", "name": "The Power of Money", "theme": "finance"},
             {"id": "UC_TEST_3", "name": "Healthy Living", "theme": "health"},
             {"id": "UC_TEST_4", "name": "Information Repository", "theme": "mystery"},
             {"id": "UC_TEST_5", "name": "Reddit History", "theme": "history"}
        ]
        TIKTOK_ACCOUNTS = [
            {"id": "tiktok_main", "name": "Main Account", "theme": "general"}
        ]
        return

    try:
        # Load accounts
        youtube_accs = mgr.get_active_accounts("youtube")
        tiktok_accs = mgr.get_active_accounts("tiktok")
        instagram_accs = mgr.get_active_accounts("instagram")
        
        # Convert to dictionary format expected by frontend
        YOUTUBE_CHANNELS = [
            {
                "id": acc.id,
                "name": acc.name,
                "theme": "mystery" if "gizem" in acc.name.lower() else "finance" if "para" in acc.name.lower() else "general"
            }
            for acc in youtube_accs
        ]
        
        TIKTOK_ACCOUNTS = [
            {
                "id": acc.id,
                "name": acc.name,
                "theme": "general"
            }
            for acc in tiktok_accs
        ]

        INSTAGRAM_ACCOUNTS = [
            {
                "id": acc.id,
                "name": acc.name,
                "theme": "general"
            }
            for acc in instagram_accs
        ]
        
        file_log(f"[SYSTEM] Loaded {len(YOUTUBE_CHANNELS)} YT, {len(TIKTOK_ACCOUNTS)} TT, {len(INSTAGRAM_ACCOUNTS)} IG accounts")
    except Exception as e:
        file_log(f"[SYSTEM] Error refreshing accounts: {e}")

# Initial load: avoid concurrent import deadlocks by loading once on main thread.
# Pytest ortamında import yan etkilerini azaltmak için atlanır.
if not os.getenv("PYTEST_CURRENT_TEST"):
    try:
        refresh_accounts()
    except Exception as _refresh_accounts_error:
        file_log(f"[SYSTEM] Initial account refresh failed: {_refresh_accounts_error}")


# Stock file path
STOCK_FILE = BASE_DIR / "stock.json"

def load_stock():
    if STOCK_FILE.exists():
        try:
            with open(STOCK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            file_log(f"Failed to load stock file: {e}")
            return {}
    return {}

def save_stock(stock_data):
    with open(STOCK_FILE, "w", encoding="utf-8") as f:
        json.dump(stock_data, f, indent=2, ensure_ascii=False)


# Flask App
app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)

_log_template_diagnostics("module_init.after_flask_app")

# Secure secret key
import secrets
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config['JSON_AS_ASCII'] = False # Fix for Turkish characters

# Async mode threading is crucial for PyWebView compatibility
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
init_socket_manager(socketio)

DB_SESSION_FACTORY = None
if install_auth and create_engine_from_env and create_session_factory:
    try:
        _db_engine = create_engine_from_env()
        DB_SESSION_FACTORY = create_session_factory(_db_engine)
    except Exception as _db_init_error:
        DB_SESSION_FACTORY = None
        if SAAS_MODE and os.getenv("DATABASE_URL"):
            raise
        print(f"[AUTH] Database init skipped: {_db_init_error}")

if install_auth:
    install_auth(app, DB_SESSION_FACTORY)
else:
    @app.route("/api/auth/register", methods=["POST"])
    def _auth_register_unavailable():
        return jsonify({"error": "auth_module_unavailable"}), 503

    @app.route("/api/auth/login", methods=["POST"])
    def _auth_login_unavailable():
        return jsonify({"error": "auth_module_unavailable"}), 503

    @app.route("/api/auth/logout", methods=["POST"])
    def _auth_logout_unavailable():
        return jsonify({"ok": True})

if install_billing_routes:
    install_billing_routes(app, DB_SESSION_FACTORY)
else:
    @app.route("/api/billing/plans", methods=["GET"])
    def _billing_plans_unavailable():
        return jsonify([])

    @app.route("/api/billing/plan-request", methods=["POST"])
    def _billing_plan_request_unavailable():
        return jsonify({"error": "billing_module_unavailable"}), 503


PUBLIC_ENDPOINT_PATHS = {
    "/",
    "/api/health",
    "/api/status",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/billing/plans",
    "/api/billing/plan-request",
}


def create_app() -> tuple[Flask, SocketIO]:
    """Return the shared singleton Flask/SocketIO application pair."""
    return app, socketio


def _is_public_endpoint() -> bool:
    if request.method == "OPTIONS":
        return True

    endpoint = request.endpoint or ""
    if endpoint == "static":
        return True

    path = request.path or ""
    if path.startswith("/static/"):
        return True

    return path in PUBLIC_ENDPOINT_PATHS


@app.before_request
def _enforce_auth_in_saas_mode():
    if not SAAS_MODE:
        return None
    if _is_public_endpoint():
        return None

    if getattr(g, "auth_source", "default") == "default":
        return jsonify({"error": "authentication_required"}), 401

    return None


@app.after_request
def _reset_tenant_context_after_request(response):
    if reset_to_default_tenant:
        reset_to_default_tenant()
    return response


@app.teardown_request
def _reset_tenant_context_teardown(_error):
    if reset_to_default_tenant:
        reset_to_default_tenant()

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    file_log(f"[SOCKET] Client connected: {request.sid}")
    # Send log history
    emit('log_history', {'logs': LOG_BUFFER})

def check_windows11_compatibility():
    """Check Windows 11 specific features and compatibility"""
    if os.name != 'nt':
        return True
    
    try:
        import platform
        import subprocess
        
        # Check Windows version
        version = platform.version()
        build = int(version.split('.')[-1]) if version else 0
        
        # Windows 11 starts from build 22000
        is_windows11 = build >= 22000
        
        if is_windows11:
            file_log("[SYSTEM] Windows 11 detected - Full compatibility mode")
            
            # Check for Windows 11 specific features
            try:
                # Check if Windows Terminal is available
                result = subprocess.run(
                    ["where", "wt"], 
                    capture_output=True, 
                    text=True,
                    creationflags=SUBPROCESS_FLAGS
                )
                if result.returncode == 0:
                    file_log("[SYSTEM] Windows Terminal available")
            except Exception as e:
                file_log(f"[SYSTEM] Windows Terminal check failed: {e}")
                
            # Check for WebView2 runtime
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
                )
                winreg.CloseKey(key)
                file_log("[SYSTEM] WebView2 runtime detected")
            except Exception as e:
                file_log("[SYSTEM] WebView2 runtime not found - using fallback")
                
        else:
            file_log("[SYSTEM] Windows 10 detected - Compatibility mode")
            
        return True
        
    except Exception as e:
        file_log(f"[SYSTEM] Compatibility check failed: {e}")
        return True  # Continue anyway


def get_all_scenarios():
    """Get all scenarios from all themes"""
    all_scenarios = []
    for theme, scenarios in SCENARIOS.items():
        for s in scenarios:
            all_scenarios.append({**s, "theme": theme})
    return all_scenarios


def get_random_scenario(theme=None):
    """Get a random scenario, optionally filtered by theme"""
    if theme and theme in SCENARIOS:
        return random.choice(SCENARIOS[theme])
    all_s = get_all_scenarios()
    return random.choice(all_s)

@app.route("/")
def index():
    """Main dashboard (Navy Blue V2)"""
    _log_template_diagnostics("route.index.before_render")
    return render_template("dashboard_v2.html")

@app.route("/setup")
def setup_page():
    """Setup / API Keys page"""
    return render_template("setup.html")

@app.route("/admin")
def admin_page():
    """Admin Panel page"""
    return render_template("admin.html")


# ============================================
# ADMIN API ENDPOINTS
# ============================================
ADMIN_SECRET_TOKEN = "stainlessmax_admin_2026"  # Admin güvenlik anahtarı

def _verify_admin_token():
    """Admin token doğrulama"""
    token = request.headers.get("X-Admin-Token", "")
    if token != ADMIN_SECRET_TOKEN:
        return False
    return True

@app.route("/api/panel/stats")
def api_admin_stats():
    if not _verify_admin_token():
        return jsonify({"error": "Yetkisiz erişim"}), 403
    try:
        total_videos = len(list(OUTPUTS_DIR.glob("*.mp4")))
        return jsonify({
            "total_users": 1,
            "videos_today": total_videos,
            "system_status": "Online",
            "version": VERSION
        })
    except Exception as e:
        return jsonify({"total_users": 0, "videos_today": 0, "system_status": "Online"})

@app.route("/api/panel/users")
def api_admin_users():
    if not _verify_admin_token():
        return jsonify({"error": "Yetkisiz erişim"}), 403
    users = [{
        "id": "admin_1",
        "name": "Enes",
        "surname": "Paslanmaz",
        "email": "enespaslanmaz1@gmail.com",
        "plan": "ultra",
        "created_at": "2026-01-01"
    }]
    return jsonify({"users": users})

@app.route("/api/panel/users/<user_id>/plan", methods=["PUT"])
def api_admin_change_plan(user_id):
    if not _verify_admin_token():
        return jsonify({"error": "Yetkisiz erişim"}), 403
    data = request.json or {}
    new_plan = data.get("plan", "free")
    file_log(f"[ADMIN] Plan değiştirildi: {user_id} -> {new_plan}")
    return jsonify({"success": True, "message": f"Plan {new_plan} olarak güncellendi"})

@app.route("/api/panel/promo", methods=["GET", "POST"])
def api_admin_promo():
    if not _verify_admin_token():
        return jsonify({"error": "Yetkisiz erişim"}), 403
    if request.method == "POST":
        data = request.json or {}
        file_log(f"[ADMIN] Promo kodu oluşturuldu: {data.get('code')}")
        return jsonify({"success": True, "message": "Promo kodu oluşturuldu"})
    return jsonify({"promo_codes": []})

@app.route("/stainlessmax_logo.png")
def serve_stainless_logo():
    """Serve logo from app dir, project root or executable dir fallback."""
    candidates = [
        BASE_DIR / "stainlessmax_logo.png",
        BASE_DIR.parent / "stainlessmax_logo.png",
    ]

    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).parent / "stainlessmax_logo.png")

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return send_from_directory(str(candidate.parent), candidate.name)
        except Exception:
            continue

    return jsonify({"error": "logo_not_found"}), 404

@app.route("/api/health")
def health_check():
    """Health check endpoint for monitoring"""
    try:
        if config_manager:
            api_key_count = len([k for k, v in config_manager.api_keys.model_dump().items() if v])
        else:
            api_key_count = len([k for k, v in API_KEYS.items() if v]) if 'API_KEYS' in globals() else 0
        
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": VERSION,
            "services": {
                "api_keys": api_key_count,
                "outputs": len(list(OUTPUTS_DIR.glob("*.mp4"))),
                "cache": len(VIRAL_CACHE.get("data", []))
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route("/outputs/<path:filename>")
def serve_output(filename):
    """Serve video files with proper MIME type"""
    response = send_from_directory(OUTPUTS_DIR, filename)
    if filename.endswith('.mp4'):
        response.headers['Content-Type'] = 'video/mp4'
        response.headers['Accept-Ranges'] = 'bytes'
    return response

@app.route("/api/status")
def api_status():
    return jsonify({
        "scenarios": len(get_all_scenarios()),
        "languages": len(LANGUAGES),
        "youtube": YOUTUBE_CHANNELS,
        "tiktok": TIKTOK_ACCOUNTS,
    })

# Viral Content Discovery
VIRAL_CACHE = {"data": [], "timestamp": 0}
VIRAL_CACHE_TTL = 3600  # 1 hour

def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe"""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=SUBPROCESS_FLAGS if os.name == 'nt' else 0,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        if error_handler:
            handle_error(e, {"context": "audio_duration_check", "audio_path": str(audio_path)})
        file_log(f"[AUDIO-WARN] Duration check failed: {e}")
    return 60.0  # Default to 60 seconds

def fetch_viral_content(platform="youtube"):
    """Delegate to core.py"""
    return core.fetch_viral_content(platform)

def get_fallback_trends(platform):
    """Return hardcoded fallback trending topics when API fails."""
    if platform == "youtube":
        return [
            {
                "title": "5 Dakikada Hayatını Değiştirecek Bilgi",
                "topic": ["life hacks", "productivity", "motivation"],
                "platform": "youtube",
            },
            {
                "title": "Bu Sırlar Gizli Kaldı",
                "topic": ["mystery", "conspiracy", "hidden"],
                "platform": "youtube",
            },
            {
                "title": "Bilim İnsanları Açıklayamıyor",
                "topic": ["science", "unexplained", "discovery"],
                "platform": "youtube",
            },
            {
                "title": "Zenginlerin Söylemediği Gerçek",
                "topic": ["money", "wealth", "finance"],
                "platform": "youtube",
            },
            {
                "title": "Vücudun Sana Verdiği Uyarılar",
                "topic": ["health", "body", "warning signs"],
                "platform": "youtube",
            },
        ]
    else:
        return [
            {
                "title": "Bunu Bilmeden Geçme",
                "topic": ["facts", "education", "viral"],
                "platform": "tiktok",
            },
            {
                "title": "POV: Gizli Bilgi",
                "topic": ["pov", "secret", "mystery"],
                "platform": "tiktok",
            },
            {
                "title": "3 Saniyede Öğren",
                "topic": ["quicktips", "learn", "hack"],
                "platform": "tiktok",
            },
            {
                "title": "Herkes Bunu Yanlış Yapıyor",
                "topic": ["lifehack", "correct", "tips"],
                "platform": "tiktok",
            },
            {
                "title": "Bu Video Sonunda",
                "topic": ["wait", "surprise", "twist"],
                "platform": "tiktok",
            },
        ]

@app.route("/api/viral")
def api_viral():
    """Get current viral/trending content from both platforms."""
    global VIRAL_CACHE
    now = time.time()
    
    # Return cached data if still valid
    if (
        VIRAL_CACHE["data"]
        and (now - VIRAL_CACHE["timestamp"]) < VIRAL_CACHE_TTL
    ):
        return jsonify(VIRAL_CACHE["data"])
    
    # Fetch fresh data
    youtube_trends = fetch_viral_content("youtube")
    tiktok_trends = fetch_viral_content("tiktok")
    
    all_trends = (youtube_trends or []) + (tiktok_trends or [])
    VIRAL_CACHE = {"data": all_trends, "timestamp": now}
    
    return jsonify(all_trends)


@app.route("/api/languages")
def api_languages():
    return jsonify(LANGUAGES)

@app.route("/api/scenarios")
def api_scenarios():
    return jsonify(get_all_scenarios())

@app.route("/api/config")
def api_config():
    return jsonify({
        "youtube": YOUTUBE_CHANNELS,
        "tiktok": TIKTOK_ACCOUNTS,
        "instagram": locals().get('INSTAGRAM_ACCOUNTS', []),
        "languages": LANGUAGES,
    })

@app.route("/api/approve", methods=["POST"])
def api_approve():
    # Input validation
    if not request.json:
        return jsonify({"error": "No JSON data provided"}), 400
    
    data = request.json
    filename = data.get("filename", "").strip()
    platform = data.get("platform", "").strip()
    scenario_id = data.get("scenario_id")
    channel_id = data.get("channel_id")
    
    # Validate filename
    if not filename:
        return jsonify({"error": "Filename is required"}), 400
    
    # Security: Prevent path traversal attacks
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400
    
    # Validate platform
    if platform not in ["youtube", "tiktok"]:
        return jsonify({"error": "Invalid platform"}), 400
    
    # Check if file exists
    video_path = OUTPUTS_DIR / filename
    if not video_path.exists() or not video_path.is_file():
        return jsonify({"error": "Video file not found"}), 404
    
    file_log(f"[ONAY] Video onaylandı: {filename} ({platform})")
    
    # Remove from stock if it was a stock item
    if scenario_id and channel_id:
        try:
            stock = load_stock()
            if channel_id in stock:
                stock[channel_id] = [
                    s
                    for s in stock[channel_id]
                    if s.get("id") != scenario_id
                ]
                save_stock(stock)
                file_log(f"[STOCK] {scenario_id} stoktan düşüldü.")
        except Exception as e:
            if error_handler:
                handle_error(e, {"context": "stock_removal", "scenario_id": scenario_id, "channel_id": channel_id})
            file_log(f"[STOCK-ERR] {e}")

    # Shared videos cleanup at end of day logic
    try:
        with open(BASE_DIR / "shared_history.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().date()}|{filename}\n")
    except Exception as e:
        file_log(f"[HISTORY-ERR] {e}")
    
    # Upload video to Telegram when shared
    try:
        message = (
            "🚀 *Video Paylaşıldı!*\n\n"
            f"📂 Dosya: `{filename}`\n"
            f"🌐 Platform: {platform.upper()}"
        )
        if video_path.exists():
            notify_admin(message, video_path=str(video_path))
        else:
            notify_admin(message)
    except Exception as e:
        if error_handler:
            handle_error(e, {"context": "telegram_video_notification", "video_path": str(video_path) if video_path else None})
        file_log(f"[TELEGRAM-ERR] {e}")

    file_log(f"[ONAY] Paylaşım süreci başlatıldı ✅")
    return jsonify(
        {
            "status": "ok",
            "message": "Video onaylandı ve paylaşıldı.",
        }
    )

@app.route("/api/stock")
def get_stock():
    return jsonify(load_stock())

@app.route("/api/batch_stock", methods=["POST"])
def batch_stock():
    data = request.json
    days = data.get("days", 30)
    
    def run_batch():
        file_log(f"[BATCH] {days} günlük stok üretimi başlatıldı...")
        stock = load_stock()
        
        channels = YOUTUBE_CHANNELS + TIKTOK_ACCOUNTS
        for ch in channels:
            ch_id = ch["id"]
            if ch_id not in stock: stock[ch_id] = []
            
            existing_count = len(stock[ch_id])
            needed = days - existing_count
            
            if needed > 0:
                file_log(
                    f"[BATCH] {ch['name']} için {needed} yeni "
                    "senaryo üretiliyor..."
                )
                new_scenarios = generate_batch_from_gemini(ch["theme"], needed)
                if new_scenarios:
                    for s in new_scenarios:
                        stock_id = (
                            f"stock_{int(time.time())}_"
                            f"{random.randint(1000, 9999)}"
                        )
                        s["id"] = stock_id
                        stock[ch_id].append(s)
                    save_stock(stock)
        
        file_log(f"[BATCH] {days} günlük stok tamamlandı ✓")

    threading.Thread(target=run_batch).start()
    return jsonify({"status": "started"})

def validate_gemini_model(model_name):
    """Validate Gemini model name"""
    valid_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash-exp",
        "gemini-pro",
        "gemini-pro-vision",
        "gemini-2.0-flash-thinking-exp-01-21",
        "gemini-2.0-flash-thinking-exp",
        "gemini-3-deep-think"
    ]
    return model_name in valid_models or model_name.startswith("gemini-")


def make_gemini_request(prompt, gemini_key=None, model="gemini-2.5-flash"):
    """Make a validated Gemini API request with OAuth support and Key Rotation"""
    # Force upgrade to Thinking model if default is used
    if model == "gemini-2.5-flash" or model == "gemini-2.0-flash-thinking-exp-01-21":
        model = "gemini-3-deep-think"

    if not validate_gemini_model(model):
        file_log(f"[GEMINI-WARN] Invalid model name: {model}, using default")
        model = "gemini-3-deep-think"
    
    # Try OAuth first, then fallback to API key
    if gemini_oauth:
        try:
            response_text = gemini_oauth.generate_content(prompt, model)
            if response_text:
                file_log("[GEMINI] OAuth request successful")
                return response_text
            else:
                file_log("[GEMINI-WARN] OAuth request failed, trying API keys")
        except Exception as e:
             file_log(f"[GEMINI-ERR] OAuth request error: {e}")

    # Fallback to API key method
    target_key = gemini_key
    if not target_key and gemini_key_manager:
        target_key = gemini_key_manager.get_client().api_key if gemini_key_manager.get_client() else None
        # Actually safer to use get_valid_key if implemented or just let manager handle it?
        # Manager is singleton, so we can access keys directly if needed but execute_with_retry is better.
        # Here we just need A key for direct request if not using manage wrapper.
        pass 

    if not target_key:
         # Last resort fallback
        if config_manager:
             target_key = config_manager.get_api_key("gemini")
        else:
             target_key = API_KEYS.get("gemini") if 'API_KEYS' in globals() else None

    if not target_key and gemini_key_manager and gemini_key_manager.keys:
        target_key = gemini_key_manager.keys[gemini_key_manager.current_index]

    if not target_key:
        file_log("[GEMINI-ERR] No valid API key found")
        return None
    
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={target_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        resp = requests.post(url, json=payload, timeout=60)
        
        if resp.status_code == 200:
            data = resp.json()
            if "candidates" in data and data["candidates"]:
                return data["candidates"][0]["content"]["parts"][0]["text"]
        elif resp.status_code == 429:
             file_log(f"[GEMINI-WARN] Rate limit (429) for key ...{target_key[-5:]}")
             if gemini_key_manager:
                 # Trigger rotation async-safe? run_async_in_thread(gemini_key_manager.rotate_key())
                 # For now just log, caller should retry.
                 pass
             return None
        else:
            file_log(f"[GEMINI-ERR] API returned {resp.status_code}: {resp.text[:200]}")
            
    except Exception as e:
        file_log(f"[GEMINI-ERR] Request failed: {e}")
    
    return None

@app.route("/api/jarvis/upload", methods=["POST"])
def api_jarvis_upload():
    """Dashboard chat file upload endpoint (compat)."""
    try:
        if "file" not in request.files:
            return jsonify({"status": "error", "error": "No file part"}), 400

        up = request.files["file"]
        raw_name = (up.filename or "").strip()
        safe_name = Path(raw_name).name
        if not safe_name:
            return jsonify({"status": "error", "error": "Filename required"}), 400

        upload_dir = BASE_DIR / "uploads"
        upload_dir.mkdir(exist_ok=True)

        target = upload_dir / safe_name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            safe_name = f"{stem}_{int(time.time())}{suffix}"
            target = upload_dir / safe_name

        up.save(str(target))
        return jsonify({"status": "success", "filename": safe_name})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """AI Chat Endpoint"""
    try:
        data = request.json
        user_message = data.get("message", "")
        if not user_message:
            return jsonify({"error": "Message required"}), 400
            
        file_log(f"[CHAT] User: {user_message[:50]}...")
        
        system_instruction = (
            "Sen STAINLESS MAX asistanısın. Türkçe konuş. "
            "Kullanıcıya video üretimi, fikir bulma ve kanal yönetimi konularında yardımcı ol. "
            "Kısa, öz ve yardımsever cevaplar ver."
        )
        
        full_prompt = f"{system_instruction}\n\nKullanıcı: {user_message}\nAsistan:"
        
        response_text = None
        # Simple retry logic for chat
        max_retries = 3
        for i in range(max_retries):
            response_text = make_gemini_request(full_prompt, model="gemini-3-deep-think")
            if response_text:
                break
            # If failed, rotate key if possible (make_gemini_request should handle it if passed manager, 
            # but here we rely on manual key rotation if needed or just retry)
            if gemini_key_manager: 
                run_async_in_thread(gemini_key_manager.rotate_key())
            
        if response_text:
            return jsonify({"response": response_text})
        else:
            return jsonify({"error": "Üzgünüm, şu an cevap veremiyorum (Limit/Hata)."}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/suggestions", methods=["GET"])
def api_suggestions():
    """Get viral video topic suggestions"""
    try:
        prompt = (
            "Bana viral olabilecek 5 adet YouTube/TikTok video fikri ver. "
            "Niş: Genel/İlginç Bilgiler. "
            "SADECE JSON FORMATINDA STRING LISTESI VER. "
            "Örnek: [\"Fikir 1\", \"Fikir 2\", ...]. "
            "Dil: TÜRKÇE."
        )
        
        response_text = make_gemini_request(prompt, model="gemini-3-deep-think")
             
        if response_text:
            try:
                # Clean markdown
                clean_text = response_text.replace("```json", "").replace("```", "").strip()
                if "[" in clean_text and "]" in clean_text:
                    start = clean_text.find("[")
                    end = clean_text.rfind("]") + 1
                    clean_text = clean_text[start:end]
                    
                suggestions = json.loads(clean_text)
                if isinstance(suggestions, list):
                    return jsonify({"suggestions": suggestions})
            except Exception as e:
                file_log(f"[SUGGEST-ERR] JSON parse error: {e}")
                
        # Fallback
        fallback = [
            "Dünyanın En Pahalı 5 Yiyeceği",
            "Mısır Piramitlerinin Sırrı Çözüldü mü?",
            "Uyurken Para Kazanmanın 3 Yolu",
            "Teknoloji Bizi Nasıl Değiştirdi?",
            "Geleceğin Meslekleri Neler Olacak?"
        ]
        return jsonify({"suggestions": fallback})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/suggestions/channel", methods=["POST"])
def api_suggestions_channel():
    """Get specific suggestions for a channel using Gemma"""
    try:
        data = request.json
        channel_name = data.get("channel_name")
        platform = data.get("platform", "youtube")
        
        if not channel_name:
            return jsonify({"error": "Channel name required"}), 400

        file_log(f"[GEMMA] {channel_name} ({platform}) için öneriler hazırlanıyor...")
        
        prompt = (
            f"Sen uzman bir sosyal medya danışmanısın. "
            f"Platform: {platform}. Kanal Adı: '{channel_name}'. "
            f"Bu kanal için büyüme stratejisi, içerik fikirleri ve iyileştirme önerileri ver. "
            f"Yanıtı SADECE geçerli bir JSON objesi olarak ver."
            f"Format: {{ 'strategy': '...', 'content_ideas': ['...', '...'], 'tips': ['...', '...'] }}"
        )
        
        response_text = make_gemini_request(prompt, model="gemini-3-deep-think")
        
        if response_text:
            try:
                clean_text = response_text.replace("```json", "").replace("```", "").strip()
                if "{" in clean_text:
                    start = clean_text.find("{")
                    end = clean_text.rfind("}") + 1
                    clean_text = clean_text[start:end]
                
                data = json.loads(clean_text)
                return jsonify(data)
            except Exception as e:
                file_log(f"[GEMMA-ERR] JSON Parse: {e}")
                return jsonify({
                    "strategy": "Genel büyüme stratejisi uygulayın.",
                    "content_ideas": ["Trendleri takip edin", "Düzenli içerik üretin"],
                    "tips": ["Kitle analizi yapın", "Etkileşimi artırın"]
                })
        else:
             return jsonify({"error": "No response from AI"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def generate_batch_from_gemini(theme, count):
    try:
        # Check for Gemini access (OAuth or API key)
        gemini_key = None
        if config_manager:
            if not config_manager.has_gemini_access():
                file_log("[AI] No Gemini access configured (OAuth or API key), using fallback scenarios")
                return None
            gemini_key = config_manager.get_api_key("gemini")  # For fallback
        else:
            gemini_key = API_KEYS.get("gemini") if 'API_KEYS' in globals() else ""
            if not gemini_key:
                file_log("[AI] Gemini API key not configured, using fallback scenarios")
                return None
            
        prompt = f'''
        Konu: {theme}
        Görev: Bu konuyla ilgili 60 saniyelik videolar için TAM
        {count} ADET benzersiz senaryo üret.
        
        Her senaryo için:
        1. Title (Emoji ile)
        2. Script (En az 250 kelime)
        3. Topics (5 adet İngilizce anahtar kelime)
        
        Çıktı Formatı (SADECE JSON LİSTESİ):
        [
          {{"title": "...", "script": "...", "topics": ["..."]}},
          ...
        ]
        '''
        
        # Use the helper function for validated request
        response_text = make_gemini_request(prompt, gemini_key)
        if response_text:
            try:
                text = (
                    response_text
                    .replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                return json.loads(text)
            except json.JSONDecodeError as e:
                file_log(f"[BATCH-ERR] JSON decode error: {e}")
        else:
            file_log("[BATCH-ERR] No response from Gemini")
    except Exception as e:
        file_log(f"[BATCH-ERR] {e}")
    return None


@app.route("/api/gemini/oauth/setup", methods=["POST"])
def api_gemini_oauth_setup():
    """Setup Gemini OAuth credentials"""
    try:
        data = request.json
        client_id = data.get("client_id", "").strip()
        client_secret = data.get("client_secret", "").strip()
        
        if not client_id or not client_secret:
            return jsonify({"error": "Client ID and Secret required"}), 400
        
        # Update config with OAuth credentials
        if config_manager:
            config_manager.api_config.gemini_oauth_client_id = client_id
            config_manager.api_config.gemini_oauth_client_secret = client_secret
            config_manager.save_config()
            
            # Initialize OAuth client
            global gemini_oauth
            from lib.gemini_oauth import GeminiOAuth
            gemini_oauth = GeminiOAuth(client_id, client_secret)
            
            return jsonify({
                "status": "success",
                "message": "OAuth credentials saved",
                "auth_url": gemini_oauth.get_authorization_url()
            })
        else:
            return jsonify({"error": "Config manager not available"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/gemini/oauth/callback", methods=["POST"])
def api_gemini_oauth_callback():
    """Handle OAuth callback with authorization code"""
    try:
        data = request.json
        auth_code = data.get("code", "").strip()
        
        if not auth_code:
            return jsonify({"error": "Authorization code required"}), 400
        
        if not gemini_oauth:
            return jsonify({"error": "OAuth client not initialized"}), 400
        
        # Exchange code for tokens
        if gemini_oauth.exchange_code_for_tokens(auth_code):
            # Test the connection
            test_response = gemini_oauth.generate_content("Test: Hello Gemini Pro!")
            
            return jsonify({
                "status": "success",
                "message": "OAuth setup completed successfully",
                "test_successful": bool(test_response)
            })
        else:
            return jsonify({"error": "Failed to exchange authorization code"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/gemini/oauth/status")
def api_gemini_oauth_status():
    """Get Gemini OAuth status"""
    try:
        if not gemini_oauth:
            return jsonify({
                "configured": False,
                "authenticated": False,
                "token_valid": False
            })
        
        return jsonify({
            "configured": True,
            "authenticated": bool(gemini_oauth.access_token),
            "token_valid": gemini_oauth.is_token_valid(),
            "expires_at": gemini_oauth.token_expires_at.isoformat() if gemini_oauth.token_expires_at else None
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/gemini/oauth/revoke", methods=["POST"])
def api_gemini_oauth_revoke():
    """Revoke Gemini OAuth tokens"""
    try:
        if gemini_oauth and gemini_oauth.revoke_tokens():
            return jsonify({
                "status": "success",
                "message": "OAuth tokens revoked successfully"
            })
        else:
            return jsonify({"error": "Failed to revoke tokens"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.json
        save_settings()
        file_log("[SETTINGS] Ayarlar kaydedildi ✓")
        return jsonify({"status": "saved"})
    
    try:
        if config_manager:
            api_keys = config_manager.api_keys.model_dump()
            youtube_config = config_manager.youtube_config.model_dump()
            tiktok_config = config_manager.tiktok_config.model_dump()
            n8n_config = config_manager.n8n_config.model_dump()
        else:
            api_keys = API_KEYS if 'API_KEYS' in globals() else {}
            youtube_config = YOUTUBE_CONFIG if 'YOUTUBE_CONFIG' in globals() else {}
            tiktok_config = TIKTOK_CONFIG if 'TIKTOK_CONFIG' in globals() else {}
            n8n_config = N8N_CONFIG if 'N8N_CONFIG' in globals() else {}
            
        return jsonify({
            "api_keys": api_keys,
            "n8n": n8n_config,
            "youtube": youtube_config,
            "tiktok": tiktok_config,
        })
    except Exception as e:
        file_log(f"[SETTINGS-ERR] {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json
    theme = data.get("theme")
    language = data.get("language", "tr")
    platform = data.get("platform", "youtube")
    channel = data.get("channel")
    account = data.get("account")
    niche = data.get("niche") # Added niche parameter
    
    # Determine account_id (handle both 'account' and 'channel' aliases)
    account_id = data.get("account") or data.get("channel") or data.get("account_id")

    # Auto-detect account if missing, 'main_user' or 'auto'
    if not account_id or account_id == "main_user" or account_id == "auto":
        from modules.account_manager import AccountManager
        acc_mgr = AccountManager()
        accounts = acc_mgr.get_active_accounts()
        # Filter by platform
        platform_accounts = [a for a in accounts if a.platform == platform]
        if platform_accounts:
            account_id = platform_accounts[0].id
            file_log(f"[SYSTEM] Auto-selected account for {platform}: {account_id}")
        else:
            return jsonify({"status": "error", "message": f"No active account found for {platform}"}), 400

    if consume_job_quota_or_raise and DB_SESSION_FACTORY:
        try:
            consume_job_quota_or_raise(DB_SESSION_FACTORY, tenant_id=g.tenant_id)
        except PlanLimitReachedError:
            return jsonify({"error": "plan_limit_reached"}), 429

    # Start generation in background
    # Use generate_video instead of undefined create_real_video
    thread = threading.Thread(
        target=generate_video,
        args=(theme, language, platform, account_id)
    )
    thread.start()
    
    return jsonify({"status": "started", "account_id": account_id})

def get_scenarios_from_gemini(theme, language, platform):
    try:
        # Check for Gemini access (OAuth or API key)
        gemini_key = None
        if config_manager:
            if not config_manager.has_gemini_access():
                file_log("[AI] No Gemini access configured (OAuth or API key), using fallback scenarios")
                return None
            gemini_key = config_manager.get_api_key("gemini")  # For fallback
        else:
            gemini_key = API_KEYS.get("gemini") if 'API_KEYS' in globals() else ""
            if not gemini_key:
                file_log("[AI] Gemini API key not configured, using fallback scenarios")
                return None
            
        file_log(f"[AI] Gemini ile {theme} temalı senaryo üretiliyor...")
        
        prompt = f'''
        Sen profesyonel bir içerik üreticisisin.
        Konu: {theme}
        Platform: {platform}
        Dil: {language}

        Görev: {platform} için viral olabilecek, izleyiciyi merak içinde
        bırakan 45-60 saniyelik bir video senaryosu yaz.
        
        Yapı (Structure):
        1. Hook (0-5 sn): İzleyiciyi hemen yakalayan şok edici bir giriş.
        2. Progression (5-45 sn): Olayın gelişimi, detaylar, gerilimin artması.
        3. Climax (45-60 sn): Zirve noktası, şaşırtıcı final veya güçlü bir
        "call to action".

        Çıktı Formatı (SADECE JSON):
        {{
            "title": "Videonun başlığı (emojili)",
            "script": "Video metni (seslendirilecek kısım). Hook ile başla, "
            "gelişimi anlat ve finali yap.",
            "topics": [
                "Segment 1 (Hook) için SADECE 2-3 İNGİLİZCE ANAHTAR "
                "KELİME (Keywords)",
                "Segment 2 (Progression) için SADECE 2-3 İNGİLİZCE ANAHTAR "
                "KELİME (Keywords)",
                "Segment 3 (Climax) için SADECE 2-3 İNGİLİZCE ANAHTAR "
                "KELİME (Keywords)"
            ]
        }}
        '''
        
        # Use the helper function for validated request
        response_text = make_gemini_request(prompt, gemini_key)
        if response_text:
            try:
                raw_text = (
                    response_text
                    .replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                return json.loads(raw_text)
            except json.JSONDecodeError as e:
                file_log(f"[AI-ERROR] JSON decode error: {e}")
        else:
            file_log("[AI-ERROR] No response from Gemini")
            
    except Exception as e:
        file_log(f"[AI-ERROR] Gemini hatası: {e}")
        
    return None

def translate_text(text, target_lang):
    """Simple translation using Google Translate"""
    if not GoogleTranslator:
        return text
    try:
        return GoogleTranslator(
            source="tr",
            target=target_lang,
        ).translate(text)
    except Exception as e:
        file_log(f"[TRANSLATE-ERR] {e}")
        return text

# Version
VERSION = "v2.1"

# Initialize Producer
# Initialize Producer
# producer is already initialized at top level or None
if get_producer() is None:
    file_log("[SYSTEM] Using fallback producer (None)")

# Initialize Special Producers
from modules.varyasyon_shitpost_manager import VaryasyonShitpostManager
from modules.reddit_history_producer import RedditHistoryProducer

try:
    varyasyon_manager = VaryasyonShitpostManager()
except Exception as e:
    file_log(f"[ERROR] VaryasyonShitpostManager init failed: {e}")
    varyasyon_manager = None

try:
    reddit_producer = RedditHistoryProducer()
except Exception as e:
    file_log(f"[ERROR] RedditHistoryProducer init failed: {e}")
    reddit_producer = None

# ... (Existing imports) ...

def generate_video(theme, language, platform="youtube", account_id=None):
    try:
        # Fix undefined 'lang' variable
        lang = next(
            (l for l in LANGUAGES if l["id"] == language),
            LANGUAGES[0],
        )

        file_log(f"--- STARTING STAINLESS MAX VIRAL GENERATION: {platform} - {language} ---")
        socketio.emit(
            "progress",
            {"percent": 5, "status": "STAINLESS MAX: Viral senaryo üretiliyor..."},
        )
        
        import asyncio
        import shutil
        
        # Account ID bul veya varsayılan kullan
        if not account_id:
            account_id = f"{platform}_genel"
            
        # --- SPECIAL ACCOUNT LOGIC ---
        
        # 1. VaryasyonMedia (Instagram Shitpost)
        if "varyasyonmedia" in str(account_id).lower():
            file_log("[SYSTEM] VaryasyonMedia modu aktif.")
            socketio.emit("progress", {"percent": 10, "status": "VaryasyonMedia: Video seçiliyor..."})
            
            video_path = varyasyon_manager.get_next_video()
            
            if video_path:
                # Copy to outputs for preview/download
                output_filename = f"Varyasyon_{video_path.name}"
                destination = OUTPUTS_DIR / output_filename
                shutil.copy2(video_path, destination)
                
                # Mark as posted? Maybe wait for actual upload. 
                # For now, we just present it.
                
                socketio.emit("progress", {"percent": 100, "status": "Video Hazır!"})
                socketio.emit("video_generated", {"filename": output_filename, "platform": "instagram", "account_id": account_id})
                file_log(f"✅ VaryasyonMedia Video Selected: {output_filename}")
                return
            else:
                socketio.emit("progress", {"percent": 0, "status": "Hata: Paylaşılacak video bulunamadı!"})
                file_log("❌ VaryasyonMedia: No videos found in assets.")
                return

        # 2. RedditHistorySS (TikTok Reddit Stories)
        elif "reddithistoriyss" in str(account_id).lower():
            file_log("[SYSTEM] RedditHistorySS modu aktif.")
            socketio.emit("progress", {"percent": 10, "status": "Reddit: Hikaye aranıyor..."})
            
            result = asyncio.run(reddit_producer.create_video(
                progress_callback=lambda p, s: socketio.emit("progress", {"percent": p, "status": s})
            ))
            
            if result and result.get("success") and result.get("video_path"):
                video_path = result["video_path"]
                filename = Path(video_path).name
                
                # Ensure it's in outputs (Producer usually puts it there or similar)
                # If not, copy it. Assuming producer returns absolute path.
                
                socketio.emit("progress", {"percent": 100, "status": "Reddit Video Hazır!"})
                socketio.emit("video_generated", {"filename": filename, "platform": "tiktok", "account_id": account_id})
                file_log(f"✅ RedditHistorySS Video Generated: {filename}")
                return
            else:
                error_msg = result.get("error", "Unknown error") if result else "Unknown error"
                socketio.emit("progress", {"percent": 0, "status": f"Hata: {error_msg}"})
                file_log(f"❌ RedditHistorySS Failed: {error_msg}")
                return

        # --- STANDARD GENERATION ---
        
        # Run the async producer
        prod = get_producer()
        if not prod:
            file_log("❌ Producer initialize edilemedi!")
            socketio.emit("progress", {"percent": 0, "status": "Hata: Producer başlatılamadı."})
            return

        result = asyncio.run(prod.create_viral_video(
            account_id=account_id,
            account_topic=theme, # Eğer boşsa otomatik üretecek
            niche=None, # Auto-detect from account
            platform=platform,
            progress_callback=lambda p, s: socketio.emit("progress", {"percent": p, "status": s})
        ))
        
        if result and result.get("video_path"):
            video_path = result["video_path"]
            filename = Path(video_path).name
            
            socketio.emit("progress", {"percent": 100, "status": "Tamamlandı!"})
            socketio.emit("video_generated", {"filename": filename})
            file_log(f"✅ STAINLESS MAX Generation Complete: {filename}")
            
            # --- AUTO UPLOAD ENTEGRASYONU ---
            try:
                file_log(f"🚀 Otomatik yükleme başlatılıyor: {platform}")
                try:
                    from modules.unified_uploader import UnifiedUploader
                except ImportError:
                    from AppCore.modules.unified_uploader import UnifiedUploader
                uploader = UnifiedUploader()
                
                # Metadata
                scenario = result.get("scenario", {})
                title = scenario.get("title", f"Viral Video {int(time.time())}")
                description = scenario.get("description", title)
                tags = scenario.get("tags", ["#shorts", "#viral"])

                upload_result = uploader.upload_to_account(
                    account_id=account_id,
                    video_path=video_path,
                    title=title,
                    description=description,
                    tags=tags
                )

                if upload_result.get("success"):
                    video_url = upload_result.get('video_url')
                    file_log(f"✅ UPLOAD BAŞARILI: {video_url}")
                    
                    # Log to shared history
                    try:
                        with open(BASE_DIR / "shared_history.log", "a", encoding="utf-8") as f:
                             f.write(f"{datetime.now().date()}|{filename}|{video_url}\n")
                    except Exception as e:
                        file_log(f"[HISTORY-ERR] {e}")

                    socketio.emit("video_uploaded", {
                        "filename": filename,
                        "url": video_url,
                        "platform": platform
                    })
                else:
                    file_log(f"❌ Upload Hatası: {upload_result.get('error')}")

            except Exception as up_err:
                file_log(f"⚠️ Auto upload error: {up_err}")
        else:
            socketio.emit("progress", {"percent": 0, "status": "Hata: Video üretilemedi."})
            file_log("❌ STAINLESS MAX Generation Failed")

    except Exception as e:
        file_log(f"[GEN-ERROR] {e}")
        socketio.emit("progress", {"percent": 0, "status": f"Hata: {str(e)}"})

# Automated Scheduling
AUTO_PROD_ACTIVE = False
LAST_PROD_TIME = {} # channel_id -> timestamp

def scheduler_loop():
    global AUTO_PROD_ACTIVE
    last_cleanup_day = None
    
    while True:
        now = datetime.now()
        
        # [NEW] Daily Cleanup at 23:55
        if (
            now.hour == 23
            and now.minute == 55
            and last_cleanup_day != now.date()
        ):
            file_log("[SYSTEM] Gün sonu temizliği başlatılıyor...")
            try:
                # Delete all processed/shared videos from outputs folder
                # (Simple logic: delete everything older than 12h in outputs)
                for f in OUTPUTS_DIR.glob("VIDEO_*.mp4"):
                    if (now.timestamp() - f.stat().st_mtime) > 43200:
                        f.unlink(missing_ok=True)
                
                # Force clean assets
                for f in ASSETS_DIR.glob("*.*"):
                    f.unlink(missing_ok=True)
                    
                file_log("[SYSTEM] Gün sonu temizliği tamamlandı ✓")
                last_cleanup_day = now.date()
            except Exception as e:
                if error_handler:
                    handle_error(e, {"context": "daily_cleanup"})
                file_log(f"[CLEANUP-ERR] {e}")

        if AUTO_PROD_ACTIVE:
            now = datetime.now()
            # Check YouTube Channels
            if config_manager:
                youtube_interval = config_manager.youtube_config.interval_hours or 4
            else:
                youtube_interval = YOUTUBE_CONFIG.get("interval_hours", 4) if 'YOUTUBE_CONFIG' in globals() else 4
            youtube_interval_seconds = youtube_interval * 3600
            for ch in YOUTUBE_CHANNELS:
                last_time = LAST_PROD_TIME.get(ch["id"], datetime.min)
                if (
                    (now - last_time).total_seconds()
                    >= youtube_interval_seconds
                ):
                    file_log(
                        f"[AUTO] {ch['name']} için otomatik üretim "
                        "başlıyor..."
                    )
                    LAST_PROD_TIME[ch["id"]] = now
                    threading.Thread(
                        target=generate_video,
                        args=(ch["theme"], "tr", "youtube"),
                    ).start()
            
            # Check TikTok Accounts
            if config_manager:
                tiktok_interval = config_manager.tiktok_config.interval_hours or 8
            else:
                tiktok_interval = TIKTOK_CONFIG.get("interval_hours", 8) if 'TIKTOK_CONFIG' in globals() else 8
            tiktok_interval_seconds = tiktok_interval * 3600
            for acc in TIKTOK_ACCOUNTS:
                last_time = LAST_PROD_TIME.get(acc["id"], datetime.min)
                if (
                    (now - last_time).total_seconds()
                    >= tiktok_interval_seconds
                ):
                    file_log(
                        f"[AUTO] {acc['name']} için otomatik üretim "
                        "başlıyor..."
                    )
                    LAST_PROD_TIME[acc["id"]] = now
                    threading.Thread(
                        target=generate_video,
                        args=(acc["theme"], "tr", "tiktok"),
                    ).start()
        
        time.sleep(60) # Check every minute

@app.route("/api/auto", methods=["GET", "POST"])
def api_auto():
    global AUTO_PROD_ACTIVE
    if request.method == "POST":
        data = request.json
        AUTO_PROD_ACTIVE = data.get("active", False)
        status = "AÇIK" if AUTO_PROD_ACTIVE else "KAPALI"
        file_log(f"[SYSTEM] Otomatik Üretim: {status}")
    return jsonify({"status": "ok", "active": AUTO_PROD_ACTIVE})

@app.route("/api/logs", methods=["GET"])
def api_logs():
    try:
        lines = 20
        log_content = []
        log_file_path = BASE_DIR / "app.log"
        if log_file_path.exists():
            with open(log_file_path, "r", encoding="utf-8") as f:
                log_content = f.readlines()[-lines:]
        return jsonify({"logs": "".join(log_content)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stats")
def api_stats():
    """Get dashboard statistics"""
    try:
        # Count all MP4 files in outputs
        all_videos = list(OUTPUTS_DIR.glob("*.mp4"))
        produced_count = len(all_videos)
        
        # Get Accounts for performance data
        from modules.account_manager import AccountManager
        mgr = AccountManager()
        
        # Calculate separately
        yt_accounts = mgr.get_active_accounts("youtube")
        tt_accounts = mgr.get_active_accounts("tiktok")
        
        # YouTube: Sum real TOTAL VIEWS from accounts, fallback to video count if 0
        yt_total_views = sum(acc.total_views for acc in yt_accounts)
        # TikTok: Sum real TOTAL LIKES from accounts
        tt_total_likes = sum(acc.total_likes for acc in tt_accounts)
        
        # Fallback for display if no real data (prevent 0 looking broken)
        # If views/likes are 0, show video count as a proxy? 
        # User specifically asked for "Views" and "Likes", so let's send 0 if it is 0.
        
        # Calculate revenue (simulation based on views/likes)
        # CPM assumption: $2 per 1000 views YT, $0.05 per 1000 likes TT
        revenue = (yt_total_views / 1000 * 2.0) + (tt_total_likes / 1000 * 0.05)
        
        # --- MILESTONE CHECKS ---
        # Define milestones
        milestones = [
            {"type": "youtube_views", "target": 1000, "message": "YouTube: 1,000 İzlenmeye Ulaştınız! 🎉"},
            {"type": "youtube_views", "target": 10000, "message": "YouTube: 10,000 İzlenme! 🚀"},
            {"type": "tiktok_likes", "target": 100, "message": "TikTok: 100 Beğeni! ❤️"},
            {"type": "tiktok_likes", "target": 1000, "message": "TikTok: 1,000 Beğeni! 🔥"},
            {"type": "produced", "target": 10, "message": "10. Video Üretildi! 🎬"},
            {"type": "produced", "target": 50, "message": "50 Video! Otomasyon Canavarı! 🤖"},
        ]
        
        # Simple file-based persistence for reached milestones to avoid repeating
        reached_file = BASE_DIR / "milestones.json"
        reached = []
        if reached_file.exists():
            try:
                with open(reached_file, 'r') as f: reached = json.load(f)
            except: pass
            
        new_reached = False
        current_stats = {
            "youtube_views": yt_total_views,
            "tiktok_likes": tt_total_likes,
            "produced": produced_count
        }
        
        for m in milestones:
            m_id = f"{m['type']}_{m['target']}"
            current_val = current_stats.get(m['type'], 0)
            
            if current_val >= m['target'] and m_id not in reached:
                # Milestone Reached!
                emit_safe('notification', {
                    "type": "milestone",
                    "title": "🎉 KİLOMETRE TAŞI!",
                    "message": m['message'],
                    "platform": "system",
                    "timestamp": "Şimdi"
                })
                reached.append(m_id)
                new_reached = True
                
        if new_reached:
            with open(reached_file, 'w') as f: json.dump(reached, f)
        # ------------------------

        return jsonify({
            "produced": produced_count,
            "youtube_views": yt_total_views,
            "tiktok_likes": tt_total_likes,
            "revenue": round(revenue, 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/accounts")
def api_accounts():
    """Get active accounts for frontend"""
    try:
        from modules.account_manager import AccountManager
        mgr = AccountManager()

        # Force refresh to ensure we get latest status
        # mgr.load_accounts() # Optional if expensive

        yt_accs = [
            {"id": a.id, "name": a.name, "theme": "mystery" if "gizem" in a.name.lower() else "general"}
            for a in mgr.get_active_accounts("youtube")
        ]

        tt_accs = [
            {"id": a.id, "name": a.name, "theme": "general"}
            for a in mgr.get_active_accounts("tiktok")
        ]

        return jsonify({
            "youtube": yt_accs,
            "tiktok": tt_accs,
            "instagram": []  # Add if needed
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/accounts/add", methods=["POST"])
def api_accounts_add():
    """Compatibility endpoint for dashboard account add modal."""
    try:
        payload = request.json or {}
        account_id = (payload.get("id") or "").strip()
        platform = (payload.get("platform") or "").strip().lower()

        if not account_id:
            return jsonify({"success": False, "error": "ID zorunludur"}), 400
        if platform not in {"youtube", "tiktok", "instagram"}:
            return jsonify({"success": False, "error": "Geçersiz platform"}), 400

        from modules.account_manager import AccountManager, Account

        manager = AccountManager()
        if manager.get_account(account_id):
            return jsonify({"success": False, "error": "Bu ID zaten mevcut"}), 409

        new_account = Account(
            id=account_id,
            platform=platform,
            niche=(payload.get("niche") or "general").strip() or "general",
            email=(payload.get("email") or payload.get("login") or "").strip(),
            password=(payload.get("password") or "").strip(),
            client_id=(payload.get("client_id") or "").strip(),
            client_secret=(payload.get("client_secret") or "").strip(),
            name=(payload.get("name") or account_id).strip(),
            username=(payload.get("login") or "").strip(),
            active=True,
        )

        ok = manager.add_account(new_account)
        if not ok:
            return jsonify({"success": False, "error": "Hesap kaydedilemedi"}), 500

        refresh_accounts()
        return jsonify({"success": True, "message": "Hesap eklendi", "account_id": account_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/accounts/delete", methods=["POST"])
def api_accounts_delete():
    """Compatibility endpoint for dashboard account delete action."""
    try:
        payload = request.json or {}
        account_id = (payload.get("id") or payload.get("account_id") or "").strip()
        if not account_id:
            return jsonify({"success": False, "error": "ID zorunludur"}), 400

        from modules.account_manager import AccountManager

        manager = AccountManager()
        deleted = manager.delete_account(account_id)
        if not deleted:
            return jsonify({"success": False, "error": "Hesap bulunamadı veya silinemedi"}), 404

        refresh_accounts()
        return jsonify({"success": True, "message": "Hesap silindi", "account_id": account_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/scan/uploads", methods=["POST"])
def api_scan_uploads():
    """Scan outputs directory and update status"""
    try:
        # Re-scan Logic (Optional: trigger account manager reload)
        return jsonify({"status": "success", "message": "Tarama tamamlandı"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/files", methods=["GET", "DELETE"])
def api_files():
    try:
        if request.method == "DELETE":
            filename = request.args.get("filename")
            if not filename: return jsonify({"error": "No filename"}), 400
            file_path = OUTPUTS_DIR / filename
            if file_path.exists():
                file_path.unlink()
                return jsonify({"status": "deleted", "file": filename})
            return jsonify({"error": "Not found"}), 404
            
        # GET - List files
        files = []
        recent_files = sorted(
            OUTPUTS_DIR.glob("*.mp4"),
            key=os.path.getmtime,
            reverse=True,
        )[:20]
        
        # Load shared history
        shared_files = {}
        history_file = BASE_DIR / "shared_history.log"
        if history_file.exists():
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    if "|" in line:
                        parts = line.strip().split("|")
                        if len(parts) >= 2:
                            # 0:date, 1:filename, 2:url (optional)
                            filename = parts[1]
                            url = parts[2] if len(parts) > 2 else None
                            shared_files[filename] = url

        for f in recent_files:
            time_str = datetime.fromtimestamp(
                f.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")
            
            is_shared = f.name in shared_files
            video_url = shared_files.get(f.name)
            
            status = "shared" if is_shared else "generated"
            
            files.append({
                "name": f.name,
                "size_mb": round(f.stat().st_size / (1024*1024), 2),
                "time": time_str,
                "status": status, 
                "url": video_url,
                "thumb": "", # Placeholder for thumbnail check
            })
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/upload/manual", methods=["POST"])
def api_upload_manual():
    """Manual upload endpoint used by frontend modal"""
    try:
        data = request.json
        filename = data.get("filename")
        platform = data.get("platform", "youtube")
        account_id = data.get("account_id")
        title = data.get("title")
        description = data.get("description")
        
        if not filename:
            return jsonify({"success": False, "error": "Filename required"}), 400
            
        video_path = OUTPUTS_DIR / filename
        if not video_path.exists():
            return jsonify({"success": False, "error": "Video file not found"}), 404
            
        video_url = None
        
        if platform == "youtube":
            from lib.youtube_uploader import upload_to_youtube
            # Start upload
            video_id = upload_to_youtube(
                video_path=video_path,
                title=title or f"Video {datetime.now().strftime('%Y-%m-%d')}",
                description=description or "Uploaded via Stainless Max",
                channel_id=account_id,
                theme="general"
            )
            
            if video_id:
                video_url = f"https://youtube.com/shorts/{video_id}"
                
        elif platform == "tiktok":
            # TikTok upload implementation
            from lib.tiktok_uploader import upload_to_tiktok
            result = upload_to_tiktok(
                video_path=video_path,
                title=title or "",
                account_id=account_id
            )
            if result and result.get("success"):
                video_url = result.get("url")
            else:
                 return jsonify({"success": False, "error": result.get("error", "TikTok upload failed")}), 500
        
        else:
            return jsonify({"success": False, "error": "Invalid platform"}), 400
            
        if video_url:
            # Log to shared history with URL
            try:
                with open(BASE_DIR / "shared_history.log", "a", encoding="utf-8") as f:
                    # Format: DATE|FILENAME|URL
                    f.write(f"{datetime.now().date()}|{filename}|{video_url}\n")
            except Exception as e:
                file_log(f"[HISTORY-ERR] Failed to write history: {e}")
                
            return jsonify({
                "success": True, 
                "url": video_url,
                "message": "Upload successful"
            })
        else:
            return jsonify({"success": False, "error": "Upload failed (no URL returned)"}), 500

    except Exception as e:
        file_log(f"[UPLOAD-ERR] {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/download/<path:filename>")
def download_file(filename):
    """Serve video files from outputs directory"""
    try:
        return send_from_directory(OUTPUTS_DIR, filename, as_attachment=True)
    except Exception as e:
        file_log(f"[ERROR] Download failed for {filename}: {e}")
        return jsonify({"error": str(e)}), 404

@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    """Get performance metrics"""
    try:
        from lib.performance_monitor import perf_monitor
        from lib.cache_manager import get_cache
        from lib.rate_limiter import rate_limiter
        
        metrics = {
            "performance": perf_monitor.get_metrics(),
            "cache": get_cache().get_stats(),
            "rate_limits": rate_limiter.get_stats()
        }
        return jsonify(metrics)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def find_free_port(start_port=5000):
    """Find a free port, Windows 11 optimized"""
    import socket
    port = start_port
    while port < start_port + 20:  # Increased range for Windows 11
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                # Windows 11 socket options
                if os.name == 'nt':
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))  # Use localhost instead of 0.0.0.0
                return port
        except OSError:
            port += 1
    return 5000

# Automation Engine and Monitoring imports
try:
    from lib.automation_engine import get_automation_engine, start_automation, stop_automation, get_automation_status
    from lib.monitoring import get_system_monitor, start_monitoring, stop_monitoring, get_system_health
    from lib.youtube_uploader import get_youtube_uploader
    from lib.tiktok_uploader import get_tiktok_uploader
    AUTOMATION_AVAILABLE = True
except ImportError as e:
    AUTOMATION_AVAILABLE = False
    file_log(f"[WARN] Automation modules not available: {e}")

# ============================================
# AUTOMATION API ENDPOINTS
# ============================================

@app.route("/api/automation/status")
def api_automation_status():
    """Get automation engine status"""
    if not AUTOMATION_AVAILABLE:
        return jsonify({"error": "Automation not available"}), 503
    
    try:
        status = get_automation_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/automation/start", methods=["POST"])
def api_automation_start():
    """Start automation engine"""
    if not AUTOMATION_AVAILABLE:
        return jsonify({"error": "Automation not available"}), 503
    
    try:
        start_automation()
        start_monitoring()
        file_log("[AUTO] Otomasyon motoru başlatıldı ✓")
        return jsonify({
            "status": "started",
            "message": "Automation engine started",
            "target": "12 videos per day (6 YouTube + 6 TikTok)"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/automation/stop", methods=["POST"])
def api_automation_stop():
    """Stop automation engine"""
    if not AUTOMATION_AVAILABLE:
        return jsonify({"error": "Automation not available"}), 503
    
    try:
        stop_automation()
        stop_monitoring()
        file_log("[AUTO] Otomasyon motoru durduruldu ✓")
        return jsonify({
            "status": "stopped",
            "message": "Automation engine stopped"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/automation/force", methods=["POST"])
def api_automation_force():
    """Force immediate video generation"""
    if not AUTOMATION_AVAILABLE:
        return jsonify({"error": "Automation not available"}), 503
    
    try:
        data = request.json or {}
        platform = data.get("platform")  # youtube, tiktok, or None for random
        
        engine = get_automation_engine()
        success = engine.force_generate(platform)
        
        if success:
            file_log(f"[AUTO] Manuel video üretimi başlatıldı: {platform or 'random'}")
            return jsonify({
                "status": "started",
                "message": "Video generation started",
                "platform": platform or "random"
            })
        else:
            return jsonify({"error": "Failed to start generation"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/automation/force_generate", methods=["POST"])
@app.route("/api/automation/force_generate_all", methods=["POST"])
def api_automation_force_all():
    """Force immediate video generation for ALL active accounts"""
    if not AUTOMATION_AVAILABLE:
        return jsonify({"error": "Automation not available"}), 503
    
    try:
        engine = get_automation_engine()
        result = engine.force_generate_all()
        
        if "error" in result:
             return jsonify({"error": result["error"]}), 500

        file_log(f"[AUTO] Toplu üretim tetiklendi: {result.get('added', 0)} video")
        return jsonify({
            "status": "success",
            "data": result
        })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/automation/clear", methods=["POST"])
def api_automation_clear():
    """Clear automation queue and status"""
    if not AUTOMATION_AVAILABLE:
        return jsonify({"error": "Automation not available"}), 503

    try:
        engine = get_automation_engine()
        engine.clear_queue() # Assuming clear_queue method exists or we implement it
        
        # Also clear global trackers if any
        global LAST_PROD_TIME
        LAST_PROD_TIME = {}
        
        file_log("[AUTO] Kuyruk ve durumlar temizlendi 🧹")
        return jsonify({"status": "cleared", "message": "Queue cleared"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/system/health")
def api_system_health():
    """Get comprehensive system health"""
    if not AUTOMATION_AVAILABLE:
        return jsonify({"error": "Monitoring not available"}), 503
    
    try:
        health = get_system_health()
        return jsonify(health)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/system/check', methods=['POST'])
def api_system_check():
    """System Health Check & AI Report (main.py ile uyumlu JSON çıktı)."""
    try:
        from lib.health_check import SystemDoctor

        checker = SystemDoctor()
        results = checker.run_all_checks()

        # AI raporu (anahtar yoksa fallback)
        ai_summary = "AI Raporu oluşturulamadı (Anahtar yok)."

        api_key = None
        try:
            from modules.gemini_key_manager import GeminiKeyManager

            km = GeminiKeyManager()
            if getattr(km, "keys", None):
                api_key = km.keys[0]
        except Exception:
            api_key = None

        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")

        if api_key:
            try:
                ai_summary = checker.analyze_with_ai(api_key)
            except Exception as ai_err:
                file_log(f"[SYSTEM-CHECK] AI summary failed: {ai_err}")

        return jsonify({
            "results": results,
            "ai_summary": ai_summary,
        })
    except Exception as e:
        file_log(f"[SYSTEM-CHECK] Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/youtube", methods=["POST"])
def api_upload_youtube():
    """Upload video to YouTube"""
    try:
        data = request.json
        video_path = data.get("video_path")
        title = data.get("title", "Video")
        script = data.get("script", "")
        channel_id = data.get("channel_id", "default")
        theme = data.get("theme", "mystery")
        
        if not video_path:
            return jsonify({"error": "video_path required"}), 400
        
        # Import and upload
        from lib.youtube_uploader import upload_to_youtube
        
        video_id = upload_to_youtube(
            video_path=video_path,
            title=title,
            script=script,
            channel_id=channel_id,
            theme=theme
        )
        
        if video_id:
            file_log(f"[YOUTUBE] Video yüklendi: {video_id}")
            return jsonify({
                "status": "uploaded",
                "video_id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}"
            })
        else:
            return jsonify({"error": "Upload failed"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/tiktok", methods=["POST"])
def api_upload_tiktok():
    """Upload video to TikTok"""
    try:
        data = request.json
        video_path = data.get("video_path")
        title = data.get("title", "Video")
        script = data.get("script", "")
        account_id = data.get("account_id", "default")
        theme = data.get("theme", "mystery")
        
        if not video_path:
            return jsonify({"error": "video_path required"}), 400
        
        # Import and upload
        from lib.tiktok_uploader import upload_to_tiktok
        
        result = upload_to_tiktok(
            video_path=video_path,
            title=title,
            script=script,
            account_id=account_id,
            theme=theme
        )
        
        if result:
            file_log(f"[TIKTOK] Video hazır: {result}")
            return jsonify({
                "status": "queued",
                "queue_file": result,
                "note": "TikTok upload instructions saved. Manual upload required if API not configured."
            })
        else:
            return jsonify({"error": "Upload preparation failed"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Legacy bot code removed in favor of bot_runner.py
# If you need to run the bot, please execute: python bot_runner.py

def _read_version_file() -> str:
    """Read current version from VERSION constant or AppCore/version.txt with encoding fallbacks."""
    version = str(VERSION).strip().lstrip("vV")
    version_file = BASE_DIR / "version.txt"
    if version_file.exists():
        raw = version_file.read_bytes()
        for enc in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
            try:
                txt = raw.decode(enc).replace("\x00", "").strip().lstrip("vV")
                if txt:
                    return txt
            except Exception:
                continue
    return version


def _version_tuple(version_str: str):
    parts = []
    for p in str(version_str).strip().lstrip("vV").split("."):
        try:
            parts.append(int(p))
        except Exception:
            parts.append(0)
    return tuple(parts)


def _resolve_updater_path() -> Path | None:
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "Updater.exe",
            exe_dir / "updater.exe",
            BASE_DIR / "Updater.exe",
        ])
    else:
        project_root = Path(__file__).resolve().parent.parent
        candidates.extend([
            project_root / "dist" / "StainlessMax" / "Updater.exe",
            project_root / "Updater.exe",
        ])

    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _fetch_update_manifest() -> dict:
    manifest_url = os.getenv("STAINLESS_UPDATE_MANIFEST_URL", "").strip()
    if not manifest_url:
        raise RuntimeError("STAINLESS_UPDATE_MANIFEST_URL tanımlı değil")

    resp = requests.get(manifest_url, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("Manifest JSON nesnesi değil")
    if not data.get("version") or not data.get("url"):
        raise RuntimeError("Manifest içinde version/url eksik")
    return data


@app.route("/api/update/check", methods=["GET"])
def check_update():
    """Checks remote manifest and reports whether a newer version exists."""
    try:
        current_version = _read_version_file()
        manifest = _fetch_update_manifest()
        latest_version = str(manifest.get("version", "")).strip().lstrip("vV")

        has_update = _version_tuple(latest_version) > _version_tuple(current_version)
        if logger:
            logger.info(
                f"[UPDATE][CHECK] current={current_version} latest={latest_version} has_update={has_update}"
            )

        return jsonify({
            "status": "ok",
            "message": "Yeni sürüm mevcut" if has_update else "Uygulama güncel",
            "current_version": current_version,
            "latest_version": latest_version,
            "has_update": has_update,
            "url": manifest.get("url"),
            "sha256": manifest.get("sha256"),
            "notes": manifest.get("notes", ""),
        })
    except Exception as e:
        if logger:
            logger.error(f"[UPDATE][CHECK][ERROR] {e}")
        return jsonify({
            "status": "error",
            "message": "Güncelleme kontrolü başarısız",
            "error": str(e),
        }), 500


@app.route("/api/update", methods=["POST"])
def trigger_update():
    """Download update package and launch Updater.exe for hot update."""
    try:
        payload = request.get_json(silent=True) or {}
        current_version = _read_version_file()

        package_url = payload.get("url")
        expected_sha256 = payload.get("sha256")
        latest_version = payload.get("version")

        if not package_url:
            manifest = _fetch_update_manifest()
            package_url = manifest.get("url")
            expected_sha256 = manifest.get("sha256")
            latest_version = manifest.get("version")

        if not package_url:
            return jsonify({
                "status": "error",
                "message": "Güncelleme paketi adresi bulunamadı",
                "error": "Update package URL bulunamadı",
            }), 400

        latest_version = str(latest_version or "unknown").strip().lstrip("vV")
        if latest_version != "unknown":
            if _version_tuple(latest_version) <= _version_tuple(current_version):
                if logger:
                    logger.info(
                        f"[UPDATE][SKIP] current={current_version} latest={latest_version} reason=up_to_date"
                    )
                return jsonify({
                    "status": "up_to_date",
                    "message": "Uygulama zaten güncel",
                    "current_version": current_version,
                    "latest_version": latest_version,
                })

        updater_path = _resolve_updater_path()
        if updater_path is None:
            return jsonify({
                "status": "error",
                "message": "Updater bulunamadı",
                "error": "Updater.exe bulunamadı",
            }), 404

        updates_dir = BASE_DIR / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        package_path = updates_dir / f"stainlessmax_update_{latest_version}.zip"

        if logger:
            logger.info(f"[UPDATE][DOWNLOAD] url={package_url} target={package_path}")

        with requests.get(package_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(package_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)

        if expected_sha256:
            import hashlib

            digest = hashlib.sha256(package_path.read_bytes()).hexdigest().lower()
            if digest != str(expected_sha256).strip().lower():
                package_path.unlink(missing_ok=True)
                if logger:
                    logger.error(
                        f"[UPDATE][VERIFY][ERROR] sha256_mismatch expected={expected_sha256} got={digest}"
                    )
                return jsonify({
                    "status": "error",
                    "message": "İndirilen paket doğrulanamadı (SHA256)",
                    "error": "SHA256 doğrulaması başarısız",
                }), 400

        target_exe = Path(sys.executable) if getattr(sys, "frozen", False) else Path("")

        subprocess.Popen(
            [
                str(updater_path),
                "--source", str(package_path),
                "--target-dir", str(BASE_DIR),
                "--wait-pid", str(os.getpid()),
                "--start", str(target_exe),
            ],
            cwd=str(BASE_DIR),
            creationflags=SUBPROCESS_FLAGS if os.name == "nt" else 0,
        )

        if logger:
            logger.info(
                f"[UPDATE][START] current={current_version} latest={latest_version} updater={updater_path}"
            )

        return jsonify({
            "status": "starting_update",
            "message": "Güncelleme başlatıldı. Uygulama kapanıp yeni sürüm açılacak.",
            "next_action": "app_will_close",
            "current_version": current_version,
            "latest_version": latest_version,
            "package": str(package_path),
        })
    except Exception as e:
        if logger:
            logger.error(f"[UPDATE][TRIGGER][ERROR] {e}")
        return jsonify({
            "status": "error",
            "message": "Güncelleme başlatılırken hata oluştu",
            "error": str(e),
        }), 500


def run_app() -> None:
    """Run the shared application entrypoint used by both app.py and main.py."""
    import signal

    def signal_handler(sig, frame):
        print(f"\n[{datetime.now()}] Shutting down gracefully...")
        if file_logger:
            file_logger.info("Application shutting down gracefully")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"🚀 Video PRO AI Studio")

    # Windows 11 compatibility check
    check_windows11_compatibility()

    print(f"🌐 Starting server...")

    # Dynamic port
    port = find_free_port()
    print(f"📡 Port: {port}")

    _app, _socketio = create_app()
    _log_template_diagnostics("run_app.after_create_app")

    # Start Flask in a background thread
    def run_server():
        try:
            print(f"🎬 Server ready")
            # Windows 11 optimized server settings
            _socketio.run(
                _app,
                host="127.0.0.1",  # Localhost for Windows 11 security
                port=port,
                debug=False,
                allow_unsafe_werkzeug=True,
                log_output=False,
                use_reloader=False,  # Disable reloader for Windows 11
            )
        except Exception as e:
            print(f"❌ Server Error: {e}")

    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

    # Start Scheduler thread (lightweight)
    scheduler = threading.Thread(target=scheduler_loop)
    scheduler.daemon = True
    scheduler.start()

    # Start Automation Engine and Monitoring
    if AUTOMATION_AVAILABLE:
        try:
            print("🤖 Automation Engine başlatılıyor...")
            from lib.automation_engine import start_automation
            from lib.monitoring import start_monitoring

            start_automation()
            start_monitoring()
            print("✅ Automation Engine hazır (12 video/gün)")
        except Exception as e:
            print(f"⚠️ Automation Engine başlatılamadı: {e}")

    # Start Telegram Bot
    if (not SAAS_MODE) or ENABLE_TELEGRAM_BOT:
        try:
            print("📱 Telegram Bot başlatılıyor...")
            from lib.telegram_bot import start_telegram_bot

            start_telegram_bot()
            print("✅ Telegram Bot aktif")
        except Exception as e:
            print(f"⚠️ Telegram Bot başlatılamadı: {e}")
    else:
        print("📱 Telegram Bot devre dışı (SAAS_MODE=true ve ENABLE_TELEGRAM_BOT=false)")

    # Desktop-only mode - Windows uygulaması olarak çalış
    def open_desktop_app():
        time.sleep(2)  # Server'ın başlamasını bekle
        try:
            if WEBVIEW_AVAILABLE:
                print(f"🖥️  Desktop mode - Windows uygulaması")
                file_log("[STARTUP] Desktop mode selected, WEBVIEW_AVAILABLE=True")
                return True  # Webview kullanacağımızı belirt
            else:
                print(f"❌ WebView mevcut değil! Lütfen webview kütüphanesini yükleyin:")
                print(f"   pip install webview")
                print(f"🚫 Tarayıcı modu devre dışı - sadece desktop mod destekleniyor")
                file_log("[STARTUP-CRASH-CANDIDATE] WEBVIEW_AVAILABLE=False -> sys.exit(1)")
                sys.exit(1)  # Webview yoksa uygulamayı kapat
        except Exception as e:
            print(f"⚠️  Desktop app hatası: {e}")
            print(f"🚫 Uygulama sadece desktop modunda çalışır")
            file_log(f"[STARTUP-CRASH-CANDIDATE] open_desktop_app exception -> sys.exit(1): {e}")
            sys.exit(1)

    # Desktop modunu kontrol et
    if SAAS_MODE:
        use_desktop = False
        print("☁️ SaaS mode aktif - desktop webview otomatik başlatılmayacak")
    else:
        use_desktop = DESKTOP_MODE and open_desktop_app()

    print(f"✅ Video PRO AI Studio hazır!")
    if use_desktop:
        print(f"🖥️  Windows Desktop Uygulaması")
        print(f"⏹️  Kapatmak için pencereyi kapatın veya Ctrl+C basın")
    else:
        print(f"🌐 Headless/SaaS sunucu modu")

    try:
        if use_desktop and WEBVIEW_AVAILABLE:
            # Ana thread'de webview çalıştır - Windows 11 optimize
            webview_kwargs = {
                "width": 1400,
                "height": 900,
                "resizable": True,
                "min_size": (1200, 800),
                "text_select": True,
                "shadow": True,
                "on_top": False,
                # Windows 11 özel webview seçenekleri
                "js_api": None,
                "easy_drag": False,
                "maximized": False,
                "fullscreen": False,
            }
            try:
                window = webview.create_window(
                    "Video PRO AI - Studio",
                    f"http://127.0.0.1:{port}",
                    **webview_kwargs,
                )
            except TypeError:
                # pywebview sürüm uyumluluğu: bazı sürümlerde 'shadow' desteklenmez.
                webview_kwargs.pop("shadow", None)
                window = webview.create_window(
                    "Video PRO AI - Studio",
                    f"http://127.0.0.1:{port}",
                    **webview_kwargs,
                )

            # Windows 11 webview başlatma
            try:
                # Öncelik: Qt backend (pythonnet/CLR bağımlılığı yok); başarısız olursa edgechromium.
                _activate_pythonnet_path_guard()
                _sanitize_system_module_for_pythonnet()
                file_log("[STARTUP] Calling webview.start(gui=qt) [primary]")
                webview.start(debug=False, http_server=False, gui="qt")
            except Exception as qt_primary_error:
                file_log(f"[STARTUP-WEBVIEW] qt primary failed: {qt_primary_error}")
                try:
                    # İkincil fallback: edgechromium
                    _activate_pythonnet_path_guard()
                    _sanitize_system_module_for_pythonnet()
                    file_log("[STARTUP] Calling webview.start(gui=edgechromium) as fallback")
                    webview.start(debug=False, http_server=False, gui="edgechromium")
                except Exception as edge_error:
                    print(f"❌ WebView başlatılamadı (qt-primary): {qt_primary_error}")
                    print(f"❌ WebView fallback (edgechromium) de başarısız: {edge_error}")
                    print("🚫 Harici tarayıcı fallback devre dışı. Uygulama sadece yerleşik desktop modunda çalışır.")
                    file_log(
                        f"[STARTUP-CRASH-CANDIDATE] webview.start failed for qt(primary) and edgechromium(fallback) -> sys.exit(1): qt={qt_primary_error} | edge={edge_error}"
                    )
                    sys.exit(1)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n👋 Kapatılıyor...")
        sys.exit(0)


if __name__ == "__main__":
    run_app()

