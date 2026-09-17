"""A shared requests session that retries transient failures with backoff."""

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gameprice_index import config

logger = logging.getLogger(__name__)


def build_session(
    retries: int = config.REQUEST_RETRIES,
    backoff_factor: float = config.REQUEST_BACKOFF,
) -> requests.Session:
    """Returns a session that retries timeouts, rate limits and server errors.

    Waits grow exponentially (backoff_factor * 2 ** attempt) and a Retry-After
    header from the server takes priority when one is sent.
    """
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=config.REQUEST_RETRY_STATUSES,
        # every POST this project sends is a read-only catalogue query, so repeating one is safe
        allowed_methods=frozenset({"GET", "HEAD", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.headers.update(config.REQUEST_HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch(
    url: str,
    session: requests.Session | None = None,
    method: str = "GET",
    **kwargs: Any,
) -> requests.Response:
    """Requests a URL with the default timeout and raises for any error status."""
    session = session or build_session()
    kwargs.setdefault("timeout", config.REQUEST_TIMEOUT)

    send = session.post if method.upper() == "POST" else session.get
    response = send(url, **kwargs)
    response.raise_for_status()
    return response
