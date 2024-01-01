"""Module to simplify asynchronous HTTP calls. For internal use only."""
from __future__ import annotations

import asyncio
import json
import logging
import plistlib
from typing import Any

from aiohttp import BasicAuth, ClientSession, ClientTimeout

logging.getLogger(__name__)


def decode_plist(data: bytes) -> Any:  # noqa: ANN401
    """Decode a plist file."""
    plist_header = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<!DOCTYPE plist PUBLIC '-//Apple//DTD PLIST 1.0//EN' 'http://www.apple.com/DTDs/PropertyList-1.0.dtd'>"
    )

    if not data.startswith(b"<?xml"):  # append header ourselves
        data = plist_header + data

    return plistlib.loads(data)


class HttpResponse:
    """Response of a request made by `HttpSession`."""

    def __init__(self, status_code: int, content: bytes) -> None:
        """Initialize the response."""
        self._status_code = status_code
        self._content = content

    @property
    def status_code(self) -> int:
        """HTTP status code of the response."""
        return self._status_code

    @property
    def ok(self) -> bool:
        """Whether the status code is "OK" (2xx)."""
        return str(self._status_code).startswith("2")

    def text(self) -> str:
        """Response content as a UTF-8 encoded string."""
        return self._content.decode("utf-8")

    def json(self) -> dict[Any, Any]:
        """Response content as a dict, obtained by JSON-decoding the response content."""
        return json.loads(self.text())

    def plist(self) -> dict[Any, Any]:
        """Response content as a dict, obtained by Plist-decoding the response content."""
        data = decode_plist(self._content)
        if not isinstance(data, dict):
            msg = f"Unknown Plist-encoded data type: {data}. This is a bug, please report it."
            raise TypeError(msg)

        return data


class HttpSession:
    """Asynchronous HTTP session manager. For internal use only."""

    def __init__(self) -> None:  # noqa: D107
        self._session: ClientSession | None = None

    async def _ensure_session(self) -> None:
        if self._session is None:
            logging.debug("Creating aiohttp session")
            self._session = ClientSession(timeout=ClientTimeout(total=5))

    async def close(self) -> None:
        """Close the underlying session. Should be called when session will no longer be used."""
        if self._session is not None:
            logging.debug("Closing aiohttp session")
            await self._session.close()
            self._session = None

    def __del__(self) -> None:
        """Attempt to gracefully close the session.

        Ideally this should be done by manually calling close().
        """
        if self._session is None:
            return

        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(loop.create_task, self.close())
        except RuntimeError:  # cannot await closure
            pass

    async def request(
        self,
        method: str,
        url: str,
        auth: tuple[str] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        """Make an HTTP request.

        Keyword arguments will directly be passed to `aiohttp.ClientSession.request`.
        """
        await self._ensure_session()

        basic_auth = None
        if auth is not None:
            basic_auth = BasicAuth(auth[0], auth[1])

        async with await self._session.request(
            method,
            url,
            auth=basic_auth,
            ssl=False,
            **kwargs,
        ) as r:
            return HttpResponse(r.status, await r.content.read())

    async def get(self, url: str, **kwargs: Any) -> HttpResponse:
        """Alias for `HttpSession.request("GET", ...)`."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> HttpResponse:
        """Alias for `HttpSession.request("POST", ...)`."""
        return await self.request("POST", url, **kwargs)
