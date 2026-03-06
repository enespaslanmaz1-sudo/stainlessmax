"""
Video PRO AI - Telegram Bot Controller
Tam entegre Telegram bot yönetimi
"""
import os
import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
    TELEBOT_AVAILABLE = True
except ImportError:
    TELEBOT_AVAILABLE = False

try:
    from lib.config_manager import get_config_manager
    from lib.logger import logger
    from lib.error_handler import handle_error
    from lib.automation_engine import get_automation_engine
    from lib.monitoring import get_system_monitor
except ImportError:
    get_config_manager = None
    logger = None
    handle_error = None
    get_automation_engine = None
    get_system_monitor = None


class TelegramBotController:
    """
    Video PRO AI için tam entegre Telegram bot kontrolcüsü
    Admin yetkilendirmeli, komut bazlı yönetim sistemi
    """
    
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path(__file__).parent.parent
        self.bot = None
        self.token = None
        self.admin_id = None
        self.running = False
        self.thread = None
        
        # Bot komutları ve açıklamaları
        self.commands = {
            'start': 'Botu başlat ve ana menüyü göster',
            'help': 'Tüm komutları ve kullanımlarını listele',
            'status': 'Sistem durumunu ve istatistikleri göster',
            'generate': 'Yeni video üret (kullanım: /generate youtube|tiktok)',
            'upload': 'Video yükle (kullanım: /upload videoadı)',
            'automation': 'Otomasyon kontrolü (kullanım: /automation start|stop|status)',
            'videos': 'Son üretilen videoları listele',
            'health': 'Sistem sağlık durumunu kontrol et',
            'settings': 'Mevcut ayarları göster',
            'stop': 'Video üretimini durdur'
        }
        
        self._load_config()
        self._init_bot()
    
    def _load_config(self):
        """Yapılandırmayı yükle"""
        if get_config_manager:
            try:
                config = get_config_manager()
                self.token = config.get_api_key("telegram_token")
                admin_id = config.get_api_key("telegram_admin")
                self.admin_id = int(admin_id) if admin_id and admin_id.isdigit() else None
            except Exception as e:
                if logger:
                    logger.error(f"Telegram config yüklenemedi: {e}")
        
        # Direkt .env'den de kontrol et
        if not self.token:
            self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not self.admin_id:
            admin = os.getenv("TELEGRAM_ADMIN_ID", "")
            if admin and admin.isdigit():
                self.admin_id = int(admin)
    
    def _init_bot(self):
        """Bot'u başlat"""
        if not TELEBOT_AVAILABLE:
            if logger:
                logger.error("TeleBot kütüphanesi yüklü değil!")
            return
        
        if not self.token:
            if logger:
                logger.error("Telegram bot tokeni bulunamadı!")
            return
        
        try:
            self.bot = telebot.TeleBot(self.token)
            self._setup_handlers()
            if logger:
                logger.info("Telegram bot başlatıldı")
        except Exception as e:
            if handle_error:
                handle_error(e, {"context": "telegram_bot_init"})
            if logger:
                logger.error(f"Telegram bot başlatma hatası: {e}")
    
    def _setup_handlers(self):
        """Komut handler'larını ayarla"""
        if not self.bot:
            return
        
        # /start komutu
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            if not self._check_admin(message):
                return
            
            welcome_text = f"""
🎬 <b>Video PRO AI - Telegram Kontrol</b>

Hoş geldiniz! Bu bot ile video üretim sisteminizi uzaktan yönetebilirsiniz.

📊 <b>Sistem Durumu:</b> {'Aktif' if self.running else 'Beklemede'}
🤖 <b>Otomasyon:</b> {'Çalışıyor' if self._is_automation_running() else 'Durduruldu'}

Kullanılabilir komutları görmek için /help yazın.
"""
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode='HTML',
                reply_markup=self._get_main_menu()
            )
        
        # /help komutu
        @self.bot.message_handler(commands=['help'])
        def handle_help(message):
            if not self._check_admin(message):
                return
            
            help_text = "📚 <b>Kullanılabilir Komutlar:</b>\n\n"
            for cmd, desc in self.commands.items():
                help_text += f"<code>/{cmd}</code> - {desc}\n"
            
            help_text += "\n💡 <b>Hızlı İpuçları:</b>\n"
            help_text += "• Video üretmek için: /generate youtube\n"
            help_text += "• Otomasyon başlatmak için: /automation start\n"
            help_text += "• Sistem durumu için: /status\n"
            
            self.bot.send_message(message.chat.id, help_text, parse_mode='HTML')
        
        # /status komutu
        @self.bot.message_handler(commands=['status'])
        def handle_status(message):
            if not self._check_admin(message):
                return
            
            status = self._get_system_status()
            self.bot.send_message(
                message.chat.id, 
                status, 
                parse_mode='HTML',
                reply_markup=self._get_control_menu()
            )
        
        # /generate komutu
        @self.bot.message_handler(commands=['generate'])
        def handle_generate(message):
            if not self._check_admin(message):
                return
            
            args = message.text.split()
            platform = args[1] if len(args) > 1 else 'youtube'
            
            if platform not in ['youtube', 'tiktok']:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Geçersiz platform. Kullanım: /generate youtube veya /generate tiktok"
                )
                return
            
            self.bot.send_message(
                message.chat.id,
                f"🎬 <b>{platform.upper()}</b> için video üretimi başlatılıyor...",
                parse_mode='HTML'
            )
            
            try:
                if get_automation_engine:
                    engine = get_automation_engine()
                    engine.force_generate(platform)
                    self.bot.send_message(
                        message.chat.id,
                        f"✅ {platform.upper()} videosu üretilmeye başlandı!\nHazır olduğunda bildirilecek.",
                        parse_mode='HTML'
                    )
                else:
                    self.bot.send_message(
                        message.chat.id,
                        "⚠️ Otomasyon motoru hazır değil"
                    )
            except Exception as e:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ Hata: {str(e)}"
                )
        
        # /automation komutu
        @self.bot.message_handler(commands=['automation'])
        def handle_automation(message):
            if not self._check_admin(message):
                return
            
            args = message.text.split()
            action = args[1] if len(args) > 1 else 'status'
            
            if action == 'start':
                try:
                    if get_automation_engine:
                        from lib.automation_engine import start_automation
                        start_automation()
                        self.bot.send_message(
                            message.chat.id,
                            "🚀 <b>Otomasyon başlatıldı!</b>\n\n"
                            "Günlük 12 video (6 YouTube + 6 TikTok) otomatik üretilecek.",
                            parse_mode='HTML'
                        )
                except Exception as e:
                    self.bot.send_message(message.chat.id, f"❌ Hata: {str(e)}")
                    
            elif action == 'stop':
                try:
                    if get_automation_engine:
                        from lib.automation_engine import stop_automation
                        stop_automation()
                        self.bot.send_message(
                            message.chat.id,
                            "⏹ <b>Otomasyon durduruldu!</b>",
                            parse_mode='HTML'
                        )
                except Exception as e:
                    self.bot.send_message(message.chat.id, f"❌ Hata: {str(e)}")
                    
            else:  # status
                status = self._get_automation_status()
                self.bot.send_message(message.chat.id, status, parse_mode='HTML')
        
        # /videos komutu
        @self.bot.message_handler(commands=['videos'])
        def handle_videos(message):
            if not self._check_admin(message):
                return
            
            try:
                import sys, os
                if sys.platform == 'darwin':
                    outputs_dir = Path(os.path.expanduser('~/Movies/StainlessMax'))
                else:
                    outputs_dir = self.base_dir / "outputs"
                
                if not outputs_dir.exists():
                    self.bot.send_message(message.chat.id, "📂 Henüz video bulunmuyor")
                    return
                
                videos = sorted(
                    outputs_dir.glob("*.mp4"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )[:10]  # Son 10 video
                
                if not videos:
                    self.bot.send_message(message.chat.id, "📂 Henüz video bulunmuyor")
                    return
                
                text = "🎬 <b>Son Videolar:</b>\n\n"
                for i, video in enumerate(videos, 1):
                    size_mb = video.stat().st_size / (1024 * 1024)
                    mtime = datetime.fromtimestamp(video.stat().st_mtime)
                    text += f"{i}. <code>{video.name}</code>\n"
                    text += f"   📦 {size_mb:.1f} MB | 📅 {mtime.strftime('%d.%m.%Y %H:%M')}\n\n"
                
                self.bot.send_message(message.chat.id, text, parse_mode='HTML')
                
            except Exception as e:
                self.bot.send_message(message.chat.id, f"❌ Hata: {str(e)}")
        
        # /health komutu
        @self.bot.message_handler(commands=['health'])
        def handle_health(message):
            if not self._check_admin(message):
                return
            
            try:
                if get_system_monitor:
                    monitor = get_system_monitor()
                    health = monitor.get_metrics()
                    
                    text = "🏥 <b>Sistem Sağlık Durumu:</b>\n\n"
                    
                    if 'current' in health:
                        curr = health['current']
                        text += f"💻 <b>CPU:</b> {curr.get('cpu_percent', 'N/A')}%\n"
                        text += f"🧠 <b>RAM:</b> {curr.get('memory_percent', 'N/A')}%\n"
                        text += f"💾 <b>Disk:</b> {curr.get('disk_usage_percent', 'N/A')}%\n"
                    
                    if 'health' in health:
                        status = health['health'].get('status', 'unknown')
                        emoji = {'healthy': '✅', 'warning': '⚠️', 'critical': '❌'}.get(status, 'ℹ️')
                        text += f"\n{emoji} <b>Genel Durum:</b> {status.upper()}\n"
                    
                    self.bot.send_message(message.chat.id, text, parse_mode='HTML')
                else:
                    self.bot.send_message(message.chat.id, "⚠️ İzleme sistemi aktif değil")
            except Exception as e:
                self.bot.send_message(message.chat.id, f"❌ Hata: {str(e)}")
        
        # /settings komutu
        @self.bot.message_handler(commands=['settings'])
        def handle_settings(message):
            if not self._check_admin(message):
                return
            
            try:
                if get_config_manager:
                    config = get_config_manager()
                    api_keys = config.api_keys.model_dump()
                    
                    text = "⚙️ <b>Mevcut Ayarlar:</b>\n\n"
                    text += f"🔑 <b>Pexels:</b> {'✅ Ayarlı' if api_keys.get('pexels') else '❌ Eksik'}\n"
                    text += f"🤖 <b>Gemini:</b> {'✅ Ayarlı' if api_keys.get('gemini') or api_keys.get('gemini_oauth_client_id') else '❌ Eksik'}\n"
                    text += f"📱 <b>Telegram:</b> {'✅ Ayarlı' if api_keys.get('telegram_token') else '❌ Eksik'}\n"
                    text += f"📊 <b>Apify:</b> {'✅ Ayarlı' if api_keys.get('apify') else '❌ Eksik'}\n"
                    
                    self.bot.send_message(message.chat.id, text, parse_mode='HTML')
                else:
                    self.bot.send_message(message.chat.id, "⚠️ Config manager erişilemiyor")
            except Exception as e:
                self.bot.send_message(message.chat.id, f"❌ Hata: {str(e)}")
        
        # /stop komutu
        @self.bot.message_handler(commands=['stop'])
        def handle_stop(message):
            if not self._check_admin(message):
                return
            
            self.bot.send_message(
                message.chat.id,
                "🛑 <b>Video üretimi durduruluyor...</b>",
                parse_mode='HTML'
            )
            # Burada aktif işlemler durdurulabilir
        
        # Inline button handler
        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback(call):
            if not self._check_admin_from_callback(call):
                return
            
            if call.data == 'status':
                status = self._get_system_status()
                self.bot.edit_message_text(
                    status,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='HTML',
                    reply_markup=self._get_control_menu()
                )
            elif call.data == 'generate_youtube':
                self.bot.send_message(call.message.chat.id, "Kullanın: /generate youtube")
            elif call.data == 'generate_tiktok':
                self.bot.send_message(call.message.chat.id, "Kullanın: /generate tiktok")
            elif call.data == 'automation_start':
                try:
                    if get_automation_engine:
                        from lib.automation_engine import start_automation
                        start_automation()
                        self.bot.send_message(call.message.chat.id, "✅ Otomasyon başlatıldı!")
                except Exception as e:
                    self.bot.send_message(call.message.chat.id, f"❌ Hata: {str(e)}")
            elif call.data == 'automation_stop':
                try:
                    if get_automation_engine:
                        from lib.automation_engine import stop_automation
                        stop_automation()
                        self.bot.send_message(call.message.chat.id, "⏹ Otomasyon durduruldu!")
                except Exception as e:
                    self.bot.send_message(call.message.chat.id, f"❌ Hata: {str(e)}")
        
        # Tüm mesajlar (bilinmeyen komutlar için)
        @self.bot.message_handler(func=lambda message: True)
        def handle_unknown(message):
            if not self._check_admin(message):
                return
            
            self.bot.send_message(
                message.chat.id,
                "❓ Bilinmeyen komut. Yardım için /help yazın.",
                reply_markup=self._get_main_menu()
            )
    
    def _check_admin(self, message) -> bool:
        """Admin yetkisini kontrol et"""
        if not self.admin_id:
            # Admin ID ayarlanmamışsa, ilk kullanıcıyı admin yap
            self.bot.send_message(
                message.chat.id,
                f"⚠️ <b>Admin ID ayarlanmamış!</b>\n\n"
                f"Sizin ID'niz: <code>{message.from_user.id}</code>\n"
                f"Bu ID'yi .env dosyasına TELEGRAM_ADMIN_ID olarak ekleyin.",
                parse_mode='HTML'
            )
            return True  # İlk kurulum için izin ver
        
        if message.from_user.id != self.admin_id:
            self.bot.send_message(message.chat.id, "🚫 Yetkisiz erişim!")
            return False
        
        return True
    
    def _check_admin_from_callback(self, call) -> bool:
        """Callback'den admin yetkisini kontrol et"""
        if not self.admin_id:
            return True
        if call.from_user.id != self.admin_id:
            self.bot.answer_callback_query(call.id, "🚫 Yetkisiz erişim!")
            return False
        return True
    
    def _get_main_menu(self) -> InlineKeyboardMarkup:
        """Ana menüyü oluştur"""
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("📊 Durum", callback_data='status'),
            InlineKeyboardButton("🎬 YouTube", callback_data='generate_youtube'),
            InlineKeyboardButton("🎵 TikTok", callback_data='generate_tiktok'),
            InlineKeyboardButton("🤖 Otomasyon", callback_data='automation_status')
        )
        return markup
    
    def _get_control_menu(self) -> InlineKeyboardMarkup:
        """Kontrol menüsü oluştur"""
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("🔄 Yenile", callback_data='status'),
            InlineKeyboardButton("▶️ Otomasyon Başlat", callback_data='automation_start'),
            InlineKeyboardButton("⏹ Otomasyon Durdur", callback_data='automation_stop')
        )
        return markup
    
    def _get_system_status(self) -> str:
        """Sistem durumunu al"""
        try:
            if get_automation_engine:
                engine = get_automation_engine()
                status = engine.get_status()
                
                text = "📊 <b>Sistem Durumu:</b>\n\n"
                text += f"🤖 <b>Otomasyon:</b> {'🟢 Aktif' if status.get('active') else '🔴 Pasif'}\n"
                text += f"📦 <b>Toplam Video:</b> {status.get('stats', {}).get('total_produced', 0)}\n"
                text += f"📤 <b>Yüklenen:</b> {status.get('stats', {}).get('total_uploaded', 0)}\n"
                text += f"❌ <b>Başarısız:</b> {status.get('stats', {}).get('total_failed', 0)}\n"
                text += f"📅 <b>Bugün:</b> {status.get('stats', {}).get('today_produced', 0)} video\n\n"
                
                queue = status.get('queue', {})
                if queue:
                    text += "📋 <b>Kuyruk Durumu:</b>\n"
                    text += f"  • Bekleyen: {queue.get('pending', 0)}\n"
                    text += f"  • Üretimde: {queue.get('generating', 0)}\n"
                    text += f"  • Hazır: {queue.get('ready', 0)}\n"
            else:
                text = "⚠️ Otomasyon motoru erişilemiyor"
            
            return text
        except Exception as e:
            return f"❌ Durum alınamadı: {str(e)}"
    
    def _get_automation_status(self) -> str:
        """Otomasyon durumunu al"""
        try:
            if get_automation_engine:
                engine = get_automation_engine()
                status = engine.get_status()
                
                text = "🤖 <b>Otomasyon Durumu:</b>\n\n"
                text += f"<b>Durum:</b> {'🟢 Çalışıyor' if status.get('active') else '🔴 Durduruldu'}\n"
                text += f"<b>Hedef:</b> Günde {status.get('target', {}).get('daily', 12)} video\n"
                text += f"  • YouTube: {status.get('target', {}).get('youtube', 6)}\n"
                text += f"  • TikTok: {status.get('target', {}).get('tiktok', 6)}\n\n"
                text += f"📊 <b>İstatistikler:</b>\n"
                text += f"  • Toplam Üretilen: {status.get('stats', {}).get('total_produced', 0)}\n"
                text += f"  • Toplam Yüklenen: {status.get('stats', {}).get('total_uploaded', 0)}\n"
                text += f"  • Bugün: {status.get('stats', {}).get('today_produced', 0)} video\n"
                
                return text
            else:
                return "⚠️ Otomasyon motoru erişilemiyor"
        except Exception as e:
            return f"❌ Hata: {str(e)}"
    
    def _is_automation_running(self) -> bool:
        """Otomasyonun çalışıp çalışmadığını kontrol et"""
        try:
            if get_automation_engine:
                engine = get_automation_engine()
                return engine.get_status().get('active', False)
            return False
        except Exception:
            return False
    
    def send_notification(self, message: str, photo_path: str = None, video_path: str = None):
        """Admin'e bildirim gönder"""
        if not self.bot or not self.admin_id:
            return
        
        try:
            if video_path and Path(video_path).exists():
                with open(video_path, 'rb') as f:
                    self.bot.send_video(self.admin_id, f, caption=message, parse_mode='HTML')
            elif photo_path and Path(photo_path).exists():
                with open(photo_path, 'rb') as f:
                    self.bot.send_photo(self.admin_id, f, caption=message, parse_mode='HTML')
            else:
                self.bot.send_message(self.admin_id, message, parse_mode='HTML')
        except Exception as e:
            if logger:
                logger.error(f"Telegram bildirim hatası: {e}")
    
    def start(self):
        """Bot'u başlat (non-blocking)"""
        if not self.bot:
            if logger:
                logger.error("Bot başlatılamadı - token eksik veya geçersiz")
            return
        
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_bot, daemon=True)
        self.thread.start()
        
        if logger:
            logger.info("Telegram bot çalışıyor")
        
        # Başlangıç bildirimi
        if self.admin_id:
            self.send_notification("🎬 <b>Video PRO AI</b> başlatıldı!\n\nBot aktif ve hazır.")
    
    def _run_bot(self):
        """Bot polling döngüsü"""
        while self.running:
            try:
                self.bot.polling(none_stop=True, interval=1, timeout=20)
            except Exception as e:
                if logger:
                    logger.error(f"Bot polling hatası: {e}")
                time.sleep(5)  # Hata durumunda bekle ve tekrar dene
    
    def stop(self):
        """Bot'u durdur"""
        self.running = False
        if self.bot:
            self.bot.stop_polling()
        if logger:
            logger.info("Telegram bot durduruldu")


# Global bot instance
_bot_controller = None


def get_telegram_bot() -> TelegramBotController:
    """Global bot controller instance'ını al"""
    global _bot_controller
    if _bot_controller is None:
        _bot_controller = TelegramBotController()
    return _bot_controller


def start_telegram_bot():
    """Telegram bot'u başlat"""
    bot = get_telegram_bot()
    bot.start()


def stop_telegram_bot():
    """Telegram bot'u durdur"""
    global _bot_controller
    if _bot_controller:
        _bot_controller.stop()
        _bot_controller = None


def send_telegram_notification(message: str, photo_path: str = None, video_path: str = None):
    """Hızlı bildirim gönder"""
    bot = get_telegram_bot()
    bot.send_notification(message, photo_path, video_path)
