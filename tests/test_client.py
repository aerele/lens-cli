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
