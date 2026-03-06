"""
STAINLESS MAX - Native Desktop Application
PyWebView (WebView2 / edgechromium) ile yerleşik Windows penceresi.
Tarayıcı açılmaz — tam native uygulama.
"""

import sys
import os
import threading
import time
import logging
import socket
import asyncio
import psutil

# Windowed modda (console=False) sys.stdout/stderr None olabilir
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# UTF-8
if sys.platform == "win32":
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

# Logging — PyInstaller EXE veya script olarak doğru BASE_DIR
if getattr(sys, 'frozen', False):
    # PyInstaller EXE: executable'ın bulunduğu klasör
    BASE_DIR = os.path.dirname(sys.executable)
    # macOS .app bundle'ları için Resources klasörüne yönlendir (add-data oraya gider)
    if sys.platform == 'darwin' and BASE_DIR.endswith('MacOS'):
        BASE_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'Resources'))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Windows görev çubuğu için AppUserModelID — process başlarken ayarla
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('StainlessMax.App.1.0')
except Exception:
    pass

# İkon dosyasını erken bul
ICON_PATH = None
for _ico_candidate in [
    os.path.join(BASE_DIR, 'stainlessmax_logo.ico'),
    os.path.join(BASE_DIR, '_internal', 'stainlessmax_logo.ico'),
    os.path.join(os.path.dirname(BASE_DIR), 'stainlessmax_logo.ico'),
]:
    if os.path.exists(_ico_candidate):
        ICON_PATH = _ico_candidate
        break

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "stainless_max.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DesktopApp")
logger.info(f"Icon path: {ICON_PATH}")

# ============================================================
# WebView2 Runtime otomatik keşif
# Registry kaydı eksik olsa bile fiziksel dosyadan bulur
# ============================================================
def _find_webview2_runtime():
    """WebView2 Runtime klasörünü disk üzerinden otomatik bul."""
    import glob
    search_dirs = [
        r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application",
        r"C:\Program Files\Microsoft\EdgeWebView\Application",
        r"C:\Program Files (x86)\Microsoft\Edge\Application",
        r"C:\Program Files\Microsoft\Edge\Application",
    ]
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for exe in glob.glob(os.path.join(search_dir, "**", "msedgewebview2.exe"), recursive=True):
            runtime_dir = os.path.dirname(exe)
            return runtime_dir
    return None

_wv2_path = _find_webview2_runtime()
if _wv2_path:
    os.environ['WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'] = _wv2_path
    logging.getLogger("DesktopApp").info(f"WebView2 runtime found at: {_wv2_path}")

# Desktop mode flag
os.environ['STAINLESS_DESKTOP_MODE'] = '1'

# AppCore path
appcore_path = os.path.join(BASE_DIR, 'AppCore')
if appcore_path not in sys.path:
    sys.path.append(appcore_path)



def _is_webview2_installed():
    """WebView2 Runtime kurulu mu kontrol et (registry + dosya sistemi)."""
    # Önce ortam değişkeninden kontrol (bizim keşif mekanizması set etmiş olabilir)
    if os.environ.get('WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'):
        exe_path = os.path.join(os.environ['WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'], 'msedgewebview2.exe')
        if os.path.exists(exe_path):
            logger.info(f"WebView2 found via env var: {exe_path}")
            return True
    # Registry kontrolü
    try:
        import winreg
        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-235B8DE50529}'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-235B8DE50529}'),
            (winreg.HKEY_CURRENT_USER, r'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-235B8DE50529}'),
        ]
        for hive, path in registry_paths:
            try:
                key = winreg.OpenKey(hive, path)
                version, _ = winreg.QueryValueEx(key, 'pv')
                winreg.CloseKey(key)
                if version and version != '0.0.0.0':
                    logger.info(f"WebView2 found in registry: {version}")
                    return True
            except (FileNotFoundError, OSError):
                continue
    except Exception as e:
        logger.warning(f"WebView2 registry check error: {e}")
    return False


def _install_webview2_silent():
    """
    WebView2 Runtime'ı otomatik kur. 
    EXE içine gömülü bootstrapper'ı kullanır, kullanıcıya soru sormaz.
    """
    import subprocess
    
    # Gömülü bootstrapper'ı bul
    meipass = getattr(sys, '_MEIPASS', BASE_DIR)
    candidates = [
        os.path.join(meipass, "MicrosoftEdgeWebview2Setup.exe"),
        os.path.join(BASE_DIR, "MicrosoftEdgeWebview2Setup.exe"),
    ]
    
    installer_path = None
    for cand in candidates:
        if os.path.exists(cand):
            installer_path = cand
            break
    
    if not installer_path:
        logger.error("WebView2 installer not found in bundle!")
        return False
    
    logger.info(f"Installing WebView2 from: {installer_path}")
    
    try:
        # Yöntem 1: ShellExecuteW ile yönetici olarak çalıştır (UAC otomatik çıkar)
        import ctypes
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd
            "runas",        # lpOperation — yönetici olarak çalıştır
            installer_path, # lpFile
            "/silent /install",  # lpParameters
            None,           # lpDirectory
            0               # nShowCmd (SW_HIDE)
        )
        # ShellExecuteW > 32 ise başarılı
        if ret > 32:
            logger.info(f"WebView2 installer launched (handle={ret}), waiting...")
            # Kurulumun bitmesini bekle (max 120 saniye)
            for _ in range(120):
                time.sleep(1)
                if _is_webview2_installed():
                    logger.info("WebView2 installation confirmed!")
                    return True
            # 120 saniye içinde kurulamadıysa yine kontrol et
            return _is_webview2_installed()
        else:
            logger.error(f"ShellExecuteW failed with code: {ret}")
            return False
    except Exception as e:
        logger.error(f"WebView2 install error: {e}")
        return False


def _preload_webview():
    """
    webview modülünü önceden yükle.
    """
    try:
        # Püf noktası: PyInstaller exe'sinde .NET Core (coreclr) bulunamayabilir.
        # Her Windows'ta yüklü olan .NET Framework'ü kullanmaya zorla.
        import os
        os.environ["PYTHONNET_RUNTIME"] = "netfx"
        
        # Önce pythonnet/.NET bridge'i test et
        try:
            import clr
            from System import Environment
            logger.info(f"pythonnet/.NET bridge OK (machine: {Environment.MachineName})")
        except Exception as e:
            import traceback
            logger.error(f"pythonnet/.NET bridge FAILED: {e}\n{traceback.format_exc()}")
        
        import webview
        logger.info(f"webview import OK")
        
        try:
            import webview.platforms.edgechromium  # noqa: F401
            logger.info("edgechromium pre-loaded OK")
        except Exception as e:
            import traceback
            logger.warning(f"edgechromium pre-load warning: {e}\n{traceback.format_exc()}")
        
        return webview
    except Exception as e:
        import traceback
        logger.error(f"webview import failed: {e}\n{traceback.format_exc()}")
        return None


def find_free_port(start=5056, end=5070):
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start


def wait_for_server(port, timeout=60):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(('127.0.0.1', port))
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.4)
    return False


def start_flask_server(port):
    """Flask + SocketIO sunucusunu arka planda başlat"""
    try:
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)

        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(BASE_DIR, '.env'))
        except ImportError:
            pass

        import importlib.util
        main_py_path = os.path.join(BASE_DIR, 'main.py')
        if not os.path.exists(main_py_path):
            meipass = getattr(sys, '_MEIPASS', BASE_DIR)
            main_py_path = os.path.join(meipass, 'main.py')

        logger.info(f"Loading main.py from: {main_py_path}")

        spec = importlib.util.spec_from_file_location("main", main_py_path)
        main_module = importlib.util.module_from_spec(spec)
        sys.modules['main'] = main_module
        spec.loader.exec_module(main_module)

        app = main_module.app
        socketio = main_module.socketio

        try:
            from AppCore.lib.system_init import initialize_system
            initialize_system()
            logger.info("System initialized")
        except Exception as e:
            logger.warning(f"System init warning: {e}")

        def _start_telegram():
            try:
                time.sleep(5)
                from AppCore.modules.telegram_bot_v2 import TelegramBotV2
                TelegramBotV2().start()
                logger.info("Telegram Bot started")
            except Exception as e:
                logger.warning(f"Telegram Bot skipped: {e}")

        threading.Thread(target=_start_telegram, daemon=True).start()

        try:
            broadcast_job_status = getattr(main_module, 'broadcast_job_status', None)
            if broadcast_job_status:
                threading.Thread(target=broadcast_job_status, daemon=True).start()
        except Exception:
            pass

        logger.info(f"Flask starting on port {port}")
        socketio.run(
            app,
            host='127.0.0.1',
            port=port,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    except Exception as e:
        logger.error(f"Flask error: {e}", exc_info=True)


def main():
    logger.info("=" * 50)
    logger.info("STAINLESS MAX - Starting...")
    logger.info("=" * 50)

    port = find_free_port()
    url = f'http://127.0.0.1:{port}'
    logger.info(f"App URL: {url}")

    # ================================================
    # ADIM 1: Flask sunucusunu arka planda başlat
    # ================================================
    flask_thread = threading.Thread(
        target=start_flask_server,
        args=(port,),
        daemon=True
    )
    flask_thread.start()

    logger.info("Waiting for Flask server...")
    if not wait_for_server(port, timeout=60):
        logger.error("Flask server could not start in 60 seconds!")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "Stainless Max başlatılamadı!\n\nDetaylar için stainless_max.log dosyasına bakın.",
                "Stainless Max - Hata",
                0x10
            )
        except Exception:
            pass
        sys.exit(1)

    logger.info("Server ready!")

    # ================================================
    # ADIM 2: UI Aç — Cross-Platform (Mac/Win) Native Window
    # ================================================
    ui_opened = False

    if sys.platform == 'darwin':
        # MacOS her zaman native WebKit (Safari) engine destekler.
        logger.info("macOS detected — directly launching PyWebView (WebKit)...")
        ui_opened = _try_pywebview(url)
    else:
        # --- Yöntem A: Windows'ta WebView2 kuruluysa PyWebView ---
        if _is_webview2_installed():
            logger.info("WebView2 found — trying PyWebView...")
            ui_opened = _try_pywebview(url)

        # --- WebView2 yoksa otomatik kur ve tekrar dene ---
        if not ui_opened and not _is_webview2_installed():
            logger.warning("WebView2 NOT installed — trying auto-install...")
            if _install_webview2_silent():
                logger.info("WebView2 installed! Trying PyWebView...")
                ui_opened = _try_pywebview(url)

    # --- Windows'ta Yöntem B (Mac için de fallback): Chrome / Edge App Mode ---
    if not ui_opened:
        logger.info("Falling back to Chrome/Edge App Mode...")
        _open_browser_app_mode(url)


def _try_pywebview(url):
    """PyWebView ile native pencere açmayı dene. Başarılıysa True döner."""
    try:
        webview = _preload_webview()
        if webview is None:
            return False

        cache_dir = os.path.join(BASE_DIR, 'AppCore', 'temp', 'webview_cache')
        os.makedirs(cache_dir, exist_ok=True)

        window = webview.create_window(
            title='Stainless Max',
            url=url,
            width=1440,
            height=900,
            min_size=(1024, 600),
            resizable=True,
            frameless=False,
            easy_drag=False,
        )

        # Arka plan thread'i ile pencere ikonunu ayarla
        def _icon_setter_thread():
            """Pencere açıldıktan sonra ikonu set eden arka plan thread'i"""
            if not ICON_PATH:
                logger.warning("Icon file not found, skipping icon set")
                return
            
            try:
                import ctypes
                import ctypes.wintypes
                
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                
                # İkonu yükle
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x0010
                LR_DEFAULTSIZE = 0x0040
                
                # Büyük ikon (32x32) ve küçük ikon (16x16) ayrı yükle
                hicon_big = user32.LoadImageW(
                    None, ICON_PATH, IMAGE_ICON, 32, 32, LR_LOADFROMFILE
                )
                hicon_small = user32.LoadImageW(
                    None, ICON_PATH, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
                )
                
                if not hicon_big:
                    logger.warning(f"Failed to load icon from {ICON_PATH}")
                    return
                
                logger.info(f"Icon loaded: big={hicon_big}, small={hicon_small}")
                
                WM_SETICON = 0x0080
                ICON_BIG = 1
                ICON_SMALL = 0
                
                pid = os.getpid()
                
                # EnumWindows callback — bu process'e ait pencereleri bul
                WNDENUMPROC = ctypes.WINFUNCTYPE(
                    ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
                )
                
                found_hwnds = []
                
                @WNDENUMPROC
                def enum_callback(hwnd, lparam):
                    if user32.IsWindowVisible(hwnd):
                        window_pid = ctypes.wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                        if window_pid.value == pid:
                            # Pencere başlığını kontrol et
                            length = user32.GetWindowTextLengthW(hwnd)
                            if length > 0:
                                buf = ctypes.create_unicode_buffer(length + 1)
                                user32.GetWindowTextW(hwnd, buf, length + 1)
                                title = buf.value
                                if 'Stainless' in title or 'stainless' in title:
                                    found_hwnds.append(hwnd)
                                    logger.info(f"Found window: hwnd={hwnd}, title='{title}'")
                    return True
                
                # 30 saniye boyunca pencereyi ara (500ms aralıklarla)
                for attempt in range(60):
                    time.sleep(0.5)
                    found_hwnds.clear()
                    user32.EnumWindows(enum_callback, 0)
                    
                    if found_hwnds:
                        for hwnd in found_hwnds:
                            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small or hicon_big)
                            logger.info(f"✅ Window icon set successfully (hwnd={hwnd}, attempt={attempt})")
                        return
                    
                    if attempt % 10 == 0:
                        logger.info(f"Searching for window... (attempt {attempt})")
                
                logger.warning("Window not found after 30s timeout")
                
            except Exception as e:
                logger.warning(f"Icon setter thread error: {e}")
                import traceback
                logger.warning(traceback.format_exc())

        # Thread'i başlat (daemon = uygulama kapanınca otomatik sonlanır)
        icon_thread = threading.Thread(target=_icon_setter_thread, daemon=True)
        icon_thread.start()

        webview.start(debug=False, private_mode=False)
        logger.info("PyWebView window closed")
        return True
    except Exception as e:
        logger.warning(f"PyWebView failed: {e}")
        return False


def _open_browser_app_mode(url):
    """Chrome veya Edge'i App Mode'da aç — native pencere gibi görünür."""
    import subprocess

    browser_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    browser_exe = None
    for p in browser_paths:
        if os.path.exists(p):
            browser_exe = p
            break

    if browser_exe:
        logger.info(f"Launching: {browser_exe} --app={url}")
        try:
            proc = subprocess.Popen([
                browser_exe,
                f"--app={url}",
                "--window-size=1440,900",
                "--disable-features=TranslateUI",
                "--no-first-run",
                "--no-default-browser-check",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            logger.info("Browser closed - app exiting")
        except Exception as e:
            logger.error(f"Browser launch failed: {e}")
            _open_default_browser(url)
    else:
        _open_default_browser(url)


def _open_default_browser(url):
    """Son çare: varsayılan tarayıcıda aç."""
    import webbrowser
    webbrowser.open(url)
    logger.info("Opened in default browser.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

