"""
Rate Limiter Module
Thread-safe token bucket rate limiting for API calls
"""
import time
import threading
from typing import Dict
from dataclasses import dataclass, field
from .logger import logger


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit bucket"""
    requests_per_minute: int = 30
    burst_size: int = 5  # Allow slight bursts


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""
    capacity: float
    tokens: float = field(init=False)
    refill_rate: float  # tokens per second
    last_refill: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        self.tokens = self.capacity

    def consume(
        self,
        tokens: int = 1,
        blocking: bool = True,
        timeout: float = 30.0,
    ) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume
            blocking: If True, wait until tokens are available
            timeout: Maximum time to wait if blocking

        Returns:
            True if tokens were consumed, False otherwise
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            if not blocking:
                return False

            # Calculate wait time
            tokens_needed = tokens - self.tokens
            wait_time = tokens_needed / self.refill_rate

            if wait_time > timeout:
                logger.warning(
                    f"[RATE-LIMIT] Wait time {wait_time:.1f}s exceeds timeout {timeout}s"
                )
                wait_time = timeout

        # Wait outside lock
        logger.info(f"[RATE-LIMIT] Waiting {wait_time:.1f}s for rate limit")
        time.sleep(wait_time)

        # Try again after waiting
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate,
        )
        self.last_refill = now


class RateLimiter:
    """
    Global rate limiter for all API services.
    Thread-safe implementation using token bucket algorithm.
    """

    # Default rate limits per service (requests per minute)
    DEFAULT_LIMITS = {
        "pexels": RateLimitConfig(requests_per_minute=30, burst_size=5),
        "pixabay": RateLimitConfig(requests_per_minute=30, burst_size=5),
        "gemini": RateLimitConfig(requests_per_minute=15, burst_size=3),
        "apify": RateLimitConfig(requests_per_minute=10, burst_size=2),
        "telegram": RateLimitConfig(requests_per_minute=20, burst_size=5),
        "youtube": RateLimitConfig(requests_per_minute=10, burst_size=2),
        "tiktok": RateLimitConfig(requests_per_minute=10, burst_size=2),
        "default": RateLimitConfig(requests_per_minute=60, burst_size=10),
    }

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

        self._buckets: Dict[str, TokenBucket] = {}
        self._stats: Dict[str, Dict] = {}
        self._stats_lock = threading.Lock()
        self._create_buckets()
        self._initialized = True
        logger.info("[RATE-LIMIT] Rate limiter initialized")

    def _create_buckets(self):
        """Create token buckets for all services"""
        for service, config in self.DEFAULT_LIMITS.items():
            self._buckets[service] = TokenBucket(
                capacity=config.burst_size,
                refill_rate=config.requests_per_minute / 60.0,
            )
            self._stats[service] = {
                "total_requests": 0,
                "blocked_requests": 0,
                "total_wait_time": 0.0,
            }

    def acquire(
        self,
        service: str,
        blocking: bool = True,
        timeout: float = 30.0,
    ) -> bool:
        """
        Acquire permission to make an API call.

        Args:
            service: Name of the API service
            blocking: If True, wait until rate limit allows
            timeout: Maximum time to wait

        Returns:
            True if call is allowed, False if rate limited
        """
        bucket = self._buckets.get(service, self._buckets["default"])

        start_time = time.time()
        result = bucket.consume(1, blocking, timeout)
        wait_time = time.time() - start_time

        # Update stats
        with self._stats_lock:
            stats = self._stats.get(service, self._stats["default"])
            stats["total_requests"] += 1
            if not result:
                stats["blocked_requests"] += 1
            stats["total_wait_time"] += wait_time

        if not result:
            logger.warning(
                f"[RATE-LIMIT] Request to {service} was rate limited"
            )

        return result

    def get_stats(self) -> Dict[str, Dict]:
        """Get rate limiting statistics"""
        with self._stats_lock:
            return {k: v.copy() for k, v in self._stats.items()}

    def reset_stats(self):
        """Reset all statistics"""
        with self._stats_lock:
            for stats in self._stats.values():
                stats["total_requests"] = 0
                stats["blocked_requests"] = 0
                stats["total_wait_time"] = 0.0

    def set_limit(
        self,
        service: str,
        requests_per_minute: int,
        burst_size: int = 5,
    ):
        """Update rate limit for a service"""
        with self._lock:
            self._buckets[service] = TokenBucket(
                capacity=burst_size,
                refill_rate=requests_per_minute / 60.0,
            )
            if service not in self._stats:
                self._stats[service] = {
                    "total_requests": 0,
                    "blocked_requests": 0,
                    "total_wait_time": 0.0,
                }
        logger.info(
            f"[RATE-LIMIT] Updated limit for {service}: {requests_per_minute}/min"
        )


# Global instance
rate_limiter = RateLimiter()


def rate_limit(service: str, blocking: bool = True):
    """
    Decorator to rate limit function calls.

    Usage:
        @rate_limit("gemini")
        def call_gemini_api():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if rate_limiter.acquire(service, blocking):
                return func(*args, **kwargs)
            raise RateLimitExceeded(f"Rate limit exceeded for {service}")
        return wrapper

    return decorator


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded in non-blocking mode"""
    pass
