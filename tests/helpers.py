"""Shared test doubles for code that talks to the network."""

import json
from typing import Any

import requests


def make_response(body: Any = "", status: int = 200, encoding: str | None = "utf-8") -> requests.Response:
    """Builds a real requests.Response around a string, bytes or JSON-serialisable body."""
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    if isinstance(body, str):
        body = body.encode("utf-8")

    response = requests.Response()
    response.status_code = status
    response._content = body
    response.encoding = encoding
    return response


class FakeSession:
    """Stands in for requests.Session: answers from canned routes and records every call.

    `routes` maps a URL fragment to a body, an exception to raise, or a callable
    taking (url, **kwargs) that returns a body. The first fragment found in the
    requested URL wins; anything else gets a 404.
    """

    def __init__(self, routes: dict[str, Any] | None = None, encoding: str | None = "utf-8"):
        self.routes = routes or {}
        self.encoding = encoding
        self.calls: list[dict[str, Any]] = []

    def _answer(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        for fragment, body in self.routes.items():
            if fragment not in url:
                continue
            if callable(body):
                body = body(url, **kwargs)
            if isinstance(body, Exception):
                raise body
            if isinstance(body, requests.Response):
                return body
            return make_response(body, encoding=self.encoding)
        return make_response("not found", status=404)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self._answer("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self._answer("POST", url, **kwargs)
