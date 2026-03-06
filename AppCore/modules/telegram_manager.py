"""
Telegram Manager - Full Control via Telegram Bot
"""

import asyncio
import threading
from datetime import datetime
from typing import Set, Dict, Callable

try:
    from telegram import Update, Bot
    from telegram.ext import ContextTypes
except ImportError:
    Update = None
    ContextTypes = None

TELEGRAM_TOKEN = "8562331689:AAFMA_sU97lmt6WcnZKx8Ql3MYnPaGxcZH0"


class TelegramManager:
    """Telegram bot for remote control"""
    
    def __init__(self, token: str = None):
        self.token = token or TELEGRAM_TOKEN
        self.app = None
        self.authorized_users: Set[int] = set()
        self.is_running = False
        self.message_handlers: Dict[str, Callable] = {}
        self.pending_approvals: Dict[str, dict] = {}
        
    def register_handler(self, command: str, handler: Callable):
        """Register command handler"""
        self.message_handlers[command] = handler
    
    def start(self):
        """Start telegram bot"""
        if self.is_running:
            return
        
        try:
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
            
            self.app = Application.builder().token(self.token).build()
            
            # Register handlers
            self.app.add_handler(CommandHandler("start", self._cmd_start))
            self.app.add_handler(CommandHandler("status", self._cmd_status))
            self.app.add_handler(CommandHandler("accounts", self._cmd_accounts))
            self.app.add_handler(CommandHandler("produce", self._cmd_produce))
            self.app.add_handler(CommandHandler("ip", self._cmd_ip))
            self.app.add_handler(CommandHandler("logs", self._cmd_logs))
            self.app.add_handler(CommandHandler("help", self._cmd_help))
            
            # Viral video komutları
            self.app.add_handler(CommandHandler("generate_video", self._cmd_generate_video))
            self.app.add_handler(CommandHandler("viral_status", self._cmd_viral_status))
            self.app.add_handler(CommandHandler("schedule_optimal", self._cmd_schedule_optimal))
            self.app.add_handler(CallbackQueryHandler(self._handle_callback))
            
            # Run in thread
            def run():
                self.is_running = True
                self.app.run_polling()
            
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            print("[Telegram] Bot started")
            
        except Exception as e:
            print(f"[Telegram] Failed to start: {e}")
    
    async def _cmd_start(self, update: Update, context):
        """Handle /start command"""
        user_id = update.effective_user.id
        self.authorized_users.add(user_id)
        
        welcome = """
🎬 **Video PRO AI - Stainless PC Farm**

Merhaba! Video otomasyon sistemine hoş geldiniz.

📱 **Komutlar:**
/status - Sistem durumu
/accounts - Hesapları görüntüle
/produce - Video üretimi başlat
/ip - IP adresini değiştir
/logs - Son logları gör
/help - Yardım

⚡️ Tüm işlemleri buradan yönetebilirsiniz!
        """
        await update.message.reply_text(welcome, parse_mode='Markdown')
    
    async def _cmd_status(self, update: Update, context):
        """Handle /status command"""
        if "status" in self.message_handlers:
            result = self.message_handlers["status"]()
            await update.message.reply_text(result, parse_mode='Markdown')
        else:
            await update.message.reply_text("ℹ️ Sistem durumu alınıyor...")
    
    async def _cmd_accounts(self, update: Update, context):
        """Handle /accounts command"""
        if "accounts" in self.message_handlers:
            result = self.message_handlers["accounts"]()
            await update.message.reply_text(result, parse_mode='Markdown')
        else:
            await update.message.reply_text("ℹ️ Hesap bilgisi alınıyor...")
    
    async def _cmd_produce(self, update: Update, context):
        """Handle /produce command"""
        keyboard = [
            [InlineKeyboardButton("🚀 Tümünü Başlat", callback_data='produce_all')],
            [InlineKeyboardButton("📺 YouTube", callback_data='produce_youtube')],
            [InlineKeyboardButton("🎵 TikTok", callback_data='produce_tiktok')]
        ]
        
        await update.message.reply_text(
            "🎬 **Video Üretimi**\n\nNe üretmek istersiniz?",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _cmd_ip(self, update: Update, context):
        """Handle /ip command"""
        if "rotate_ip" in self.message_handlers:
            await update.message.reply_text("🔄 IP değiştiriliyor...")
            result = self.message_handlers["rotate_ip"]()
            await update.message.reply_text(result)
    
    async def _cmd_logs(self, update: Update, context):
        """Handle /logs command"""
        if "logs" in self.message_handlers:
            result = self.message_handlers["logs"]()
            await update.message.reply_text(result, parse_mode='Markdown')
        else:
            await update.message.reply_text("ℹ️ Loglar alınıyor...")
    
    async def _cmd_help(self, update: Update, context):
        """Handle /help command"""
        help_text = """
🤖 **Telegram Bot Komutları**

📊 Genel:
/start - Bot'u başlat
/status - Sistem durumu
/accounts - Hesapları listele
/help - Bu mesaj

🎬 Viral Video AI:
/generate_video [account_id] - Viral video üret
/viral_status - Video üretim durumu
/schedule_optimal [account_id] - Gemini ile optimal saat belirle

📺 Yükleme:
/produce - Video üretimi başlat (eski)
/ip - IP adresini göster
/logs - Son logları göster

📱 Authorized users only!
        """
        await update.message.reply_text(
            help_text,
            parse_mode="Markdown"
        )
    
    async def _handle_callback(self, update: Update, context):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith('produce_'):
            target = data.replace('produce_', '')
            if "produce" in self.message_handlers:
                self.message_handlers["produce"](target)
                await query.edit_message_text(f"🚀 {target} için üretim başlatıldı!")
        
        elif data.startswith('approve_'):
            video_id = data.replace('approve_', '')
            if video_id in self.pending_approvals:
                if "approve_video" in self.message_handlers:
                    self.message_handlers["approve_video"](video_id)
                del self.pending_approvals[video_id]
                await query.edit_message_text("✅ Video onaylandı ve paylaşılıyor...")
        
        elif data.startswith('reject_'):
            video_id = data.replace('reject_', '')
            if video_id in self.pending_approvals:
                if "reject_video" in self.message_handlers:
                    self.message_handlers["reject_video"](video_id)
                del self.pending_approvals[video_id]
                await query.edit_message_text("❌ Video reddedildi ve silindi.")
    
    def send_video_for_approval(self, video_path: str, title: str, 
                                account_id: str, chat_id: int = None):
        """Send video for approval"""
        if not chat_id and self.authorized_users:
            chat_id = list(self.authorized_users)[0]
        
        if not chat_id:
            return
        
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            video_id = f"{account_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            self.pending_approvals[video_id] = {
                'path': video_path,
                'title': title,
                'account': account_id
            }
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Onayla", callback_data=f'approve_{video_id}'),
                    InlineKeyboardButton("❌ Reddet", callback_data=f'reject_{video_id}')
                ]
            ]
            
            caption = f"""
🎬 **Video Onayı Gerekli**

📌 Başlık: {title}
👤 Hesap: {account_id}
⏰ {datetime.now().strftime('%H:%M:%S')}

Onay verirseniz paylaşılacak.
            """
            
            async def send():
                try:
                    with open(video_path, 'rb') as video_file:
                        await self.app.bot.send_video(
                            chat_id=chat_id,
                            video=video_file,
                            caption=caption,
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                except Exception as e:
                    print(f"[Telegram] Send video error: {e}")
            
            asyncio.run(send())
            
        except Exception as e:
            print(f"[Telegram] Approval error: {e}")
    
    def send_notification(self, message: str):
        """Send notification to all authorized users"""
        if not self.authorized_users:
            return
        
        async def notify():
            for chat_id in self.authorized_users:
                try:
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    print(f"Failed to notify {chat_id}: {e}")
        
        asyncio.run(notify())
