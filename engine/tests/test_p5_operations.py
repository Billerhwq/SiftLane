from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from siftlane_engine.api import create_app
from siftlane_engine.config import Settings
from siftlane_engine.models import FlowDefinition
from siftlane_engine.operations import create_backup, file_sha256, manifest_path, restore_backup, verify_backup
from siftlane_engine.storage import SCHEMA_VERSION, Storage


def flow_definition() -> dict:
    return json.loads((Path(__file__).parent / "fixtures" / "v0.2-flow.json").read_text(encoding="utf-8"))


def test_live_ready_metrics_schema_and_v0_2_contract(tmp_path):
    legacy = FlowDefinition.model_validate(flow_definition())
    assert legacy.visibility.value == "team"

    app = create_app(Settings(data_dir=tmp_path, worker_count=1))
    with TestClient(app) as client:
        created = client.post("/api/v1/flows", json=flow_definition())
        assert created.status_code == 201
        assert client.get("/health/live").json()["status"] == "UP"
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["schemaVersion"] == SCHEMA_VERSION
        schema = client.get("/api/v1/operations/schema")
        assert schema.status_code == 200
        assert schema.json() == {
            "current": SCHEMA_VERSION,
            "supportedMinimum": 2,
            "latest": SCHEMA_VERSION,
            "lastMigrationAt": schema.json()["lastMigrationAt"],
            "ready": True,
        }
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "siftlane_queue_size 0" in metrics.text
        assert "siftlane_database_bytes" in metrics.text
        app.state.crawler.ready = False
        assert client.get("/health/ready").status_code == 503


def test_online_backup_verify_restore_and_tamper_rejection(tmp_path):
    source_dir = tmp_path / "source"
    app = create_app(Settings(data_dir=source_dir, worker_count=1))
    backup = tmp_path / "backup" / "siftlane.sqlite3"
    with TestClient(app) as client:
        assert client.post("/api/v1/flows", json=flow_definition()).status_code == 201
        manifest = create_backup(source_dir / "crawler.db", backup)
        assert manifest["schemaVersion"] == SCHEMA_VERSION
        assert manifest["counts"]["flows"] == 1
        assert verify_backup(backup)["verified"] is True

        command = subprocess.run(
            [sys.executable, "-m", "siftlane_engine.operations", "verify", "--backup", str(backup)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert command.returncode == 0, command.stderr
        assert json.loads(command.stdout)["ok"] is True

    restored_dir = tmp_path / "restored"
    restored = restore_backup(backup, restored_dir / "crawler.db")
    assert restored["schemaVersion"] == SCHEMA_VERSION
    with TestClient(create_app(Settings(data_dir=restored_dir, worker_count=1))) as client:
        flows = client.get("/api/v1/flows").json()
        assert len(flows) == 1
        assert flows[0]["name"] == "v0.2 compatibility fixture"

    with pytest.raises(FileExistsError):
        restore_backup(backup, restored_dir / "crawler.db")
    replaced = restore_backup(backup, restored_dir / "crawler.db", replace=True)
    assert Path(replaced["safetyCopy"]).is_file()

    tampered = tmp_path / "tampered.sqlite3"
    shutil.copy2(backup, tampered)
    shutil.copy2(manifest_path(backup), manifest_path(tampered))
    tampered_manifest = json.loads(manifest_path(tampered).read_text(encoding="utf-8"))
    tampered_manifest["database"] = tampered.name
    manifest_path(tampered).write_text(json.dumps(tampered_manifest), encoding="utf-8")
    with tampered.open("ab") as output:
        output.write(b"tamper")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_backup(tampered)


@pytest.mark.asyncio
async def test_additive_schema_migration_records_current_version(tmp_path):
    storage = Storage(tmp_path / "crawler.db")
    await storage.initialize()
    with sqlite3.connect(storage.path) as database:
        database.execute("DELETE FROM schema_meta")
        database.commit()
    await storage.initialize()
    status = await storage.schema_status()
    assert status["current"] == SCHEMA_VERSION
    assert status["ready"] is True
