"""HTTP client for the Lens API."""
from __future__ import annotations

import httpx

from lens_cli.config import Credentials


class LensAuthError(Exception):
    """Raised on 401/403 from the server."""


class LensNetworkError(Exception):
    """Raised when the server is unreachable or times out."""


def _detail(resp: httpx.Response) -> str:
    """The server's ``{"detail": "..."}`` message, or "" if there isn't one."""
    try:
        detail = resp.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detail.rstrip(".") if isinstance(detail, str) else ""


def _raise_for_status(resp: httpx.Response, auth_hint: str = "") -> None:
    """Map an error response to a LensAuthError / LensNetworkError with a useful message."""
    if resp.is_success:
        return
    detail = _detail(resp)
    status = resp.status_code
    if status in (401, 403):
        raise LensAuthError(f"{detail or 'Authentication failed'}.{auth_hint}")
    # A reachable-but-failing server (5xx, 429, 413, ...). Treat as a scan
    # failure, not a client bug, so the CLI's fail-open logic decides.
    if status == 413:
        msg = (
            f"server rejected the scan ({detail or 'payload too large'}). "
            "Stage fewer files or add paths to `ignore` in .lens.yml"
        )
    elif status == 429:
        retry = resp.headers.get("Retry-After")
        wait = f"retry in {retry}s" if retry and retry.isdigit() else "try again shortly"
        msg = f"Lens rate limit reached; {wait}"
    else:
        msg = f"server returned HTTP {status}" + (f": {detail}" if detail else "")
    raise LensNetworkError(msg)


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
        _raise_for_status(resp, auth_hint=" Run `lens login`.")
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
        _raise_for_status(resp)
        data = resp.json()
        # Current Lens servers wrap account fields in ``user`` alongside
        # feature flags. Older/self-hosted servers returned the profile at the
        # top level, so normalize the current shape without breaking either.
        if isinstance(data, dict) and isinstance(data.get("user"), dict):
            return data["user"]
        return data
