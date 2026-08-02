from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import sys
from importlib.metadata import distributions, entry_points
from urllib.parse import urlparse

import httpx
from siftlane_connector_sdk import (
    ConnectorContext,
    ConnectorEvent,
    ConnectorHttpRequest,
    ConnectorHttpResponse,
    ConnectorOperationRequest,
    ConnectorRuntime,
    SecretRef,
)

from .connectors import CONNECTOR_ENTRYPOINT_GROUP
from .reference_connectors import load_builtin


class ManagedSecrets:
    def __init__(self, values: dict[str, str]):
        self._values = values

    async def resolve(self, reference: SecretRef) -> str:
        try:
            return self._values[reference.key]
        except KeyError as error:
            raise RuntimeError("connector credential is unavailable") from error


class StderrEvents:
    async def emit(self, event: ConnectorEvent) -> None:
        print(json.dumps(event.model_dump(mode="json"), ensure_ascii=False), file=sys.stderr)


class ManagedHttp:
    def __init__(
        self,
        *,
        allow_private_networks: bool,
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_domains: list[str],
    ):
        self.allow_private_networks = allow_private_networks
        self.max_response_bytes = max_response_bytes
        self.allowed_domains = {value.lower() for value in allowed_domains}
        self.client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "SiftlaneConnectorWorker/1.0"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, request: ConnectorHttpRequest) -> ConnectorHttpResponse:
        parsed = urlparse(request.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("connector URL must use HTTP or HTTPS")
        if parsed.username or parsed.password:
            raise RuntimeError("connector URL user information is not allowed")
        hostname = parsed.hostname.lower()
        if self.allowed_domains and not any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.allowed_domains
        ):
            raise RuntimeError("connector target domain is not allowed by its manifest")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM),
        )
        if not self.allow_private_networks:
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
                    raise RuntimeError("connector target is not publicly routable")
        response = await self.client.request(
            request.method,
            request.url,
            headers=request.headers,
            params=request.query,
            json=request.json_body,
        )
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.max_response_bytes:
            raise RuntimeError("connector response exceeds the size limit")
        body = response.content
        if len(body) > self.max_response_bytes:
            raise RuntimeError("connector response exceeds the size limit")
        return ConnectorHttpResponse(
            status=response.status_code,
            url=str(response.url),
            headers={key.lower(): value for key, value in response.headers.items()},
            body=body,
        )


def load_runtime(name: str, python_path: str | None = None) -> ConnectorRuntime:
    if name.startswith("builtin."):
        return load_builtin(name)
    if python_path:
        selected = [
            candidate
            for distribution in distributions(path=[python_path])
            for candidate in distribution.entry_points
            if candidate.group == CONNECTOR_ENTRYPOINT_GROUP and candidate.name == name
        ]
    else:
        discovered = entry_points()
        selected = (
            list(discovered.select(group=CONNECTOR_ENTRYPOINT_GROUP, name=name))
            if hasattr(discovered, "select")
            else [
                item
                for item in discovered.get(CONNECTOR_ENTRYPOINT_GROUP, [])
                if item.name == name
            ]
        )
    matches = list(selected)
    if len(matches) != 1:
        raise RuntimeError(f"connector entry point {name!r} was not found uniquely")
    loaded = matches[0].load()
    runtime = loaded() if callable(loaded) else loaded
    if not isinstance(runtime, ConnectorRuntime):
        raise RuntimeError(f"connector entry point {name!r} is invalid")
    return runtime


async def execute(name: str, payload: dict, python_path: str | None = None) -> dict:
    runtime = load_runtime(name, python_path)
    request = ConnectorOperationRequest.model_validate(payload.get("request", payload))
    secrets = payload.get("secrets", {})
    policy = payload.get("http_policy", {})
    http = ManagedHttp(
        allow_private_networks=bool(policy.get("allow_private_networks", False)),
        timeout_seconds=float(policy.get("timeout_seconds", 30)),
        max_response_bytes=int(policy.get("max_response_bytes", 10 * 1024 * 1024)),
        allowed_domains=runtime.manifest.runtime.allowed_domains,
    )
    context = ConnectorContext(
        run_id="managed-operation",
        node_id=f"connector:{runtime.manifest.id}",
        secrets=ManagedSecrets(secrets if isinstance(secrets, dict) else {}),
        events=StderrEvents(),
        http=http,
    )
    try:
        result = await runtime.execute(request, context)
        return result.model_dump(mode="json")
    finally:
        await http.close()


def main() -> None:
    if len(sys.argv) not in {3, 4} or sys.argv[1] not in {"describe", "execute"}:
        raise SystemExit(
            "usage: connector_worker <describe|execute> <entry-point> [python-path]"
        )
    command, name = sys.argv[1:3]
    python_path = sys.argv[3] if len(sys.argv) == 4 else None
    if python_path:
        sys.path.insert(0, python_path)
    payload = json.loads(sys.stdin.buffer.read() or b"{}")
    if command == "describe":
        result = load_runtime(name, python_path).manifest.model_dump(mode="json")
    else:
        result = asyncio.run(execute(name, payload, python_path))
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()
