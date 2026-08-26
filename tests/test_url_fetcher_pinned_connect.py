from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from scp.core import url_fetcher


@pytest.fixture(autouse=True)
def _allow_local_fixture_egress(monkeypatch):
    monkeypatch.setenv("SCP_EGRESS_MODE", "allow")


class _Handler(BaseHTTPRequestHandler):
    observed_host = ""

    def do_GET(self):
        type(self).observed_host = self.headers.get("Host", "")
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://trusted-two.example:{self.server.server_address[1]}/final")
            self.end_headers()
            return
        body = b"pinned-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *args):
        return


def test_fetch_connects_to_validated_ip_and_preserves_hostname(monkeypatch) -> None:
    _Handler.observed_host = ""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(url_fetcher, "_resolve_public_ips", lambda _hostname: ("127.0.0.1",))
        port = server.server_address[1]
        body = url_fetcher._safe_fetch_url(f"http://trusted.example:{port}/resource", timeout=2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert body == b"pinned-ok"
    assert _Handler.observed_host == f"trusted.example:{port}"


def test_redirect_revalidates_and_repins_new_hostname(monkeypatch) -> None:
    _Handler.observed_host = ""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(url_fetcher, "_resolve_public_ips", lambda _hostname: ("127.0.0.1",))
        port = server.server_address[1]
        body = url_fetcher._safe_fetch_url(f"http://trusted-one.example:{port}/redirect", timeout=2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert body == b"pinned-ok"
    assert _Handler.observed_host == f"trusted-two.example:{port}"


def test_redirect_to_metadata_is_blocked_before_connection(monkeypatch) -> None:
    _Handler.observed_host = ""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def resolve(hostname: str):
            if hostname == "169.254.169.254":
                raise ValueError("host resolves to disallowed IP range")
            return ("127.0.0.1",)

        monkeypatch.setattr(url_fetcher, "_resolve_public_ips", resolve)
        # Make this redirect response point to the metadata address.
        original_do_get = _Handler.do_GET
        def metadata_redirect(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.end_headers()
                return
            original_do_get(self)
        monkeypatch.setattr(_Handler, "do_GET", metadata_redirect)
        port = server.server_address[1]
        try:
            url_fetcher._safe_fetch_url(f"http://trusted-one.example:{port}/redirect", timeout=2)
        except ValueError as exc:
            assert "disallowed" in str(exc)
        else:
            raise AssertionError("metadata redirect was not blocked")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_resolver_rejects_any_private_address_in_mixed_dns_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        url_fetcher.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("93.184.216.34", 0)),
            (2, 1, 6, "", ("169.254.169.254", 0)),
        ],
    )
    try:
        url_fetcher._resolve_public_ips("mixed.example")
    except ValueError as exc:
        assert "disallowed" in str(exc)
    else:
        raise AssertionError("mixed public/private DNS answer was accepted")
