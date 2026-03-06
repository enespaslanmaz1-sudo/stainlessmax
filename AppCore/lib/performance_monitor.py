"""
Performance Monitor Module
System metrics collection and reporting
"""
import time
import threading

try:
    import psutil
except Exception:
    psutil = None

from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from .logger import logger


@dataclass
class MetricSample:
    """Single metric sample"""
    timestamp: float
    value: float

    def to_dict(self) -> Dict:
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "value": self.value,
        }


@dataclass
class TimingMetric:
    """Timing metric with min/max/avg"""
    name: str
    samples: deque = field(default_factory=lambda: deque(maxlen=100))
    total_time: float = 0.0
    count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, duration: float):
        with self._lock:
            self.samples.append(MetricSample(time.time(), duration))
            self.total_time += duration
            self.count += 1

    def get_stats(self) -> Dict:
        with self._lock:
            if self.count == 0:
                return {"min": 0, "max": 0, "avg": 0, "count": 0}

            values = [s.value for s in self.samples]
            return {
                "min": round(min(values), 3) if values else 0,
                "max": round(max(values), 3) if values else 0,
                "avg": round(self.total_time / self.count, 3),
                "count": self.count,
                "recent_samples": len(self.samples),
            }


@dataclass
class CounterMetric:
    """Counter metric (success/failure counts)"""
    name: str
    success: int = 0
    failure: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment_success(self):
        with self._lock:
            self.success += 1

    def increment_failure(self):
        with self._lock:
            self.failure += 1

    def get_stats(self) -> Dict:
        with self._lock:
            total = self.success + self.failure
            rate = (self.success / total * 100) if total > 0 else 0
            return {
                "success": self.success,
                "failure": self.failure,
                "total": total,
                "success_rate": f"{rate:.1f}%",
            }


class PerformanceMonitor:
    """
    Performance monitoring system.
    Collects and reports various metrics.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Timing metrics
        self._timings: Dict[str, TimingMetric] = {
            "video_generation": TimingMetric("video_generation"),
            "tts_generation": TimingMetric("tts_generation"),
            "video_download": TimingMetric("video_download"),
            "ffmpeg_processing": TimingMetric("ffmpeg_processing"),
            "api_gemini": TimingMetric("api_gemini"),
            "api_pexels": TimingMetric("api_pexels"),
            "api_apify": TimingMetric("api_apify"),
        }

        # Counter metrics
        self._counters: Dict[str, CounterMetric] = {
            "video_generation": CounterMetric("video_generation"),
            "tts_generation": CounterMetric("tts_generation"),
            "video_download": CounterMetric("video_download"),
            "api_calls": CounterMetric("api_calls"),
            "telegram_notifications": CounterMetric("telegram_notifications"),
        }

        # System metrics history
        self._system_samples: deque = deque(maxlen=60)
        self._sample_interval = 60  # 1 hour at 1 sample/minute
        self._sampling_thread: Optional[threading.Thread] = None
        self._stop_sampling = threading.Event()

        # Alerts
        self._alert_callbacks: List[Callable] = []
        self._alert_thresholds = {
            "cpu_percent": 90,
            "memory_percent": 85,
            "disk_percent": 95,
        }

        self._initialized = True
        logger.info("[PERF] Performance monitor initialized")

    def start_sampling(self):
        """Start background system sampling"""
        if self._sampling_thread and self._sampling_thread.is_alive():
            return

        self._stop_sampling.clear()
        self._sampling_thread = threading.Thread(
            target=self._sample_loop,
            daemon=True,
        )
        self._sampling_thread.start()
        logger.info("[PERF] System sampling started")

    def stop_sampling(self):
        """Stop background system sampling"""
        self._stop_sampling.set()
        if self._sampling_thread:
            self._sampling_thread.join(timeout=5)

    def _sample_loop(self):
        """Background sampling loop"""
        while not self._stop_sampling.is_set():
            try:
                sample = self._collect_system_sample()
                self._system_samples.append(sample)
                self._check_alerts(sample)
            except Exception as e:
                logger.error(f"[PERF] Sampling error: {e}")

            self._stop_sampling.wait(self._sample_interval)

    def _collect_system_sample(self) -> Dict:
        """Collect current system metrics"""
        try:
            if psutil is None:
                logger.warning(
                    "[PERF] psutil not available, system metrics disabled"
                )
                return {
                    "timestamp": time.time(),
                    "error": "psutil not available",
                }
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "timestamp": time.time(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_mb": memory.used / (1024 * 1024),
                "memory_available_mb": memory.available / (1024 * 1024),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / (1024 * 1024 * 1024),
            }
        except Exception as e:
            logger.error(f"[PERF] Failed to collect system sample: {e}")
            return {"timestamp": time.time(), "error": str(e)}

    def _check_alerts(self, sample: Dict):
        """Check if any thresholds are exceeded"""
        for metric, threshold in self._alert_thresholds.items():
            value = sample.get(metric, 0)
            if value > threshold:
                alert_msg = (
                    f"[PERF-ALERT] {metric} is at {value}% "
                    f"(threshold: {threshold}%)"
                )
                logger.warning(alert_msg)
                for callback in self._alert_callbacks:
                    try:
                        callback(metric, value, threshold)
                    except Exception as e:
                        logger.error(f"[PERF] Alert callback error: {e}")

    def add_alert_callback(self, callback: Callable):
        """Add callback for alert notifications"""
        self._alert_callbacks.append(callback)

    # Context managers for timing
    def time_operation(self, operation: str):
        """Context manager to time an operation"""
        return TimingContext(self, operation)

    def record_timing(self, operation: str, duration: float):
        """Record a timing measurement"""
        if operation not in self._timings:
            self._timings[operation] = TimingMetric(operation)
        self._timings[operation].record(duration)

    def record_success(self, operation: str):
        """Record a successful operation"""
        if operation not in self._counters:
            self._counters[operation] = CounterMetric(operation)
        self._counters[operation].increment_success()

    def record_failure(self, operation: str):
        """Record a failed operation"""
        if operation not in self._counters:
            self._counters[operation] = CounterMetric(operation)
        self._counters[operation].increment_failure()

    def get_metrics(self) -> Dict:
        """Get all metrics"""
        # Current system state
        current_system = self._collect_system_sample()

        return {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "current": current_system,
                "history_samples": len(self._system_samples),
            },
            "timings": {
                name: metric.get_stats()
                for name, metric in self._timings.items()
            },
            "counters": {
                name: metric.get_stats()
                for name, metric in self._counters.items()
            },
        }

    def get_summary(self) -> str:
        """Get human-readable performance summary"""
        metrics = self.get_metrics()
        cpu_percent = metrics["system"]["current"].get("cpu_percent", "N/A")
        memory_percent = metrics["system"]["current"].get(
            "memory_percent",
            "N/A",
        )
        disk_percent = metrics["system"]["current"].get("disk_percent", "N/A")

        lines = [
            "📊 **Performance Summary**",
            "",
            f"🖥️ CPU: {cpu_percent}%",
            f"💾 Memory: {memory_percent}%",
            f"💿 Disk: {disk_percent}%",
            "",
            "⏱️ **Timing Stats:**",
        ]

        for name, stats in metrics["timings"].items():
            if stats["count"] > 0:
                lines.append(
                    f"  • {name}: avg={stats['avg']}s, count={stats['count']}"
                )

        lines.append("")
        lines.append("📈 **Operation Stats:**")

        for name, stats in metrics["counters"].items():
            if stats["total"] > 0:
                success = stats["success"]
                total = stats["total"]
                rate = stats["success_rate"]
                lines.append(f"  • {name}: {success}/{total} ({rate})")

        return "\n".join(lines)

    def reset(self):
        """Reset all metrics"""
        for timing in self._timings.values():
            timing.samples.clear()
            timing.total_time = 0
            timing.count = 0

        for counter in self._counters.values():
            counter.success = 0
            counter.failure = 0

        self._system_samples.clear()
        logger.info("[PERF] Metrics reset")


class TimingContext:
    """Context manager for timing operations"""

    def __init__(self, monitor: PerformanceMonitor, operation: str):
        self.monitor = monitor
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.monitor.record_timing(self.operation, duration)

        # Also record success/failure
        if exc_type is None:
            self.monitor.record_success(self.operation)
        else:
            self.monitor.record_failure(self.operation)

        return False  # Don't suppress exceptions


# Global instance
perf_monitor = PerformanceMonitor()


def timed(operation: str):
    """
    Decorator to time function execution.

    Usage:
        @timed("video_generation")
        def generate_video():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with perf_monitor.time_operation(operation):
                return func(*args, **kwargs)
        return wrapper

    return decorator
