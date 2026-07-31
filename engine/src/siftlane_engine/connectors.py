from __future__ import annotations

from importlib.metadata import EntryPoint, entry_points
from typing import Callable, Iterable

from siftlane_connector_sdk import ConnectorManifest, ConnectorRuntime


CONNECTOR_ENTRYPOINT_GROUP = "siftlane.connectors"
ConnectorFactory = Callable[[], ConnectorRuntime]


class ConnectorContractError(RuntimeError):
    pass


class ConnectorRegistry:
    def __init__(self, runtimes: Iterable[ConnectorRuntime] = ()):
        self._runtimes: dict[str, ConnectorRuntime] = {}
        for runtime in runtimes:
            self.register(runtime)

    @classmethod
    def discover(cls) -> ConnectorRegistry:
        registry = cls()
        discovered = entry_points()
        selected = (
            discovered.select(group=CONNECTOR_ENTRYPOINT_GROUP)
            if hasattr(discovered, "select")
            else discovered.get(CONNECTOR_ENTRYPOINT_GROUP, [])
        )
        for entry_point in selected:
            registry.register(cls._load(entry_point))
        return registry

    @staticmethod
    def _load(entry_point: EntryPoint) -> ConnectorRuntime:
        loaded = entry_point.load()
        runtime = loaded() if callable(loaded) else loaded
        if not isinstance(runtime, ConnectorRuntime):
            raise ConnectorContractError(
                f"connector entry point {entry_point.name!r} does not implement ConnectorRuntime"
            )
        return runtime

    def register(self, runtime: ConnectorRuntime) -> None:
        if not isinstance(runtime, ConnectorRuntime):
            raise ConnectorContractError("connector does not implement ConnectorRuntime")
        manifest = ConnectorManifest.model_validate(runtime.manifest)
        if manifest.id in self._runtimes:
            raise ConnectorContractError(f"duplicate connector id: {manifest.id}")
        self._runtimes[manifest.id] = runtime

    def manifests(self) -> list[ConnectorManifest]:
        return sorted(
            (runtime.manifest for runtime in self._runtimes.values()),
            key=lambda manifest: manifest.id,
        )

    def get(self, connector_id: str) -> ConnectorRuntime | None:
        return self._runtimes.get(connector_id)
