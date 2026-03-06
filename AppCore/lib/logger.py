"""
Secure Logger with sensitive data masking
"""
import logging
import sys
import re
from pathlib import Path
from logging.handlers import RotatingFileHandler


class SensitiveDataFilter(logging.Filter):
    """Filter to mask sensitive data in logs"""

    SENSITIVE_PATTERNS = [
        (r"AIza[0-9A-Za-z_-]{35}", "AIza****"),  # Google API keys
        (r"sk-[0-9A-Za-z]{48}", "sk-****"),  # OpenAI API keys
        (r"\d{10}:[A-Za-z0-9_-]{35}", "****:****"),  # Telegram bot tokens
        (r"Bearer [A-Za-z0-9_-]+", "Bearer ****"),  # Bearer tokens
        (r'"token":\s*"[^"]*"', '"token": "****"'),  # JSON tokens
        (r'"key":\s*"[^"]*"', '"key": "****"'),  # JSON keys
        (r'"password":\s*"[^"]*"', '"password": "****"'),  # Passwords
    ]

    def filter(self, record):
        if hasattr(record, "msg"):
            message = str(record.msg)
            for pattern, replacement in self.SENSITIVE_PATTERNS:
                message = re.sub(pattern, replacement, message)
            record.msg = message
        return True


class SecureLogger:
    """Secure logger with rotation and sensitive data masking"""

    def __init__(self, name: str = "video_pro_ai", log_dir: Path = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Prevent duplicate handlers
        if self.logger.handlers:
            return

        # Determine log directory
        if log_dir is None:
            if hasattr(sys, "frozen") and sys.frozen:
                log_dir = Path(sys.executable).parent
            else:
                log_dir = Path(__file__).parent.parent

        log_file = log_dir / "app.log"

        # File handler with rotation
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Add sensitive data filter
        sensitive_filter = SensitiveDataFilter()
        file_handler.addFilter(sensitive_filter)
        console_handler.addFilter(sensitive_filter)

        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def debug(self, message):
        self.logger.debug(message)

    def critical(self, message):
        self.logger.critical(message)


# Global logger instance
logger = SecureLogger()
