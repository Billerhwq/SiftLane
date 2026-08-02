from __future__ import annotations

import argparse
import asyncio
import json
import platform
import time
import tracemalloc
from pathlib import Path

import aiosqlite

from siftlane_engine.models import FlowDefinition, RunStatus, utc_now
from siftlane_engine.storage import Storage


def definition() -> FlowDefinition:
    return FlowDefinition.model_validate(
        {
            "name": "P5 soak fixture",
            "enabled": True,
            "max_items": 1000,
            "timeout_seconds": 3600,
            "nodes": [
                {"id": "start", "type": "start", "name": "Start", "config": {"urls": ["https://example.com"]}},
                {"id": "emit", "type": "emit", "name": "Emit", "config": {}},
            ],
            "edges": [{"id": "edge", "source": "start", "target": "emit"}],
        }
    )


async def count(path: Path, table: str) -> int:
    async with aiosqlite.connect(path) as database:
        return int((await (await database.execute(f"SELECT COUNT(*) FROM {table}")).fetchone())[0])


async def execute(arguments: argparse.Namespace) -> dict:
    database_path = arguments.data_dir.resolve() / "crawler.db"
    if database_path.exists():
        raise FileExistsError("soak data directory must start empty")
    storage = Storage(database_path)
    await storage.initialize()
    flow = await storage.create_flow(definition())
    tracemalloc.start()
    baseline_current, _ = tracemalloc.get_traced_memory()
    started = time.perf_counter()
    cycle = 0
    samples: list[dict[str, int | float]] = []
    while time.perf_counter() - started < arguments.duration_seconds:
        run, _ = await storage.create_run(flow, {}, f"soak-{cycle}")
        for item_index in range(arguments.items_per_cycle):
            await storage.add_item(
                run.id,
                f"{cycle}-{item_index}",
                f"https://example.com/{cycle}/{item_index}",
                "Soak item",
                "steady payload",
                "text/plain",
                utc_now(),
                {"cycle": cycle},
            )
        await storage.finalize_run(
            run.id,
            status=RunStatus.SUCCEEDED,
            run_message="Soak cycle complete",
            event_type="run.completed",
            event_level="info",
            event_message="Soak cycle complete",
            processed_items=arguments.items_per_cycle,
            total_items=arguments.items_per_cycle,
        )
        cycle += 1
        current, peak = tracemalloc.get_traced_memory()
        samples.append(
            {
                "second": round(time.perf_counter() - started, 3),
                "heapBytes": current,
                "peakHeapBytes": peak,
                "databaseBytes": database_path.stat().st_size,
            }
        )
        await asyncio.sleep(arguments.interval_seconds)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    run_count = await count(database_path, "runs")
    item_count = await count(database_path, "items")
    expected_items = cycle * arguments.items_per_cycle
    heap_growth = max(0, current - baseline_current)
    passed = bool(
        run_count == cycle
        and item_count == expected_items
        and heap_growth <= arguments.max_heap_growth_bytes
        and peak <= arguments.max_peak_heap_bytes
    )
    return {
        "format": "siftlane.soak/v1",
        "profile": {
            "durationSeconds": arguments.duration_seconds,
            "intervalSeconds": arguments.interval_seconds,
            "itemsPerCycle": arguments.items_per_cycle,
        },
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "result": {
            "cycles": cycle,
            "persistedRuns": run_count,
            "persistedItems": item_count,
            "expectedItems": expected_items,
            "heapGrowthBytes": heap_growth,
            "peakHeapBytes": peak,
            "databaseBytes": database_path.stat().st_size,
        },
        "thresholds": {
            "maxHeapGrowthBytes": arguments.max_heap_growth_bytes,
            "maxPeakHeapBytes": arguments.max_peak_heap_bytes,
            "zeroDataLoss": True,
        },
        "samples": samples,
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=30)
    parser.add_argument("--interval-seconds", type=float, default=0.25)
    parser.add_argument("--items-per-cycle", type=int, default=5)
    parser.add_argument("--max-heap-growth-bytes", type=int, default=32 * 1024 * 1024)
    parser.add_argument("--max-peak-heap-bytes", type=int, default=128 * 1024 * 1024)
    arguments = parser.parse_args()
    report = asyncio.run(execute(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
