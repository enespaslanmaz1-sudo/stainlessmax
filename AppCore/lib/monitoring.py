"""
Video PRO AI - System Monitoring
Advanced monitoring, error recovery, and self-healing system
"""
import os
import sys
import json
import time
import psutil
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from collections import deque

try:
    from lib.config_manager import get_config_manager
    from lib.logger import logger
except ImportError:
    logger = None
    get_config_manager = None


@dataclass
class SystemMetrics:
    """System performance metrics"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_usage_percent: float
    network_io_sent: int
    network_io_recv: int
    active_threads: int
    python_memory_mb: float


@dataclass
class ErrorLog:
    """Error log entry"""
    timestamp: datetime
    level: str
    context: str
    message: str
    stack_trace: Optional[str] = None
    recovered: bool = False


class SystemMonitor:
    """
    Advanced system monitoring and self-healing
    """
    
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path(__file__).parent.parent
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        self.metrics_file = self.logs_dir / "metrics.json"
        self.errors_file = self.logs_dir / "errors.json"
        self.health_file = self.logs_dir / "health.json"
        
        # Metrics history (keep last 24 hours)
        self.metrics_history: deque = deque(maxlen=1440)  # 1 minute intervals
        self.error_history: deque = deque(maxlen=1000)
        
        # Monitoring state
        self.active = False
        self.monitor_thread = None
        self.health_check_thread = None
        self.lock = threading.Lock()
        
        # Health status
        self.health_status = {
            "status": "healthy",  # healthy, warning, critical
            "last_check": None,
            "issues": [],
            "recommendations": []
        }
        
        # Thresholds
        self.thresholds = {
            "cpu_warning": 80,
            "cpu_critical": 95,
            "memory_warning": 80,
            "memory_critical": 95,
            "disk_warning": 85,
            "disk_critical": 95,
            "error_rate_warning": 10,  # errors per hour
            "error_rate_critical": 30
        }
        
        # Load existing data
        self._load_data()
    
    def _load_data(self):
        """Load historical data"""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    for item in data[-1440:]:  # Last 24 hours
                        item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                        self.metrics_history.append(SystemMetrics(**item))
            except Exception as e:
                if logger:
                    logger.error(f"Failed to load metrics: {e}")
        
        if self.errors_file.exists():
            try:
                with open(self.errors_file, 'r') as f:
                    data = json.load(f)
                    for item in data[-1000:]:
                        item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                        self.error_history.append(ErrorLog(**item))
            except Exception as e:
                if logger:
                    logger.error(f"Failed to load errors: {e}")
    
    def _save_data(self):
        """Save data to files"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump([{
                    **asdict(m),
                    'timestamp': m.timestamp.isoformat()
                } for m in self.metrics_history], f, indent=2)
            
            with open(self.errors_file, 'w') as f:
                json.dump([{
                    **asdict(e),
                    'timestamp': e.timestamp.isoformat()
                } for e in self.error_history], f, indent=2)
            
            with open(self.health_file, 'w') as f:
                json.dump({
                    **self.health_status,
                    'last_check': self.health_status['last_check'].isoformat() if self.health_status['last_check'] else None
                }, f, indent=2)
                
        except Exception as e:
            if logger:
                logger.error(f"Failed to save monitoring data: {e}")
    
    def start(self):
        """Start monitoring"""
        if self.active:
            return
        
        self.active = True
        
        # Start metrics collection
        self.monitor_thread = threading.Thread(target=self._metrics_loop, daemon=True)
        self.monitor_thread.start()
        
        # Start health checks
        self.health_check_thread = threading.Thread(target=self._health_loop, daemon=True)
        self.health_check_thread.start()
        
        if logger:
            logger.info("📊 System monitoring started")
    
    def stop(self):
        """Stop monitoring"""
        self.active = False
        self._save_data()
        
        if logger:
            logger.info("📊 System monitoring stopped")
    
    def _metrics_loop(self):
        """Collect system metrics every minute"""
        while self.active:
            try:
                metrics = self._collect_metrics()
                
                with self.lock:
                    self.metrics_history.append(metrics)
                
                # Save every 10 minutes
                if len(self.metrics_history) % 10 == 0:
                    self._save_data()
                
                time.sleep(60)
                
            except Exception as e:
                if logger:
                    logger.error(f"Metrics collection error: {e}")
                time.sleep(60)
    
    def _collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics"""
        process = psutil.Process()
        
        return SystemMetrics(
            timestamp=datetime.now(),
            cpu_percent=psutil.cpu_percent(interval=1),
            memory_percent=psutil.virtual_memory().percent,
            disk_usage_percent=psutil.disk_usage('/').percent,
            network_io_sent=psutil.net_io_counters().bytes_sent,
            network_io_recv=psutil.net_io_counters().bytes_recv,
            active_threads=threading.active_count(),
            python_memory_mb=process.memory_info().rss / 1024 / 1024
        )
    
    def _health_loop(self):
        """Run health checks every 5 minutes"""
        while self.active:
            try:
                self._check_health()
                time.sleep(300)  # 5 minutes
            except Exception as e:
                if logger:
                    logger.error(f"Health check error: {e}")
                time.sleep(300)
    
    def _check_health(self):
        """Perform comprehensive health check"""
        issues = []
        recommendations = []
        
        with self.lock:
            if not self.metrics_history:
                return
            
            # Get recent metrics
            recent = list(self.metrics_history)[-10:]  # Last 10 minutes
            avg_cpu = sum(m.cpu_percent for m in recent) / len(recent)
            avg_memory = sum(m.memory_percent for m in recent) / len(recent)
            latest = recent[-1]
            
            # CPU check
            if avg_cpu > self.thresholds['cpu_critical']:
                issues.append(f"CRITICAL: CPU usage at {avg_cpu:.1f}%")
                recommendations.append("Consider reducing concurrent video generations")
            elif avg_cpu > self.thresholds['cpu_warning']:
                issues.append(f"WARNING: High CPU usage at {avg_cpu:.1f}%")
            
            # Memory check
            if avg_memory > self.thresholds['memory_critical']:
                issues.append(f"CRITICAL: Memory usage at {avg_memory:.1f}%")
                recommendations.append("Restart application to clear memory")
            elif avg_memory > self.thresholds['memory_warning']:
                issues.append(f"WARNING: High memory usage at {avg_memory:.1f}%")
                recommendations.append("Consider closing other applications")
            
            # Disk check
            if latest.disk_usage_percent > self.thresholds['disk_critical']:
                issues.append(f"CRITICAL: Disk usage at {latest.disk_usage_percent:.1f}%")
                recommendations.append("Clear old video files immediately")
            elif latest.disk_usage_percent > self.thresholds['disk_warning']:
                issues.append(f"WARNING: Disk usage at {latest.disk_usage_percent:.1f}%")
                recommendations.append("Clean up old outputs folder")
            
            # Error rate check
            hour_ago = datetime.now() - timedelta(hours=1)
            recent_errors = [e for e in self.error_history if e.timestamp > hour_ago]
            error_rate = len(recent_errors)
            
            if error_rate > self.thresholds['error_rate_critical']:
                issues.append(f"CRITICAL: {error_rate} errors in last hour")
                recommendations.append("Check API keys and connections")
            elif error_rate > self.thresholds['error_rate_warning']:
                issues.append(f"WARNING: {error_rate} errors in last hour")
            
            # Update health status
            self.health_status = {
                "status": "critical" if any("CRITICAL" in i for i in issues) else 
                         "warning" if issues else "healthy",
                "last_check": datetime.now(),
                "issues": issues,
                "recommendations": recommendations
            }
    
    def log_error(self, context: str, message: str, level: str = "error", stack_trace: str = None):
        """Log an error"""
        error = ErrorLog(
            timestamp=datetime.now(),
            level=level,
            context=context,
            message=message,
            stack_trace=stack_trace
        )
        
        with self.lock:
            self.error_history.append(error)
        
        if logger:
            logger.error(f"[{context}] {message}")
    
    def mark_recovered(self, context: str):
        """Mark recent errors in context as recovered"""
        with self.lock:
            for error in self.error_history:
                if error.context == context and not error.recovered:
                    error.recovered = True
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        with self.lock:
            if not self.metrics_history:
                return {"status": "no_data"}
            
            recent = list(self.metrics_history)[-10:]
            latest = recent[-1]
            
            return {
                "current": {
                    "cpu_percent": latest.cpu_percent,
                    "memory_percent": latest.memory_percent,
                    "disk_usage_percent": latest.disk_usage_percent,
                    "python_memory_mb": round(latest.python_memory_mb, 2),
                    "active_threads": latest.active_threads
                },
                "averages": {
                    "cpu_10min": round(sum(m.cpu_percent for m in recent) / len(recent), 2),
                    "memory_10min": round(sum(m.memory_percent for m in recent) / len(recent), 2)
                },
                "health": self.health_status
            }
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        with self.lock:
            now = datetime.now()
            hour_ago = now - timedelta(hours=1)
            day_ago = now - timedelta(days=1)
            
            recent_errors = [e for e in self.error_history if e.timestamp > hour_ago]
            daily_errors = [e for e in self.error_history if e.timestamp > day_ago]
            
            # Group by context
            context_counts = {}
            for error in daily_errors:
                context_counts[error.context] = context_counts.get(error.context, 0) + 1
            
            return {
                "last_hour": len(recent_errors),
                "last_24h": len(daily_errors),
                "total_recorded": len(self.error_history),
                "by_context": context_counts,
                "unrecovered": len([e for e in daily_errors if not e.recovered])
            }
    
    def self_heal(self) -> List[str]:
        """Attempt automatic recovery actions"""
        actions = []
        
        with self.lock:
            # Check if we need to clean up disk
            if self.metrics_history:
                latest = list(self.metrics_history)[-1]
                if latest.disk_usage_percent > 80:
                    actions.append("Cleaning up old video files...")
                    self._cleanup_old_files()
            
            # Check for stuck processes
            hour_ago = datetime.now() - timedelta(hours=1)
            old_errors = [e for e in self.error_history if e.timestamp < hour_ago and not e.recovered]
            if len(old_errors) > 5:
                actions.append(f"Clearing {len(old_errors)} old unresolved errors")
                for error in old_errors:
                    error.recovered = True
        
        return actions
    
    def _cleanup_old_files(self):
        """Clean up old video files"""
        try:
            outputs_dir = self.base_dir / "outputs"
            if outputs_dir.exists():
                # Delete files older than 7 days
                cutoff = time.time() - (7 * 24 * 3600)
                for file in outputs_dir.glob("*.mp4"):
                    if file.stat().st_mtime < cutoff:
                        file.unlink(missing_ok=True)
                        if logger:
                            logger.info(f"Cleaned up old file: {file.name}")
        except Exception as e:
            if logger:
                logger.error(f"Cleanup error: {e}")


# Global monitor instance
_system_monitor = None


def get_system_monitor() -> SystemMonitor:
    """Get global system monitor instance"""
    global _system_monitor
    if _system_monitor is None:
        _system_monitor = SystemMonitor()
    return _system_monitor


def start_monitoring():
    """Start system monitoring"""
    monitor = get_system_monitor()
    monitor.start()


def stop_monitoring():
    """Stop system monitoring"""
    monitor = get_system_monitor()
    monitor.stop()


def log_system_error(context: str, message: str, level: str = "error", stack_trace: str = None):
    """Log error to system monitor"""
    monitor = get_system_monitor()
    monitor.log_error(context, message, level, stack_trace)


def get_system_health() -> Dict[str, Any]:
    """Get comprehensive system health"""
    monitor = get_system_monitor()
    return {
        "metrics": monitor.get_metrics(),
        "errors": monitor.get_error_stats(),
        "timestamp": datetime.now().isoformat()
    }
