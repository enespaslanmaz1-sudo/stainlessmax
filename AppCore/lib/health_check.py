import os
import sys
import socket
import logging
import importlib
import requests
from pathlib import Path
from datetime import datetime

# Configure logger
logger = logging.getLogger(__name__)

class SystemDoctor:
    def __init__(self):
        self.results = {
            "network": {},
            "api_keys": {},
            "storage": {},
            "dependencies": {},
            "accounts": {},
            "system": {}
        }

    def check_network(self):
        """Check internet connectivity"""
        try:
            # Check Google DNS
            requests.get("https://8.8.8.8", timeout=2)
            self.results["network"]["internet"] = {"status": "ok", "message": "Internet bağlantısı aktif"}
        except:
            try:
                # Fallback to Google.com
                requests.get("https://www.google.com", timeout=2)
                self.results["network"]["internet"] = {"status": "ok", "message": "Internet bağlantısı aktif"}
            except Exception as e:
                self.results["network"]["internet"] = {"status": "error", "message": f"Bağlantı hatası: {str(e)}"}

        # Check Local Port (legacy 5056 + current defaults)
        ports_to_check = [5056, 5000]
        active_port = None

        for port in ports_to_check:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = s.connect_ex(('127.0.0.1', port))
            s.close()
            if result == 0:
                active_port = port
                break

        self.results["network"]["local_server"] = {
            "status": "ok" if active_port else "warning",
            "message": f"Port {active_port} aktif" if active_port else "Yerel sunucu portları (5056/5000) erişilemiyor"
        }

    def check_api_keys(self):
        """Verify API Keys in Environment"""
        keys = [
            ("GEMINI_API_KEY", "Gemini AI"),
            ("PEXELS_API_KEY", "Pexels"),
            ("FLASK_SECRET_KEY", "Flask Secret")
        ]
        
        for env_var, label in keys:
            val = os.getenv(env_var)
            if val and len(val) > 5:
                self.results["api_keys"][label] = {"status": "ok", "message": "Tanımlı"}
            else:
                self.results["api_keys"][label] = {"status": "error", "message": "Tanımlı Değil veya Hatalı"}

    def check_storage(self):
        """Check critical directories"""
        base_dir = Path(os.getcwd())
        if "System" not in str(base_dir):
            if (base_dir / "System").exists():
                base_dir = base_dir / "System"
                
        paths = {
            "Outputs": base_dir / "outputs",
            "Temp": base_dir / "temp",
            "Lib": base_dir / "lib"
        }

        for label, path in paths.items():
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    self.results["storage"][label] = {"status": "warning", "message": "Klasör yoktu, oluşturuldu"}
                except Exception as e:
                    self.results["storage"][label] = {"status": "error", "message": f"Oluşturulamadı: {e}"}
            else:
                # Check write permission
                if os.access(path, os.W_OK):
                    self.results["storage"][label] = {"status": "ok", "message": "Erişilebilir"}
                else:
                    self.results["storage"][label] = {"status": "error", "message": "Yazma izni yok"}

    def check_dependencies(self):
        """Check critical python packages and tools"""
        packages = ["flask", "moviepy", "cv2", "PIL", "google.generativeai"]
        for pkg in packages:
            try:
                importlib.import_module(pkg)
                self.results["dependencies"][pkg] = {"status": "ok", "message": "Yüklü"}
            except ImportError:
                self.results["dependencies"][pkg] = {"status": "error", "message": "Yüklü Değil!"}

        # Check FFmpeg
        from moviepy.config import get_setting
        try:
            ffmpeg_path = get_setting("FFMPEG_BINARY")
            if ffmpeg_path and os.path.exists(ffmpeg_path):
                 self.results["dependencies"]["ffmpeg"] = {"status": "ok", "message": "Bulundu"}
            else:
                 # Try shutil
                 import shutil
                 if shutil.which("ffmpeg"):
                     self.results["dependencies"]["ffmpeg"] = {"status": "ok", "message": "PATH üzerinde bulundu"}
                 else:
                     self.results["dependencies"]["ffmpeg"] = {"status": "error", "message": "FFmpeg bulunamadı!"}
        except Exception as e:
             self.results["dependencies"]["ffmpeg"] = {"status": "warning", "message": f"Kontrol hatası: {e}"}

    def check_accounts(self):
        """Get account summary"""
        try:
            # Need to append path if not already done in main
            sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
            from modules.account_manager import AccountManager
            mgr = AccountManager()
            
            yt_count = len(mgr.get_active_accounts("youtube"))
            tt_count = len(mgr.get_active_accounts("tiktok"))
            
            self.results["accounts"]["YouTube"] = {"status": "ok" if yt_count > 0 else "warning", "message": f"{yt_count} hesap aktif"}
            self.results["accounts"]["TikTok"] = {"status": "ok" if tt_count > 0 else "warning", "message": f"{tt_count} hesap aktif"}
            
        except ImportError:
             self.results["accounts"]["Manager"] = {"status": "error", "message": "Modül yüklenemedi"}
        except Exception as e:
             self.results["accounts"]["Status"] = {"status": "error", "message": f"Hata: {e}"}

    def run_all_checks(self):
        """Run all checks sequence"""
        self.check_network()
        self.check_api_keys()
        self.check_storage()
        self.check_dependencies()
        self.check_accounts()
        
        # Add timestamp
        self.results["system"]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.results["system"]["platform"] = sys.platform
        
        return self.results

    def analyze_with_ai(self, api_key):
        """Send results to Gemini for analysis"""
        if not api_key:
            return "Gemini API anahtarı eksik, analiz yapılamıyor."
            
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=api_key)
            
            # Try newer model first, fallback to stable
            model_name = 'gemini-2.5-flash'
            
            # Context construction
            prompt = f"""
            Sen Jarvis adında bir yapay zeka asistanısın. Aşağıdaki sistem sonuçlarını analiz et.
            Kullanıcıya sistemin sağlığı hakkında kısa ve öz bilgi ver.
            Sorun varsa (disk doluluğu, internet, servis hataları) uyar.
            
            Sistem Verileri:
            {str(self.results)}
            
            Raporu Türkçe, profesyonel ama samimi bir dille yaz. Emoji kullan.
            """
            
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                return response.text
            except Exception:
                # Fallback
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content(prompt)
                return response.text
        except Exception as e:
            logger.error(f"AI Analysis failed: {e}")
            return f"Yapay zeka analizi sırasında hata oluştu: {str(e)}"
