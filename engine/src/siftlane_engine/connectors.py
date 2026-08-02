from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Callable, Iterable

from siftlane_connector_sdk import (
    ConnectorContext,
    ConnectorManifest,
    ConnectorOperationRequest,
    ConnectorOperationResult,
    ConnectorRuntime,
)


CONNECTOR_ENTRYPOINT_GROUP = "siftlane.connectors"
ConnectorFactory = Callable[[], ConnectorRuntime]
MAX_CONNECTOR_OUTPUT_BYTES = 8 * 1024 * 1024


class ConnectorContractError(RuntimeError):
    pass


class ConnectorProcessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IsolatedConnector:
    entry_point: str
    manifest: ConnectorManifest


def _connector_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _decode_worker_output(completed: subprocess.CompletedProcess[bytes]) -> dict:
    if completed.returncode != 0:
        raise ConnectorProcessError(f"connector exited with {completed.returncode}")
    if len(completed.stdout) > MAX_CONNECTOR_OUTPUT_BYTES:
        raise ConnectorProcessError("connector response exceeded the output limit")
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConnectorProcessError("connector returned invalid JSON") from error
    if not isinstance(value, dict):
        raise ConnectorProcessError("connector response must be an object")
    return value


class ConnectorRegistry:
    def __init__(self, runtimes: Iterable[ConnectorRuntime] = ()):
        self._runtimes: dict[str, ConnectorRuntime] = {}
        self._isolated: dict[str, IsolatedConnector] = {}
        self._errors: dict[str, str] = {}
        for runtime in runtimes:
            self.register(runtime)

    @classmethod
    def discover(cls) -> "ConnectorRegistry":
        registry = cls()
        discovered = entry_points()
        selected = (
            discovered.select(group=CONNECTOR_ENTRYPOINT_GROUP)
            if hasattr(discovered, "select")
            else discovered.get(CONNECTOR_ENTRYPOINT_GROUP, [])
        )
        for entry_point in selected:
            try:
                manifest = registry._describe_isolated(entry_point)
                if manifest.id in registry._runtimes or manifest.id in registry._isolated:
                    raise ConnectorContractError(f"duplicate connector id: {manifest.id}")
                registry._isolated[manifest.id] = IsolatedConnector(
                    entry_point=entry_point.name,
                    manifest=manifest,
                )
            except (ConnectorContractError, ConnectorProcessError) as error:
                registry._errors[entry_point.name] = str(error)[:2000]
        return registry

    @staticmethod
    def _describe_isolated(entry_point: EntryPoint) -> ConnectorManifest:
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "siftlane_engine.connector_worker",
                    "describe",
                    entry_point.name,
                ],
                input=b"{}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
                env=_connector_environment(),
            )
        except subprocess.TimeoutExpired as error:
            raise ConnectorProcessError(
                f"connector {entry_point.name!r} timed out during discovery"
            ) from error
        return ConnectorManifest.model_validate(_decode_worker_output(completed))

    def register(self, runtime: ConnectorRuntime) -> None:
        if not isinstance(runtime, ConnectorRuntime):
            raise ConnectorContractError("connector does not implement ConnectorRuntime")
        manifest = ConnectorManifest.model_validate(runtime.manifest)
        if manifest.id in self._runtimes or manifest.id in self._isolated:
            raise ConnectorContractError(f"duplicate connector id: {manifest.id}")
        self._runtimes[manifest.id] = runtime

    def manifests(self) -> list[ConnectorManifest]:
        values = [runtime.manifest for runtime in self._runtimes.values()]
        values.extend(connector.manifest for connector in self._isolated.values())
        return sorted(values, key=lambda manifest: manifest.id)

    def get(self, connector_id: str) -> ConnectorRuntime | IsolatedConnector | None:
        return self._runtimes.get(connector_id) or self._isolated.get(connector_id)

    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    async def execute(
        self,
        connector_id: str,
        request: ConnectorOperationRequest,
        context: ConnectorContext | None = None,
        *,
        timeout_seconds: float = 30,
    ) -> ConnectorOperationResult:
        direct = self._runtimes.get(connector_id)
        if direct is not None:
            if context is None:
                raise ConnectorContractError("a connector context is required")
            return ConnectorOperationResult.model_validate(
                await asyncio.wait_for(
                    direct.execute(request, context), timeout=timeout_seconds
                )
            )
        connector = self._isolated.get(connector_id)
        if connector is None:
            raise KeyError(connector_id)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "siftlane_engine.connector_worker",
            "execute",
            connector.entry_point,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_connector_environment(),
        )
        payload = json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode(
            "utf-8"
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(payload), timeout=timeout_seconds
            )
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise ConnectorProcessError("connector execution timed out") from error
        completed = subprocess.CompletedProcess(
            args=[], returncode=process.returncode or 0, stdout=stdout, stderr=stderr
        )
        return ConnectorOperationResult.model_validate(_decode_worker_output(completed))
