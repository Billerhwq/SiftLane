from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from siftlane_engine.api import create_app
from siftlane_engine.config import Settings
from siftlane_engine import __version__


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
        else:
            body = b"""
                <html><body>
                  <article><h2>First result</h2><a href="/one">Open</a><p>Useful body</p></article>
                  <article><h2>Second result</h2><a href="/two">Open</a><p>More body</p></article>
                </body></html>
            """
        self.send_response(200)
        self.send_header("Content-Type", "text/plain" if self.path == "/robots.txt" else "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


def flow(base_url: str) -> dict:
    return {
        "name": "HTML fixture",
        "description": "End-to-end fixture",
        "max_items": 10,
        "timeout_seconds": 10,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Seeds",
                "x": 0,
                "y": 0,
                "config": {"urls": [base_url]},
            },
            {
                "id": "request",
                "type": "http_request",
                "name": "Fetch",
                "x": 220,
                "y": 0,
                "config": {"url": "{{url}}", "respect_robots": True},
            },
            {
                "id": "extract",
                "type": "html_extract",
                "name": "Extract",
                "x": 440,
                "y": 0,
                "config": {
                    "item_selector": "article",
                    "fields": {
                        "title": "h2",
                        "url": {"selector": "a", "attribute": "href"},
                        "content": "p",
                    },
                },
            },
            {
                "id": "emit",
                "type": "emit",
                "name": "Emit",
                "x": 660,
                "y": 0,
                "config": {},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "request"},
            {"id": "e2", "source": "request", "target": "extract"},
            {"id": "e3", "source": "extract", "target": "emit"},
        ],
    }


def simple_flow(name: str = "Snapshot fixture") -> dict:
    return {
        "name": name,
        "max_items": 10,
        "timeout_seconds": 10,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Seeds",
                "config": {"urls": ["https://example.com/item"]},
            },
            {
                "id": "emit",
                "type": "emit",
                "name": "Emit",
                "config": {},
            },
        ],
        "edges": [{"id": "e1", "source": "start", "target": "emit"}],
    }


def wait_for_terminal(client: TestClient, run_id: str) -> dict:
    for _ in range(100):
        run = client.get(f"/api/v1/runs/{run_id}").json()
        if run["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        time.sleep(0.03)
    raise AssertionError(f"run {run_id} did not reach a terminal state")


def test_flow_run_and_result_persistence(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/page"
    settings = Settings(
        data_dir=tmp_path,
        allow_private_networks=True,
        request_min_delay_seconds=0,
        worker_count=1,
    )
    try:
        with TestClient(create_app(settings)) as client:
            created = client.post("/api/v1/flows", json=flow(base_url))
            assert created.status_code == 201, created.text
            flow_id = created.json()["id"]
            first = client.post(
                "/api/v1/runs",
                json={"flow_id": flow_id, "idempotency_key": "fixture-1", "parameters": {}},
            )
            assert first.status_code == 202
            duplicate = client.post(
                "/api/v1/runs",
                json={"flow_id": flow_id, "idempotency_key": "fixture-1", "parameters": {}},
            )
            assert duplicate.json()["id"] == first.json()["id"]
            run_id = first.json()["id"]
            for _ in range(100):
                run = client.get(f"/api/v1/runs/{run_id}").json()
                if run["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    break
                time.sleep(0.03)
            assert run["status"] == "SUCCEEDED", run
            assert run["processed_items"] == 2
            page = client.get(f"/api/v1/runs/{run_id}/items").json()
            assert [item["title"] for item in page["items"]] == [
                "First result",
                "Second result",
            ]
            events = client.get(f"/api/v1/runs/{run_id}/events").json()
            assert events[-1]["type"] == "run.completed"
    finally:
        server.shutdown()
        server.server_close()


def test_run_snapshot_cors_and_sse_resume(tmp_path):
    settings = Settings(data_dir=tmp_path, request_min_delay_seconds=0, worker_count=1)
    with TestClient(create_app(settings)) as client:
        cors = client.options(
            "/api/v1/flows",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert cors.status_code == 200
        assert cors.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

        created = client.post("/api/v1/flows", json=simple_flow())
        assert created.status_code == 201, created.text
        flow_id = created.json()["id"]
        run_response = client.post(
            "/api/v1/runs",
            json={"flow_id": flow_id, "parameters": {}},
        )
        assert run_response.status_code == 202, run_response.text
        run_id = run_response.json()["id"]
        assert wait_for_terminal(client, run_id)["status"] == "SUCCEEDED"

        changed = simple_flow("Changed after run creation")
        updated = client.put(
            f"/api/v1/flows/{flow_id}?expectedRevision=1", json=changed
        )
        assert updated.status_code == 200, updated.text
        snapshot = client.get(f"/api/v1/runs/{run_id}/flow").json()
        assert snapshot["flow_revision"] == 1
        assert snapshot["definition"]["name"] == "Snapshot fixture"

        events = client.get(f"/api/v1/runs/{run_id}/events").json()
        assert len(events) >= 2
        resume_after = events[-2]["sequence"]
        with client.stream(
            "GET",
            f"/api/v1/runs/{run_id}/events/stream",
            headers={"Last-Event-ID": str(resume_after)},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())
        assert f"id: {events[-1]['sequence']}\n" in body
        assert f"event: {events[-1]['type']}\n" in body
        assert f"id: {resume_after}\n" not in body

        invalid_resume = client.get(
            f"/api/v1/runs/{run_id}/events/stream",
            headers={"Last-Event-ID": "not-a-sequence"},
        )
        assert invalid_resume.status_code == 400


def test_api_token_protects_engine_routes(tmp_path):
    settings = Settings(data_dir=tmp_path, api_token="test-token", worker_count=1)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/flows").status_code == 401
        authorized = client.get(
            "/api/v1/flows", headers={"Authorization": "Bearer test-token"}
        )
        assert authorized.status_code == 200


def test_health_and_openapi_expose_runtime_version(tmp_path):
    settings = Settings(data_dir=tmp_path, worker_count=1)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["version"] == __version__
        assert client.get("/openapi.json").json()["info"]["version"] == __version__


def test_capabilities_expose_connector_contract(tmp_path):
    settings = Settings(data_dir=tmp_path, worker_count=1)
    with TestClient(create_app(settings)) as client:
        capabilities = client.get("/api/v1/capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()["features"]["connectorSdk"] is True
        assert capabilities.json()["connectorCount"] == 0
        connectors = client.get("/api/v1/connectors")
        assert connectors.status_code == 200
        assert connectors.json() == []
        contract = client.get("/api/v1/connector-contract")
        assert contract.status_code == 200
        assert contract.json()["apiVersion"] == "siftlane.connector/v1"
        assert contract.json()["entryPointGroup"] == "siftlane.connectors"
        assert contract.json()["schemas"]["manifest"]["title"] == "ConnectorManifest"


def test_schedule_api_create_update_trigger_and_delete(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        worker_count=1,
        scheduler_poll_seconds=0.05,
    )
    with TestClient(create_app(settings)) as client:
        created_flow = client.post("/api/v1/flows", json=simple_flow())
        assert created_flow.status_code == 201
        flow_id = created_flow.json()["id"]
        definition = {
            "flow_id": flow_id,
            "name": "Morning crawl",
            "cron": "0 8 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "parameters": {},
        }
        created = client.post("/api/v1/schedules", json=definition)
        assert created.status_code == 201, created.text
        schedule = created.json()
        assert schedule["next_run_at"] is not None

        definition["enabled"] = False
        updated = client.put(
            f"/api/v1/schedules/{schedule['id']}?expectedRevision=1",
            json=definition,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert updated.json()["next_run_at"] is None

        triggered = client.post(f"/api/v1/schedules/{schedule['id']}/trigger")
        assert triggered.status_code == 202, triggered.text
        assert wait_for_terminal(client, triggered.json()["id"])["status"] == "SUCCEEDED"

        listed = client.get("/api/v1/schedules").json()
        assert listed[0]["last_run_id"] == triggered.json()["id"]
        deleted = client.delete(f"/api/v1/schedules/{schedule['id']}")
        assert deleted.status_code == 204
