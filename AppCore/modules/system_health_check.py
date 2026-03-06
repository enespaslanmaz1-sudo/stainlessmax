import platform
import psutil
import socket
import os
import requests
from datetime import datetime

class SystemHealthCheck:
    def __init__(self):
        pass

    def check_network(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return {"status": "ok", "message": "İnternet bağlantısı aktif."}
        except OSError:
            return {"status": "error", "message": "İnternet bağlantısı yok!"}

    def check_dependencies(self):
        """Check for FFmpeg and Chrome dependencies"""
        results = {}
        
        # FFmpeg
        try:
            import sys
            _no_win = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5, creationflags=_no_win)
            if res.returncode == 0:
                ver = res.stdout.split('\n')[0]
                results["ffmpeg"] = {"status": "ok", "message": f"FFmpeg hazır: {ver[:40]}"}
            else:
                results["ffmpeg"] = {"status": "error", "message": "FFmpeg yüklü değil veya hata veriyor!"}
        except Exception as e:
            results["ffmpeg"] = {"status": "error", "message": f"FFmpeg bulunamadı: {e}"}

        # Chrome / Driver (Simple existence check)
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
        exists = any(os.path.exists(p) for p in chrome_paths)
        results["chrome"] = {
            "status": "ok" if exists else "warning",
            "message": "Chrome tarayıcı bulundu." if exists else "Chrome standart dizinde bulunamadı (Farklı dizinde olabilir)."
        }
        
        return results

    def check_disk_space(self, path="."):
        try:
            usage = psutil.disk_usage(os.path.abspath(path))
            free_gb = usage.free / (1024**3)
            percent = usage.percent
            status = "ok"
            if free_gb < 10: status = "warning"
            if free_gb < 2: status = "error"
            
            return {
                "status": status, 
                "message": f"Boş Alan: {free_gb:.1f} GB ({percent}% dolu)",
                "details": {"free_gb": free_gb, "percent": percent}
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def check_api_keys(self):
        """Check availability and validity of API keys"""
        from AppCore.lib.config_manager import get_config_manager
        cm = get_config_manager()
        keys = cm.api_keys
        
        results = {}
        # Gemini
        if keys.gemini:
            results["gemini"] = {"status": "ok", "message": "Gemini Anahtarı tanımlı."}
        else:
            results["gemini"] = {"status": "error", "message": "Gemini API Anahtarı eksik!"}
            
        # Others
        results["pexels"] = {"status": "ok" if keys.pexels else "warning", "message": "Pexels anahtarı mevcut." if keys.pexels else "Pexels anahtarı eksik (Stok videolar çalışmayabilir)."}
        results["telegram"] = {"status": "ok" if keys.telegram_token else "error", "message": "Telegram Token hazır." if keys.telegram_token else "Telegram Token eksik!"}
        
        return results
        
    def check_storage_folders(self):
        """Check if required folders exist"""
        folders = ["System_Data/outputs", "profiles", "config", "logs"]
        results = {}
        for folder in folders:
            path = os.path.abspath(folder)
            exists = os.path.exists(path)
            results[folder] = {
                "status": "ok" if exists else "warning",
                "message": f"{folder} dizini mevcut." if exists else f"{folder} dizini yok, otomatik oluşturulacak."
            }
        return results

    def check_video_production(self):
        """Check video production capabilities"""
        results = {}
        
        # 1. FFmpeg Check (Reuse check_dependencies logic)
        ffmpeg_res = self.check_dependencies().get("ffmpeg", {})
        results["ffmpeg"] = ffmpeg_res
        
        # 2. Assets Check
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_dir = os.path.join(base_dir, "assets")
        
        if os.path.exists(assets_dir):
             results["assets"] = {"status": "ok", "message": "Assets klasörü mevcut."}
        else:
             results["assets"] = {"status": "error", "message": "Assets klasörü bulunamadı (Video üretimi için gerekli)!"}
             
        # 3. Output Write Permission
        output_dir = os.path.join(base_dir, "outputs")
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            test_file = os.path.join(output_dir, "write_test.tmp")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            results["write_permission"] = {"status": "ok", "message": "Outputs dizinine yazılabilir."}
        except Exception as e:
            results["write_permission"] = {"status": "error", "message": f"Outputs dizinine yazma hatası: {e}"}
            
        return results

    def run_check(self):
        storage_info = self.check_storage_folders()
        disk_info = self.check_disk_space()
        # Merge disk info into storage for frontend display
        storage_info["Disk Alanı"] = disk_info
        
        return {
            "network": {"Internet": self.check_network()},
            "dependencies": self.check_dependencies(),
            "api_keys": self.check_api_keys(),
            "storage": storage_info,
            "video_production": self.check_video_production(),
            "system": {
                "os": platform.system(),
                "release": platform.release(),
                "cpu_usage": psutil.cpu_percent(),
                "memory_usage": psutil.virtual_memory().percent
            }
        }

    def generate_ai_report(self, system_status, api_key=None):
        if not api_key:
             return "API Anahtarı eksik, rapor oluşturulamadı."
             
        try:
            # Prepare context for AI (Deep Scan)
            disk_msg = system_status['storage'].get("Disk Alanı", {}).get("message", "Bilinmiyor")
            net_msg = system_status['network'].get("Internet", {}).get("message", "Bilinmiyor")
            
            deps_summary = "\n".join([f"- {k.upper()}: {v['message']}" for k, v in system_status['dependencies'].items()])
            api_summary = "\n".join([f"- {k.capitalize()}: {v['message']}" for k, v in system_status['api_keys'].items()])
            
            context = f"""
            DETAYLI SİSTEM ANALİZİ:
            - İşletim Sistemi: {system_status['system']['os']} {system_status['system']['release']}
            - CPU: %{system_status['system']['cpu_usage']} | Bellek: %{system_status['system']['memory_usage']}
            - Disk Durumu: {disk_msg}
            - Ağ Durumu: {net_msg}
            
            BAĞIMLILIKLAR:
            {deps_summary}
            
            API DURUMU:
            {api_summary}
            """
            
            prompt = f"""
            Sen Jarvis adında bir yapay zeka asistanısın. Aşağıdaki derin sistem taraması raporunu analiz et ve kullanıcıya samimi, profesyonel bir özet sun.
            Sistemin üretime hazır olup olmadığını belirt. Eğer FFmpeg veya API anahtarlarında sorun varsa kritik uyarı ver.
            
            {context}
            
            Raporu Türkçe olarak, maddeler halinde ve emoji kullanarak yaz.
            """
            
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            response = model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            return f"Yapay zeka raporu oluşturulurken hata: {e}"
