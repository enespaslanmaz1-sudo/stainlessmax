"""
Enhanced Error Handling System
Provides comprehensive error handling, logging, and recovery mechanisms
"""
import traceback
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better classification"""
    API_ERROR = "api_error"
    CONFIGURATION_ERROR = "configuration_error"
    NETWORK_ERROR = "network_error"
    FILE_SYSTEM_ERROR = "file_system_error"
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    PROCESSING_ERROR = "processing_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorContext:
    """Error context information"""
    timestamp: datetime
    error_type: str
    message: str
    stack_trace: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    additional_data: Dict[str, Any] = None
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR

    def __post_init__(self):
        if self.additional_data is None:
            self.additional_data = {}


class CriticalError(Exception):
    """Critical error that requires immediate attention"""
    def __init__(self, message: str, context: ErrorContext):
        super().__init__(message)
        self.context = context


class RecoverableError(Exception):
    """Recoverable error that can be handled gracefully"""
    def __init__(self, message: str, context: ErrorContext):
        super().__init__(message)
        self.context = context


class ErrorHandler:
    """Enhanced error handler with logging, notification, and recovery"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.error_stats = {
            "total_errors": 0,
            "critical_errors": 0,
            "recoverable_errors": 0,
            "last_error_time": None
        }
        
    def handle_exception(self, exc: Exception, context: Dict[str, Any] = None) -> ErrorContext:
        """Handle any exception with proper classification and logging"""
        if context is None:
            context = {}
            
        # Create error context
        error_context = ErrorContext(
            timestamp=datetime.now(),
            error_type=type(exc).__name__,
            message=str(exc),
            stack_trace=traceback.format_exc(),
            user_id=context.get("user_id"),
            request_id=context.get("request_id"),
            additional_data=context,
            severity=self._classify_severity(exc),
            category=self._classify_category(exc)
        )
        
        # Update statistics
        self._update_stats(error_context)
        
        # Log the error
        self.log_error(error_context)
        
        # Handle based on severity
        if error_context.severity == ErrorSeverity.CRITICAL:
            self.notify_admin(CriticalError(str(exc), error_context))
        
        return error_context
    
    def log_error(self, error_context: ErrorContext) -> None:
        """Log error with appropriate level and formatting"""
        log_message = (
            f"[{error_context.category.value.upper()}] "
            f"{error_context.error_type}: {error_context.message}"
        )
        
        # Add context information to the message instead of using extra
        if error_context.user_id:
            log_message += f" | User: {error_context.user_id}"
        if error_context.request_id:
            log_message += f" | Request: {error_context.request_id}"
        if error_context.additional_data:
            log_message += f" | Context: {error_context.additional_data}"
        
        if error_context.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(log_message)
        elif error_context.severity == ErrorSeverity.HIGH:
            self.logger.error(log_message)
        elif error_context.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
            
        # Always log stack trace for debugging
        if error_context.stack_trace:
            self.logger.debug(f"Stack trace: {error_context.stack_trace}")
    
    def notify_admin(self, error: CriticalError) -> None:
        """Notify admin of critical errors"""
        try:
            # Try to get config manager for admin notification
            from lib.config_manager import get_config_manager
            config = get_config_manager()
            
            if config and config.api_keys.telegram_token and config.api_keys.telegram_admin:
                self._send_telegram_notification(error, config)
            else:
                self.logger.warning("Admin notification failed: Telegram not configured")
                
        except Exception as e:
            self.logger.error(f"Failed to notify admin: {e}")
    
    def _send_telegram_notification(self, error: CriticalError, config) -> None:
        """Send Telegram notification for critical errors"""
        try:
            import telebot
            
            bot = telebot.TeleBot(config.api_keys.telegram_token)
            message = (
                "🚨 *CRITICAL ERROR ALERT* 🚨\n\n"
                f"**Error Type:** {error.context.error_type}\n"
                f"**Message:** {error.context.message}\n"
                f"**Time:** {error.context.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"**Category:** {error.context.category.value}\n"
                f"**Severity:** {error.context.severity.value}\n"
            )
            
            if error.context.user_id:
                message += f"**User ID:** {error.context.user_id}\n"
            if error.context.request_id:
                message += f"**Request ID:** {error.context.request_id}\n"
                
            bot.send_message(
                config.api_keys.telegram_admin,
                message,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            self.logger.error(f"Telegram notification failed: {e}")
    
    def get_recovery_strategy(self, error_type: str) -> str:
        """Get recovery strategy for specific error types"""
        strategies = {
            "ConnectionError": "retry_with_backoff",
            "TimeoutError": "retry_with_increased_timeout",
            "APIError": "use_fallback_api",
            "ConfigurationError": "reload_configuration",
            "FileNotFoundError": "create_default_file",
            "PermissionError": "check_file_permissions",
            "ValidationError": "sanitize_input",
            "AuthenticationError": "refresh_credentials"
        }
        
        return strategies.get(error_type, "log_and_continue")
    
    def attempt_recovery(self, error_context: ErrorContext) -> bool:
        """Attempt to recover from error based on its type"""
        strategy = self.get_recovery_strategy(error_context.error_type)
        
        try:
            if strategy == "retry_with_backoff":
                return self._retry_with_backoff(error_context)
            elif strategy == "use_fallback_api":
                return self._use_fallback_api(error_context)
            elif strategy == "reload_configuration":
                return self._reload_configuration(error_context)
            elif strategy == "create_default_file":
                return self._create_default_file(error_context)
            elif strategy == "sanitize_input":
                return self._sanitize_input(error_context)
            else:
                self.logger.info(f"No recovery strategy for {error_context.error_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Recovery attempt failed: {e}")
            return False
    
    def _classify_severity(self, exc: Exception) -> ErrorSeverity:
        """Classify error severity based on exception type"""
        critical_errors = [
            "SystemExit", "KeyboardInterrupt", "MemoryError",
            "OSError", "IOError"
        ]
        
        high_errors = [
            "ConnectionError", "TimeoutError", "AuthenticationError",
            "PermissionError", "FileNotFoundError"
        ]
        
        medium_errors = [
            "ValueError", "TypeError", "AttributeError",
            "KeyError", "IndexError"
        ]
        
        error_name = type(exc).__name__
        
        if error_name in critical_errors:
            return ErrorSeverity.CRITICAL
        elif error_name in high_errors:
            return ErrorSeverity.HIGH
        elif error_name in medium_errors:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW
    
    def _classify_category(self, exc: Exception) -> ErrorCategory:
        """Classify error category based on exception type"""
        categories = {
            "ConnectionError": ErrorCategory.NETWORK_ERROR,
            "TimeoutError": ErrorCategory.NETWORK_ERROR,
            "HTTPError": ErrorCategory.API_ERROR,
            "APIError": ErrorCategory.API_ERROR,
            "FileNotFoundError": ErrorCategory.FILE_SYSTEM_ERROR,
            "PermissionError": ErrorCategory.FILE_SYSTEM_ERROR,
            "IOError": ErrorCategory.FILE_SYSTEM_ERROR,
            "OSError": ErrorCategory.FILE_SYSTEM_ERROR,
            "ConfigurationError": ErrorCategory.CONFIGURATION_ERROR,
            "ValidationError": ErrorCategory.VALIDATION_ERROR,
            "AuthenticationError": ErrorCategory.AUTHENTICATION_ERROR,
            "ValueError": ErrorCategory.VALIDATION_ERROR,
            "TypeError": ErrorCategory.VALIDATION_ERROR,
        }
        
        error_name = type(exc).__name__
        return categories.get(error_name, ErrorCategory.UNKNOWN_ERROR)
    
    def _update_stats(self, error_context: ErrorContext) -> None:
        """Update error statistics"""
        self.error_stats["total_errors"] += 1
        self.error_stats["last_error_time"] = error_context.timestamp
        
        if error_context.severity == ErrorSeverity.CRITICAL:
            self.error_stats["critical_errors"] += 1
        elif error_context.severity in [ErrorSeverity.HIGH, ErrorSeverity.MEDIUM]:
            self.error_stats["recoverable_errors"] += 1
    
    def _retry_with_backoff(self, error_context: ErrorContext) -> bool:
        """Implement retry with exponential backoff"""
        # This would be implemented based on specific use case
        self.logger.info("Implementing retry with backoff strategy")
        return False
    
    def _use_fallback_api(self, error_context: ErrorContext) -> bool:
        """Use fallback API when primary fails"""
        self.logger.info("Switching to fallback API")
        return False
    
    def _reload_configuration(self, error_context: ErrorContext) -> bool:
        """Reload configuration from file"""
        try:
            from lib.config_manager import get_config_manager
            config = get_config_manager()
            config._load_config()  # Reload configuration
            self.logger.info("Configuration reloaded successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reload configuration: {e}")
            return False
    
    def _create_default_file(self, error_context: ErrorContext) -> bool:
        """Create default file when missing"""
        self.logger.info("Creating default file")
        return False
    
    def _sanitize_input(self, error_context: ErrorContext) -> bool:
        """Sanitize input data"""
        self.logger.info("Sanitizing input data")
        return False
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        return self.error_stats.copy()
    
    def reset_stats(self) -> None:
        """Reset error statistics"""
        self.error_stats = {
            "total_errors": 0,
            "critical_errors": 0,
            "recoverable_errors": 0,
            "last_error_time": None
        }


# Global error handler instance
_error_handler = None


def get_error_handler() -> ErrorHandler:
    """Get global error handler instance"""
    global _error_handler
    if _error_handler is None:
        try:
            from lib.logger import logger
            _error_handler = ErrorHandler(logger)
        except ImportError:
            _error_handler = ErrorHandler()
    return _error_handler


def handle_error(exc: Exception, context: Dict[str, Any] = None) -> ErrorContext:
    """Convenience function to handle errors"""
    return get_error_handler().handle_exception(exc, context)


def log_error(error_type: str, message: str, context: Dict[str, Any] = None) -> None:
    """Convenience function to log errors"""
    if context is None:
        context = {}
        
    error_context = ErrorContext(
        timestamp=datetime.now(),
        error_type=error_type,
        message=message,
        stack_trace="",
        additional_data=context
    )
    
    get_error_handler().log_error(error_context)