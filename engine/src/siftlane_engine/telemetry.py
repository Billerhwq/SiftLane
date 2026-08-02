from __future__ import annotations

from collections import Counter, deque
from datetime import datetime
from threading import Lock
from typing import Any

from .models import utc_now


class OperationsMonitor:
    def __init__(self, *, alert_limit: int = 100):
        self._counters: Counter[str] = Counter()
        self._alerts: deque[dict[str, Any]] = deque(maxlen=alert_limit)
        self._lock = Lock()

    def increment(
        self,
        name: str,
        *,
        alert: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._counters[name] += 1
            if alert:
                self._alerts.appendleft(
                    {
                        "type": alert,
                        "detail": detail or {},
                        "created_at": utc_now().isoformat(),
                    }
                )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(sorted(self._counters.items())),
                "recentAlerts": list(self._alerts),
            }

    def prometheus(self, *, queue_size: int) -> str:
        with self._lock:
            lines = [
                "# HELP siftlane_queue_size Number of runs waiting for a worker.",
                "# TYPE siftlane_queue_size gauge",
                f"siftlane_queue_size {queue_size}",
            ]
            for name, value in sorted(self._counters.items()):
                metric = "siftlane_" + "".join(
                    character if character.isalnum() or character == "_" else "_"
                    for character in name.lower()
                )
                lines.extend(
                    [
                        f"# TYPE {metric} counter",
                        f"{metric} {value}",
                    ]
                )
            return "\n".join(lines) + "\n"
