"""
Tests for Automation Engine Module
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import json
import tempfile
from datetime import datetime
from hypothesis import HealthCheck, given, settings, strategies as st


class TestAutomationEngineStats:
    """Tests for AutomationEngine stats handling"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def automation_engine(self, temp_dir):
        """Create AutomationEngine instance with temp directory"""
        from lib.automation_engine import AutomationEngine
        
        # Mock the imports that might not be available
        with patch('lib.automation_engine.logger', MagicMock()), \
             patch('lib.automation_engine.handle_error', MagicMock()), \
             patch('lib.automation_engine.HesaplarParser', None):
            
            engine = AutomationEngine(base_dir=temp_dir / "System")
            engine.queue_dir.mkdir(parents=True, exist_ok=True)
            return engine

    @settings(
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
        max_examples=25,
    )
    @given(
        total_produced=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
        total_uploaded=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
        total_failed=st.one_of(st.none(), st.integers(min_value=0, max_value=10000))
    )
    def test_property_stats_dictionary_default_values(
        self, automation_engine, total_produced, total_uploaded, total_failed
    ):
        """
        **Property 1: Stats Dictionary Default Values**
        **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
        
        For any missing key in the stats dictionary (total_uploaded, total_produced, 
        total_failed), the get_status() method should return a default value of 0 
        without raising a KeyError.
        """
        # Arrange: Create stats dictionary with randomly missing keys
        stats_dict = {}
        if total_produced is not None:
            stats_dict["total_produced"] = total_produced
        if total_uploaded is not None:
            stats_dict["total_uploaded"] = total_uploaded
        if total_failed is not None:
            stats_dict["total_failed"] = total_failed
        
        # Set the stats dictionary (may have missing keys)
        automation_engine.stats = stats_dict
        
        # Act: Call get_status() - should not raise KeyError
        try:
            status = automation_engine.get_status()
        except KeyError as e:
            pytest.fail(f"get_status() raised KeyError for missing key: {e}")
        
        # Assert: Verify all expected fields are present with default values
        assert "stats" in status, "Response should contain 'stats' field"
        assert "total_produced" in status["stats"], "Stats should contain 'total_produced'"
        assert "total_uploaded" in status["stats"], "Stats should contain 'total_uploaded'"
        assert "total_failed" in status["stats"], "Stats should contain 'total_failed'"
        
        # Verify default values are used when keys are missing
        expected_produced = total_produced if total_produced is not None else 0
        expected_uploaded = total_uploaded if total_uploaded is not None else 0
        expected_failed = total_failed if total_failed is not None else 0
        
        assert status["stats"]["total_produced"] == expected_produced, \
            f"total_produced should be {expected_produced}, got {status['stats']['total_produced']}"
        assert status["stats"]["total_uploaded"] == expected_uploaded, \
            f"total_uploaded should be {expected_uploaded}, got {status['stats']['total_uploaded']}"
        assert status["stats"]["total_failed"] == expected_failed, \
            f"total_failed should be {expected_failed}, got {status['stats']['total_failed']}"

    def test_get_status_with_empty_stats(self, automation_engine):
        """Test get_status() with completely empty stats dictionary"""
        # Arrange: Empty stats
        automation_engine.stats = {}
        
        # Act
        status = automation_engine.get_status()
        
        # Assert: All stats should default to 0
        assert status["stats"]["total_produced"] == 0
        assert status["stats"]["total_uploaded"] == 0
        assert status["stats"]["total_failed"] == 0

    def test_get_status_with_partial_stats(self, automation_engine):
        """Test get_status() with partially populated stats dictionary"""
        # Arrange: Only some stats present
        automation_engine.stats = {
            "total_produced": 42,
            # total_uploaded missing
            "total_failed": 3
        }
        
        # Act
        status = automation_engine.get_status()
        
        # Assert
        assert status["stats"]["total_produced"] == 42
        assert status["stats"]["total_uploaded"] == 0  # Should default to 0
        assert status["stats"]["total_failed"] == 3

    def test_get_status_with_all_stats(self, automation_engine):
        """Test get_status() with all stats present"""
        # Arrange
        automation_engine.stats = {
            "total_produced": 100,
            "total_uploaded": 95,
            "total_failed": 5
        }
        
        # Act
        status = automation_engine.get_status()
        
        # Assert
        assert status["stats"]["total_produced"] == 100
        assert status["stats"]["total_uploaded"] == 95
        assert status["stats"]["total_failed"] == 5

    def test_get_status_response_structure(self, automation_engine):
        """Test that get_status() returns the expected response structure"""
        # Act
        status = automation_engine.get_status()
        
        # Assert: Verify complete response structure
        assert "active" in status
        assert "queue" in status
        assert "stats" in status
        assert "accounts" in status
        assert "target" in status
        assert "recent_jobs" in status
        
        # Verify queue structure
        assert "pending" in status["queue"]
        assert "generating" in status["queue"]
        assert "ready" in status["queue"]
        assert "uploading" in status["queue"]
        assert "uploaded" in status["queue"]
        assert "failed" in status["queue"]
        assert "total" in status["queue"]
        
        # Verify stats structure
        assert "total_produced" in status["stats"]
        assert "total_uploaded" in status["stats"]
        assert "total_failed" in status["stats"]
        assert "today_produced" in status["stats"]
