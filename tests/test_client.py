import pytest

from lens_cli.client import LensAuthError, LensClient, LensNetworkError
from lens_cli.config import Credentials


def test_scan_posts_and_returns(httpx_mock):
    httpx_mock.add_response(
        url="https://x/api/cli/scan",
        json={"findings": [], "scan_mode": "changed-files", "engine_version": "static"},
    )
    c = LensClient(Credentials("https://x", "lens_pat_abc"), timeout=5)
    out = c.scan([{"path": "a.py", "content": "x=1\n"}], categories=None)

    assert out["scan_mode"] == "changed-files"
    req = httpx_mock.get_requests()[0]
    assert req.headers["Authorization"] == "Bearer lens_pat_abc"


def test_scan_401_raises_auth(httpx_mock):
    httpx_mock.add_response(url="https://x/api/cli/scan", status_code=401, json={"detail": "nope"})
    c = LensClient(Credentials("https://x", "bad"), timeout=5)
    with pytest.raises(LensAuthError):
        c.scan([], categories=None)


def test_scan_network_error(httpx_mock):
    import httpx

    httpx_mock.add_exception(httpx.ConnectError("down"))
    c = LensClient(Credentials("https://x", "k"), timeout=5)
    with pytest.raises(LensNetworkError):
        c.scan([], categories=None)


def test_scan_500_raises_network_not_auth(httpx_mock):
    # A reachable-but-failing server (5xx) is a scan failure -> LensNetworkError,
    # so the CLI's fail-open logic decides (not swallowed, not an auth error).
    httpx_mock.add_response(url="https://x/api/cli/scan", status_code=500, json={"detail": "boom"})
    c = LensClient(Credentials("https://x", "k"), timeout=5)
    with pytest.raises(LensNetworkError):
        c.scan([], categories=None)


def test_whoami_normalizes_nested_profile_response(httpx_mock):
    """Current Lens servers return the profile under the ``user`` key."""
    httpx_mock.add_response(
        url="https://x/api/auth/me",
        json={"user": {"email": "user@example.com"}, "billing_enabled": True},
    )
    c = LensClient(Credentials("https://x", "lens_pat_abc"), timeout=5)

    assert c.whoami()["email"] == "user@example.com"


def test_whoami_keeps_legacy_top_level_profile_response(httpx_mock):
    """Remain compatible with self-hosted servers using the old response."""
    httpx_mock.add_response(
        url="https://x/api/auth/me",
        json={"email": "legacy@example.com"},
    )
    c = LensClient(Credentials("https://x", "lens_pat_abc"), timeout=5)

    assert c.whoami()["email"] == "legacy@example.com"


def test_scan_401_uses_server_detail(httpx_mock):
    httpx_mock.add_response(
        url="https://x/api/cli/scan", status_code=401, json={"detail": "Invalid or revoked API key"}
    )
    c = LensClient(Credentials("https://x", "bad"), timeout=5)
    with pytest.raises(LensAuthError, match="Invalid or revoked API key. Run `lens login`."):
        c.scan([], categories=None)


@pytest.mark.parametrize(
    "detail",
    ["Too many files (max 300).", "Payload too large."],
)
def test_scan_413_names_the_limit(httpx_mock, detail):
    httpx_mock.add_response(url="https://x/api/cli/scan", status_code=413, json={"detail": detail})
    c = LensClient(Credentials("https://x", "k"), timeout=5)
    with pytest.raises(LensNetworkError, match="rejected the scan") as exc:
        c.scan([], categories=None)
    assert detail.rstrip(".") in str(exc.value)
    assert "ignore" in str(exc.value)


def test_scan_429_reports_retry_after(httpx_mock):
    httpx_mock.add_response(
        url="https://x/api/cli/scan",
        status_code=429,
        headers={"Retry-After": "12"},
        json={"detail": "Scan rate limit reached. Try again shortly."},
    )
    c = LensClient(Credentials("https://x", "k"), timeout=5)
    with pytest.raises(LensNetworkError, match="rate limit reached; retry in 12s"):
        c.scan([], categories=None)


def test_scan_429_without_retry_after(httpx_mock):
    httpx_mock.add_response(url="https://x/api/cli/scan", status_code=429, json={"detail": "x"})
    c = LensClient(Credentials("https://x", "k"), timeout=5)
    with pytest.raises(LensNetworkError, match="try again shortly"):
        c.scan([], categories=None)


def test_scan_500_includes_detail(httpx_mock):
    httpx_mock.add_response(url="https://x/api/cli/scan", status_code=500, json={"detail": "Scan failed."})
    c = LensClient(Credentials("https://x", "k"), timeout=5)
    with pytest.raises(LensNetworkError, match="HTTP 500: Scan failed"):
        c.scan([], categories=None)


def test_scan_error_without_json_body(httpx_mock):
    httpx_mock.add_response(url="https://x/api/cli/scan", status_code=502, text="<html>bad gateway</html>")
    c = LensClient(Credentials("https://x", "k"), timeout=5)
    with pytest.raises(LensNetworkError, match=r"^server returned HTTP 502$"):
        c.scan([], categories=None)
