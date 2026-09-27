"""LoopbackBrowserGuardMiddleware — browser pages must not inherit loopback trust.

Loopback peers need no credential, so a website open in the user's browser
could previously drive the local API: DNS rebinding (foreign Host) gave full
read/write, and blind cross-site requests (form POST, <img>, WebSocket) could
e.g. hit ``/system/network/enable`` to open a PIN-only 0.0.0.0 listener.
"""
import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import pytest
from starlette.websockets import WebSocketDisconnect

REJECTED = "browser origin rejected"


@pytest.fixture(autouse=True)
def _strict_hosts(monkeypatch):
    # conftest allows the TestClient's "testserver" host; this suite tests the
    # real policy, so start from nothing configured.
    for name in (
        "OMNIVOICE_ALLOWED_HOSTS",
        "OMNIVOICE_MCP_ALLOWED_HOSTS",
        "OMNIVOICE_ALLOWED_ORIGINS",
        "OMNIVOICE_UI_PORT",
    ):
        monkeypatch.delenv(name, raising=False)


def _client(host="127.0.0.1:3900", peer=("127.0.0.1", 1)):
    from fastapi.testclient import TestClient
    from main import app

    # Host is sent as a header: TestClient cannot parse IPv6 netlocs.
    return TestClient(
        app, client=peer, base_url="http://127.0.0.1:3900", headers={"host": host}
    )


def _rejected(response) -> bool:
    return response.status_code == 403 and response.json().get("detail") == REJECTED


# ── Host (DNS rebinding) ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1:3900",
        "localhost:3900",
        "localhost",
        "[::1]:3900",
        "app.localhost:3900",
        "gpu-box.tailnet-1234.ts.net",
    ],
)
def test_loopback_and_builtin_hosts_pass(host):
    assert not _rejected(_client(host).get("/system/info"))


@pytest.mark.parametrize(
    "host",
    ["rebind.attacker.example:3900", "127.0.0.1.attacker.example", "ts.net.evil.example"],
)
def test_foreign_host_on_loopback_is_rejected(host):
    assert _rejected(_client(host).get("/system/info"))


def test_malformed_host_is_rejected():
    c = _client()
    assert _rejected(c.get("/system/info", headers={"host": "127.0.0.1:not-a-port"}))
    assert _rejected(c.get("/system/info", headers={"host": "user@127.0.0.1"}))


def test_missing_host_passes():
    # Browsers always send Host; HTTP/1.0 tools and raw ASGI callers may not.
    assert not _rejected(_client().get("/system/info", headers={"host": ""}))


def test_configured_hosts_extend_the_allowlist(monkeypatch):
    monkeypatch.setenv("OMNIVOICE_ALLOWED_HOSTS", "studio.lan:3900, *.corp.example")
    monkeypatch.setenv("OMNIVOICE_MCP_ALLOWED_HOSTS", "host.docker.internal:*")
    for host in ("studio.lan:3900", "voice.corp.example", "host.docker.internal:3900"):
        assert not _rejected(_client(host).get("/system/info")), host
    assert _rejected(_client("corp.example.evil").get("/system/info"))


def test_non_loopback_peers_are_not_host_checked():
    # LAN / Docker clients are governed by the PIN / API-key gates instead.
    r = _client("rebind.attacker.example", peer=("10.0.0.5", 1)).get("/system/info")
    assert not _rejected(r)


# ── Origin / Sec-Fetch-Site (cross-site requests) ───────────────────────────


def test_cross_site_post_cannot_open_the_lan_share():
    from services import network_share

    r = _client().post(
        "/system/network/enable", headers={"origin": "https://attacker.example"}
    )
    assert _rejected(r)
    assert not network_share._runtime.state.enabled


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "http://localhost:5173"])
def test_foreign_origin_is_rejected(origin):
    assert _rejected(_client().get("/system/info", headers={"origin": origin}))


@pytest.mark.parametrize(
    "origin",
    [
        "app://voicestudio",  # Electron renderer
        "http://localhost:3901",  # dev UI
        "http://127.0.0.1:3900",  # same-origin (backend-served UI)
    ],
)
def test_app_origins_pass(origin):
    assert not _rejected(_client().get("/system/info", headers={"origin": origin}))


def test_cross_site_request_without_origin_is_rejected():
    # <img src> / top-level GETs carry no Origin but are marked by the browser.
    r = _client().get("/system/info", headers={"sec-fetch-site": "cross-site"})
    assert _rejected(r)


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
def test_non_cross_site_fetch_metadata_passes(site):
    assert not _rejected(_client().get("/system/info", headers={"sec-fetch-site": site}))


def test_non_browser_client_passes():
    # CLIs, MCP agents, the native helper and Electron's main-process proxy
    # send neither Origin nor Sec-Fetch-Site.
    assert not _rejected(_client().get("/system/info"))


def test_cross_site_websocket_is_closed():
    c = _client()
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with c.websocket_connect(
            "/ws/events", headers={"origin": "https://attacker.example"}
        ):
            pass
    assert exc_info.value.code == 1008


def test_rebound_websocket_is_closed():
    c = _client("rebind.attacker.example:3900")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with c.websocket_connect("/ws/tts"):
            pass
    assert exc_info.value.code == 1008
