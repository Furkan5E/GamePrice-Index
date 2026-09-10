import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from gameprice_index import config
from gameprice_index.http_client import build_session, fetch


class FlakyHandler(BaseHTTPRequestHandler):
    """Fails with a 503 for the first few requests, then answers normally."""

    failures_left = 0
    hits = 0

    def do_GET(self):
        cls = type(self)
        cls.hits += 1
        if cls.failures_left > 0:
            cls.failures_left -= 1
            self.send_response(503)
            self.end_headers()
            return

        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep test output quiet


@pytest.fixture
def flaky_server():
    FlakyHandler.failures_left = 0
    FlakyHandler.hits = 0
    server = HTTPServer(("127.0.0.1", 0), FlakyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()
    server.server_close()


def test_session_sends_default_headers():
    session = build_session()

    assert session.headers["User-Agent"] == config.REQUEST_HEADERS["User-Agent"]


def test_fetch_retries_server_errors(flaky_server):
    """Two 503s followed by a 200 should succeed on the third attempt."""
    FlakyHandler.failures_left = 2
    session = build_session(retries=3, backoff_factor=0)

    response = fetch(flaky_server, session=session)

    assert response.text == "ok"
    assert FlakyHandler.hits == 3


def test_fetch_raises_once_retries_are_exhausted(flaky_server):
    FlakyHandler.failures_left = 10
    session = build_session(retries=2, backoff_factor=0)

    with pytest.raises(requests.HTTPError):
        fetch(flaky_server, session=session)

    assert FlakyHandler.hits == 3  # the first try plus two retries


def test_fetch_applies_default_timeout():
    seen = {}

    class FakeSession:
        def get(self, url, **kwargs):
            seen.update(kwargs)
            response = requests.Response()
            response.status_code = 200
            return response

    fetch("https://example.test", session=FakeSession())

    assert seen["timeout"] == config.REQUEST_TIMEOUT
