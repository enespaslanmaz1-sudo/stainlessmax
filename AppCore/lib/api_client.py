"""
Secure API Client with retry mechanism and SSL enforcement
"""
import requests
from typing import Tuple
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urlunparse


class APIClient:
    """Secure API client with retry mechanism and SSL enforcement"""

    def __init__(
        self,
        timeout: Tuple[int, int] = (5, 30),
        retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.timeout = timeout
        self.session = requests.Session()

        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.session.headers.update(
            {
                "User-Agent": "VideoPROAI/1.0 (Secure Client)",
                "Accept": "application/json",
                "Connection": "close",
            }
        )

    def _upgrade_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme == "http":
            hostname = parsed.hostname or ""
            if hostname not in ("localhost", "127.0.0.1"):
                return urlunparse(parsed._replace(scheme="https"))
        return url

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        url = self._upgrade_url(url)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", True)
        return self.session.request(method, url, **kwargs)

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> requests.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        return self.request("DELETE", url, **kwargs)

    def close(self):
        self.session.close()


class SecureAPIClient(APIClient):
    """Backwards compatible alias for APIClient"""


# Global API client instance
api = SecureAPIClient()
