from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def request_json(base: str, path: str, payload: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{base}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def start_engine(engine_dir: Path, data_dir: Path, port: int) -> subprocess.Popen:
    environment = os.environ.copy()
    environment.update(
        {
            "SIFTLANE_ENGINE_DATA_DIR": str(data_dir),
            "SIFTLANE_ENGINE_PORT": str(port),
            "SIFTLANE_ENGINE_WORKER_COUNT": "1",
            "SIFTLANE_ENGINE_SCHEDULER_POLL_SECONDS": "0.1",
            "SIFTLANE_ENGINE_REQUEST_MIN_DELAY_SECONDS": "0",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return subprocess.Popen(
        [sys.executable, "-m", "siftlane_engine.main"],
        cwd=engine_dir,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_health(base: str, process: subprocess.Popen) -> None:
    for _ in range(200):
        if process.poll() is not None:
            raise AssertionError(f"engine exited with {process.returncode}")
        try:
            if request_json(base, "/health")["status"] == "UP":
                return
        except (URLError, TimeoutError):
            time.sleep(0.025)
    raise AssertionError("engine did not become healthy")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def read_run_state(database_path: Path, run_id: str) -> tuple[str, int] | None:
    try:
        with sqlite3.connect(database_path, timeout=1) as database:
            row = database.execute(
                "SELECT status,processed_items FROM runs WHERE id=?", (run_id,)
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    return (str(row[0]), int(row[1])) if row else None


def test_worker_process_recovers_without_duplicate_results(tmp_path):
    engine_dir = Path(__file__).resolve().parents[1]
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    process = start_engine(engine_dir, tmp_path, port)
    restarted: subprocess.Popen | None = None
    total = 250
    try:
        wait_for_health(base, process)
        flow = {
            "name": "Crash recovery fixture",
            "max_items": total,
            "timeout_seconds": 120,
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "name": "Seeds",
                    "config": {
                        "urls": [f"https://example.com/items/{index}" for index in range(total)]
                    },
                },
                {"id": "emit", "type": "emit", "name": "Emit", "config": {}},
            ],
            "edges": [{"id": "edge", "source": "start", "target": "emit"}],
        }
        created = request_json(base, "/api/v1/flows", flow)
        run = request_json(
            base,
            "/api/v1/runs",
            {"flow_id": created["id"], "parameters": {}, "idempotency_key": "crash-test"},
        )
        run_id = run["id"]
        interrupted_at = 0
        interrupt_deadline = time.monotonic() + 30
        while time.monotonic() < interrupt_deadline:
            if process.poll() is not None:
                raise AssertionError(f"engine exited with {process.returncode}")
            current = read_run_state(tmp_path / "crawler.db", run_id)
            if current and current[0] == "RUNNING" and 10 <= current[1] < total:
                interrupted_at = current[1]
                break
            time.sleep(0.025)
        assert 0 < interrupted_at < total, "run completed before it could be interrupted"

        stop_process(process)
        restarted = start_engine(engine_dir, tmp_path, port)
        wait_for_health(base, restarted)
        terminal = None
        recovery_deadline = time.monotonic() + 120
        while time.monotonic() < recovery_deadline:
            if restarted.poll() is not None:
                raise AssertionError(f"restarted engine exited with {restarted.returncode}")
            state = read_run_state(tmp_path / "crawler.db", run_id)
            if state and state[0] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                terminal = {"status": state[0], "processed_items": state[1]}
                break
            time.sleep(0.025)
        assert terminal is not None and terminal["status"] == "SUCCEEDED", terminal
        assert terminal["processed_items"] == total

        with sqlite3.connect(tmp_path / "crawler.db") as database:
            row = database.execute(
                """SELECT COUNT(*),COUNT(DISTINCT external_id)
                   FROM items WHERE run_id=?""",
                (run_id,),
            ).fetchone()
            assert row == (total, total)
            started = database.execute(
                """SELECT COUNT(*) FROM events
                   WHERE run_id=? AND type='node.started'
                     AND json_extract(data_json, '$.nodeId')='start'""",
                (run_id,),
            ).fetchone()[0]
            restored = database.execute(
                """SELECT COUNT(*) FROM events
                   WHERE run_id=? AND type='node.restored'
                     AND json_extract(data_json, '$.nodeId')='start'""",
                (run_id,),
            ).fetchone()[0]
        assert started == 1
        assert restored == 1
    finally:
        stop_process(process)
        if restarted is not None:
            stop_process(restarted)
