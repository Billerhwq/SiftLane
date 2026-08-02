from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError

from siftlane_engine.api import create_app
from siftlane_engine.config import Settings
from siftlane_engine.connectors import (
    MAX_CONNECTOR_OUTPUT_BYTES,
    ConnectorProcessError,
    ConnectorRegistry,
    _connector_environment,
    _decode_worker_output,
)
from subprocess import CompletedProcess
import os
import pytest


ADMIN_PASSWORD = "Admin-password-123"
EDITOR_PASSWORD = "Editor-password-123"
VIEWER_PASSWORD = "Viewer-password-123"


def simple_flow(name: str, visibility: str = "team") -> dict:
    return {
        "name": name,
        "visibility": visibility,
        "max_items": 10,
        "timeout_seconds": 10,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Start",
                "config": {"urls": ["https://example.com/item"]},
            },
            {"id": "emit", "type": "emit", "name": "Emit", "config": {}},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "emit"}],
    }


def team_settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        auth_mode="team",
        bootstrap_admin_username="admin",
        bootstrap_admin_password=ADMIN_PASSWORD,
        secret_key="test-engine-secret-key-32-characters-long",
        worker_count=1,
        request_min_delay_seconds=0,
    )


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(
    client: TestClient,
    headers: dict[str, str],
    username: str,
    password: str,
    role: str,
) -> dict:
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": username,
            "display_name": username.title(),
            "password": password,
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_team_auth_sessions_users_and_last_admin_guard(tmp_path):
    with TestClient(create_app(team_settings(tmp_path))) as client:
        assert client.get("/api/v1/flows").status_code == 401
        admin_headers = login(client, "admin", ADMIN_PASSWORD)
        me = client.get("/api/v1/auth/me", headers=admin_headers)
        assert me.status_code == 200
        assert me.json()["role"] == "admin"
        assert me.json()["auth_mode"] == "team"

        editor = create_user(
            client, admin_headers, "editor", EDITOR_PASSWORD, "editor"
        )
        create_user(client, admin_headers, "viewer", VIEWER_PASSWORD, "viewer")
        assert len(client.get("/api/v1/users", headers=admin_headers).json()) == 3

        cannot_remove_last_admin = client.patch(
            f"/api/v1/users/{me.json()['id']}",
            headers=admin_headers,
            json={"active": False},
        )
        assert cannot_remove_last_admin.status_code == 409

        editor_headers = login(client, "editor", EDITOR_PASSWORD)
        refreshed = client.post("/api/v1/auth/refresh", headers=editor_headers)
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"] != editor_headers["Authorization"][7:]
        assert client.get("/api/v1/auth/me", headers=editor_headers).status_code == 401
        editor_headers = {
            "Authorization": f"Bearer {refreshed.json()['access_token']}"
        }
        changed = client.patch(
            f"/api/v1/users/{editor['id']}",
            headers=admin_headers,
            json={"password": "Editor-password-456"},
        )
        assert changed.status_code == 200
        assert client.get("/api/v1/auth/me", headers=editor_headers).status_code == 401

        logout_headers = login(client, "editor", "Editor-password-456")
        assert client.post("/api/v1/auth/logout", headers=logout_headers).status_code == 204
        assert client.get("/api/v1/auth/me", headers=logout_headers).status_code == 401


def test_resource_authorization_covers_flows_runs_results_and_schedules(tmp_path):
    with TestClient(create_app(team_settings(tmp_path))) as client:
        admin = login(client, "admin", ADMIN_PASSWORD)
        create_user(client, admin, "editor", EDITOR_PASSWORD, "editor")
        create_user(client, admin, "viewer", VIEWER_PASSWORD, "viewer")
        editor = login(client, "editor", EDITOR_PASSWORD)
        viewer = login(client, "viewer", VIEWER_PASSWORD)

        private_flow = client.post(
            "/api/v1/flows", headers=admin, json=simple_flow("Private", "private")
        ).json()
        team_flow = client.post(
            "/api/v1/flows", headers=admin, json=simple_flow("Team", "team")
        ).json()

        assert client.get(f"/api/v1/flows/{private_flow['id']}", headers=editor).status_code == 404
        assert [flow["id"] for flow in client.get("/api/v1/flows", headers=editor).json()] == [
            team_flow["id"]
        ]
        assert client.put(
            f"/api/v1/flows/{team_flow['id']}",
            headers=editor,
            json=simple_flow("Changed", "team"),
        ).status_code == 404

        run_response = client.post(
            "/api/v1/runs",
            headers=editor,
            json={"flow_id": team_flow["id"], "parameters": {}},
        )
        assert run_response.status_code == 202, run_response.text
        run_id = run_response.json()["id"]
        assert client.get(f"/api/v1/runs/{run_id}/events", headers=viewer).status_code == 200
        assert client.get(f"/api/v1/runs/{run_id}/items", headers=viewer).status_code == 200
        assert client.post(
            f"/api/v1/runs/{run_id}/cancel", headers=viewer
        ).status_code == 404
        assert client.post(
            "/api/v1/runs",
            headers=viewer,
            json={"flow_id": team_flow["id"], "parameters": {}},
        ).status_code == 404

        schedule = client.post(
            "/api/v1/schedules",
            headers=editor,
            json={
                "flow_id": team_flow["id"],
                "name": "Editor schedule",
                "cron": "0 8 * * *",
                "timezone": "Asia/Shanghai",
                "enabled": False,
                "parameters": {},
            },
        )
        assert schedule.status_code == 201, schedule.text
        assert client.post(
            f"/api/v1/schedules/{schedule.json()['id']}/trigger", headers=viewer
        ).status_code == 404

        audit = client.get("/api/v1/audit", headers=admin)
        assert audit.status_code == 200
        actions = {(row["action"], row["outcome"]) for row in audit.json()}
        assert ("flow.read", "denied") in actions
        assert ("run.create", "denied") in actions
        assert ("schedule.create", "success") in actions
        assert client.get("/api/v1/audit", headers=viewer).status_code == 403
        security = client.get("/api/v1/operations/security", headers=admin)
        assert security.status_code == 200
        assert security.json()["counters"]["authorization_denied_total"] >= 4

        rejected_origin = client.options(
            "/api/v1/flows",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in rejected_origin.headers


def test_role_demotion_removes_owner_mutation_and_execution_rights(tmp_path):
    with TestClient(create_app(team_settings(tmp_path))) as client:
        admin = login(client, "admin", ADMIN_PASSWORD)
        editor_user = create_user(
            client, admin, "editor", EDITOR_PASSWORD, "editor"
        )
        editor = login(client, "editor", EDITOR_PASSWORD)
        owned_flow = client.post(
            "/api/v1/flows",
            headers=editor,
            json=simple_flow("Owned before demotion", "private"),
        ).json()
        owned_target = client.post(
            "/api/v1/delivery-targets",
            headers=editor,
            json={"name": "Owned archive", "type": "ndjson", "visibility": "private"},
        ).json()

        demoted = client.patch(
            f"/api/v1/users/{editor_user['id']}",
            headers=admin,
            json={"role": "viewer"},
        )
        assert demoted.status_code == 200, demoted.text
        viewer = login(client, "editor", EDITOR_PASSWORD)

        assert client.get(
            f"/api/v1/flows/{owned_flow['id']}", headers=viewer
        ).status_code == 200
        assert client.put(
            f"/api/v1/flows/{owned_flow['id']}",
            headers=viewer,
            json=simple_flow("Mutation denied", "private"),
        ).status_code == 404
        assert client.post(
            "/api/v1/runs",
            headers=viewer,
            json={"flow_id": owned_flow["id"], "parameters": {}},
        ).status_code == 404
        assert client.put(
            f"/api/v1/delivery-targets/{owned_target['id']}",
            headers=viewer,
            json={"name": "Mutation denied", "type": "ndjson", "visibility": "private"},
        ).status_code == 404
        assert client.delete(
            f"/api/v1/delivery-targets/{owned_target['id']}", headers=viewer
        ).status_code == 404


def test_login_rate_limit_and_non_loopback_auth_guard(tmp_path):
    settings = team_settings(tmp_path)
    settings.login_max_attempts = 2
    with TestClient(create_app(settings)) as client:
        for _ in range(2):
            assert client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrong"},
            ).status_code == 401
        limited = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": ADMIN_PASSWORD},
        )
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1

    try:
        Settings(bind_address="0.0.0.0")
    except ValidationError as error:
        assert "non-loopback bind" in str(error)
    else:
        raise AssertionError("non-loopback local mode without a token must be rejected")


def test_connector_discovery_failure_stays_outside_engine_process(monkeypatch):
    class MissingEntryPoint:
        name = "missing-connector"

    class EntryPoints:
        @staticmethod
        def select(**_):
            return [MissingEntryPoint()]

    monkeypatch.setattr("siftlane_engine.connectors.entry_points", EntryPoints)
    registry = ConnectorRegistry.discover()
    assert registry.manifests() == []
    assert "missing-connector" in registry.errors()

    os.environ["SIFTLANE_ENGINE_SECRET_FIXTURE"] = "must-not-cross-process"
    try:
        assert "SIFTLANE_ENGINE_SECRET_FIXTURE" not in _connector_environment()
    finally:
        del os.environ["SIFTLANE_ENGINE_SECRET_FIXTURE"]

    oversized = CompletedProcess(
        args=[],
        returncode=0,
        stdout=b"x" * (MAX_CONNECTOR_OUTPUT_BYTES + 1),
        stderr=b"",
    )
    with pytest.raises(ConnectorProcessError, match="output limit"):
        _decode_worker_output(oversized)
