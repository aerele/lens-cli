"""HTTP client for the Lens API."""
from __future__ import annotations

import httpx

from lens_cli.config import Credentials


class LensAuthError(Exception):
    """Raised on 401/403 from the server."""


class LensNetworkError(Exception):
    """Raised when the server is unreachable or times out."""


class LensClient:
    def __init__(self, creds: Credentials, timeout: int = 15) -> None:
        self._creds = creds
        self._timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._creds.api_key}"}

    def scan(self, files: list[dict], categories: list[str] | None) -> dict:
        try:
            resp = httpx.post(
                f"{self._creds.api_url}/api/cli/scan",
                json={"files": files, "categories": categories},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except httpx.HTTPError as e:
            raise LensNetworkError(str(e)) from e
        if resp.status_code in (401, 403):
            raise LensAuthError("Authentication failed. Run `lens login`.")
        resp.raise_for_status()
        return resp.json()

    def whoami(self) -> dict:
        try:
            resp = httpx.get(
                f"{self._creds.api_url}/api/auth/me",
                headers=self._headers(),
                timeout=self._timeout,
            )
        except httpx.HTTPError as e:
            raise LensNetworkError(str(e)) from e
        if resp.status_code in (401, 403):
            raise LensAuthError("Authentication failed.")
        resp.raise_for_status()
        return resp.json()
