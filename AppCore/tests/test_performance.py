"""
Tests for Performance Monitor Module
"""
import pytest
import time


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor class"""

    def test_initialization(self):
        """Test performance monitor initialization"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        assert "video_generation" in monitor._timings
        assert "video_generation" in monitor._counters

    def test_record_timing(self):
        """Test recording timing metrics"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        monitor.record_timing("test_operation", 1.5)
        monitor.record_timing("test_operation", 2.0)
        monitor.record_timing("test_operation", 1.0)

        stats = monitor._timings["test_operation"].get_stats()

        assert stats["count"] == 3
        assert stats["min"] == 1.0
        assert stats["max"] == 2.0
        assert 1.4 <= stats["avg"] <= 1.6  # ~1.5 average

    def test_record_success_failure(self):
        """Test recording success/failure counts"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        monitor.record_success("test_counter")
        monitor.record_success("test_counter")
        monitor.record_failure("test_counter")

        stats = monitor._counters["test_counter"].get_stats()

        assert stats["success"] == 2
        assert stats["failure"] == 1
        assert stats["total"] == 3
        assert "66" in stats["success_rate"]  # ~66.7%

    def test_timing_context_manager(self):
        """Test timing context manager"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        with monitor.time_operation("context_test"):
            time.sleep(0.1)

        stats = monitor._timings["context_test"].get_stats()

        assert stats["count"] == 1
        assert stats["avg"] >= 0.1

    def test_timing_context_records_success(self):
        """Test that context manager records success on normal exit"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        with monitor.time_operation("success_test"):
            pass

        stats = monitor._counters["success_test"].get_stats()
        assert stats["success"] == 1
        assert stats["failure"] == 0

    def test_timing_context_records_failure(self):
        """Test that context manager records failure on exception"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        with pytest.raises(ValueError):
            with monitor.time_operation("failure_test"):
                raise ValueError("Test error")

        stats = monitor._counters["failure_test"].get_stats()
        assert stats["failure"] == 1

    def test_get_metrics(self):
        """Test getting all metrics"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        monitor.record_timing("api_gemini", 0.5)
        monitor.record_success("api_calls")

        metrics = monitor.get_metrics()

        assert "timestamp" in metrics
        assert "system" in metrics
        assert "timings" in metrics
        assert "counters" in metrics
        assert "api_gemini" in metrics["timings"]

    def test_get_summary(self):
        """Test getting human-readable summary"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        monitor.record_timing("video_generation", 30.0)
        monitor.record_success("video_generation")

        summary = monitor.get_summary()

        assert "Performance Summary" in summary
        assert "CPU" in summary
        assert "Memory" in summary

    def test_reset(self):
        """Test resetting all metrics"""
        from lib.performance_monitor import PerformanceMonitor

        monitor = PerformanceMonitor()

        monitor.record_timing("test", 1.0)
        monitor.record_success("test")

        monitor.reset()

        assert monitor._timings["test"].count == 0
        assert monitor._counters["test"].success == 0


class TestTimedDecorator:
    """Tests for timed decorator"""

    def test_decorator_times_function(self):
        """Test that decorator records timing"""
        from lib.performance_monitor import timed, perf_monitor

        @timed("decorated_function")
        def slow_function():
            time.sleep(0.1)
            return "done"

        result = slow_function()

        assert result == "done"

        stats = perf_monitor._timings["decorated_function"].get_stats()
        assert stats["count"] >= 1
        assert stats["avg"] >= 0.1

    def test_decorator_records_success(self):
        """Test that decorator records success"""
        from lib.performance_monitor import timed, perf_monitor

        @timed("success_decorated")
        def successful_function():
            return "success"

        successful_function()

        stats = perf_monitor._counters["success_decorated"].get_stats()
        assert stats["success"] >= 1

    def test_decorator_records_failure(self):
        """Test that decorator records failure on exception"""
        from lib.performance_monitor import timed, perf_monitor

        @timed("failure_decorated")
        def failing_function():
            raise RuntimeError("Failed")

        with pytest.raises(RuntimeError):
            failing_function()

        stats = perf_monitor._counters["failure_decorated"].get_stats()
        assert stats["failure"] >= 1


class TestTimingMetric:
    """Tests for TimingMetric class"""

    def test_record_samples(self):
        """Test recording timing samples"""
        from lib.performance_monitor import TimingMetric

        metric = TimingMetric(name="test")

        metric.record(1.0)
        metric.record(2.0)
        metric.record(3.0)

        stats = metric.get_stats()

        assert stats["count"] == 3
        assert stats["min"] == 1.0
        assert stats["max"] == 3.0
        assert stats["avg"] == 2.0

    def test_sample_limit(self):
        """Test that samples are limited (LRU)"""
        from lib.performance_monitor import TimingMetric
        from collections import deque

        metric = TimingMetric(name="test")
        metric.samples = deque(maxlen=5)  # Override for test

        # Add more than limit
        for i in range(10):
            metric.record(float(i))

        assert len(metric.samples) == 5
        assert metric.count == 10


class TestCounterMetric:
    """Tests for CounterMetric class"""

    def test_increment_success(self):
        """Test incrementing success counter"""
        from lib.performance_monitor import CounterMetric

        counter = CounterMetric(name="test")

        counter.increment_success()
        counter.increment_success()

        assert counter.success == 2
        assert counter.failure == 0

    def test_increment_failure(self):
        """Test incrementing failure counter"""
        from lib.performance_monitor import CounterMetric

        counter = CounterMetric(name="test")

        counter.increment_failure()

        assert counter.failure == 1
        assert counter.success == 0

    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        from lib.performance_monitor import CounterMetric

        counter = CounterMetric(name="test")

        counter.success = 3
        counter.failure = 1

        stats = counter.get_stats()

        assert stats["total"] == 4
        assert "75" in stats["success_rate"]  # 75%
