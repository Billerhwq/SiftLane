from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from email.message import Message
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import Settings


class FetchRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ResponsePayload:
    url: str
    status: int
    media_type: str
    body: bytes
    headers: dict[str, str]

    def text(self) -> str:
        message = Message()
        if content_type := self.headers.get("content-type"):
            message["content-type"] = content_type
        charset = message.get_content_charset() or "utf-8"
        return self.body.decode(charset, errors="replace")


class SecureHttpClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._last_request: dict[str, float] = {}
        self._rate_lock = asyncio.Lock()
        self._robots: dict[str, tuple[float, RobotFileParser]] = {}
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            headers={"User-Agent": settings.user_agent, "Accept": "*/*"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        respect_robots: bool | None = None,
    ) -> ResponsePayload:
        robots_enabled = (
            self.settings.respect_robots_txt if respect_robots is None else respect_robots
        )
        if robots_enabled and not await self._robots_allowed(url):
            raise FetchRejected(f"robots.txt does not allow {url}")

        current = url
        for redirect_count in range(self.settings.max_redirects + 1):
            response = await self._request(current, headers or {})
            if response.status_code not in {301, 302, 303, 307, 308}:
                return await self._read_response(response)
            location = response.headers.get("location")
            await response.aclose()
            if not location:
                raise FetchRejected("redirect response did not include a location")
            if redirect_count >= self.settings.max_redirects:
                raise FetchRejected("redirect limit exceeded")
            current = urljoin(current, location)
        raise FetchRejected("redirect limit exceeded")

    async def _request(self, url: str, headers: dict[str, str]) -> httpx.Response:
        parsed = await self._validate_url(url)
        await self._wait_for_host(parsed.hostname or "")
        request = self._client.build_request("GET", url, headers=headers)
        return await self._client.send(request, stream=True)

    async def _read_response(self, response: httpx.Response) -> ResponsePayload:
        try:
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.settings.max_response_bytes:
                raise FetchRejected("response exceeds configured size limit")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self.settings.max_response_bytes:
                    raise FetchRejected("response exceeds configured size limit")
                chunks.append(chunk)
            media_type = response.headers.get("content-type", "application/octet-stream")
            media_type = media_type.split(";", 1)[0].strip().lower()
            return ResponsePayload(
                url=str(response.url),
                status=response.status_code,
                media_type=media_type,
                body=b"".join(chunks),
                headers={key.lower(): value for key, value in response.headers.items()},
            )
        finally:
            await response.aclose()

    async def _robots_allowed(self, url: str) -> bool:
        parsed = await self._validate_url(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self._robots.get(origin)
        if cached and cached[0] > time.monotonic():
            return cached[1].can_fetch(self.settings.user_agent, url)

        parser = RobotFileParser()
        robots_url = f"{origin}/robots.txt"
        parser.set_url(robots_url)
        try:
            response = await self._request(robots_url, {})
            payload = await self._read_response(response)
            if 200 <= payload.status < 300:
                parser.parse(payload.text().splitlines())
            else:
                parser.parse([])
        except (httpx.HTTPError, FetchRejected):
            parser.parse([])
        self._robots[origin] = (time.monotonic() + 900, parser)
        return parser.can_fetch(self.settings.user_agent, url)

    async def _validate_url(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise FetchRejected("only http and https URLs are supported")
        if not parsed.hostname:
            raise FetchRejected("URL must contain a hostname")
        if parsed.username or parsed.password:
            raise FetchRejected("URL user information is not allowed")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as error:
            raise FetchRejected("URL port is invalid") from error

        loop = asyncio.get_running_loop()
        try:
            addresses = await loop.run_in_executor(
                None,
                lambda: socket.getaddrinfo(
                    parsed.hostname, port, type=socket.SOCK_STREAM
                ),
            )
        except socket.gaierror as error:
            raise FetchRejected(f"hostname could not be resolved: {parsed.hostname}") from error
        if not addresses:
            raise FetchRejected("hostname did not resolve")
        if not self.settings.allow_private_networks:
            for address in addresses:
                ip = ipaddress.ip_address(address[4][0])
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                    or ip.is_unspecified
                ):
                    raise FetchRejected(f"target address is not publicly routable: {ip}")
        return parsed

    async def _wait_for_host(self, hostname: str) -> None:
        delay = self.settings.request_min_delay_seconds
        if delay <= 0:
            return
        async with self._rate_lock:
            now = time.monotonic()
            previous = self._last_request.get(hostname, 0.0)
            wait = delay - (now - previous)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request[hostname] = time.monotonic()
