from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from siftlane_engine.api import create_app
from siftlane_engine.config import Settings


ADMIN_PASSWORD = "Admin-password-123"
SECRET_KEY = "p4-test-engine-secret-key-32-characters-long"


class IntegrationHandler(BaseHTTPRequestHandler):
    posts: list[dict[str, object]] = []
    fail_posts = False

    def do_GET(self):
        body = json.dumps(
            {
                "version": "https://jsonfeed.org/version/1.1",
                "title": "P4 fixture feed",
                "items": [
                    {
                        "id": "feed-item-1",
                        "url": f"http://127.0.0.1:{self.server.server_port}/items/1",
                        "title": "Managed connector item",
                        "content_text": "Collected in an isolated connector process.",
                        "date_published": "2026-08-01T00:00:00Z",
                    }
                ],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/feed+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        type(self).posts.append(
            {
                "body": body,
                "idempotency": self.headers.get("Idempotency-Key"),
                "signature": self.headers.get("X-Siftlane-Signature"),
            }
        )
        self.send_response(503 if type(self).fail_posts else 204)
        self.end_headers()

    def log_message(self, *_):
        pass


def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        auth_mode="team",
        bootstrap_admin_username="admin",
        bootstrap_admin_password=ADMIN_PASSWORD,
        secret_key=SECRET_KEY,
        worker_count=1,
        delivery_poll_seconds=60,
        allow_private_networks=True,
        request_min_delay_seconds=0,
    )


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def flow_definition() -> dict:
    return {
        "name": "P4 delivery source",
        "description": "",
        "enabled": True,
        "visibility": "team",
        "max_items": 10,
        "timeout_seconds": 30,
        "parameter_schema": {"type": "object"},
        "nodes": [
            {"id": "start", "type": "start", "name": "Start", "config": {"urls": ["https://example.com"]}},
            {"id": "emit", "type": "emit", "name": "Emit", "config": {}},
        ],
        "edges": [{"id": "edge", "source": "start", "target": "emit"}],
    }


def create_wheel(
    inbox: Path,
    version: str,
    *,
    compatible: bool = True,
    leak_secret: bool = False,
) -> tuple[str, str]:
    filename = f"fixture_connector-{version}-py3-none-any.whl"
    path = inbox / filename
    execution_setup = (
        'credential = await context.secrets.resolve(request.credential)\n        title = f"leak:{credential}"'
        if leak_secret
        else 'title = "Fixture"'
    )
    module = f'''from datetime import datetime, timezone
from siftlane_connector_sdk import ConnectorCapability, ConnectorItem, ConnectorManifest, ConnectorOperationResult

class FixtureConnector:
    @property
    def manifest(self):
        return ConnectorManifest(api_version={"'siftlane.connector/v1'" if compatible else "'siftlane.connector/v2'"}, id="io.siftlane.fixture", name="Fixture", version="{version}", capabilities=[ConnectorCapability(id="fetch", label="Fetch", input_schema={{"type": "object"}})])

    async def execute(self, request, context):
        {execution_setup}
        return ConnectorOperationResult(items=[ConnectorItem(external_id="fixture", url="https://example.com", title=title, observed_at=datetime.now(timezone.utc))])
'''
    dist = f"fixture_connector-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fixture_connector/__init__.py", module)
        archive.writestr(f"{dist}/METADATA", f"Metadata-Version: 2.1\nName: fixture-connector\nVersion: {version}\n")
        archive.writestr(f"{dist}/WHEEL", "Wheel-Version: 1.0\nGenerator: Siftlane tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr(f"{dist}/entry_points.txt", "[siftlane.connectors]\nfixture = fixture_connector:FixtureConnector\n")
        archive.writestr(f"{dist}/RECORD", "")
    return filename, hashlib.sha256(path.read_bytes()).hexdigest()


def test_managed_reference_connector_and_package_lifecycle(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), IntegrationHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with TestClient(create_app(settings(tmp_path))) as client:
            headers = login(client)
            connectors = client.get("/api/v1/managed-connectors", headers=headers)
            assert connectors.status_code == 200
            assert connectors.json()[0]["id"] == "io.siftlane.json-feed"

            executed = client.post(
                "/api/v1/managed-connectors/io.siftlane.json-feed/execute",
                headers=headers,
                json={
                    "capability": "fetch",
                    "parameters": {"url": f"http://127.0.0.1:{server.server_port}/feed.json"},
                },
            )
            assert executed.status_code == 200, executed.text
            assert executed.json()["items"][0]["external_id"] == "feed-item-1"
            assert client.post(
                "/api/v1/managed-connectors/io.siftlane.json-feed/disable", headers=headers
            ).json()["state"] == "disabled"
            assert client.post(
                "/api/v1/managed-connectors/io.siftlane.json-feed/execute",
                headers=headers,
                json={"capability": "fetch", "parameters": {"url": "https://example.com"}},
            ).status_code == 502
            assert client.post(
                "/api/v1/managed-connectors/io.siftlane.json-feed/enable", headers=headers
            ).json()["state"] == "enabled"

            inbox = tmp_path / "connector-inbox"
            filename, digest = create_wheel(inbox, "1.0.0")
            installed = client.post(
                "/api/v1/managed-connectors/install",
                headers=headers,
                json={"filename": filename, "sha256": digest},
            )
            assert installed.status_code == 201, installed.text
            assert installed.json()["version"] == "1.0.0"

            filename, digest = create_wheel(inbox, "1.1.0")
            upgraded = client.post(
                "/api/v1/managed-connectors/io.siftlane.fixture/upgrade",
                headers=headers,
                json={"filename": filename, "sha256": digest},
            )
            assert upgraded.status_code == 200, upgraded.text
            assert upgraded.json()["previous_version"] == "1.0.0"
            rolled_back = client.post(
                "/api/v1/managed-connectors/io.siftlane.fixture/rollback", headers=headers
            )
            assert rolled_back.json()["version"] == "1.0.0"

            filename, digest = create_wheel(inbox, "2.0.0", compatible=False)
            incompatible = client.post(
                "/api/v1/managed-connectors/io.siftlane.fixture/upgrade",
                headers=headers,
                json={"filename": filename, "sha256": digest},
            )
            assert incompatible.status_code == 409
            current = client.get("/api/v1/managed-connectors", headers=headers).json()
            assert next(row for row in current if row["id"] == "io.siftlane.fixture")["version"] == "1.0.0"
            assert client.delete(
                "/api/v1/managed-connectors/io.siftlane.fixture", headers=headers
            ).status_code == 204
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_connector_response_cannot_echo_scoped_secret(tmp_path):
    secret_value = "connector-secret-never-returned"
    with TestClient(create_app(settings(tmp_path))) as client:
        headers = login(client)
        filename, digest = create_wheel(
            tmp_path / "connector-inbox", "1.0.0", leak_secret=True
        )
        installed = client.post(
            "/api/v1/managed-connectors/install",
            headers=headers,
            json={"filename": filename, "sha256": digest},
        )
        assert installed.status_code == 201, installed.text
        secret = client.post(
            "/api/v1/secrets",
            headers=headers,
            json={
                "name": "credential",
                "scope_type": "connector",
                "scope_id": "io.siftlane.fixture",
                "value": secret_value,
            },
        )
        assert secret.status_code == 201, secret.text

        response = client.post(
            "/api/v1/managed-connectors/io.siftlane.fixture/execute",
            headers=headers,
            json={
                "capability": "fetch",
                "parameters": {},
                "credential": {"provider": "engine", "key": "credential"},
            },
        )
        assert response.status_code == 502
        assert secret_value not in response.text
        assert secret_value not in client.get("/api/v1/audit", headers=headers).text


def test_scoped_secrets_ndjson_and_webhook_delivery_lifecycle(tmp_path):
    IntegrationHandler.posts = []
    IntegrationHandler.fail_posts = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), IntegrationHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    secret_value = "webhook-secret-value-never-returned"
    try:
        app = create_app(settings(tmp_path))
        with TestClient(app) as client:
            headers = login(client)
            flow = client.post("/api/v1/flows", headers=headers, json=flow_definition()).json()
            run = client.post(
                "/api/v1/runs",
                headers=headers,
                json={"flow_id": flow["id"], "parameters": {}, "idempotency_key": "p4-source"},
            ).json()

            ndjson_target = client.post(
                "/api/v1/delivery-targets",
                headers=headers,
                json={"name": "Archive", "type": "ndjson"},
            )
            assert ndjson_target.status_code == 201, ndjson_target.text
            delivery = client.post(
                "/api/v1/deliveries",
                headers=headers,
                json={"target_id": ndjson_target.json()["id"], "run_id": run["id"], "idempotency_key": "archive-1"},
            )
            assert delivery.status_code == 201, delivery.text
            assert delivery.json()["status"] == "succeeded"
            artifact = tmp_path / delivery.json()["artifact_path"]
            assert artifact.is_file()
            duplicate = client.post(
                "/api/v1/deliveries",
                headers=headers,
                json={"target_id": ndjson_target.json()["id"], "run_id": run["id"], "idempotency_key": "archive-1"},
            )
            assert duplicate.json()["id"] == delivery.json()["id"]

            webhook_target = client.post(
                "/api/v1/delivery-targets",
                headers=headers,
                json={
                    "name": "Signed webhook",
                    "type": "webhook",
                    "url": f"http://127.0.0.1:{server.server_port}/delivery",
                    "max_attempts": 1,
                },
            ).json()
            secret = client.post(
                "/api/v1/secrets",
                headers=headers,
                json={
                    "name": "signing-key",
                    "scope_type": "delivery_target",
                    "scope_id": webhook_target["id"],
                    "value": secret_value,
                },
            )
            assert secret.status_code == 201, secret.text
            assert secret_value not in secret.text
            assert "value" not in secret.json()
            updated_target = {
                key: webhook_target[key]
                for key in (
                    "name", "type", "visibility", "enabled", "url", "auth_scheme",
                    "secret_id", "max_attempts", "backoff_seconds"
                )
            }
            updated_target.update({"auth_scheme": "hmac_sha256", "secret_id": secret.json()["id"]})
            update = client.put(
                f"/api/v1/delivery-targets/{webhook_target['id']}?expectedRevision={webhook_target['revision']}",
                headers=headers,
                json=updated_target,
            )
            assert update.status_code == 200, update.text

            IntegrationHandler.fail_posts = True
            failed = client.post(
                "/api/v1/deliveries",
                headers=headers,
                json={"target_id": webhook_target["id"], "run_id": run["id"], "idempotency_key": "webhook-1"},
            )
            assert failed.json()["status"] == "dead_letter"
            duplicate = client.post(
                "/api/v1/deliveries",
                headers=headers,
                json={"target_id": webhook_target["id"], "run_id": run["id"], "idempotency_key": "webhook-1"},
            )
            assert duplicate.json()["id"] == failed.json()["id"]
            assert len(IntegrationHandler.posts) == 1

            IntegrationHandler.fail_posts = False
            replayed = client.post(
                f"/api/v1/deliveries/{failed.json()['id']}/replay", headers=headers
            )
            assert replayed.status_code == 200, replayed.text
            assert replayed.json()["status"] == "succeeded"
            assert len(IntegrationHandler.posts) == 2
            assert IntegrationHandler.posts[0]["idempotency"] == "webhook-1"
            assert str(IntegrationHandler.posts[0]["signature"]).startswith("sha256=")

            current_target = update.json()
            retry_definition = {
                key: current_target[key]
                for key in (
                    "name", "type", "visibility", "enabled", "url", "auth_scheme",
                    "secret_id", "max_attempts", "backoff_seconds"
                )
            }
            retry_definition["max_attempts"] = 3
            updated = client.put(
                f"/api/v1/delivery-targets/{webhook_target['id']}?expectedRevision={current_target['revision']}",
                headers=headers,
                json=retry_definition,
            )
            assert updated.status_code == 200
            IntegrationHandler.fail_posts = True
            pending = client.post(
                "/api/v1/deliveries",
                headers=headers,
                json={"target_id": webhook_target["id"], "run_id": run["id"], "idempotency_key": "webhook-cancel"},
            )
            assert pending.json()["status"] == "retrying"
            cancelled = client.post(
                f"/api/v1/deliveries/{pending.json()['id']}/cancel", headers=headers
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"

            audit_text = client.get("/api/v1/audit", headers=headers).text
            secret_list_text = client.get("/api/v1/secrets", headers=headers).text
            assert secret_value not in audit_text
            assert secret_value not in secret_list_text
            with sqlite3.connect(tmp_path / "crawler.db") as db:
                ciphertext = db.execute("SELECT ciphertext FROM scoped_secrets WHERE id=?", (secret.json()["id"],)).fetchone()[0]
            assert secret_value not in ciphertext
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
