"""
Telegram Bot V2 - Enhanced Control System
Built with python-telegram-bot v20+
"""

import asyncio
import threading
import logging
import os
import json
from datetime import datetime
from typing import Dict, Callable, Optional, List

# Try imports
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, 
        CommandHandler, 
        CallbackQueryHandler, 
        ContextTypes, 
        MessageHandler, 
        filters
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot library not installed.")
    # Mock classes for type hints to avoid NameError
    class Update: pass
    class ContextTypes:
        class DEFAULT_TYPE: pass

# Config
from AppCore.lib.config_manager import get_config_manager

logger = logging.getLogger(__name__)

class TelegramBotV2:
    """
    Enhanced Telegram Bot for System Control
    """
    
    def __init__(self):
        self.config_manager = get_config_manager()
        self.token = self.config_manager.api_keys.telegram_token
        self.admin_id = self.config_manager.api_keys.telegram_admin
        
        # Fallback: Direkt .env'den de kontrol et
        if not self.token:
            self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not self.admin_id:
            self.admin_id = os.getenv("TELEGRAM_ADMIN_ID", "")
        
        self.app: Optional[Application] = None
        self.is_running = False
        self.thread = None
        
        # Callbacks registered by main system
        self.callbacks: Dict[str, Callable] = {}
        
        # Pending sensitive actions
        self.pending_actions: Dict[str, dict] = {}
        
        logger.debug(f"Telegram Bot initialized. Admin ID: {self.admin_id}")
        logger.debug(f"Token available: {'Yes' if self.token else 'No'}")

    def register_callback(self, name: str, func: Callable):
        """Register a system callback (e.g., 'produce', 'status', 'logs')"""
        self.callbacks[name] = func

    def start(self):
        """Start the bot in a background thread"""
        if not TELEGRAM_AVAILABLE:
            logger.error("Cannot start Telegram Bot: python-telegram-bot library missing")
            logger.error("Install with: pip install python-telegram-bot")
            return
            
        if not self.token:
            logger.error("Cannot start Telegram Bot: TELEGRAM_BOT_TOKEN not found in .env")
            return
            
        if not self.admin_id:
            logger.warning("TELEGRAM_ADMIN_ID not set - bot will not restrict access")

        if self.is_running:
            logger.warning("Telegram Bot already running")
            return

        def run_bot():
            try:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
                
                self.app = Application.builder().token(self.token).build()
                
                # Handlers
                self.app.add_handler(CommandHandler("start", self._cmd_start))
                self.app.add_handler(CommandHandler("help", self._cmd_help))
                self.app.add_handler(CommandHandler("status", self._cmd_status))
                self.app.add_handler(CommandHandler("menu", self._cmd_menu))
                self.app.add_handler(CommandHandler("logs", self._cmd_logs))
                self.app.add_handler(CommandHandler("ip", self._cmd_ip))
                
                # Callback Queries (Buttons)
                self.app.add_handler(CallbackQueryHandler(self._handle_button))
                
                # Message Handler (for specific inputs if needed)
                self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
                
                # Error handler for Conflict errors
                async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
                    """Handle errors, especially Conflict errors from multiple bot instances"""
                    if context.error:
                        error_str = str(context.error)
                        if "Conflict" in error_str or "409" in error_str or "terminated by other getUpdates" in error_str:
                            # Suppress conflict errors - they're not critical, just means another instance is running
                            logger.debug(f"Telegram conflict (ignored, another bot instance may be running): {error_str}")
                            return
                        else:
                            # Log other errors normally
                            logger.error(f"Telegram error: {context.error}", exc_info=True)
                
                self.app.add_error_handler(error_handler)
                
                self.is_running = True
                logger.debug("✅ Telegram Bot V2 polling başlatıldı")
                logger.debug(f"📱 Bot hazır! Admin: {self.admin_id}")
                
                # Send startup notification
                if self.admin_id:
                    try:
                        self.loop.run_until_complete(
                            self.app.bot.send_message(
                                chat_id=self.admin_id,
                                text="🚀 **STAINLESS MAX Bot Aktif**\n\nSistem başlatıldı ve hazır!\n\nKomutlar için /menu yazın.",
                                parse_mode="Markdown"
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Startup notification failed: {e}")
                
                self.app.run_polling(drop_pending_updates=True)
                
            except Exception as e:
                logger.error(f"❌ Telegram Bot error: {e}")
                self.is_running = False

        self.thread = threading.Thread(target=run_bot, daemon=True)
        self.thread.start()
        logger.debug("🤖 Telegram Bot thread started")

    async def _check_auth(self, update: Update) -> bool:
        """Check if user is authorized"""
        user_id = update.effective_user.id
        # Convert to string for comparison as config might have it as str
        if str(user_id) == str(self.admin_id):
            return True
        
        logger.warning(f"Unauthorized access attempt from {user_id} ({update.effective_user.username})")
        await update.message.reply_text("⛔ Unauthorized access.")
        return False

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start"""
        if not await self._check_auth(update):
            return

        text = (
            "🤖 **STAINLESS MAX Control System**\n\n"
            f"Admin: `{self.admin_id}`\n"
            "System is Online.\n\n"
            "Use /menu for controls."
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        await self._send_main_menu(update)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update): return
        text = """
        **Commands:**
        /start - Initialize
        /menu - Show Control Panel
        /status - Check System Status
        /logs - View Recent Logs
        /ip - Check/Change IP
        """
        await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update): return
        await self._send_main_menu(update)
        
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update): return
        
        if "status" in self.callbacks:
            status_text = self.callbacks["status"]()
            await update.message.reply_text(f"📊 **System Status**\n\n{status_text}", parse_mode="Markdown")
        else:
            await update.message.reply_text("Status callback not connected.")

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update): return
        
        if "logs" in self.callbacks:
            logs = self.callbacks["logs"]()
            # Split logs if too long
            if len(logs) > 4000:
                chunks = [logs[i:i+4000] for i in range(0, len(logs), 4000)]
                for chunk in chunks:
                    await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"📋 **Recent Logs**\n```\n{logs}\n```", parse_mode="Markdown")
        else:
            await update.message.reply_text("Logs callback not connected.")

    async def _cmd_ip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update): return
        await update.message.reply_text("🔍 Checking IP...")
        if "check_ip" in self.callbacks:
            ip_info = self.callbacks["check_ip"]()
            await update.message.reply_text(f"🌐 **IP Info**\n{ip_info}", parse_mode="Markdown")

    async def _send_main_menu(self, update: Update, edit=False):
        keyboard = [
            [
                InlineKeyboardButton("🚀 Produce (All)", callback_data="prod_all"),
                InlineKeyboardButton("📺 YouTube", callback_data="prod_yt")
            ],
            [
                InlineKeyboardButton("🎵 TikTok", callback_data="prod_tt"),
                InlineKeyboardButton("📸 Instagram", callback_data="prod_ig")
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("📋 Logs", callback_data="logs")
            ],
            [
                InlineKeyboardButton("🔄 Restart System", callback_data="restart")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "🎛️ **Control Panel**\nSelect an action:"
        
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    async def _handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "menu":
            await self._send_main_menu(update, edit=True)
            return

        # Status
        if data == "status":
            if "status" in self.callbacks:
                status = self.callbacks["status"]()
                await query.edit_message_text(f"📊 **Status**\n{status}", parse_mode="Markdown", 
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
            return

        # Logs
        if data == "logs":
            if "logs" in self.callbacks:
                logs = self.callbacks["logs"]()
                log_preview = logs[-1000:] if len(logs) > 1000 else logs
                await query.edit_message_text(f"📋 **Latest Logs**\n```\n{log_preview}\n```", parse_mode="Markdown",
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
            return

        # Production
        if data.startswith("prod_"):
            platform = data.split("_")[1] # all, yt, tt, ig
            
            # Ask for confirmation
            keyboard = [
                [InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_prod_{platform}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="menu")]
            ]
            platform_name = {"all": "ALL Platforms", "yt": "YouTube", "tt": "TikTok", "ig": "Instagram"}.get(platform, platform)
            await query.edit_message_text(f"⚠️ **Confirm Production**\n\nStart generating videos for: **{platform_name}**?", 
                                        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Confirmation
        if data.startswith("confirm_prod_"):
            platform = data.split("_")[2]
            if "produce" in self.callbacks:
                # Trigger production in background
                threading.Thread(target=self.callbacks["produce"], args=(platform,)).start()
                await query.edit_message_text(f"🚀 **Production Started** for {platform.upper()}!", 
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
            else:
                await query.edit_message_text("❌ Production callback not linked.", 
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
            return

        # Simple text handler if needed
    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        pass

    # --- Public Methods ---

    def send_notification(self, message: str):
        """Send a notification to the admin"""
        if not self.app or not self.admin_id: return

        async def _send():
            try:
                await self.app.bot.send_message(chat_id=self.admin_id, text=message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send telegram notification: {e}")

        # Run safely in loop
        try:
             if hasattr(self, 'loop') and self.loop and self.loop.is_running():
                 asyncio.run_coroutine_threadsafe(_send(), self.loop)
             else:
                 # Fallback if loop is not ready
                 logger.debug("Telegram loop not running yet, skipping notification")
        except Exception as e:
            logger.error(f"Error in send_notification: {e}")

    def send_video(self, video_path: str, caption: str = ""):
        """Send a video to the admin"""
        if not self.app or not self.admin_id: return
        if not os.path.exists(video_path): return

        async def _send():
            try:
                with open(video_path, 'rb') as video:
                    await self.app.bot.send_video(
                        chat_id=self.admin_id, 
                        video=video, 
                        caption=caption, 
                        parse_mode="Markdown", 
                        read_timeout=120, 
                        write_timeout=120, 
                        connect_timeout=120, 
                        pool_timeout=120
                    )
            except Exception as e:
                logger.error(f"Failed to send video: {e}")
        
        try:
            if hasattr(self, 'loop') and self.loop and self.loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_send(), self.loop)
                # No await/blocking here as it's meant to be background
            else:
                 logger.error("Bot loop not available for sending video")
        except Exception as e:
            logger.error(f"Video send error: {e}")

