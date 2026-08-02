from __future__ import annotations

import argparse
import asyncio
import json
import platform
import time
from datetime import timezone
from pathlib import Path

from siftlane_engine.models import FlowDefinition, RunStatus, utc_now
from siftlane_engine.storage import Storage


def definition() -> FlowDefinition:
    return FlowDefinition.model_validate(
        {
            "name": "P5 capacity fixture",
            "description": "",
            "enabled": True,
            "max_items": 10000,
            "timeout_seconds": 3600,
            "parameter_schema": {"type": "object"},
            "nodes": [
                {"id": "start", "type": "start", "name": "Start", "config": {"urls": ["https://example.com"]}},
                {"id": "emit", "type": "emit", "name": "Emit", "config": {}},
            ],
            "edges": [{"id": "edge", "source": "start", "target": "emit"}],
        }
    )


async def execute(arguments: argparse.Namespace) -> dict:
    database_path = arguments.data_dir.resolve() / "crawler.db"
    if database_path.exists():
        raise FileExistsError("capacity data directory must start empty")
    storage = Storage(database_path)
    await storage.initialize()
    flow = await storage.create_flow(definition())
    semaphore = asyncio.Semaphore(arguments.concurrency)
    started = time.perf_counter()

    async def create_one(run_index: int) -> None:
        async with semaphore:
            run, _ = await storage.create_run(flow, {}, f"capacity-{run_index}")
            for item_index in range(arguments.items_per_run):
                await storage.add_item(
                    run.id,
                    f"{run_index}-{item_index}",
                    f"https://example.com/{run_index}/{item_index}",
                    f"Item {run_index}-{item_index}",
                    "capacity payload",
                    "text/plain",
                    utc_now().astimezone(timezone.utc),
                    {"run": run_index, "item": item_index},
                )
            await storage.finalize_run(
                run.id,
                status=RunStatus.SUCCEEDED,
                run_message="Capacity fixture complete",
                event_type="run.completed",
                event_level="info",
                event_message="Capacity fixture complete",
                processed_items=arguments.items_per_run,
                total_items=arguments.items_per_run,
            )

    await asyncio.gather(*(create_one(index) for index in range(arguments.runs)))
    elapsed = time.perf_counter() - started
    stats = await storage.operational_stats()
    expected_items = arguments.runs * arguments.items_per_run
    passed = bool(
        stats["runs"].get("SUCCEEDED", 0) == arguments.runs
        and await _count(database_path, "items") == expected_items
        and elapsed <= arguments.max_seconds
        and stats["databaseBytes"] <= arguments.max_database_bytes
    )
    return {
        "format": "siftlane.capacity/v1",
        "profile": {
            "runs": arguments.runs,
            "itemsPerRun": arguments.items_per_run,
            "concurrency": arguments.concurrency,
        },
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "result": {
            "elapsedSeconds": round(elapsed, 6),
            "runsPerSecond": round(arguments.runs / elapsed, 3),
            "itemsPerSecond": round(expected_items / elapsed, 3),
            "databaseBytes": stats["databaseBytes"],
            "completedRuns": stats["runs"].get("SUCCEEDED", 0),
            "persistedItems": await _count(database_path, "items"),
        },
        "thresholds": {
            "maxSeconds": arguments.max_seconds,
            "maxDatabaseBytes": arguments.max_database_bytes,
            "zeroDataLoss": True,
        },
        "passed": passed,
    }


async def _count(path: Path, table: str) -> int:
    import aiosqlite

    async with aiosqlite.connect(path) as database:
        return int((await (await database.execute(f"SELECT COUNT(*) FROM {table}")).fetchone())[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=120)
    parser.add_argument("--items-per-run", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-seconds", type=float, default=30)
    parser.add_argument("--max-database-bytes", type=int, default=64 * 1024 * 1024)
    arguments = parser.parse_args()
    report = asyncio.run(execute(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
