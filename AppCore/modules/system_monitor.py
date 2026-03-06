"""
System Monitor - Gemini Pro ile Sürekli Denetim
Hata tespiti ve otomatik çözüm önerileri
"""

import os
import sys
import json
import time
import psutil
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from google import genai


class SystemMonitor:
    """Gemini Pro ile sistem denetimi"""
    
    def __init__(self, check_interval: int = 300):  # 5 dakika
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.check_interval = check_interval
        self.running = False
        self.monitor_thread = None
        self.health_history = []
        self.issues_found = []
        
        # Gemma AI setup (new SDK - hafif görev)
        self.model_name = "gemma-3-27b-it"
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
        
        # İzlenecek metrikler
        self.metrics = {
            'cpu_usage': 0,
            'memory_usage': 0,
            'disk_usage': 0,
            'network_status': True,
            'chrome_running': False,
            'last_check': None
        }
    
    def start_monitoring(self):
        """Sürekli denetimi başlat"""
        if self.running:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("[Monitor] Sistem denetimi başlatıldı")
    
    def stop_monitoring(self):
        """Denetimi durdur"""
        self.running = False
    
    def _monitor_loop(self):
        """Ana denetim döngüsü"""
        while self.running:
            try:
                self._collect_metrics()
                self._analyze_with_ai()
                time.sleep(self.check_interval)
            except Exception as e:
                print(f"[Monitor] Hata: {e}")
                time.sleep(60)
    
    def _collect_metrics(self):
        """Sistem metriklerini topla"""
        # CPU kullanımı
        self.metrics['cpu_usage'] = psutil.cpu_percent(interval=1)
        
        # RAM kullanımı
        memory = psutil.virtual_memory()
        self.metrics['memory_usage'] = memory.percent
        
        # Disk kullanımı
        disk = psutil.disk_usage('/')
        self.metrics['disk_usage'] = (disk.used / disk.total) * 100
        
        # Chrome çalışıyor mu
        self.metrics['chrome_running'] = self._is_chrome_running()
        
        self.metrics['last_check'] = datetime.now().isoformat()
        
        # Geçmişe ekle
        self.health_history.append({
            'timestamp': self.metrics['last_check'],
            'metrics': self.metrics.copy()
        })
        
        # Son 100 kaydı tut
        if len(self.health_history) > 100:
            self.health_history = self.health_history[-100:]
    
    def _is_chrome_running(self) -> bool:
        """Chrome çalışıyor mu kontrol et"""
        for proc in psutil.process_iter(['name']):
            try:
                if 'chrome' in proc.info['name'].lower():
                    return True
            except Exception:
                pass
        return False
    
    def _analyze_with_ai(self):
        """Gemini Pro ile analiz"""
        if not self.client:
            return
        
        try:
            # Sorunları tespit et
            issues = self._detect_issues()
            
            if issues:
                # Gemini'ye sor
                prompt = f"""
Sistem sağlığı analizi yap ve çözüm öner:

METRIKLER:
- CPU: %{self.metrics['cpu_usage']}
- RAM: %{self.metrics['memory_usage']}
- Disk: %{self.metrics['disk_usage']:.1f}
- Chrome: {'Çalışıyor' if self.metrics['chrome_running'] else 'Kapalı'}

TESPIT EDILEN SORUNLAR:
{chr(10).join(issues)}

Lütfen:
1. Her sorun için kısa analiz (1 cümle)
2. Hemen uygulanabilir çözüm önerisi
3. Önem derecesi (Düşük/Orta/Yüksek)

Format: JSON olarak döndür.
"""
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                analysis = response.text
                
                # Sorunları kaydet
                self.issues_found.append({
                    'timestamp': datetime.now().isoformat(),
                    'issues': issues,
                    'analysis': analysis
                })
                
                print(f"[Monitor] AI Analizi: {analysis[:200]}...")
                
        except Exception as e:
            print(f"[Monitor] AI analiz hatası: {e}")
    
    def _detect_issues(self) -> List[str]:
        """Sistem sorunlarını tespit et"""
        issues = []
        
        if self.metrics['cpu_usage'] > 80:
            issues.append(f"Yüksek CPU kullanımı: %{self.metrics['cpu_usage']}")
        
        if self.metrics['memory_usage'] > 85:
            issues.append(f"Yüksek RAM kullanımı: %{self.metrics['memory_usage']}")
        
        if self.metrics['disk_usage'] > 90:
            issues.append(f"Dolmak üzere olan disk: %{self.metrics['disk_usage']:.1f}")
        
        return issues
    
    def get_health_status(self) -> Dict:
        """Sağlık durumunu getir"""
        return {
            'status': 'healthy' if not self._detect_issues() else 'warning',
            'metrics': self.metrics,
            'issues': self.issues_found[-5:] if self.issues_found else [],
            'uptime': len(self.health_history) * self.check_interval / 3600  # saat
        }
    
    def get_recommendations(self) -> List[str]:
        """Gemini'den öneriler al"""
        if not self.client:
            return ["Gemini API aktif değil"]
        
        try:
            prompt = """
Video üretim sistemi için performans optimizasyonu önerileri:
1. CPU/RAM kullanımını azaltma
2. Disk temizliği
3. Chrome profil optimizasyonu

3 maddelik kısa liste ver.
"""
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text.split('\n')[:3]
        except Exception:
            return ["Öneriler alınamadı"]


# Global instance
system_monitor = SystemMonitor()
