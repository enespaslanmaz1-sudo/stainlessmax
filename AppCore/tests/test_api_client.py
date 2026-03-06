"""
Tests for API Client Module
"""
import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import Timeout, ConnectionError, SSLError


class TestAPIClient:
    """Tests for APIClient class"""

    def test_client_initialization(self):
        """Test API client initializes correctly"""
        from lib.api_client import APIClient

        client = APIClient(retries=3, backoff_factor=0.5)
        assert client.timeout == (5, 30)
        assert client.session is not None

    def test_get_request_success(self, mock_api_response):
        """Test successful GET request"""
        from lib.api_client import APIClient

        client = APIClient()

        with patch.object(
            client.session,
            "request",
            return_value=mock_api_response(200, {"data": "test"}),
        ):
            response = client.get("https://api.example.com/test")
            assert response.status_code == 200
            assert response.json()["data"] == "test"

    def test_post_request_success(self, mock_api_response):
        """Test successful POST request"""
        from lib.api_client import APIClient

        client = APIClient()

        with patch.object(
            client.session,
            "request",
            return_value=mock_api_response(200, {"created": True}),
        ):
            response = client.post(
                "https://api.example.com/create",
                json={"name": "test"},
            )
            assert response.status_code == 200
            assert response.json()["created"] is True

    def test_http_to_https_upgrade(self):
        """Test that HTTP URLs are upgraded to HTTPS"""
        from lib.api_client import APIClient

        client = APIClient()

        with patch.object(client.session, "request") as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            mock_request.return_value.raise_for_status = MagicMock()

            # Call with HTTP URL
            client.get("http://api.example.com/test")

            # Verify it was called with HTTPS
            call_args = mock_request.call_args
            assert "https://api.example.com/test" in str(call_args)

    def test_localhost_not_upgraded(self):
        """Test that localhost URLs are not upgraded"""
        from lib.api_client import APIClient

        client = APIClient()

        with patch.object(client.session, "request") as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            mock_request.return_value.raise_for_status = MagicMock()

            client.get("http://localhost:5000/test")

            call_args = mock_request.call_args
            assert "http://localhost" in str(call_args)

    def test_timeout_handling(self):
        """Test timeout exception handling"""
        from lib.api_client import APIClient

        client = APIClient()

        with patch.object(
            client.session,
            "request",
            side_effect=Timeout("Connection timed out"),
        ):
            with pytest.raises(Timeout):
                client.get("https://api.example.com/slow")

    def test_connection_error_handling(self):
        """Test connection error handling"""
        from lib.api_client import APIClient

        client = APIClient()

        with patch.object(
            client.session,
            "request",
            side_effect=ConnectionError("Connection refused"),
        ):
            with pytest.raises(ConnectionError):
                client.get("https://api.example.com/unreachable")

    def test_ssl_error_handling(self):
        """Test SSL error handling"""
        from lib.api_client import APIClient

        client = APIClient()

        with patch.object(
            client.session,
            "request",
            side_effect=SSLError("Certificate verify failed"),
        ):
            with pytest.raises(SSLError):
                client.get("https://api.example.com/bad-cert")

    def test_default_timeout_applied(self):
        """Test that default timeout is applied"""
        from lib.api_client import APIClient

        client = APIClient(timeout=(10, 60))

        with patch.object(client.session, "request") as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            mock_request.return_value.raise_for_status = MagicMock()

            client.get("https://api.example.com/test")

            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs.get("timeout") == (10, 60)
