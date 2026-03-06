"""
Notification Manager - Windows Bildirimleri
"""

import platform
from pathlib import Path
from typing import Optional
from datetime import datetime


class NotificationManager:
    """Windows bildirim yöneticisi"""
    
    def __init__(self, app_name: str = "Video PRO AI"):
        self.app_name = app_name
        self.enabled = True
        self.notification_history = []
        
        # Windows kontrolü
        if platform.system() == "Windows":
            try:
                from win10toast import ToastNotifier
                self.toaster = ToastNotifier()
                self.available = True
            except ImportError:
                self.toaster = None
                self.available = False
        else:
            self.toaster = None
            self.available = False
    
    def notify(self, title: str, message: str, duration: int = 5, 
               icon_path: Optional[str] = None, callback=None):
        """Bildirim göster"""
        if not self.enabled:
            return
        
        # Geçmişe ekle
        self.notification_history.append({
            'time': datetime.now().isoformat(),
            'title': title,
            'message': message
        })
        
        # Windows bildirimi
        if self.available and self.toaster:
            try:
                self.toaster.show_toast(
                    title=title,
                    msg=message,
                    icon_path=icon_path,
                    duration=duration,
                    threaded=True,
                    callback_on_click=callback
                )
            except Exception as e:
                print(f"[Notification] Hata: {e}")
        else:
            # Fallback: konsola yaz
            print(f"[BİLDİRİM] {title}: {message}")
    
    def notify_video_complete(self, title: str, account_id: str):
        """Video tamamlandı bildirimi"""
        self.notify(
            "✅ Video Hazır",
            f"'{title}' videosu hazır. Onayınız bekleniyor.",
            duration=10
        )
    
    def notify_upload_success(self, title: str, platform: str):
        """Yükleme başarılı bildirimi"""
        platform_emoji = "📺" if platform == "youtube" else "🎵"
        self.notify(
            f"{platform_emoji} Paylaşım Başarılı",
            f"'{title}' {platform}'da paylaşıldı.",
            duration=5
        )
    
    def notify_upload_failed(self, title: str, error: str):
        """Yükleme hatası bildirimi"""
        self.notify(
            "❌ Paylaşım Başarısız",
            f"'{title}' - {error[:50]}...",
            duration=10
        )
    
    def notify_ip_changed(self, old_ip: str, new_ip: str):
        """IP değişti bildirimi"""
        self.notify(
            "🌐 IP Değiştirildi",
            f"Eski: {old_ip}\nYeni: {new_ip}",
            duration=5
        )
    
    def notify_schedule_reminder(self, task_name: str, minutes: int):
        """Zamanlayıcı hatırlatma"""
        self.notify(
            "⏰ Zamanlayıcı",
            f"'{task_name}' görevi {minutes} dakika sonra çalışacak.",
            duration=5
        )
    
    def notify_error(self, error_message: str, component: str = "Sistem"):
        """Hata bildirimi"""
        self.notify(
            f"⚠️ Hata - {component}",
            error_message[:100],
            duration=10
        )
    
    def toggle(self) -> bool:
        """Bildirimleri aç/kapat"""
        self.enabled = not self.enabled
        return self.enabled
    
    def get_history(self, limit: int = 50) -> list:
        """Bildirim geçmişini getir"""
        return self.notification_history[-limit:]


# Global instance
notification_manager = NotificationManager()
