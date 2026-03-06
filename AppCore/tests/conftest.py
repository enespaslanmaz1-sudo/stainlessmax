"""
Pytest Configuration and Fixtures
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    from lib.config_manager import APIConfig, PlatformConfig

    config = MagicMock()
    config.api_keys = APIConfig(
        pexels="test_pexels_key",
        pixabay="test_pixabay_key",
        gemini="AIzaTestGeminiKey",
        telegram_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        telegram_admin="123456789",
        apify="test_apify_token",
    )
    config.youtube = PlatformConfig(
        client_id="test_youtube_client",
        client_secret="test_youtube_secret",
        daily_limit=10,
        interval_hours=4,
    )
    config.tiktok = PlatformConfig(
        client_id="test_tiktok_client",
        client_secret="test_tiktok_secret",
        daily_limit=5,
        interval_hours=8,
    )
    config.n8n = {"url": "", "webhook_id": "", "sheets_id": ""}

    return config


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Temporary directory for cache testing"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def mock_api_response():
    """Mock API response factory"""
    def _create_response(status_code=200, json_data=None):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = str(json_data)
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            from requests.exceptions import HTTPError
            response.raise_for_status.side_effect = HTTPError()
        return response
    return _create_response


@pytest.fixture
def sample_viral_trends():
    """Sample viral trends data"""
    return [
        {"title": "Test Trend 1", "platform": "youtube"},
        {"title": "Test Trend 2", "platform": "youtube"},
        {"title": "Test Trend 3", "platform": "tiktok"},
    ]


@pytest.fixture
def sample_scenario():
    """Sample video scenario"""
    return {
        "title": "Test Video Title 🎬",
        "script": "This is a test script for video generation. " * 20,
        "topics": ["test", "video", "generation", "demo"]
    }


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests"""
    yield

    # Reset rate limiter
    from lib.rate_limiter import RateLimiter
    RateLimiter._instance = None

    # Reset cache manager
    from lib.cache_manager import CacheManager
    CacheManager._instance = None

    # Reset performance monitor
    from lib.performance_monitor import PerformanceMonitor
    PerformanceMonitor._instance = None


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for external command testing"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield mock_run
