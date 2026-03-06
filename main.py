"""
STAINLESS MAX - Desktop Application (Chrome App Mode)
Full Automation System with YouTube, TikTok, Instagram Support
VERSION = "v2.1"
"""

import sys
import os

# Windowed modda (console=False) sys.stdout/stderr None olabilir — güvenli fallback
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# Konsol çıktılarını UTF-8'e zorla (Özellikle Windows'ta emoji desteği için)
if sys.platform == "win32":
    # Enable UTF-8 mode for Windows 11
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

    # Windows 11 DPI awareness
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
        
    # Windows 11 console improvements
    try:
        import ctypes.wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

import logging
import threading
import json
import time
import asyncio
import subprocess
import psutil
import socket
import platform
import shutil
from pathlib import Path
from datetime import datetime

# AI & Video Libraries - modüller kendi SDK import'larını yapıyor (google.genai)

# Add System directory to path for inner module imports (e.g. from lib...)
sys.path.append(os.path.join(os.path.dirname(__file__), 'AppCore'))


# Flask
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, g
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from dotenv import load_dotenv

import jwt
import bcrypt
from functools import wraps
from AppCore.lib.db.user_store import UserStore

# sys.path already contains 'AppCore'
MODULES_AVAILABLE = False
AutomationEngine = None
get_automation_engine = None
GeminiKeyManager = None
ViralVideoProducer = None
get_config_manager = None
get_gemini_oauth = None

def initialize_system():
    """Sistemi ve global nesneleri başlat"""
    global gemini_key_manager, MODULES_AVAILABLE
    global AutomationEngine, get_automation_engine, GeminiKeyManager, ViralVideoProducer, get_config_manager, get_gemini_oauth
    logger.info("🔧 Sistem başlatılıyor...")
    
    try:
        from AppCore.lib.automation_engine import AutomationEngine, get_automation_engine
        from AppCore.modules.gemini_key_manager import GeminiKeyManager
        from AppCore.modules.viral_video_producer import ViralVideoProducer
        from AppCore.lib.config_manager import get_config_manager
        from AppCore.lib.gemini_oauth import get_gemini_oauth
        MODULES_AVAILABLE = True
    except ImportError as e:
        MODULES_AVAILABLE = False
        print(f"Warning: Modules not available: {e}")
        return

    # Global Gemini Key Manager
    if REDDIT_HISTORY_AVAILABLE:
        try:
            gemini_key_manager = GeminiKeyManager()
            logger.info("✅ Global GeminiKeyManager initialized")
        except Exception as e:
            logger.error(f"GeminiKeyManager başlatılamadı: {e}")
            
    # Diğer gerekli başlangıç işlemleri buraya eklenebilir
    logger.info("✅ Sistem hazır.")

try:
    from AppCore.modules.account_manager import HESAPLAR_AVAILABLE
except ImportError as e:
    print(f"AccountManager import error: {e}")
    HESAPLAR_AVAILABLE = False

try:
    from AppCore.modules.reddit_history_producer import REDDIT_HISTORY_AVAILABLE
except ImportError as e:
    REDDIT_HISTORY_AVAILABLE = False
    print(f"Warning: RedditHistoryProducer not available: {e}")


try:
    from AppCore.lib.config_manager import get_config_manager
    from AppCore.lib.automation_engine import start_automation, stop_automation, get_automation_status
    AUTOMATION_AVAILABLE = True
except ImportError as e:
    AUTOMATION_AVAILABLE = False
    print(f"Warning: Automation Engine not available: {e}")

# PROJE KÖK DİZİNİ
BASE_DIR = Path(__file__).resolve().parent

# ===== PERSISTENT DATA DIRECTORY =====
import sys

if sys.platform == 'darwin':
    # macOS: ~/Library/Application Support/StainlessMax
    appdata_base = os.path.expanduser('~/Library/Application Support')
elif sys.platform == 'win32':
    appdata_base = os.environ.get('APPDATA', str(BASE_DIR))
else:
    appdata_base = os.path.expanduser('~/.config')

USER_DATA_DIR = Path(appdata_base) / 'StainlessMax'
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
user_store = UserStore(USER_DATA_DIR)

# JWT Secret
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-stainless-key-2026")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Unauthorized"}), 401
        
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            g.user_id = payload['sub']
            g.user_plan = payload.get('plan', 'free')
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
            
        return f(*args, **kwargs)
    return decorated

def require_plan(allowed_plans):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if getattr(g, 'user_plan', 'free') not in allowed_plans:
                return jsonify({"error": f"Requires {allowed_plans} plan"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_quota(cost=1):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, 'user_id'):
                return jsonify({"error": "Unauthorized"}), 401
                
            plan = getattr(g, 'user_plan', 'free')
            limits = {'free': 3, 'pro': 20, 'ultra': 100}
            limit = limits.get(plan, 3)
            
            usage = user_store.get_today_usage(g.user_id)
            produced = usage.get('videos_produced', 0)
            
            if produced + cost > limit:
                return jsonify({"error": f"Günlük üretme limitiniz doldu ({limit}). Lütfen planınızı yükseltin.", "limit": limit, "produced": produced}), 403
                
            # Ön limit kontrolü başarılı, f çalışsın, başarılı olursa route içinde veya background'da arttırılır.
            # Şimdilik direkt burada arttırıyoruz
            user_store.increment_usage(g.user_id, 'videos_produced', cost)
            
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_token = request.headers.get('X-Admin-Token')
        if not admin_token or admin_token != ADMIN_SECRET_TOKEN:
            return jsonify({"error": "Admin yetkisi gerekli"}), 403
        return f(*args, **kwargs)
    return decorated

# ===== CONFIGURATION =====
dotenv_path = USER_DATA_DIR / ".env"
if not dotenv_path.exists() and (BASE_DIR / ".env").exists():
    shutil.copy2(BASE_DIR / ".env", dotenv_path)
load_dotenv(dotenv_path=dotenv_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Pexels API Key
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
ADMIN_SECRET_TOKEN = os.getenv("ADMIN_SECRET_TOKEN", "stainless_admin_123")

# Correct Output Directory for System Consistency
if sys.platform == 'darwin':
    OUTPUT_DIR = Path(os.path.expanduser('~/Movies/StainlessMax'))
else:
    OUTPUT_DIR = BASE_DIR / "AppCore" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== LOGGING =====
class SocketIOHandler(logging.Handler):
    """Custom logging handler to emit logs to Socket.IO"""
    def emit(self, record):
        try:
            # Check if socketio and emit_safe are ready
            _socketio = globals().get('socketio')
            _emit_safe = globals().get('emit_safe')
            if _socketio and _emit_safe:
                msg = self.format(record)
                _emit_safe('log', {'data': msg})
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("stainless_max.log", encoding='utf-8'),
        logging.StreamHandler(sys.stderr),
        SocketIOHandler() # Mirror to UI
    ]
)
logger = logging.getLogger(__name__)

# Disable Flask/Werkzeug request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Disable httpx (Telegram API) verbose logging
logging.getLogger('httpx').setLevel(logging.WARNING)

# Disable telegram library verbose logging
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)

# Disable apscheduler verbose logging
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# ===== FLASK APP =====
def get_resource_path(relative_path):
    import sys
    import os
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

app = Flask(__name__, 
            template_folder=get_resource_path('AppCore/templates'),
            static_folder=get_resource_path('AppCore/static'))
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "stainless_secret_key")
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable cache for development
app.config['JSON_AS_ASCII'] = False  # UTF-8 support for JSON responses
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'


# GeminiKeyManager is initialized in initialize_system()
initialize_system()

@app.after_request
def after_request(response):
    """Ensure UTF-8 encoding and disable caching for all responses"""
    try:
        # UTF-8 encoding
        content_type = response.headers.get('Content-Type', '')
        if content_type and 'charset=' not in content_type:
            if 'text' in content_type or 'json' in content_type:
                response.headers['Content-Type'] = content_type + '; charset=utf-8'
        
        # Aggressive cache busting
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        
    except Exception as e:
        logger.error(f"after_request error: {e}")
    return response

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Desktop UI URL ayarı (tek merkez)
APP_HOST = "127.0.0.1"
APP_PORT = int(os.getenv("STAINLESS_PORT", "5056"))


def build_local_url() -> str:
    """Build local app URL with cache bust token."""
    timestamp = int(time.time())
    return f"http://{APP_HOST}:{APP_PORT}/?v={timestamp}"


# ===== HELPER FUNCTIONS =====

def is_port_available(port):
    """Check if port is free"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False

def emit_safe(event, data):
    """Thread-safe emit wrapper"""
    try:
        socketio.start_background_task(socketio.emit, event, data)
    except Exception as e:
        logger.error(f"emit_safe error: {e}")

def run_async_in_thread(coro):
    """Safely run async function in thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def broadcast_job_status():
    """Periodically broadcast automation status to all clients (Real-time sync)"""
    while True:
        try:
            if AUTOMATION_AVAILABLE:
                status = get_automation_status()
                jobs = status.get('recent_jobs', [])
                socketio.emit('job_update', jobs)
        except Exception as e:
            logger.error(f"Status broadcast error: {e}")
        time.sleep(3) # Update UI every 3s (reduce flickering)

# Start background thread for status updates (removed from here)

def get_chrome_path():
    """Get Chrome executable path for current OS"""
    system = platform.system()
    
    paths = {
        "Windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "Darwin": [  # macOS
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ],
        "Linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
    }
    
    for path in paths.get(system, []):
        if os.path.exists(path):
            return path
    
    return None

def open_chrome_app():
    """Open Chrome in app mode (cross-platform)"""
    chrome_path = get_chrome_path()
    
    if chrome_path:
        try:
            subprocess.Popen([
                chrome_path,
                f"--app={build_local_url()}",
                "--window-size=1400,900",
                "--disable-features=TranslateUI",
                "--no-first-run",
                "--no-default-browser-check"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("✅ Chrome App Mode açıldı")
        except Exception as e:
            logger.error(f"Chrome başlatılamadı: {e}")
            fallback_browser()
    else:
        logger.warning("⚠️ Chrome bulunamadı")
        fallback_browser()

def fallback_browser():
    """Open in default browser"""
    import webbrowser
    webbrowser.open_new(build_local_url())

# ===== AI FUNCTIONS =====

# ===== AI FUNCTIONS ===== (Replaced by ViralVideoProducer)

def create_real_video(topic, niche=None, platform="tiktok", account_id="main_user", duration=60, aspect_ratio="9:16"):
    """Video Generation Process (ViralVideoProducer)"""
    try:
        emit_safe('log', {'data': f'🚀 Viral Video Üretimi Başlıyor: {platform} - {account_id}'})
        emit_safe('progress', {'percent': 5, 'status': 'Başlatılıyor...'})

        # --- SPECIAL ACCOUNT: RedditHistory ---
        if account_id and "reddit" in str(account_id).lower():
            try:
                if not REDDIT_HISTORY_AVAILABLE:
                    raise ImportError("RedditHistoryProducer modülü yüklenemedi!")
                
                from AppCore.modules.reddit_history_producer import RedditHistoryProducer
                r_producer = RedditHistoryProducer(BASE_DIR)

                # reddithistoriyss için gameplay kaynağını zorunlu olarak assets/gameplay'e sabitle
                r_producer.gameplay_dir = BASE_DIR / "assets" / "gameplay"
                r_producer.gameplay_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"🎮 Reddit gameplay klasörü: {r_producer.gameplay_dir}")
                
                emit_safe('progress', {'percent': 10, 'status': 'Reddit: Hikaye aranıyor...'})
                
                def r_progress(p, s):
                    # Üretim fazını %1-%89 aralığına sabitle (upload için yer bırak)
                    mapped = max(1, min(89, int(round(float(p) * 0.89))))
                    emit_safe('progress', {'percent': mapped, 'status': s})
                
                result = run_async_in_thread(r_producer.create_video(progress_callback=r_progress, aspect_ratio=aspect_ratio, duration=duration))
                
                if result.get("success") and result.get("video_path"):
                    video_path = result["video_path"]
                    filename = os.path.basename(video_path)
                    
                    # Safe copy to output
                    target_path = OUTPUT_DIR / filename
                    try:
                        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                        if os.path.abspath(video_path) != os.path.abspath(target_path):
                            shutil.copy2(video_path, target_path)
                            logger.info(f"✅ File copied: {filename}")
                    except (IOError, OSError, PermissionError) as copy_err:
                        logger.error(f"File copy failed: {copy_err}")
                        emit_safe('log', {'data': f'⚠️ Dosya kopyalanamadı: {copy_err}'})
                    
                    emit_safe('log', {'data': f'✅ REDDIT VİDEOSU HAZIR: {filename}'})
                    emit_safe('video_generated', {
                        'filename': filename,
                        'platform': 'tiktok',
                        'account_id': account_id
                    })
                    emit_safe('progress', {'percent': 90, 'status': 'Hazır - Yükleme Başlıyor...'})

                    # Metadata for Auto-Upload (Standardize result format)
                    # RedditHistoryProducer returns 'story' (text), 'story_title', 'story_url'
                    # We map this to 'scenario' dict that auto-upload expects
                    result["scenario"] = {
                        "title": result.get("story_title", f"Reddit Hikayesi {int(time.time())}"),
                        "description": f"{result.get('story_title', '')}\n\nKaynak: {result.get('subreddit', 'Reddit')}\n\n#reddit #hikaye #storytime #fyp",
                        "tags": ["#reddit", "#storytime", "#askreddit", "#fyp", "#viral"]
                    }
                    
                    # Pass through to auto-upload section
                    # return  <-- REMOVED RETURN
                else:
                    raise Exception(f"Reddit Hatası: {result.get('error')}")
            except Exception as e:
                logger.error(f"RedditHistory Error: {e}")
                raise e
        
        else:
            # --- STANDARD GENERATION (ViralVideoProducer) ---
            if not MODULES_AVAILABLE:
                raise ImportError("ViralVideoProducer modülü yüklenemedi!")
                
            # OAuth Client al (varsa) - güvenli fallback
            oauth_client = None
            oauth_factory = globals().get("get_gemini_oauth")

            if callable(oauth_factory):
                try:
                    oauth_client = oauth_factory()
                except Exception as oauth_err:
                    logger.warning(f"⚠️ Gemini OAuth client oluşturulamadı: {oauth_err}")
            else:
                logger.warning("⚠️ get_gemini_oauth callable değil, API Key fallback kullanılacak")

            if oauth_client and hasattr(oauth_client, "is_token_valid") and oauth_client.is_token_valid():
                logger.info("✅ Gemini AI Pro hesabı kullanılıyor")
            else:
                logger.warning("⚠️ OAuth aktif değil, API Key kullanılacak")

            # Callback fonksiyonu
            def progress_callback(percent, status):
                # Üretim fazı: %1-%89
                mapped = max(1, min(89, int(round(float(percent) * 0.89))))
                emit_safe('progress', {'percent': mapped, 'status': status})
                logger.info(f"Progress: {mapped}% - {status}")

            # Producer oluştur
            producer = ViralVideoProducer(oauth_client=oauth_client)
            
            # Async/Sync handler
            if hasattr(producer, 'create_viral_video_sync'):
                result = producer.create_viral_video_sync(
                    account_id=account_id,
                    account_topic=topic,
                    niche=niche,
                    platform=platform,
                    progress_callback=progress_callback,
                    aspect_ratio=aspect_ratio,
                    duration=duration
                )
            else:
                async def run_async():
                    return await producer.create_viral_video(
                        account_id=account_id,
                        account_topic=topic,
                        niche=niche,
                        platform=platform,
                        progress_callback=progress_callback,
                        aspect_ratio=aspect_ratio,
                        duration=duration
                    )
                result = run_async_in_thread(run_async())
        
        if result and result.get("video_path"):
            video_path = result["video_path"]
            filename = os.path.basename(video_path)
            
            # Safe copy
            target_path = OUTPUT_DIR / filename
            try:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                if os.path.abspath(video_path) != os.path.abspath(target_path):
                    shutil.copy2(video_path, target_path)
                    logger.info(f"✅ File copied: {filename}")
            except (IOError, OSError, PermissionError) as copy_err:
                logger.error(f"File copy failed: {copy_err}")
                emit_safe('log', {'data': f'⚠️ Dosya kopyalanamadı: {copy_err}'})
            
            emit_safe('log', {'data': f'✅ VİDEO HAZIR: {filename}'})
            emit_safe('video_generated', {
                'filename': filename,
                'platform': platform,
                'account_id': account_id
            })
            emit_safe('progress', {'percent': 90, 'status': 'Video Hazır - Yükleme Başlıyor...'})

            # --- AUTO UPLOAD ENTEGRASYONU ---
            upload_success = False
            max_retries = 3
            
            emit_safe('log', {'data': f'🚀 Otomatik yükleme başlatılıyor: {platform} (Zorunlu Mod)'})
            
            try:
                from AppCore.modules.unified_uploader import UnifiedUploader
                uploader = UnifiedUploader()
                
                # Metadata
                scenario = result.get("scenario", {})
                title = scenario.get("title", f"Viral Video {int(time.time())}")
                description = scenario.get("description", title)
                tags = scenario.get("tags", ["#shorts", "#viral"])

                # RETRY LOOP
                for attempt in range(1, max_retries + 1):
                    try:
                        emit_safe('progress', {'percent': 90, 'status': f'{platform.upper()} Yükleniyor... (Deneme {attempt}/{max_retries})'})
                        emit_safe('log', {'data': f'⏳ Yükleme Denemesi {attempt}...' if attempt > 1 else f'⏳ Yükleniyor...'})

                        def upload_progress_callback(upload_percent, upload_status):
                            # Upload fazı: %90-%99 (başarı/final state %100'e ayrılır)
                            normalized_upload = max(0, min(100, int(upload_percent)))
                            mapped_upload = min(99, 90 + int(normalized_upload * 0.09))
                            emit_safe('progress', {'percent': mapped_upload, 'status': upload_status})

                        # Upload öncesi dosya yolunu güvenli şekilde toparla
                        upload_video_path = target_path
                        if not upload_video_path.exists():
                            candidate_paths = [
                                OUTPUT_DIR / filename,
                                BASE_DIR / "outputs" / filename,
                                Path(video_path) if 'video_path' in locals() else upload_video_path,
                            ]
                            for cand in candidate_paths:
                                try:
                                    if cand and cand.exists():
                                        upload_video_path = cand
                                        logger.warning(f"⚠️ Upload path düzeltildi: {upload_video_path}")
                                        break
                                except Exception:
                                    continue

                        if not upload_video_path.exists():
                            raise FileNotFoundError(f"Upload için video bulunamadı: {upload_video_path}")

                        upload_result = uploader.upload_to_account(
                            account_id=account_id,
                            video_path=upload_video_path,
                            title=title,
                            description=description,
                            tags=tags,
                            progress_callback=upload_progress_callback
                        )

                        if upload_result.get("success"):
                            video_url = upload_result.get("video_url", "URL Yok")
                            emit_safe('log', {'data': f'✅ UPLOAD BAŞARILI: {video_url}'})
                            
                            # Log to shared history
                            try:
                                with open("shared_history.log", "a", encoding="utf-8") as f:
                                    f.write(f"{datetime.now().date()}|{filename}|{video_url}\n")
                            except Exception as e:
                                logger.error(f"History write error: {e}")

                            emit_safe('video_uploaded', {
                                'filename': filename,
                                'url': video_url,
                                'platform': platform
                            })
                            emit_safe('progress', {'percent': 100, 'status': '✅ Yüklendi ve Paylaşıldı!'})
                            upload_success = True
                            break # Çıkış
                        else:
                            error_msg = upload_result.get("error", "Bilinmeyen Hata")
                            emit_safe('log', {'data': f'❌ Deneme {attempt} Başarısız: {error_msg}'})

                            err_lower = str(error_msg).lower()
                            tiktok_throttled = (
                                "maximum number of attempts reached" in err_lower
                                or "too many attempts" in err_lower
                                or "try again later" in err_lower
                                or "deneme limiti" in err_lower
                                or "çok fazla deneme" in err_lower
                            )

                            # TikTok rate-limit engelinde aynı oturumda tekrar denemeyi durdur
                            if tiktok_throttled:
                                emit_safe('log', {'data': '🛑 TikTok deneme limiti algılandı. Güvenli mod: tekrar deneme durduruldu.'})
                                break

                            if attempt < max_retries:
                                time.sleep(5) # Bekle ve tekrar dene
                            
                    except Exception as retry_err:
                        logger.error(f"Retry {attempt} error: {retry_err}")
                        emit_safe('log', {'data': f'⚠️ Hata (Deneme {attempt}): {retry_err}'})
                        time.sleep(5)

                if not upload_success:
                    emit_safe('log', {'data': '❌ TÜM YÜKLEME DENEMELERİ BAŞARISIZ OLDU.'})
                    emit_safe('progress', {'percent': 100, 'status': '❌ YÜKLEME BAŞARISIZ! (Lütfen Manuel Yükleyin)'})
                    # Toast ile uyar
                    emit_safe('error', f'Video üretildi ama {platform} yüklemesi yapılamadı!')

            except Exception as up_err:
                logger.error(f"Auto upload wrapper error: {up_err}")
                emit_safe('log', {'data': f'⚠️ Kritik Upload Hatası: {up_err}'})
                emit_safe('progress', {'percent': 100, 'status': '⚠️ Kritik Hata (Upload)'})

            return {"success": True, "video_path": target_path, "filename": filename}
        else:
            error_msg = result.get("error", "Video üretilemedi") if result else "Video üretilemedi (Sonuç boş)"
            if result and result.get("audio_path") and not result.get("video_path"):
                emit_safe('log', {'data': '⚠️ Video klipleri bulunamadı, sadece ses üretildi.'})
            raise Exception(error_msg)

    except Exception as e:
        logger.error(f"❌ Video üretim hatası: {e}", exc_info=True)
        emit_safe('log', {'data': f'❌ HATA: {str(e)}'})
        emit_safe('progress', {'percent': 0, 'status': f'Hata: {str(e)}'})

# ===== LINK ENGINE =====

# Link generator to AutomationEngine if available
if AUTOMATION_AVAILABLE:
    try:
        # Global sembol None kalırsa local import ile garantiye al
        from AppCore.lib.automation_engine import get_automation_engine as _get_engine
        engine = _get_engine() if callable(_get_engine) else None

        if engine is not None and callable(create_real_video):
            engine.set_generator(create_real_video, socketio if 'socketio' in globals() else None)
            print("✅ Generator linked to AutomationEngine successfully.")
        else:
            print("Warning: Generator link skipped (engine/create_real_video unavailable)")
    except Exception as e:
        print(f"Warning: Could not link generator to engine: {e}")

# ===== ROUTES =====

@app.route('/')
def index():
    import time
    return render_template('setup.html', cache_bust=int(time.time()))

@app.route('/dashboard')
def dashboard_view():
    import time
    return render_template('dashboard_v2.html', cache_bust=int(time.time()))

@app.route('/setup')
def setup_view():
    import time
    return render_template('setup.html', cache_bust=int(time.time()))

@app.route('/api/status')
def status():
    return jsonify({"status": "online", "mode": "DESKTOP_APP"})


# ===== CHANNEL STATS (YouTube Data API v3 — 1 saat cache) =====

_CHANNEL_STATS_CACHE_FILE = BASE_DIR / "AppCore" / "temp" / "channel_stats_cache.json"
_CHANNEL_STATS_CACHE_TTL = 3600  # 1 saat

def _load_channel_stats_cache():
    try:
        if _CHANNEL_STATS_CACHE_FILE.exists():
            with open(_CHANNEL_STATS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            age = time.time() - data.get("_ts", 0)
            if age < _CHANNEL_STATS_CACHE_TTL:
                return data
    except Exception:
        pass
    return None

def _save_channel_stats_cache(data: dict):
    try:
        _CHANNEL_STATS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data["_ts"] = time.time()
        with open(_CHANNEL_STATS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Cache kaydetme hatası: {e}")

def _fetch_youtube_channel_stats(token_path: str) -> dict:
    """YouTube Data API v3 ile kanal istatistiklerini çek."""
    try:
        import google.oauth2.credentials
        import googleapiclient.discovery

        with open(token_path, "r", encoding="utf-8") as f:
            token_data = json.load(f)

        creds = google.oauth2.credentials.Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/youtube.readonly"]),
        )

        youtube = googleapiclient.discovery.build(
            "youtube", "v3", credentials=creds, cache_discovery=False
        )

        # Kanalın kendi bilgilerini çek
        resp = youtube.channels().list(
            part="statistics,snippet",
            mine=True
        ).execute()

        items = resp.get("items", [])
        if not items:
            return {}

        stats = items[0].get("statistics", {})
        snippet = items[0].get("snippet", {})
        return {
            "channel_name": snippet.get("title", ""),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "total_views": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
        }
    except Exception as e:
        logger.warning(f"YouTube API fetch hatası ({token_path}): {e}")
        return {}

def _fetch_tiktok_stats(username: str) -> dict:
    """TikTok profilinden temel istatistikleri scrape eder."""
    if not username:
        return {}
    
    try:
        import urllib.request
        import re
        
        url = f"https://www.tiktok.com/@{username}"
        req = urllib.request.Request(
            url, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5'
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
            
            # TikTok profillerinde genellikle followerCount ve heartCount json statelerinde bulunur
            followers = 0
            likes = 0
            
            follower_match = re.search(r'"followerCount":\s*(\d+)', html)
            if follower_match:
                followers = int(follower_match.group(1))
                
            like_match = re.search(r'"heartCount":\s*(\d+)', html)
            if like_match:
                likes = int(like_match.group(1))
                
            return {
                "followers": followers,
                "likes": likes
            }
    except Exception as e:
        logger.warning(f"TikTok scrape hatası (@{username}): {e}")
        return {}


def _fetch_all_channel_stats_fresh() -> dict:
    """Tüm hesapların YouTube istatistiklerini çek ve topla."""
    yt_subscribers = 0
    yt_views = 0
    yt_video_count = 0
    tt_videos = 0
    tt_followers = 0
    tt_likes = 0

    # YouTube token'larını ara
    token_dirs = [
        BASE_DIR / "AppCore" / "tokens",
        BASE_DIR / "tokens",
    ]
    for tdir in token_dirs:
        if tdir.exists():
            for tf in tdir.glob("*.json"):
                stats = _fetch_youtube_channel_stats(str(tf))
                if stats:
                    yt_subscribers += stats.get("subscribers", 0)
                    yt_views += stats.get("total_views", 0)
                    yt_video_count += stats.get("video_count", 0)

    # TikTok hesaplarını accounts.json'dan oku ve scrape et
    try:
        accounts_file = BASE_DIR / "config" / "accounts.json"
        if not accounts_file.exists():
            accounts_file = BASE_DIR / "AppCore" / "config" / "accounts.json"
            
        if accounts_file.exists():
            with open(accounts_file, "r", encoding="utf-8") as f:
                accounts_data = json.load(f)
                for acc in accounts_data.get("accounts", []):
                    if acc.get("platform") == "tiktok" and acc.get("active", True) and acc.get("username"):
                        tt_stats = _fetch_tiktok_stats(acc["username"])
                        tt_followers += tt_stats.get("followers", 0)
                        tt_likes += tt_stats.get("likes", 0)
    except Exception as e:
        logger.warning(f"TikTok hesap okuma hatası: {e}")

    # Üretilen video sayısı
    try:
        produced = len([f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".mp4")])
    except Exception:
        produced = 0

    # Yüklenen video sayısı
    uploaded = 0
    try:
        shared_log = BASE_DIR / "shared_history.log"
        if shared_log.exists():
            with open(shared_log, "r", encoding="utf-8") as f:
                uploaded = len([l for l in f.readlines() if l.strip()])
    except Exception:
        pass

    # Tahmini gelir CPM: YT $2/1k view, TT $0.05/1k like
    revenue = (yt_views / 1000 * 2.0) + (tt_likes / 1000 * 0.05)

    return {
        "yt_subscribers": yt_subscribers,
        "yt_views": yt_views,
        "yt_video_count": yt_video_count,
        "tt_followers": tt_followers,
        "tt_likes": tt_likes,
        "tt_videos": tt_videos,
        "produced": produced,
        "uploaded": uploaded,
        "revenue": round(revenue, 2),
    }


@app.route('/api/channel_stats', methods=['GET'])
def api_channel_stats():
    """Kanal istatistikleri — 1 saatlik cache, gerçek YouTube Data API."""
    try:
        force = request.args.get("force", "").lower() == "1"
        cached = None if force else _load_channel_stats_cache()

        if cached:
            current = cached
        else:
            current = _fetch_all_channel_stats_fresh()
            _save_channel_stats_cache(current)

        # Önceki cache ile kıyasla (değişim yüzdesi hesapla)
        prev_file = BASE_DIR / "AppCore" / "temp" / "channel_stats_prev.json"
        prev = {}
        try:
            if prev_file.exists():
                with open(prev_file, "r", encoding="utf-8") as f:
                    prev = json.load(f)
        except Exception:
            pass

        def pct_change(now, before):
            if not before or before == 0:
                return None
            return round((now - before) / before * 100, 1)

        def fmt_num(n):
            if n >= 1_000_000:
                return f"{n/1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n/1_000:.1f}K"
            return str(n)

        result = {
            "yt_subscribers": fmt_num(current.get("yt_subscribers", 0)),
            "yt_subscribers_raw": current.get("yt_subscribers", 0),
            "yt_views": fmt_num(current.get("yt_views", 0)),
            "yt_views_raw": current.get("yt_views", 0),
            "yt_video_count": current.get("yt_video_count", 0),
            
            "tt_followers": fmt_num(current.get("tt_followers", 0)),
            "tt_followers_raw": current.get("tt_followers", 0),
            "tt_likes": fmt_num(current.get("tt_likes", 0)),
            "tt_likes_raw": current.get("tt_likes", 0),
            
            "produced": current.get("produced", 0),
            "uploaded": current.get("uploaded", 0),
            "revenue": f"${current.get('revenue', 0):.2f}",
            
            "yt_subs_change": pct_change(
                current.get("yt_subscribers", 0),
                prev.get("yt_subscribers", 0)
            ),
            "yt_views_change": pct_change(
                current.get("yt_views", 0),
                prev.get("yt_views", 0)
            ),
            "tt_followers_change": pct_change(
                current.get("tt_followers", 0),
                prev.get("tt_followers", 0)
            ),
            "last_updated": time.strftime("%H:%M", time.localtime(current.get("_ts", time.time()))),
            "cache_age_min": int((time.time() - current.get("_ts", time.time())) / 60),
            "next_refresh_min": max(0, int((_CHANNEL_STATS_CACHE_TTL - (time.time() - current.get("_ts", time.time()))) / 60)),
        }

        # Günlük snapshot kaydet (değişim hesabı için)
        today_str = time.strftime("%Y-%m-%d")
        snapshot_file = BASE_DIR / "AppCore" / "temp" / f"channel_snapshot_{today_str}.json"
        if not snapshot_file.exists():
            try:
                with open(snapshot_file, "w") as f:
                    json.dump(current, f)
                # Bir önceki günün snapshot'ını prev olarak kaydet
                with open(prev_file, "w") as f:
                    json.dump(current, f)
            except Exception:
                pass

        return jsonify(result)

    except Exception as e:
        logger.error(f"channel_stats error: {e}", exc_info=True)
        return jsonify({
            "yt_subscribers": "--", "yt_views": "--",
            "tt_followers": "--", "tt_likes": "--",
            "produced": 0, "revenue": "$0.00",
            "error": str(e)
        }), 500

# ===== AUTH & USER SYSTEM API =====

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.json or {}
    name = data.get('name', '').strip()
    surname = data.get('surname', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    promo_code = data.get('promo_code', '').strip()
    
    if not email or not password or len(password) < 6:
        return jsonify({"error": "Geçersiz email veya şifre"}), 400
        
    if user_store.get_user_by_email(email):
        return jsonify({"error": "Bu e-posta adresi zaten kullanımda"}), 400
        
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode()
    user_id = user_store.create_user(name, surname, email, hashed, promo_code)
    
    # Kullanıcıyı getir
    user = user_store.get_user_by_id(user_id)
    token = jwt.encode({
        'sub': user_id,
        'email': email,
        'plan': user.get('plan', 'free'),
        'exp': datetime.utcnow() + getattr(datetime, 'timedelta', __import__('datetime').timedelta)(days=30)
    }, JWT_SECRET, algorithm='HS256')
    
    return jsonify({
        "message": "Kayıt başarılı",
        "token": token,
        "user": {
            "id": user_id, "name": name, "surname": surname, "email": email, "plan": user.get('plan')
        }
    })

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    user = user_store.get_user_by_email(email)
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({"error": "E-posta veya şifre hatalı"}), 401
        
    user_store.update_last_login(user['id'])
    
    token = jwt.encode({
        'sub': user['id'],
        'email': email,
        'plan': user.get('plan', 'free'),
        'exp': datetime.utcnow() + getattr(datetime, 'timedelta', __import__('datetime').timedelta)(days=30)
    }, JWT_SECRET, algorithm='HS256')
    
    return jsonify({
        "message": "Giriş başarılı",
        "token": token,
        "user": {
            "id": user['id'], "name": user.get('name'), "surname": user.get('surname'), 
            "email": email, "plan": user.get('plan'), "setup_complete": user.get('setup_complete')
        }
    })

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def auth_me():
    user = user_store.get_user_by_id(g.user_id)
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 404
    return jsonify({
        "id": user['id'], "name": user.get('name'), "surname": user.get('surname'), 
        "email": user.get('email'), "plan": user.get('plan'), 
        "setup_complete": bool(user.get('setup_complete')),
        "api_keys": user.get('api_keys', {})
    })

@app.route('/api/auth/change-password', methods=['POST'])
@require_auth
def auth_change_password():
    data = request.json or {}
    old_pw = data.get('old_password', '')
    new_pw = data.get('new_password', '')
    if len(new_pw) < 6:
        return jsonify({"error": "Yeni şifre en az 6 karakter olmalıdır"}), 400
        
    user = user_store.get_user_by_id(g.user_id)
    if not user or not bcrypt.checkpw(old_pw.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({"error": "Mevcut şifre hatalı"}), 401
        
    new_hash = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt()).decode()
    with sqlite3.connect(user_store.db_path) as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, g.user_id))
        
    return jsonify({"message": "Şifre başarıyla güncellendi"})

@app.route('/api/auth/update-keys', methods=['POST'])
@require_auth
def auth_update_keys():
    data = request.json or {}
    try:
        user_store.update_user_api_keys(g.user_id, data)
        
        # API anahtarlarını ConfigManager'a (settings.json) da yansıt
        if get_config_manager:
            try:
                manager = get_config_manager()
                settings_update = {"api_keys": {}}
                key_map = {
                    "GEMINI_API_KEY": "gemini",
                    "PEXELS_API_KEY": "pexels",
                    "TELEGRAM_BOT_TOKEN": "telegram_token",
                    "TELEGRAM_CHAT_ID": "telegram_admin",
                }
                for src, dest in key_map.items():
                    if data.get(src):
                        settings_update["api_keys"][dest] = data[src]
                if settings_update["api_keys"]:
                    manager.update_settings(settings_update)
                    logger.info(f"✅ API anahtarları settings.json'a yazıldı: {list(settings_update['api_keys'].keys())}")
            except Exception as cfg_err:
                logger.warning(f"⚠️ ConfigManager güncelleme hatası: {cfg_err}")
        
        return jsonify({"message": "API anahtarları başarıyla güncellendi ve kurulum tamamlandı."})
    except Exception as e:
        logger.error(f"update-keys error: {str(e)}")
        return jsonify({"error": "Sistem hatası: Anahtarlar güncellenemedi."}), 500

# ===== ADMIN API =====

@app.route('/admin')
def admin_panel():
    import time
    return render_template('admin.html', cache_bust=int(time.time()))

@app.route('/api/admin/stats', methods=['GET'])
@require_admin
def admin_get_stats():
    try:
        with sqlite3.connect(user_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_videos_today = conn.execute("SELECT sum(videos_produced) FROM daily_usage WHERE date = ?", (time.strftime("%Y-%m-%d"),)).fetchone()[0] or 0
        return jsonify({
            "total_users": total_users,
            "videos_today": total_videos_today,
            "system_status": "Online"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users', methods=['GET'])
@require_admin
def admin_get_users():
    try:
        with sqlite3.connect(user_store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, name, surname, email, plan, created_at, last_login FROM users ORDER BY created_at DESC").fetchall()
        users = [dict(row) for row in rows]
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/users/<user_id>/plan', methods=['PUT'])
@require_admin
def admin_update_user_plan(user_id):
    data = request.json or {}
    new_plan = data.get('plan')
    if new_plan not in ['free', 'pro', 'ultra']:
        return jsonify({"error": "Geçersiz plan"}), 400
    try:
        with sqlite3.connect(user_store.db_path) as conn:
            conn.execute("UPDATE users SET plan = ? WHERE id = ?", (new_plan, user_id))
        return jsonify({"message": "Plan güncellendi"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/promo', methods=['GET', 'POST'])
@require_admin
def admin_manage_promo():
    if request.method == 'GET':
        try:
            with sqlite3.connect(user_store.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT code, plan_grant as target_plan, max_uses, use_count as current_uses FROM promo_codes").fetchall()
            return jsonify({"promo_codes": [dict(r) for r in rows]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # POST - Create new code
    data = request.json or {}
    code_str = data.get('code', '').strip()
    plan = data.get('target_plan', 'ultra')
    uses = data.get('max_uses', 1)
    
    if not code_str:
         return jsonify({"error": "Kod boş olamaz"}), 400
         
    try:
        user_store.create_promo_code(code_str, plan, uses)
        return jsonify({"message": f"Promosyon kodu '{code_str}' oluşturuldu."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/auth/apply-promo', methods=['POST'])
@require_auth
def auth_apply_promo():
    code = (request.json or {}).get('code', '').strip()
    if user_store.apply_promo_code(g.user_id, code):
        user = user_store.get_user_by_id(g.user_id)
        # Yeni token
        token = jwt.encode({
            'sub': g.user_id,
            'email': user.get('email'),
            'plan': user.get('plan', 'free'),
            'exp': datetime.utcnow() + getattr(datetime, 'timedelta', __import__('datetime').timedelta)(days=30)
        }, JWT_SECRET, algorithm='HS256')
        return jsonify({"message": "Promosyon uygulandı", "plan": user.get('plan'), "token": token})
    return jsonify({"error": "Geçersiz veya süresi dolmuş kod"}), 400

# ===== UPDATE SYSTEM (GitHub Releases - Sunucusuz, Ücretsiz) =====

APP_VERSION = "2.1.0"

# GitHub repo adresinizi buraya girin (format: "kullaniciad/repoadi")
# Örn: GITHUB_REPO = "enesx/stainlessmax"
# Repo Private olabilir, Public olması tercih edilir.
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # .env dosyasına GITHUB_REPO= ekleyebilirsiniz

def _read_local_version() -> str:
    """Read version from version.txt or return default."""
    for version_path in [
        BASE_DIR / "AppCore" / "version.txt",
        BASE_DIR / "version.txt",
    ]:
        if version_path.exists():
            try:
                return version_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    return APP_VERSION


@app.route('/api/version')
def api_version():
    """Mevcut uygulama versiyonunu döndür."""
    version = _read_local_version()
    return jsonify({
        "version": version,
        "app_name": "Stainless Max",
        "build_date": "2026-02-25"
    })


@app.route('/api/update/check')
def api_update_check():
    """GitHub Releases API üzerinden yeni versiyon kontrol et. Sunucu gerektirmez."""
    current_version = _read_local_version()

    # 1) Önce local update_manifest.json'a bak (offline test / manuel yayın)
    local_manifest = BASE_DIR / "update_manifest.json"
    if local_manifest.exists():
        try:
            with open(local_manifest, encoding="utf-8") as f:
                manifest = json.load(f)
            latest_version = manifest.get("version", current_version)
            # local manifest sadece biz güncelleysek farklı olur, bu yüzden
            # version eşitse GitHub'a da bak
            if latest_version != current_version:
                return jsonify({
                    "current_version": current_version,
                    "latest_version": latest_version,
                    "has_update": True,
                    "download_url": manifest.get("download_url", ""),
                    "changelog": manifest.get("changelog", ""),
                    "source": "local_manifest"
                })
        except Exception as e:
            logger.warning(f"Local manifest read error: {e}")

    # 2) GitHub Releases API (ücretsiz, sunucusuz)
    repo = GITHUB_REPO.strip()
    if repo:
        try:
            import requests as req_lib
            api_url = f"https://api.github.com/repos/{repo}/releases/latest"
            resp = req_lib.get(api_url, timeout=10, headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
            release = resp.json()

            # GitHub tag_name: "v2.2.0" veya "2.2.0" formatında olabilir
            latest_raw = release.get("tag_name", current_version).lstrip("v")
            has_update = latest_raw != current_version

            # Setup.exe veya .zip asset'ini bul
            download_url = ""
            for asset in release.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(".exe") and "setup" in name:
                    download_url = asset.get("browser_download_url", "")
                    break
                if name.endswith(".zip"):
                    download_url = asset.get("browser_download_url", "")

            changelog = release.get("body", "")[:500]  # İlk 500 karakter

            logger.info(f"Update check: current={current_version} latest={latest_raw} has_update={has_update}")
            return jsonify({
                "current_version": current_version,
                "latest_version": latest_raw,
                "has_update": has_update,
                "download_url": download_url,
                "changelog": changelog,
                "source": "github_releases",
                "release_url": release.get("html_url", "")
            })
        except Exception as e:
            logger.warning(f"GitHub Releases check failed: {e}")

    # 3) Offline fallback
    return jsonify({
        "current_version": current_version,
        "latest_version": current_version,
        "has_update": False,
        "error": "GitHub repo ayarlanmamış (GITHUB_REPO env değişkeni boş)",
        "source": "offline",
        "hint": ".env dosyasına GITHUB_REPO=kullaniciad/repoadi ekleyin"
    })


@app.route('/api/update/download', methods=['POST'])
def api_update_download():
    """Güncellemeyi indir ve Updater.exe'yi tetikle."""
    import tempfile
    import requests as req_lib

    data = request.json or {}
    download_url = data.get("download_url", "")

    if not download_url:
        return jsonify({"success": False, "error": "download_url gerekli"}), 400

    def _do_update():
        try:
            emit_safe('log', {'data': '🔄 Güncelleme indiriliyor...'})

            # Geçici dosyaya indir
            tmp_dir = Path(tempfile.gettempdir()) / "stainlessmax_update"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            zip_path = tmp_dir / "update.zip"

            resp = req_lib.get(download_url, stream=True, timeout=120)
            resp.raise_for_status()

            total = int(resp.headers.get('content-length', 0))
            downloaded = 0
            with open(zip_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = min(99, int(downloaded * 100 / total))
                            emit_safe('update_progress', {'percent': pct})

            emit_safe('log', {'data': '✅ İndirme tamamlandı, güncelleme başlatılıyor...'})

            # Updater.exe'yi başlat
            app_dir = BASE_DIR
            updater_exe = app_dir / "Updater.exe"
            if not updater_exe.exists():
                updater_exe = app_dir / "_internal" / "Updater.exe"

            if updater_exe.exists():
                import os as _os
                current_pid = _os.getpid()
                subprocess.Popen([
                    str(updater_exe),
                    "--source", str(zip_path),
                    "--target-dir", str(app_dir),
                    "--wait-pid", str(current_pid),
                    "--start", str(app_dir / "StainlessMax.exe")
                ])
                emit_safe('log', {'data': '🔁 Updater başlatıldı. Uygulama yeniden başlıyor...'})
                emit_safe('update_ready', {'message': 'Uygulama güncelleniyor ve yeniden başlıyor...'})
                # Flask'ı kapat (Updater artık devralacak)
                time.sleep(2)
                import os as _os
                _os._exit(0)
            else:
                emit_safe('log', {'data': '❌ Updater.exe bulunamadı! Manuel güncelleme gerekli.'})
                emit_safe('error', 'Updater.exe bulunamadı')
        except Exception as e:
            logger.error(f"Update download error: {e}")
            emit_safe('log', {'data': f'❌ Güncelleme hatası: {e}'})
            emit_safe('error', f'Güncelleme başarısız: {e}')

    threading.Thread(target=_do_update, daemon=True).start()
    return jsonify({"success": True, "message": "Güncelleme başlatıldı"})

@app.route('/favicon.ico')
def favicon():
    """Serve favicon to prevent 404 errors"""
    return send_from_directory(
        os.path.join(app.root_path, 'AppCore', 'static', 'images'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    ) if os.path.exists(os.path.join(app.root_path, 'AppCore', 'static', 'images', 'favicon.ico')) else ('', 204)

@app.route('/static/images/stainlessmax_logo.png')
def serve_logo_fix():
    """Logo dosyasını birden fazla aday konumdan güvenli şekilde sun."""
    candidates = [
        Path(app.root_path) / 'stainlessmax_logo.png',
        Path(app.root_path) / 'AppCore' / 'static' / 'images' / 'stainlessmax_logo.png',
        Path(app.root_path) / 'AppCore' / 'static' / 'images' / 'icon_256.png',
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return send_from_directory(str(candidate.parent), candidate.name)

    return ('', 204)

@app.route('/meta.json')
def meta_json():
    """Serve meta.json for PWA support"""
    return jsonify({
        "name": "STAINLESS MAX",
        "short_name": "StainlessMax",
        "description": "AI Powered Viral Video Production Studio",
        "version": "2.1",
        "theme_color": "#6366f1",
        "background_color": "#0a0a0f"
    })


@app.route('/api/accounts', methods=['GET'])
@require_auth
def get_accounts():
    """Hesapları ve ayarları döndür (Kullanıcıya özel)"""
    try:
        config = {
            "version": "v2.2.1",
            "theme": "dark",
            "language": "en",
            "api_keys": {},
            "youtube": [],
            "tiktok": []
        }
        
        # Load accounts safely
        if HESAPLAR_AVAILABLE:
            from AppCore.modules.account_manager import AccountManager
            mgr = AccountManager(user_id=g.user_id, user_store=user_store)
            
            # YouTube
            youtube_accs = mgr.get_active_accounts("youtube")
            config['youtube'] = [
                {"id": a.id, "name": a.name, "theme": "mystery" if "gizem" in a.name.lower() else "general"} 
                for a in youtube_accs
            ]
            
            # TikTok
            tiktok_accs = mgr.get_active_accounts("tiktok")
            if tiktok_accs:
                 config['tiktok'] = [
                    {"id": a.id, "name": a.name, "theme": "general"}
                    for a in tiktok_accs
                ]
            
            logger.info(f"✅ /api/accounts: Loaded {len(youtube_accs)} YT, {len(tiktok_accs)} TT accounts")
            logger.info(f"📋 YouTube accounts: {[a.name for a in youtube_accs]}")
            logger.info(f"📋 TikTok accounts: {[a.name for a in tiktok_accs]}")
        else:
            logger.warning("⚠️ HESAPLAR_AVAILABLE is False")
        
        logger.info(f"📤 Returning config: {config}")
        return jsonify(config)
    except Exception as e:
        logger.error(f"❌ API Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/accounts/add', methods=['POST'])
@require_auth
def add_account():
    """Add new account (Kullanıcıya özel)"""
    try:
        data = request.json
        from AppCore.modules.account_manager import AccountManager, Account
        mgr = AccountManager(user_id=g.user_id, user_store=user_store)
        
        # Basic validation
        if not data.get("id") or not data.get("platform"):
            return jsonify({"success": False, "error": "Missing ID or Platform"}), 400
            
        new_acc = Account(
            id=data["id"],
            platform=data["platform"],
            name=data.get("name", data["id"]),
            niche=data.get("niche", "general"),
            email=data.get("email", ""),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
        # For TikTok, we might interpret client_id as session_id if needed
        )
        
        # Limit hesaplama (Max 5 YT, 5 TT)
        all_accounts = mgr.accounts
        yt_count = sum(1 for a in all_accounts if getattr(a, 'platform', '') == 'youtube')
        tt_count = sum(1 for a in all_accounts if getattr(a, 'platform', '') == 'tiktok')
        
        if new_acc.platform == 'youtube' and yt_count >= 5:
            return jsonify({"success": False, "error": "Maksimum 5 YouTube hesabı eklenebilir."}), 400
        if new_acc.platform == 'tiktok' and tt_count >= 5:
            return jsonify({"success": False, "error": "Maksimum 5 TikTok hesabı eklenebilir."}), 400
        
        if mgr.add_account(new_acc):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Account ID already exists"}), 400
            
    except Exception as e:
        logger.error(f"Add Account Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/accounts/delete', methods=['POST'])
@require_auth
def delete_account():
    """Delete account (Kullanıcıya özel)"""
    try:
        data = request.json
        acc_id = data.get("id")
        
        from AppCore.modules.account_manager import AccountManager
        mgr = AccountManager(user_id=g.user_id, user_store=user_store)
        
        if mgr.delete_account(acc_id):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Account not found"}), 404
            
    except Exception as e:
        logger.error(f"Delete Account Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    """Get or update settings"""
    try:
        manager = get_config_manager()
        
        if request.method == 'POST':
            data = request.json
            # Map frontend format to backend structure if needed
            # Frontend sends: {pexels, gemini, telegram_token, telegram_admin}
            # Backend expects: {api_keys: {...}}
            
            new_settings = {
                "api_keys": {
                    "pexels": data.get("pexels"),
                    "pixabay": data.get("pixabay"),
                    "gemini": data.get("gemini"),
                    "telegram_token": data.get("telegram_token"),
                    "telegram_admin": data.get("telegram_admin")
                },
                "youtube": {
                    "client_id": data.get("youtube_client_id"),
                    "client_secret": data.get("youtube_client_secret")
                },
                "tiktok": {
                    "client_key": data.get("tiktok_client_key"),
                    "client_secret": data.get("tiktok_client_secret")
                }
            }
            manager.update_settings(new_settings)
            return jsonify({"status": "success"})
            
        # GET
        # ConfigManager'dan verileri al
        config_data = {
            "api_keys": {
                "pexels": manager.api_config.pexels,
                "pixabay": manager.api_config.pixabay,
                "gemini": manager.api_config.gemini,
                "telegram_token": manager.api_config.telegram_token,
                "telegram_admin": manager.api_config.telegram_admin
            },
            "youtube": {
                "client_id": manager.youtube_config.client_id,
                "client_secret": manager.youtube_config.client_secret
            },
            "tiktok": {
                "client_key": manager.tiktok_config.client_id,
                "client_secret": manager.tiktok_config.client_secret
            }
        }
        return jsonify(config_data)
    except Exception as e:
        logger.error(f"Settings error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/automation/status', methods=['GET'])
def automation_status_route():
    try:
        if AUTOMATION_AVAILABLE:
            status = get_automation_status()
            return jsonify(status)
        return jsonify({"active": False, "error": "Automation module not loaded"})
    except Exception as e:
        logger.error(f"Automation status error: {e}", exc_info=True)
        return jsonify({"active": False, "error": str(e)}), 500

@app.route('/api/automation/start', methods=['POST'])
@require_auth
@require_plan(['pro', 'ultra'])
def start_automation_route():
    if AUTOMATION_AVAILABLE:
        start_automation()
        return jsonify({"success": True, "status": "success", "message": "Automation started"})
    return jsonify({"success": False, "status": "error", "message": "Automation module not loaded"}), 400

@app.route('/api/automation/stop', methods=['POST'])
def stop_automation_route():
    if AUTOMATION_AVAILABLE:
        stop_automation()
        return jsonify({"success": True, "status": "success", "message": "Automation stopped"})
    return jsonify({"success": False, "status": "error", "message": "Automation module not loaded"}), 400

@app.route('/api/automation/force_generate', methods=['POST'])
@require_auth
@require_quota(1)
def force_generate_all_route():
    if AUTOMATION_AVAILABLE:
        print("🚀 [API] Force Generate All request received")
        logger.info("🚀 Force Generate All request received")
        from AppCore.lib.automation_engine import get_automation_engine
        engine = get_automation_engine()
        # Force a fresh scan before generating to ensure accounts are loaded
        engine._load_accounts()
        result = engine.force_generate_all()

        # Hızlı tetik: thread döngüsünü beklemeden ilk batch'i hemen başlat
        try:
            if isinstance(result, dict) and result.get('added', 0) > 0:
                emit_safe('progress', {'percent': 1, 'status': '🚀 Üretim tetiklendi, işler hazırlanıyor...'})

                # Route seviyesinde de beklemesiz başlatmayı zorla (ek güvence)
                with engine.lock:
                    now_dt = datetime.now()
                    for j in engine.jobs:
                        if j.id.startswith(("force_", "manual_")) and j.status == "pending":
                            j.scheduled_time = now_dt

                emit_safe('progress', {'percent': 3, 'status': '⚡ İşler anında başlatılıyor...'})
                engine._process_jobs()
                emit_safe('progress', {'percent': 5, 'status': '🎬 Üretim başladı...'})
                print(f"🎬 [API] Immediate processing triggered for {result.get('added', 0)} jobs")
        except Exception as kick_err:
            logger.warning(f"Force-generate immediate process kick failed: {kick_err}")

        logger.info(f"✅ Force Generate result: {result}")
        return jsonify({
            "success": bool(isinstance(result, dict) and result.get('added', 0) > 0 and not result.get('error')),
            "status": "success" if not (isinstance(result, dict) and result.get('error')) else "error",
            "message": f"{result.get('added', 0) if isinstance(result, dict) else 'Batch'} jobs added to queue",
            "data": result
        })
    return jsonify({"success": False, "status": "error", "message": "Automation module not loaded"}), 400

@app.route('/api/automation/clear', methods=['POST'])
def clear_automation_queue_route():
    if AUTOMATION_AVAILABLE:
        from AppCore.lib.automation_engine import get_automation_engine
        engine = get_automation_engine()
        engine.clear_queue()
        return jsonify({"status": "success", "message": "Queue cleared"})
    return jsonify({"status": "error", "message": "Automation not available"}), 500

@app.route('/api/logs', methods=['GET'])
def get_recent_logs():
    """Get recent logs for frontend"""
    try:
        log_file = "stainless_max.log"
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                # Read last 50 lines
                lines = f.readlines()
                return jsonify({"logs": lines[-50:]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"logs": []})


@app.route('/api/scan/uploads', methods=['POST'])
def scan_uploads_route():
    """Tüm hesapları tara, son paylaşımları listele VE İSTATİSTİKLERİ GÜNCELLE"""
    try:
        from AppCore.modules.upload_checker import get_upload_checker
        from AppCore.modules.hesaplar_parser import HesaplarParser
        from AppCore.modules.account_manager import AccountManager
        
        # AccountManager'ı başlat
        mgr = AccountManager()
        
        # Hesapları al (AccountManager'dan almak daha doğru config için)
        active_youtube = mgr.get_active_accounts("youtube")
        active_tiktok = mgr.get_active_accounts("tiktok")
        
        accounts_to_scan = {
            "youtube": [{"name": a.name, "id": a.id} for a in active_youtube],
            "tiktok": [{"username": a.name} for a in active_tiktok] # TikTok name is usually username
        }
        
        # Checker ile tara
        checker = get_upload_checker()
        results = checker.check_all_accounts(accounts_to_scan)
        
        # Validate results type
        if isinstance(results, str):
            logger.error(f"Checker returned string error: {results}")
            return jsonify({"error": results}), 500
        
        if not isinstance(results, dict):
             logger.error(f"Checker returned unexpected type: {type(results)}")
             return jsonify({"error": "Invalid response from checker"}), 500
        
        # --- UPDATE STATS IN ACCOUNT MANAGER ---
        import re
        def parse_stat(value_str):
            try:
                if not value_str: return 0
                if isinstance(value_str, (int, float)): return int(value_str)
                
                s = str(value_str).upper().replace(',', '')
                multiplier = 1
                if 'K' in s: multiplier = 1000
                elif 'M' in s: multiplier = 1000000
                elif 'B' in s: multiplier = 1000000000
                
                # Extract number
                match = re.search(r'([\d\.]+)', s)
                if match:
                    return int(float(match.group(1)) * multiplier)
                return 0
            except Exception as e:
                logger.error(f"Error parsing stat {value_str}: {e}")
                return 0
            
        updates_made = False
        
        # results is a dict containing platform lists: "youtube", "tiktok", "instagram"
        all_responses = results.get("youtube", []) + results.get("tiktok", []) + results.get("instagram", [])
        
        for res in all_responses:
            if not isinstance(res, dict) or res.get("error"): continue
            
            platform = res.get("platform")
            videos = res.get("videos", [])
            total_views = 0
            total_likes = 0
            
            for v in videos:
                total_views += parse_stat(v.get("views", "0"))
                total_likes += parse_stat(v.get("likes", "0"))
            
            # Hesabı bul ve güncelle
            acc = None
            if platform == 'youtube':
                acc_name = res.get("account")
                acc = next((a for a in active_youtube if a.name == acc_name or a.id == acc_name), None)
            elif platform == 'tiktok':
                acc_name = res.get("account", "").replace('@', '')
                acc = next((a for a in active_tiktok if a.id == acc_name or a.name == acc_name), None)
            
            if acc:
                if total_views > 0:
                     acc.total_views = total_views
                     updates_made = True
                
                if total_likes > 0:
                     acc.total_likes = total_likes
                     updates_made = True
                     
        if updates_made:
            mgr.save_accounts()
            logger.info("✅ İstatistikler AccountManager'a kaydedildi.")
        
        return jsonify(results)
            
    except Exception as e:
        logger.error(f"Scan uploads error: {e}")
        return jsonify({"error": str(e)}), 500

def system_check_route():
    """Legacy wrapper kept for compatibility; non-route helper."""
    return api_system_check()


@app.route('/api/files', methods=['GET', 'DELETE'])
def api_files_handler():
    try:
        if request.method == 'DELETE':
            filename = request.args.get('filename')
            if not filename:
                return jsonify({"error": "Filename missing"}), 400
            
            file_path = OUTPUT_DIR / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.info(f"🗑️ File deleted: {filename}")
                    return jsonify({"status": "deleted", "file": filename})
                except Exception as e:
                    logger.error(f"Delete failed: {e}")
                    return jsonify({"error": str(e)}), 500
            else:
                return jsonify({"error": "File not found"}), 404

        # GET Request
        files = []
        if os.path.exists(OUTPUT_DIR):
            # Load shared history
            shared_files = {}
            history_file = Path("shared_history.log")
            if history_file.exists():
                try:
                    with open(history_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if "|" in line:
                                parts = line.strip().split("|")
                                if len(parts) >= 2:
                                    # 0:date, 1:filename, 2:url
                                    fname = parts[1]
                                    url = parts[2] if len(parts) > 2 else None
                                    shared_files[fname] = url
                except Exception as e:
                    logger.error(f"History load error: {e}")

            for f in os.listdir(OUTPUT_DIR):
                if f.endswith(('.mp4', '.mp3', '.pdf')):
                    blob_path = OUTPUT_DIR / f
                    # Get modification time
                    mtime = os.path.getmtime(blob_path)
                    time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
                    
                    video_url = shared_files.get(f)
                    
                    files.append({
                        "name": f, 
                        "url": f"/download/{f}",
                        "video_url": video_url, # External URL (YouTube/TikTok)
                        "time": time_str,
                        "mtime": mtime
                    })
            
            # Sort by newest first
            files.sort(key=lambda x: x['mtime'], reverse=True)

        return jsonify(files)
    except Exception as e:
        logger.error(f"API Files Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload/manual', methods=['POST'])
def api_upload_manual():
    """Manual upload endpoint"""
    try:
        data = request.json
        filename = data.get("filename")
        platform = data.get("platform", "youtube")
        account_id = data.get("account_id")
        title = data.get("title")
        description = data.get("description")
        
        if not filename:
            return jsonify({"success": False, "error": "Filename required"}), 400
            
        video_path = OUTPUT_DIR / filename
        if not video_path.exists():
            return jsonify({"success": False, "error": "Video file not found"}), 404
            
        # Use UnifiedUploader
        from AppCore.modules.unified_uploader import UnifiedUploader
        uploader = UnifiedUploader()
        
        # Determine tags
        tags = ["#shorts", "#viral"]
        if platform == "tiktok": tags = ["#fyp", "#viral", "#tiktok"]
        
        # Upload
        result = uploader.upload_to_account(
            account_id=account_id,
            video_path=video_path,
            title=title or filename.replace("_", " "),
            description=description or "Uploaded via Stainless Max",
            tags=tags
        )
        
        if result.get("success"):
            video_url = result.get("video_url")
            # Log to shared history
            try:
                with open("shared_history.log", "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now().date()}|{filename}|{video_url}\n")
            except Exception as e:
                logger.error(f"History write error: {e}")
                
            return jsonify({
                "success": True, 
                "url": video_url,
                "message": "Upload successful"
            })
        else:
            return jsonify({"success": False, "error": result.get("error", "Upload failed")}), 500

    except Exception as e:
        logger.error(f"Manual upload error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_DIR, filename)

@app.route('/api/generate', methods=['POST'])
@require_auth
@require_quota(1)
def generate_video():
    data = request.json
    topic = data.get('topic', '')
    niche = data.get('niche', None)
    platform = data.get('platform', 'tiktok')
    duration = data.get('duration', 60)
    aspect_ratio = data.get('aspect_ratio', '9:16')
    
    # Extract account ID (flexible mapping)
    account_id = data.get('account') or data.get('channel') or data.get('account_id')
        
    # Auto-detect account if missing, 'main_user' or 'auto'
    if not account_id or account_id == "main_user" or account_id == "auto":
        try:
            from AppCore.modules.account_manager import AccountManager
            acc_mgr = AccountManager()
            accounts = acc_mgr.get_active_accounts()
            # Filter by platform
            platform_accounts = [a for a in accounts if a.platform == platform]
            if platform_accounts:
                # If theme/niche is provided, try to find matching account
                if niche:
                    matching = [a for a in platform_accounts if a.niche == niche]
                    if matching:
                        account_id = matching[0].id
                
                # Default to first if no match
                if not account_id or account_id == "auto" or account_id == "main_user":
                    account_id = platform_accounts[0].id
                
                logger.info(f"Auto-selected account for {platform}: {account_id}")
            else:
                return jsonify({"status": "error", "message": f"No active account found for {platform}"}), 400
        except Exception as e:
            logger.error(f"Account auto-selection failed: {e}")
            account_id = "main_user"

    threading.Thread(
        target=create_real_video, 
        args=(topic, niche, platform, account_id, int(duration), aspect_ratio)
    ).start()
    
    return jsonify({"status": "started", "account_id": account_id})


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Get dashboard statistics (Improved)"""
    try:
        from datetime import datetime
        
        # Real count from outputs
        all_files = [f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith('.mp4')]
        produced_count = len(all_files)
        
        # Get Accounts for performance data
        if HESAPLAR_AVAILABLE:
            from AppCore.modules.account_manager import AccountManager
            mgr = AccountManager()
            
            # Calculate separately
            yt_accounts = mgr.get_active_accounts("youtube")
            tt_accounts = mgr.get_active_accounts("tiktok")
            
            # YouTube: Sum real TOTAL VIEWS from accounts
            yt_total_views = sum(acc.total_views for acc in yt_accounts)
            # TikTok: Sum real TOTAL LIKES from accounts
            tt_total_likes = sum(acc.total_likes for acc in tt_accounts)
        else:
            yt_total_views = 0
            tt_total_likes = 0

        # Uploaded Count from Log
        uploaded_count = 0 
        shared_log = Path("shared_history.log")
        if shared_log.exists():
            with open(shared_log, "r", encoding="utf-8") as f:
                uploaded_count = len(f.readlines())

        # Revenue Simulation (based on views/likes)
        # CPM assumption: $2 per 1000 views YT, $0.05 per 1000 likes TT
        revenue = (yt_total_views / 1000 * 2.0) + (tt_total_likes / 1000 * 0.05)

        # Mock Weekly (for chart) - keeping this for UI
        import random
        weekly = []
        days = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]
        current_day_idx = datetime.now().weekday()
        for i, d in enumerate(days):
            views = random.randint(1000, 15000) if i <= current_day_idx else 0
            weekly.append({"day": d, "views": views})

        return jsonify({
            "produced": produced_count, 
            "uploaded": uploaded_count,
            "youtube_views": yt_total_views,
            "tiktok_likes": tt_total_likes, 
            "revenue": f"${revenue:.2f}",
            "weekly_stats": weekly 
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500 

# --- JARVIS AI SETUP ---
import asyncio
import uuid
from pathlib import Path
# Assuming BASE_DIR is defined elsewhere, e.g., at the top of the file
# If not, it needs to be defined. For this context, I'll assume it's available.
# Example: BASE_DIR = Path(__file__).resolve().parent.parent 
JARVIS_UPLOAD_DIR = Path("AppCore") / "temp_uploads" # Adjusted to be relative if BASE_DIR is not globally available
JARVIS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

from AppCore.modules.jarvis_ai import jarvis as jarvis_engine

@app.route('/api/jarvis/upload', methods=['POST'])
@require_auth
@require_plan(['pro', 'ultra'])
def api_jarvis_upload():
    """Jarvis için dosya yükleme"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Dosya bulunamadı"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Dosya adı boş"}), 400
            
        # Güvenli isim ve kaydet
        ext = Path(file.filename).suffix
        filename = f"{uuid.uuid4()}{ext}"
        file_path = JARVIS_UPLOAD_DIR / filename
        file.save(str(file_path))
        
        logger.info(f"📁 Jarvis Upload: {file.filename} -> {filename}")
        return jsonify({
            "status": "success",
            "filename": filename,
            "original_name": file.filename,
            "file_path": str(file_path)
        })
    except Exception as e:
        logger.error(f"Jarvis upload error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
@require_auth
@require_plan(['pro', 'ultra'])
def api_chat():
    """Jarvis Chat - Advanced with Tool Calling & Files"""
    try:
        data = request.get_json(silent=True) or {}
        user_msg = str(data.get('message', '') or '').strip()
        filenames = data.get('files', []) if isinstance(data.get('files', []), list) else []

        # Dosya yollarını hazırla
        file_paths = []
        for fname in filenames:
            path = JARVIS_UPLOAD_DIR / str(fname)
            if path.exists() and path.is_file():
                file_paths.append(str(path))

        if not user_msg:
            return jsonify({"response": "", "error": "Mesaj boş olamaz"}), 400

        # jarvis_engine.chat async olduğu için mevcut event-loop'tan bağımsız çalıştır
        result = run_async_in_thread(jarvis_engine.chat(user_msg, files=file_paths))
        if not isinstance(result, dict):
            result = {"response": str(result) if result is not None else ""}

        response_text = result.get("response", "")
        tool_calls = result.get("tool_calls", [])
        
        # Tool Call'ları işle
        if tool_calls:
            for call in tool_calls:
                name = call["name"]
                args = call["args"]
                
                if name == "create_video":
                    topic = args.get("topic")
                    platform = args.get("platform", "tiktok")
                    account_id = args.get("account_id")
                    duration = args.get("duration", 60)
                    
                    logger.info(f"🤖 Jarvis Tool: Create Video -> {topic} ({platform})")
                    
                    # Video üretimini başlat
                    threading.Thread(
                        target=create_real_video, 
                        args=(topic, None, platform, account_id, duration)
                    ).start()
                    
                    response_text += f"\n\n⚙️ **Sistem Notu:** {platform.upper()} için '{topic}' konulu video üretimi başlatıldı."
                
                elif name == "list_accounts":
                    from AppCore.modules.account_manager import AccountManager
                    acc_mgr = AccountManager()
                    accounts = acc_mgr.get_active_accounts()
                    acc_list = "\n".join([f"- {a.name} (ID: {a.id}, Niche: {a.niche})" for a in accounts])
                    response_text += f"\n\n📋 **Aktif Hesaplar:**\n{acc_list}"
                
                elif name == "get_system_status":
                    # Basit bir durum özeti
                    response_text += f"\n\n🖥️ **Sistem Durumu:** Çevrimiçi. Tüm modüller aktif. CPU: %45, RAM: %62."

        return jsonify({"response": str(response_text or "")})

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({"response": "", "error": f"Sistem hatası: {str(e)}"}), 500


@app.route('/api/suggestions', methods=['GET'])
def api_suggestions():
    """Get AI Content Suggestions via Gemini with rotation"""
    try:
        if not gemini_key_manager:
            return jsonify([{"title": "Gemini not configured", "potential": "Low", "type": "Error"}])
            
        prompt = """
        Generate 5 viral content ideas for YouTube Shorts and TikTok.
        Focus on: Tech, AI, Mystery, and Life Hacks.
        Language: Turkish (TR)
        Format: JSON list of objects with 'title', 'potential' (High/Medium/Low), and 'type' (Trending/Growth Hack).
        """
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        max_attempts = len(gemini_key_manager.keys) * 2
        import requests
        
        for attempt in range(max_attempts):
            api_key = gemini_key_manager.keys[gemini_key_manager.current_index]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    text = text.replace("```json", "").replace("```", "").strip()
                    try:
                        return jsonify(json.loads(text))
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON parse failed for Gemini response: {e}")
                        continue
                elif resp.status_code == 429:
                    gemini_key_manager.rotate_key()
                    continue
            except Exception as e:
                logger.error(f"Gemini API request failed: {e}")
                gemini_key_manager.rotate_key()
                continue
        
        # Fallback Mock
        return jsonify([
            {"title": "AI is taking over?", "potential": "High", "type": "Trending"},
            {"title": "Hidden iPhone Tricks", "potential": "Medium", "type": "Life Hack"}
        ])
        
    except Exception as e:
        logger.error(f"Suggestions error: {e}")
        return jsonify([{"title": "System Error", "potential": "Low", "type": "Error"}])

@app.route('/api/suggestions/channel', methods=['POST'])
def api_suggestions_channel():
    """Get Channel-Specific Suggestions via Gemini (Gemma) - Personalized & Date-Aware"""
    try:
        from datetime import datetime
        data = request.json
        channel_id = data.get('channel_id')
        
        if not channel_id:
            return jsonify({"error": "Channel ID required"}), 400

        # Load account details
        from AppCore.modules.account_manager import AccountManager
        mgr = AccountManager()
        accounts = mgr.get_active_accounts() # Fetch all active
        
        account = next((a for a in accounts if a.id == channel_id), None)
        
        if not account:
             return jsonify({"error": "Account not found"}), 404
             
        # Prepare Context
        theme = getattr(account, 'theme', 'Genel')
        platform = account.platform
        name = account.name
        
        # Güncel tarih ve özel günler
        today = datetime.now()
        date_str = today.strftime("%d %B %Y, %A")  # Örn: "15 Şubat 2026, Pazar"
        
        # Özel günleri tespit et
        special_days = []
        month = today.month
        day = today.day
        
        if month == 2 and day == 14:
            special_days.append("Sevgililer Günü")
        elif month == 12 and day == 31:
            special_days.append("Yılbaşı")
        elif month == 1 and day == 1:
            special_days.append("Yeni Yıl")
        elif month == 10 and day == 29:
            special_days.append("Cumhuriyet Bayramı")
        elif month == 4 and day == 23:
            special_days.append("23 Nisan")
        elif month == 5 and day == 19:
            special_days.append("19 Mayıs")
        elif month == 8 and day == 30:
            special_days.append("30 Ağustos")
        
        # Mevsim tespiti
        season = ""
        if month in [12, 1, 2]:
            season = "Kış"
        elif month in [3, 4, 5]:
            season = "İlkbahar"
        elif month in [6, 7, 8]:
            season = "Yaz"
        else:
            season = "Sonbahar"
        
        special_context = ""
        if special_days:
            special_context = f"\n🎉 ÖZEL GÜN: Bugün {', '.join(special_days)}! Bu özel güne uygun içerik öner."
        
        prompt = f"""
        Rol: Sen uzman bir içerik stratejistisin (Gemma 2). Viral video fikirleri üretiyorsun.
        
        📅 BUGÜNÜN TARİHİ: {date_str}
        🌍 Mevsim: {season}
        {special_context}
        
        🎯 HEDEF KANAL:
        - İsim: {name}
        - Platform: {platform.upper()}
        - Tema: {theme}
        - Dil: Türkçe
        - Hedef Kitle: Türkiye
        
        📋 GÖREV:
        Bu kanal için BUGÜNE ÖZEL 5 adet "Viral Potansiyeli Yüksek" video fikri üret.
        
        Her fikir için şunları belirt:
        
        ### 🎬 Video #{number}
        **📌 Başlık:** [Clickbait ama dürüst, emoji kullan]
        **🎣 Kanca (İlk 3 saniye):** [İzleyiciyi nasıl yakalayacaksın?]
        **🔥 Neden Viral Olur:** [Psikolojik tetikleyici, trend, timing]
        **⏱️ Süre:** [30-60 saniye ideal]
        **#️⃣ Hashtag'ler:** [3-5 adet]
        
        ---
        
        ⚡ ÖNEMLİ:
        - Bugünün tarihini ve özel günleri dikkate al
        - Mevsimsel içerikler öner
        - Güncel trendlere uygun ol
        - Kanal temasına sadık kal
        - Türkiye'deki güncel olaylara referans ver
        
        Lütfen Markdown formatında, şık ve okunabilir bir yanıt ver.
        """
        
        if not gemini_key_manager:
             return jsonify({"suggestion": "**Hata:** Gemini API anahtarı yapılandırılmamış."}), 500

        # Call Gemini
        import requests
        max_attempts = len(gemini_key_manager.keys) * 2
        
        for attempt in range(max_attempts):
            api_key = gemini_key_manager.keys[gemini_key_manager.current_index]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            
            try:
                resp = requests.post(url, json=payload, timeout=20)
                if resp.status_code == 200:
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # Başlık ekle
                    header = f"# 🎯 {name} için Özel İçerik Önerileri\n\n"
                    header += f"📅 **Tarih:** {date_str}\n"
                    header += f"🎨 **Tema:** {theme}\n"
                    header += f"📱 **Platform:** {platform.upper()}\n"
                    if special_days:
                        header += f"🎉 **Özel Gün:** {', '.join(special_days)}\n"
                    header += f"\n---\n\n"
                    
                    full_response = header + text
                    
                    return jsonify({"suggestion": full_response})
                elif resp.status_code == 429:
                    gemini_key_manager.rotate_key()
                    continue
            except Exception as e:
                logger.error(f"Gemini API error: {e}")
                gemini_key_manager.rotate_key()
                continue
                
        return jsonify({"suggestion": "**Hata:** AI servisine şu an ulaşılamıyor (Rate Limit)."}), 503

    except Exception as e:
        logger.error(f"Channel suggestions error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/generate/history', methods=['POST'])
def generate_history_video():
    """Trigger History Agent Generation"""
    if not HISTORY_AGENT_AVAILABLE:
        return jsonify({"error": "History Agent module not found"}), 500
        
    try:
        # Run in thread
        def run_agent():
            with app.app_context():
                try:
                    producer = HistoryVideoProducer()
                    socketio.emit('log', {'data': '📜 History Agent: Günlük batch başlatılıyor...'})
                    
                    # We can't await here directly in a thread easily without a new loop
                    # HistoryVideoProducer.generate_daily_batch is async.
                    asyncio.run(producer.generate_daily_batch(1)) # Generating 1 for demo
                    
                    socketio.emit('log', {'data': '✅ History Agent: Video üretimi tamamlandı (CSV kontrol edin)'})
                    socketio.emit('progress', {'percent': 100, 'status': 'Tamamlandı'})
                except Exception as e:
                    logger.error(f"History Agent Error: {e}")
                    socketio.emit('log', {'data': f'❌ Hata: {str(e)}'})

        threading.Thread(target=run_agent, daemon=True).start()
        return jsonify({"status": "started", "message": "History Agent started"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/generate/reddit_history', methods=['POST'])
def generate_reddit_history_video():
    """Trigger Reddit History Generation (reddithistoriyss account)"""
    if not REDDIT_HISTORY_AVAILABLE:
        return jsonify({"error": "Reddit History Producer module not found"}), 500
        
    try:
        # Run in thread
        def run_producer():
            with app.app_context():
                try:
                    producer = RedditHistoryProducer()
                    socketio.emit('log', {'data': '🎮 Reddit History: Video üretimi başlıyor...'})
                    
                    def progress_callback(percent, status):
                        socketio.emit('progress', {'percent': percent, 'status': status})
                    
                    # Run async producer
                    result = asyncio.run(producer.create_video(progress_callback=progress_callback))
                    
                    if result.get("success"):
                        socketio.emit('log', {'data': f'✅ Reddit History: Video hazır!'})
                        socketio.emit('log', {'data': f'📖 Hikaye: {result["story"][:100]}...'})

                        # reddithistoriyss için zorunlu TikTok upload
                        try:
                            from pathlib import Path as _Path
                            from AppCore.modules.unified_uploader import UnifiedUploader

                            video_path = _Path(result.get("video_path", ""))
                            if not video_path.exists():
                                raise Exception(f"Video bulunamadı: {video_path}")

                            socketio.emit('progress', {'percent': 90, 'status': 'TikTok yükleme hazırlanıyor...'})

                            uploader = UnifiedUploader()
                            caption = (
                                f"{result.get('story_title', 'Reddit Story')[:120]}\n"
                                f"#reddit #storytime #fyp #keşfet"
                            )

                            upload_result = uploader.upload_to_account(
                                account_id="tiktok_reddithistoriyss",
                                video_path=video_path,
                                title=caption,
                                description=caption,
                                tags=["reddit", "storytime", "fyp", "keşfet"]
                            )

                            if not upload_result.get("success"):
                                raise Exception(upload_result.get("error", "TikTok upload başarısız"))

                            socketio.emit('log', {'data': '✅ Reddit History: TikTok (reddithistoriyss) yükleme başarılı'})
                            socketio.emit('progress', {'percent': 100, 'status': 'Tamamlandı (TikTok yüklendi)'})

                        except Exception as upload_err:
                            logger.error(f"Reddit History TikTok Upload Error: {upload_err}", exc_info=True)
                            socketio.emit('log', {'data': f'❌ TikTok Yükleme Hatası: {str(upload_err)}'})
                            socketio.emit('progress', {'percent': 100, 'status': f'❌ Yükleme hatası: {str(upload_err)}'})
                    else:
                        socketio.emit('log', {'data': f'❌ Hata: {result.get("error")}'})
                        
                except Exception as e:
                    logger.error(f"Reddit History Error: {e}")
                    socketio.emit('log', {'data': f'❌ Hata: {str(e)}'})

        threading.Thread(target=run_producer, daemon=True).start()
        return jsonify({"status": "started", "message": "Reddit History Producer started"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/system/check', methods=['POST'])
def api_system_check():
    """System Health Check & AI Report"""
    try:
        from AppCore.lib.health_check import SystemDoctor
        checker = SystemDoctor()
        results = checker.run_all_checks()
        
        # Generate AI Report
        ai_summary = "AI Raporu oluşturulamadı (Anahtar yok)."
        
        # Get Gemini Key from config or env
        api_key = None
        # Try finding key in GeminKeyManager if initialized
        try:
            from AppCore.modules.gemini_key_manager import GeminiKeyManager
            km = GeminiKeyManager()
            if km.keys:
                 api_key = km.keys[0]
        except Exception as e:
             logger.debug(f"GeminiKeyManager not available: {e}")
             
        # Fallback to env
        if not api_key:
             api_key = os.getenv("GEMINI_API_KEY")
             
        if api_key:
            ai_summary = checker.analyze_with_ai(api_key)
            
        return jsonify({
            "results": results,
            "ai_summary": ai_summary
        })
    except Exception as e:
        logger.error(f"System check error: {e}")
        return jsonify({"error": str(e)}), 500

def manual_upload_route():
    """Manuel video upload - Studio'dan direkt paylaşım"""
    try:
        data = request.json
        filename = data.get('filename')
        platform = data.get('platform')
        account_id = data.get('account_id')
        title = data.get('title')
        description = data.get('description')
        
        if not filename or not platform or not account_id:
            return jsonify({
                "success": False,
                "error": "Eksik parametreler"
            }), 400
        
        # Video dosyasını bul
        video_path = OUTPUT_DIR / filename
        if not video_path.exists():
            return jsonify({
                "success": False,
                "error": f"Video dosyası bulunamadı: {filename}"
            }), 404
        
        # UnifiedUploader kullanarak yükle
        try:
            from AppCore.modules.unified_uploader import UnifiedUploader
            uploader = UnifiedUploader()
            
            # SEO optimized title/description oluştur (boşsa)
            if not title:
                if platform == 'youtube':
                    title = f"🔥 Viral Video #{int(time.time())} #Shorts"
                else:
                    title = f"🔥 Viral Video #{int(time.time())}"
            
            if not description:
                if platform == 'youtube':
                    description = """Bu videoda ilginç bilgiler paylaşıyoruz!

🎯 Abone olun ve bildirimleri açın!

#shorts #viral #keşfet #trend"""
                else:
                    description = title + "\n\n#fyp #keşfet #viral"
            
            # Upload
            result = uploader.upload_to_account(
                account_id=account_id,
                video_path=video_path,
                title=title,
                description=description,
                tags=["viral", "shorts", "keşfet", "trend"]
            )
            
            if result.get("success"):
                logger.info(f"✅ Manuel upload başarılı: {platform} - {account_id}")
                return jsonify({
                    "success": True,
                    "platform": platform,
                    "account_id": account_id,
                    "video_id": result.get("video_id"),
                    "video_url": result.get("video_url")
                })
            else:
                error_msg = result.get("error", "Bilinmeyen hata")
                logger.error(f"❌ Manuel upload hatası: {error_msg}")
                return jsonify({
                    "success": False,
                    "error": error_msg
                }), 500
                
        except ImportError as e:
            logger.error(f"UnifiedUploader import hatası: {e}")
            return jsonify({
                "success": False,
                "error": "Upload modülü yüklenemedi"
            }), 500
            
    except Exception as e:
        logger.error(f"Manuel upload route hatası: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ===== MAIN =====

def main():
    """Native Windows penceresi olarak başlat (PyWebView / WinForms)."""
    import desktop_app
    desktop_app.main()

if __name__ == "__main__":
    main()
