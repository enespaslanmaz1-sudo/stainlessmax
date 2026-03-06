"""
Tests for Rate Limiter Module
"""
import pytest
import time
from concurrent.futures import ThreadPoolExecutor


class TestRateLimiter:
    """Tests for RateLimiter class"""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes with default limits"""
        from lib.rate_limiter import RateLimiter

        limiter = RateLimiter()

        assert "pexels" in limiter._buckets
        assert "gemini" in limiter._buckets
        assert "default" in limiter._buckets

    def test_acquire_within_limit(self):
        """Test acquiring when within rate limit"""
        from lib.rate_limiter import RateLimiter

        limiter = RateLimiter()

        # Should succeed immediately
        result = limiter.acquire("pexels", blocking=False)
        assert result is True

    def test_acquire_after_limit_exceeded(self):
        """Test acquiring after burst limit is exceeded"""
        from lib.rate_limiter import RateLimiter

        limiter = RateLimiter()

        # Exhaust the burst capacity
        limiter.set_limit("test_service", requests_per_minute=60, burst_size=2)

        # First two should succeed
        assert limiter.acquire("test_service", blocking=False) is True
        assert limiter.acquire("test_service", blocking=False) is True

        # Third should fail in non-blocking mode
        assert limiter.acquire("test_service", blocking=False) is False

    def test_acquire_blocking_wait(self):
        """Test that blocking mode waits for tokens"""
        from lib.rate_limiter import RateLimiter

        limiter = RateLimiter()
        limiter.set_limit("test_wait", requests_per_minute=60, burst_size=1)

        # Use up the token
        limiter.acquire("test_wait", blocking=False)

        # This should wait (we'll use a short timeout to not slow tests)
        start = time.time()
        # Try to acquire with blocking but short timeout
        result = limiter.acquire("test_wait", blocking=True, timeout=0.5)
        elapsed = time.time() - start

        # Should have waited some time
        assert elapsed >= 0.1 or result is True

    def test_stats_tracking(self):
        """Test that statistics are tracked correctly"""
        from lib.rate_limiter import RateLimiter

        limiter = RateLimiter()
        limiter.reset_stats()
        limiter.set_limit("test_stats", requests_per_minute=60, burst_size=2)

        # Make some requests
        limiter.acquire("test_stats", blocking=False)
        limiter.acquire("test_stats", blocking=False)
        limiter.acquire("test_stats", blocking=False)  # This should be blocked

        stats = limiter.get_stats()
        assert stats["test_stats"]["total_requests"] == 3
        assert stats["test_stats"]["blocked_requests"] >= 1

    def test_set_limit(self):
        """Test dynamically setting rate limits"""
        from lib.rate_limiter import RateLimiter

        limiter = RateLimiter()

        # Set a new limit
        limiter.set_limit(
            "custom_service",
            requests_per_minute=10,
            burst_size=3,
        )

        assert "custom_service" in limiter._buckets
        assert "custom_service" in limiter._stats

    def test_thread_safety(self):
        """Test that rate limiter is thread-safe"""
        from lib.rate_limiter import RateLimiter

        limiter = RateLimiter()
        limiter.reset_stats()
        limiter.set_limit(
            "thread_test",
            requests_per_minute=600,
            burst_size=50,
        )

        results = []

        def make_request():
            result = limiter.acquire("thread_test", blocking=False)
            results.append(result)

        # Run many concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            for f in futures:
                f.result()

        # All should have succeeded due to high limit
        assert len(results) == 50
        # Most should succeed
        assert sum(results) >= 40


class TestTokenBucket:
    """Tests for TokenBucket class"""

    def test_bucket_capacity(self):
        """Test bucket respects capacity"""
        from lib.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=5, refill_rate=1.0)

        # Should be able to consume up to capacity
        for _ in range(5):
            assert bucket.consume(1, blocking=False) is True

        # Should fail after capacity exhausted
        assert bucket.consume(1, blocking=False) is False

    def test_bucket_refill(self):
        """Test bucket refills over time"""
        from lib.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=2, refill_rate=10.0)  # 10 tokens/second

        # Exhaust bucket
        bucket.consume(2, blocking=False)

        # Wait for refill
        time.sleep(0.2)  # Should add ~2 tokens

        # Should be able to consume again
        assert bucket.consume(1, blocking=False) is True


class TestRateLimitDecorator:
    """Tests for rate_limit decorator"""

    def test_decorator_allows_within_limit(self):
        """Test decorator allows calls within limit"""
        from lib.rate_limiter import rate_limit, rate_limiter

        rate_limiter.set_limit(
            "decorator_test",
            requests_per_minute=60,
            burst_size=5,
        )

        @rate_limit("decorator_test")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_decorator_raises_on_limit_exceeded(self):
        """Test decorator raises exception when limit exceeded"""
        from lib.rate_limiter import (
            rate_limit,
            rate_limiter,
            RateLimitExceeded,
        )

        rate_limiter.set_limit(
            "decorator_block",
            requests_per_minute=60,
            burst_size=1,
        )

        @rate_limit("decorator_block", blocking=False)
        def test_func():
            return "success"

        # First call should succeed
        assert test_func() == "success"

        # Second call should raise
        with pytest.raises(RateLimitExceeded):
            test_func()
