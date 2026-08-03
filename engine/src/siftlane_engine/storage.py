from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from .models import (
    AuditRecord,
    EventRecord,
    FlowDefinition,
    FlowRecord,
    FlowVisibility,
    ItemRecord,
    ImportPreviewItem,
    ImportEventRecord,
    ImportStatus,
    NodeCheckpoint,
    RunFlowSnapshot,
    RunRecord,
    RunStatus,
    ScheduleDefinition,
    ScheduleRecord,
    UserRecord,
    UserRole,
    WebsiteImportCreate,
    WebsiteImportRecord,
    utc_now,
)


SCHEMA_VERSION = 7
MIN_COMPATIBLE_SCHEMA_VERSION = 2


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  active INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  actor_user_id TEXT,
  actor_username TEXT,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  outcome TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS flows (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  max_items INTEGER NOT NULL,
  timeout_seconds INTEGER NOT NULL,
  parameter_schema_json TEXT NOT NULL,
  graph_json TEXT NOT NULL,
  owner_id TEXT NOT NULL DEFAULT 'local-operator',
  visibility TEXT NOT NULL DEFAULT 'team',
  revision INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  flow_id TEXT NOT NULL REFERENCES flows(id),
  flow_name TEXT NOT NULL,
  flow_revision INTEGER NOT NULL,
  flow_snapshot_json TEXT NOT NULL,
  owner_id TEXT NOT NULL DEFAULT 'local-operator',
  visibility TEXT NOT NULL DEFAULT 'team',
  created_by TEXT NOT NULL DEFAULT 'local-operator',
  status TEXT NOT NULL,
  parameters_json TEXT NOT NULL,
  idempotency_key TEXT,
  current_node TEXT,
  message TEXT,
  processed_items INTEGER NOT NULL DEFAULT 0,
  total_items INTEGER,
  error_code TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_idempotency
  ON runs(flow_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  external_id TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  media_type TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_items_run_created ON items(run_id, created_at, id);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  type TEXT NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  data_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_events_run_sequence ON events(run_id, sequence);
CREATE TABLE IF NOT EXISTS node_checkpoints (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL,
  status TEXT NOT NULL,
  output_blob BLOB NOT NULL,
  output_checksum TEXT NOT NULL,
  attempt_count INTEGER NOT NULL,
  emitted_count INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(run_id, node_id)
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON node_checkpoints(run_id);
CREATE TABLE IF NOT EXISTS schedules (
  id TEXT PRIMARY KEY,
  flow_id TEXT NOT NULL REFERENCES flows(id),
  name TEXT NOT NULL,
  cron TEXT NOT NULL,
  timezone TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  parameters_json TEXT NOT NULL,
  owner_id TEXT NOT NULL DEFAULT 'local-operator',
  visibility TEXT NOT NULL DEFAULT 'team',
  created_by TEXT NOT NULL DEFAULT 'local-operator',
  next_run_at TEXT,
  last_run_at TEXT,
  last_run_id TEXT REFERENCES runs(id),
  last_error TEXT,
  revision INTEGER NOT NULL,
  lease_owner TEXT,
  lease_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedules_due
  ON schedules(enabled, next_run_at, lease_until);
CREATE TABLE IF NOT EXISTS website_imports (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, visibility TEXT NOT NULL,
  status TEXT NOT NULL, source_url TEXT NOT NULL, intent_json TEXT NOT NULL,
  scope_json TEXT NOT NULL, runtime_preference TEXT NOT NULL,
  probe_revision INTEGER NOT NULL DEFAULT 0, draft_revision INTEGER NOT NULL DEFAULT 0,
  preview_revision INTEGER NOT NULL DEFAULT 0, probe_report_json TEXT,
  flow_draft_json TEXT, created_flow_id TEXT REFERENCES flows(id), confirm_idempotency_key TEXT,
  error_code TEXT,
  error_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_website_imports_updated ON website_imports(updated_at DESC);
CREATE TABLE IF NOT EXISTS preview_items (
  id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES website_imports(id) ON DELETE CASCADE,
  draft_revision INTEGER NOT NULL, external_id TEXT NOT NULL, normalized_json TEXT NOT NULL,
  field_evidence_json TEXT NOT NULL, quality_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(import_id, draft_revision, external_id)
);
CREATE TABLE IF NOT EXISTS import_events (
  id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES website_imports(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL, type TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL,
  data_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(import_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_import_events_sequence ON import_events(import_id, sequence);
"""


@dataclass(frozen=True)
class RecoveryPlan:
    requeued: list[str]
    recovered: list[str]
    cancelled: list[str]


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.executescript(SCHEMA)
            run_columns = {
                row["name"]
                for row in await (await db.execute("PRAGMA table_info(runs)")).fetchall()
            }
            if "flow_revision" not in run_columns:
                await db.execute("ALTER TABLE runs ADD COLUMN flow_revision INTEGER")
            if "flow_snapshot_json" not in run_columns:
                await db.execute("ALTER TABLE runs ADD COLUMN flow_snapshot_json TEXT")
            for name, declaration in {
                "owner_id": "TEXT NOT NULL DEFAULT 'local-operator'",
                "visibility": "TEXT NOT NULL DEFAULT 'team'",
                "created_by": "TEXT NOT NULL DEFAULT 'local-operator'",
            }.items():
                if name not in run_columns:
                    await db.execute(f"ALTER TABLE runs ADD COLUMN {name} {declaration}")

            flow_columns = {
                row["name"]
                for row in await (await db.execute("PRAGMA table_info(flows)")).fetchall()
            }
            for name, declaration in {
                "owner_id": "TEXT NOT NULL DEFAULT 'local-operator'",
                "visibility": "TEXT NOT NULL DEFAULT 'team'",
            }.items():
                if name not in flow_columns:
                    await db.execute(f"ALTER TABLE flows ADD COLUMN {name} {declaration}")

            schedule_columns = {
                row["name"]
                for row in await (await db.execute("PRAGMA table_info(schedules)")).fetchall()
            }
            for name, declaration in {
                "owner_id": "TEXT NOT NULL DEFAULT 'local-operator'",
                "visibility": "TEXT NOT NULL DEFAULT 'team'",
                "created_by": "TEXT NOT NULL DEFAULT 'local-operator'",
            }.items():
                if name not in schedule_columns:
                    await db.execute(
                        f"ALTER TABLE schedules ADD COLUMN {name} {declaration}"
                    )
            import_columns = {
                row["name"] for row in await (await db.execute("PRAGMA table_info(website_imports)")).fetchall()
            }
            if "confirm_idempotency_key" not in import_columns:
                await db.execute("ALTER TABLE website_imports ADD COLUMN confirm_idempotency_key TEXT")
            now = utc_now().isoformat()
            await db.execute(
                """INSERT OR IGNORE INTO users(
                     id,username,display_name,password_hash,role,active,created_at,updated_at
                   ) VALUES('local-operator','local','Local operator','',?,1,?,?)""",
                (UserRole.ADMIN.value, now, now),
            )
            await db.execute(
                """UPDATE runs
                   SET flow_revision=COALESCE(
                         flow_revision,
                         (SELECT revision FROM flows WHERE flows.id=runs.flow_id)
                       ),
                       flow_snapshot_json=COALESCE(
                         flow_snapshot_json,
                         (SELECT graph_json FROM flows WHERE flows.id=runs.flow_id)
                       )
                   WHERE flow_revision IS NULL OR flow_snapshot_json IS NULL"""
            )
            await db.execute(
                """UPDATE runs SET
                     owner_id=COALESCE(NULLIF(owner_id,''),
                       (SELECT owner_id FROM flows WHERE flows.id=runs.flow_id),
                       'local-operator'),
                     visibility=COALESCE(NULLIF(visibility,''),
                       (SELECT visibility FROM flows WHERE flows.id=runs.flow_id),
                       'team'),
                     created_by=COALESCE(NULLIF(created_by,''),'local-operator')"""
            )
            await db.execute(
                """UPDATE schedules SET
                     owner_id=COALESCE(NULLIF(owner_id,''),
                       (SELECT owner_id FROM flows WHERE flows.id=schedules.flow_id),
                       'local-operator'),
                     visibility=COALESCE(NULLIF(visibility,''),
                       (SELECT visibility FROM flows WHERE flows.id=schedules.flow_id),
                       'team'),
                     created_by=COALESCE(NULLIF(created_by,''),'local-operator')"""
            )
            await db.execute(
                """INSERT INTO schema_meta(key,value) VALUES('schema_version',?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (str(SCHEMA_VERSION),),
            )
            await db.execute(
                """INSERT INTO schema_meta(key,value) VALUES('last_migration_at',?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (now,),
            )
            await db.commit()

    async def _connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        return db

    async def count_team_users(self) -> int:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT COUNT(*) AS total FROM users WHERE id<>'local-operator'"
                )
            ).fetchone()
            return int(row["total"])
        finally:
            await db.close()

    async def schema_status(self) -> dict[str, Any]:
        db = await self._connect()
        try:
            rows = await (await db.execute("SELECT key,value FROM schema_meta")).fetchall()
            values = {row["key"]: row["value"] for row in rows}
            await db.execute("SELECT 1")
            return {
                "current": int(values.get("schema_version", "0")),
                "supportedMinimum": MIN_COMPATIBLE_SCHEMA_VERSION,
                "latest": SCHEMA_VERSION,
                "lastMigrationAt": values.get("last_migration_at"),
                "ready": int(values.get("schema_version", "0")) == SCHEMA_VERSION,
            }
        finally:
            await db.close()

    async def operational_stats(self) -> dict[str, dict[str, int] | int]:
        db = await self._connect()
        try:
            run_rows = await (await db.execute("SELECT status,COUNT(*) AS total FROM runs GROUP BY status")).fetchall()
            delivery_table = await (
                await db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='deliveries'"
                )
            ).fetchone()
            delivery_rows = (
                await (await db.execute("SELECT status,COUNT(*) AS total FROM deliveries GROUP BY status")).fetchall()
                if delivery_table
                else []
            )
            database_bytes = self.path.stat().st_size if self.path.exists() else 0
            return {
                "runs": {row["status"]: int(row["total"]) for row in run_rows},
                "deliveries": {row["status"]: int(row["total"]) for row in delivery_rows},
                "databaseBytes": database_bytes,
            }
        finally:
            await db.close()

    async def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password_hash: str,
        role: UserRole,
    ) -> UserRecord:
        now = utc_now()
        user_id = str(uuid.uuid4())
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    """INSERT INTO users(
                         id,username,display_name,password_hash,role,active,
                         created_at,updated_at
                       ) VALUES(?,?,?,?,?,1,?,?)""",
                    (
                        user_id,
                        username,
                        display_name,
                        password_hash,
                        role.value,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        user = await self.get_user(user_id)
        if user is None:
            raise RuntimeError("user was not persisted")
        return user

    async def list_users(self) -> list[UserRecord]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    """SELECT * FROM users WHERE id<>'local-operator'
                       ORDER BY username"""
                )
            ).fetchall()
            return [self._user(row) for row in rows]
        finally:
            await db.close()

    async def get_user(self, user_id: str) -> UserRecord | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute("SELECT * FROM users WHERE id=?", (user_id,))
            ).fetchone()
            return self._user(row) if row else None
        finally:
            await db.close()

    async def get_user_credentials(
        self, username: str
    ) -> tuple[UserRecord, str] | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT * FROM users WHERE username=?", (username.lower(),)
                )
            ).fetchone()
            return (self._user(row), row["password_hash"]) if row else None
        finally:
            await db.close()

    async def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        password_hash: str | None = None,
        role: UserRole | None = None,
        active: bool | None = None,
    ) -> UserRecord | None:
        changes: list[str] = []
        values: list[Any] = []
        if display_name is not None:
            changes.append("display_name=?")
            values.append(display_name)
        if password_hash is not None:
            changes.append("password_hash=?")
            values.append(password_hash)
        if role is not None:
            changes.append("role=?")
            values.append(role.value)
        if active is not None:
            changes.append("active=?")
            values.append(int(active))
        if not changes:
            return await self.get_user(user_id)
        changes.append("updated_at=?")
        values.append(utc_now().isoformat())
        values.append(user_id)
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    f"UPDATE users SET {','.join(changes)} WHERE id=? AND id<>'local-operator'",
                    values,
                )
                if cursor.rowcount != 1:
                    return None
                if active is False or password_hash is not None:
                    await db.execute(
                        "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                        (utc_now().isoformat(), user_id),
                    )
                await db.commit()
            finally:
                await db.close()
        return await self.get_user(user_id)

    async def count_active_admins(self) -> int:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    """SELECT COUNT(*) AS total FROM users
                       WHERE id<>'local-operator' AND role='admin' AND active=1"""
                )
            ).fetchone()
            return int(row["total"])
        finally:
            await db.close()

    async def create_session(
        self, user_id: str, token_hash: str, expires_at: datetime
    ) -> str:
        session_id = str(uuid.uuid4())
        now = utc_now()
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    "DELETE FROM sessions WHERE expires_at<=? OR revoked_at IS NOT NULL",
                    (now.isoformat(),),
                )
                await db.execute(
                    """INSERT INTO sessions(
                         id,user_id,token_hash,expires_at,created_at
                       ) VALUES(?,?,?,?,?)""",
                    (
                        session_id,
                        user_id,
                        token_hash,
                        expires_at.isoformat(),
                        now.isoformat(),
                    ),
                )
                await db.execute(
                    "UPDATE users SET last_login_at=?,updated_at=? WHERE id=?",
                    (now.isoformat(), now.isoformat(), user_id),
                )
                await db.commit()
            finally:
                await db.close()
        return session_id

    async def get_session_user(
        self, token_hash: str, now: datetime
    ) -> tuple[str, UserRecord, datetime] | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    """SELECT s.id AS session_id,s.expires_at,u.*
                       FROM sessions s JOIN users u ON u.id=s.user_id
                       WHERE s.token_hash=? AND s.revoked_at IS NULL
                         AND s.expires_at>? AND u.active=1""",
                    (token_hash, now.isoformat()),
                )
            ).fetchone()
            if row is None:
                return None
            return row["session_id"], self._user(row), self._dt(row["expires_at"])
        finally:
            await db.close()

    async def revoke_session(self, session_id: str) -> None:
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    "UPDATE sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                    (utc_now().isoformat(), session_id),
                )
                await db.commit()
            finally:
                await db.close()

    async def add_audit(
        self,
        *,
        actor_user_id: str | None,
        actor_username: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str,
        detail: dict[str, Any] | None = None,
    ) -> AuditRecord:
        event_id = str(uuid.uuid4())
        now = utc_now()
        safe_detail = detail or {}
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    """INSERT INTO audit_events(
                         id,actor_user_id,actor_username,action,resource_type,
                         resource_id,outcome,detail_json,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        event_id,
                        actor_user_id,
                        actor_username,
                        action,
                        resource_type,
                        resource_id,
                        outcome,
                        self._json(safe_detail),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        return AuditRecord(
            id=event_id,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            detail=safe_detail,
            created_at=now,
        )

    async def list_audit(self, limit: int = 200) -> list[AuditRecord]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    """SELECT * FROM audit_events
                       ORDER BY created_at DESC,id DESC LIMIT ?""",
                    (max(1, min(limit, 1000)),),
                )
            ).fetchall()
            return [self._audit(row) for row in rows]
        finally:
            await db.close()

    async def list_flows(self) -> list[FlowRecord]:
        db = await self._connect()
        try:
            rows = await (await db.execute("SELECT * FROM flows ORDER BY updated_at DESC")).fetchall()
            return [self._flow(row) for row in rows]
        finally:
            await db.close()

    async def get_flow(self, flow_id: str) -> FlowRecord | None:
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT * FROM flows WHERE id=?", (flow_id,))).fetchone()
            return self._flow(row) if row else None
        finally:
            await db.close()

    def _website_import(self, row: aiosqlite.Row) -> WebsiteImportRecord:
        return WebsiteImportRecord(
            id=row["id"], owner_id=row["owner_id"], visibility=FlowVisibility(row["visibility"]),
            status=ImportStatus(row["status"]), source_url=row["source_url"],
            intent=json.loads(row["intent_json"]), scope=json.loads(row["scope_json"]),
            runtime_preference=row["runtime_preference"], probe_revision=row["probe_revision"],
            draft_revision=row["draft_revision"], preview_revision=row["preview_revision"],
            probe_report_json=json.loads(row["probe_report_json"]) if row["probe_report_json"] else None,
            flow_draft_json=json.loads(row["flow_draft_json"]) if row["flow_draft_json"] else None,
            created_flow_id=row["created_flow_id"], error_code=row["error_code"], error_message=row["error_message"],
            created_at=self._dt(row["created_at"]), updated_at=self._dt(row["updated_at"]),
        )

    async def create_website_import(self, definition: WebsiteImportCreate, owner_id: str) -> WebsiteImportRecord:
        now = utc_now().isoformat(); import_id = str(uuid.uuid4())
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute("INSERT INTO website_imports(id,owner_id,visibility,status,source_url,intent_json,scope_json,runtime_preference,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (import_id, owner_id, "team", ImportStatus.DRAFT.value, definition.source_url, self._json(definition.intent.model_dump()), self._json(definition.scope.model_dump()), definition.runtime_preference, now, now))
                await db.commit()
            finally: await db.close()
        result = await self.get_website_import(import_id)
        if result is None: raise RuntimeError("import was not persisted")
        return result

    async def list_website_imports(self) -> list[WebsiteImportRecord]:
        db = await self._connect()
        try: return [self._website_import(row) for row in await (await db.execute("SELECT * FROM website_imports ORDER BY updated_at DESC")).fetchall()]
        finally: await db.close()

    async def get_website_import(self, import_id: str) -> WebsiteImportRecord | None:
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT * FROM website_imports WHERE id=?", (import_id,))).fetchone()
            return self._website_import(row) if row else None
        finally: await db.close()

    async def update_website_import(self, import_id: str, **changes: Any) -> WebsiteImportRecord | None:
        if not changes: return await self.get_website_import(import_id)
        allowed = {"status", "probe_revision", "draft_revision", "preview_revision", "probe_report_json", "flow_draft_json", "created_flow_id", "error_code", "error_message"}
        if set(changes) - allowed: raise ValueError("invalid import update")
        values = []
        for key, value in changes.items():
            values.append(self._json(value) if key.endswith("_json") and value is not None else (value.value if isinstance(value, ImportStatus) else value))
        assignments = ", ".join(f"{key}=?" for key in changes) + ", updated_at=?"
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(f"UPDATE website_imports SET {assignments} WHERE id=?", (*values, utc_now().isoformat(), import_id)); await db.commit()
                if cursor.rowcount != 1: return None
            finally: await db.close()
        return await self.get_website_import(import_id)

    async def confirm_website_import(self, import_id: str, definition: FlowDefinition, owner_id: str, idempotency_key: str) -> WebsiteImportRecord | None:
        """Atomically create revision 1 and make the source Import Job terminal."""
        now = utc_now(); flow_id = str(uuid.uuid4()); graph = definition.model_dump(mode="json"); visibility = graph.pop("visibility")
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute("BEGIN IMMEDIATE")
                current = await (await db.execute("SELECT * FROM website_imports WHERE id=?", (import_id,))).fetchone()
                if current is None: await db.rollback(); return None
                if current["status"] == ImportStatus.CREATED.value:
                    if current["confirm_idempotency_key"] != idempotency_key:
                        raise RevisionConflict(1)
                    await db.rollback(); return self._website_import(current)
                if current["status"] != ImportStatus.PREVIEW_READY.value:
                    await db.rollback(); raise ValueError("preview must complete before confirm")
                await db.execute("INSERT INTO flows(id,name,description,enabled,max_items,timeout_seconds,parameter_schema_json,graph_json,owner_id,visibility,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (flow_id,definition.name,definition.description,int(definition.enabled),definition.max_items,definition.timeout_seconds,self._json(definition.parameter_schema),self._json(graph),owner_id,visibility,1,now.isoformat(),now.isoformat()))
                await db.execute("UPDATE website_imports SET status=?, created_flow_id=?, confirm_idempotency_key=?, updated_at=? WHERE id=?", (ImportStatus.CREATED.value,flow_id,idempotency_key,now.isoformat(),import_id))
                await db.commit()
            except Exception:
                await db.rollback(); raise
            finally: await db.close()
        return await self.get_website_import(import_id)

    async def replace_preview_items(self, import_id: str, revision: int, items: list[dict[str, Any]]) -> list[ImportPreviewItem]:
        now = utc_now().isoformat()
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute("DELETE FROM preview_items WHERE import_id=? AND draft_revision=?", (import_id, revision))
                for item in items[:10]:
                    await db.execute("INSERT INTO preview_items(id,import_id,draft_revision,external_id,normalized_json,field_evidence_json,quality_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), import_id, revision, item["external_id"], self._json(item["normalized_json"]), self._json(item["field_evidence_json"]), self._json(item["quality_json"]), now))
                await db.commit()
            finally: await db.close()
        return await self.list_preview_items(import_id)

    async def list_preview_items(self, import_id: str) -> list[ImportPreviewItem]:
        db = await self._connect()
        try:
            rows = await (await db.execute("SELECT * FROM preview_items WHERE import_id=? ORDER BY created_at,id", (import_id,))).fetchall()
            return [ImportPreviewItem(id=row["id"], import_id=row["import_id"], draft_revision=row["draft_revision"], external_id=row["external_id"], normalized_json=json.loads(row["normalized_json"]), field_evidence_json=json.loads(row["field_evidence_json"]), quality_json=json.loads(row["quality_json"]), created_at=self._dt(row["created_at"])) for row in rows]
        finally: await db.close()

    async def add_import_event(self, import_id: str, event_type: str, level: str, message: str, data: dict[str, Any]) -> ImportEventRecord:
        now = utc_now()
        async with self._write_lock:
            db = await self._connect()
            try:
                row = await (await db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM import_events WHERE import_id=?", (import_id,))).fetchone()
                event = ImportEventRecord(id=str(uuid.uuid4()), import_id=import_id, sequence=int(row["sequence"]), type=event_type, level=level, message=message[:1000], data=data, created_at=now)
                await db.execute("INSERT INTO import_events(id,import_id,sequence,type,level,message,data_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (event.id,event.import_id,event.sequence,event.type,event.level,event.message,self._json(event.data),now.isoformat()))
                await db.commit(); return event
            finally: await db.close()

    async def list_import_events(self, import_id: str, after: int = 0) -> list[ImportEventRecord]:
        db = await self._connect()
        try:
            rows = await (await db.execute("SELECT * FROM import_events WHERE import_id=? AND sequence>? ORDER BY sequence", (import_id, after))).fetchall()
            return [ImportEventRecord(id=row["id"], import_id=row["import_id"], sequence=row["sequence"], type=row["type"], level=row["level"], message=row["message"], data=json.loads(row["data_json"]), created_at=self._dt(row["created_at"])) for row in rows]
        finally: await db.close()

    async def create_flow(
        self, definition: FlowDefinition, owner_id: str = "local-operator"
    ) -> FlowRecord:
        now = utc_now()
        flow_id = str(uuid.uuid4())
        graph = definition.model_dump(mode="json")
        visibility = graph.pop("visibility")
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    """INSERT INTO flows(
                         id,name,description,enabled,max_items,timeout_seconds,
                         parameter_schema_json,graph_json,owner_id,visibility,
                         revision,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        flow_id,
                        definition.name,
                        definition.description,
                        int(definition.enabled),
                        definition.max_items,
                        definition.timeout_seconds,
                        self._json(definition.parameter_schema),
                        self._json(graph),
                        owner_id,
                        visibility,
                        1,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        created = await self.get_flow(flow_id)
        if created is None:
            raise RuntimeError("flow was not persisted")
        return created

    async def update_flow(
        self, flow_id: str, definition: FlowDefinition, expected_revision: int | None
    ) -> FlowRecord | None:
        now = utc_now()
        graph = definition.model_dump(mode="json")
        visibility = graph.pop("visibility")
        async with self._write_lock:
            db = await self._connect()
            try:
                current = await (
                    await db.execute(
                        "SELECT revision,created_at FROM flows WHERE id=?", (flow_id,)
                    )
                ).fetchone()
                if not current:
                    return None
                if expected_revision is not None and current["revision"] != expected_revision:
                    raise RevisionConflict(current["revision"])
                revision = current["revision"] + 1
                await db.execute(
                    """UPDATE flows SET name=?,description=?,enabled=?,max_items=?,
                         timeout_seconds=?,parameter_schema_json=?,graph_json=?,
                         visibility=?,revision=?,updated_at=? WHERE id=?""",
                    (
                        definition.name,
                        definition.description,
                        int(definition.enabled),
                        definition.max_items,
                        definition.timeout_seconds,
                        self._json(definition.parameter_schema),
                        self._json(graph),
                        visibility,
                        revision,
                        now.isoformat(),
                        flow_id,
                    ),
                )
                await db.commit()
                created_at = self._dt(current["created_at"])
            finally:
                await db.close()
        return await self.get_flow(flow_id)

    async def delete_flow(self, flow_id: str) -> bool:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute("DELETE FROM flows WHERE id=?", (flow_id,))
                await db.commit()
                return cursor.rowcount == 1
            finally:
                await db.close()

    async def list_schedules(self) -> list[ScheduleRecord]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute("SELECT * FROM schedules ORDER BY updated_at DESC")
            ).fetchall()
            return [self._schedule(row) for row in rows]
        finally:
            await db.close()

    async def get_schedule(self, schedule_id: str) -> ScheduleRecord | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,))
            ).fetchone()
            return self._schedule(row) if row else None
        finally:
            await db.close()

    async def create_schedule(
        self,
        definition: ScheduleDefinition,
        next_run_at: datetime | None,
        *,
        owner_id: str = "local-operator",
        visibility: FlowVisibility = FlowVisibility.TEAM,
        created_by: str = "local-operator",
    ) -> ScheduleRecord:
        now = utc_now()
        schedule_id = str(uuid.uuid4())
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    """INSERT INTO schedules(
                         id,flow_id,name,cron,timezone,enabled,parameters_json,
                         owner_id,visibility,created_by,next_run_at,revision,
                         created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                    (
                        schedule_id,
                        definition.flow_id,
                        definition.name,
                        definition.cron,
                        definition.timezone,
                        int(definition.enabled),
                        self._json(definition.parameters),
                        owner_id,
                        visibility.value,
                        created_by,
                        next_run_at.isoformat() if next_run_at else None,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        created = await self.get_schedule(schedule_id)
        if created is None:
            raise RuntimeError("schedule was not persisted")
        return created

    async def update_schedule(
        self,
        schedule_id: str,
        definition: ScheduleDefinition,
        expected_revision: int | None,
        next_run_at: datetime | None,
        *,
        owner_id: str | None = None,
        visibility: FlowVisibility | None = None,
    ) -> ScheduleRecord | None:
        now = utc_now()
        async with self._write_lock:
            db = await self._connect()
            try:
                current = await (
                    await db.execute(
                        "SELECT revision FROM schedules WHERE id=?", (schedule_id,)
                    )
                ).fetchone()
                if current is None:
                    return None
                if expected_revision is not None and current["revision"] != expected_revision:
                    raise RevisionConflict(current["revision"])
                revision = int(current["revision"]) + 1
                await db.execute(
                    """UPDATE schedules SET flow_id=?,name=?,cron=?,timezone=?,
                         enabled=?,parameters_json=?,next_run_at=?,revision=?,
                         owner_id=COALESCE(?,owner_id),
                         visibility=COALESCE(?,visibility),
                         lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?""",
                    (
                        definition.flow_id,
                        definition.name,
                        definition.cron,
                        definition.timezone,
                        int(definition.enabled),
                        self._json(definition.parameters),
                        next_run_at.isoformat() if next_run_at else None,
                        revision,
                        owner_id,
                        visibility.value if visibility else None,
                        now.isoformat(),
                        schedule_id,
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        return await self.get_schedule(schedule_id)

    async def delete_schedule(self, schedule_id: str) -> bool:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    "DELETE FROM schedules WHERE id=?", (schedule_id,)
                )
                await db.commit()
                return cursor.rowcount == 1
            finally:
                await db.close()

    async def claim_due_schedules(
        self,
        owner: str,
        now: datetime,
        *,
        lease_seconds: float,
        limit: int = 20,
    ) -> list[ScheduleRecord]:
        lease_until = now + timedelta(seconds=lease_seconds)
        claimed: list[ScheduleRecord] = []
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute("BEGIN IMMEDIATE")
                rows = await (
                    await db.execute(
                        """SELECT id FROM schedules
                           WHERE enabled=1 AND next_run_at IS NOT NULL
                             AND next_run_at<=?
                             AND (lease_until IS NULL OR lease_until<=?)
                           ORDER BY next_run_at LIMIT ?""",
                        (now.isoformat(), now.isoformat(), max(1, min(limit, 100))),
                    )
                ).fetchall()
                for row in rows:
                    cursor = await db.execute(
                        """UPDATE schedules SET lease_owner=?,lease_until=?
                           WHERE id=? AND enabled=1
                             AND (lease_until IS NULL OR lease_until<=?)""",
                        (
                            owner,
                            lease_until.isoformat(),
                            row["id"],
                            now.isoformat(),
                        ),
                    )
                    if cursor.rowcount == 1:
                        claimed_row = await (
                            await db.execute(
                                "SELECT * FROM schedules WHERE id=?", (row["id"],)
                            )
                        ).fetchone()
                        claimed.append(self._schedule(claimed_row))
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                await db.close()
        return claimed

    async def complete_schedule_fire(
        self,
        schedule_id: str,
        owner: str,
        *,
        fired_at: datetime,
        next_run_at: datetime | None,
        last_run_id: str | None,
        last_error: str | None,
    ) -> bool:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    """UPDATE schedules SET next_run_at=?,last_run_at=?,last_run_id=?,
                         last_error=?,lease_owner=NULL,lease_until=NULL,updated_at=?
                       WHERE id=? AND lease_owner=?""",
                    (
                        next_run_at.isoformat() if next_run_at else None,
                        fired_at.isoformat(),
                        last_run_id,
                        last_error,
                        utc_now().isoformat(),
                        schedule_id,
                        owner,
                    ),
                )
                await db.commit()
                return cursor.rowcount == 1
            finally:
                await db.close()

    async def record_manual_schedule_run(
        self, schedule_id: str, run_id: str
    ) -> ScheduleRecord:
        now = utc_now()
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    """UPDATE schedules SET last_run_at=?,last_run_id=?,last_error=NULL,
                         updated_at=? WHERE id=?""",
                    (now.isoformat(), run_id, now.isoformat(), schedule_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(schedule_id)
                await db.commit()
            finally:
                await db.close()
        result = await self.get_schedule(schedule_id)
        if result is None:
            raise KeyError(schedule_id)
        return result

    async def create_run(
        self,
        flow: FlowRecord,
        parameters: dict[str, Any],
        idempotency_key: str | None,
        created_by: str = "local-operator",
    ) -> tuple[RunRecord, bool]:
        now = utc_now()
        async with self._write_lock:
            db = await self._connect()
            try:
                if idempotency_key:
                    row = await (
                        await db.execute(
                            "SELECT * FROM runs WHERE flow_id=? AND idempotency_key=?",
                            (flow.id, idempotency_key),
                        )
                    ).fetchone()
                    if row:
                        return self._run(row), False
                run_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO runs(
                         id,flow_id,flow_name,flow_revision,flow_snapshot_json,
                         owner_id,visibility,created_by,status,parameters_json,
                         idempotency_key,processed_items,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?)""",
                    (
                        run_id,
                        flow.id,
                        flow.name,
                        flow.revision,
                        self._json(
                            flow.model_dump(
                                mode="json",
                                exclude={
                                    "id",
                                    "owner_id",
                                    "revision",
                                    "created_at",
                                    "updated_at",
                                },
                            )
                        ),
                        flow.owner_id,
                        flow.visibility.value,
                        created_by,
                        RunStatus.QUEUED.value,
                        self._json(parameters),
                        idempotency_key,
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        run = await self.get_run(run_id)
        if run is None:
            raise RuntimeError("run was not persisted")
        return run, True

    async def list_runs(self, limit: int = 100) -> list[RunRecord]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)
                )
            ).fetchall()
            return [self._run(row) for row in rows]
        finally:
            await db.close()

    async def get_run(self, run_id: str) -> RunRecord | None:
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT * FROM runs WHERE id=?", (run_id,))).fetchone()
            return self._run(row) if row else None
        finally:
            await db.close()

    async def get_run_flow(self, run_id: str) -> FlowRecord | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    """SELECT flow_id,flow_revision,flow_snapshot_json,owner_id,created_at
                       FROM runs WHERE id=?""",
                    (run_id,),
                )
            ).fetchone()
            if not row or not row["flow_snapshot_json"]:
                return None
            definition = FlowDefinition.model_validate_json(row["flow_snapshot_json"])
            created_at = self._dt(row["created_at"])
            return FlowRecord(
                id=row["flow_id"],
                owner_id=row["owner_id"],
                revision=int(row["flow_revision"] or 1),
                created_at=created_at,
                updated_at=created_at,
                **definition.model_dump(),
            )
        finally:
            await db.close()

    async def get_run_flow_snapshot(self, run_id: str) -> RunFlowSnapshot | None:
        flow = await self.get_run_flow(run_id)
        if flow is None:
            return None
        return RunFlowSnapshot(
            run_id=run_id,
            flow_id=flow.id,
            flow_revision=flow.revision,
            definition=FlowDefinition.model_validate(
                flow.model_dump(
                    exclude={"id", "owner_id", "revision", "created_at", "updated_at"}
                )
            ),
        )

    async def recover_runs(self) -> RecoveryPlan:
        async with self._write_lock:
            db = await self._connect()
            try:
                rows = await (
                    await db.execute(
                        """SELECT id,status FROM runs
                           WHERE status IN ('QUEUED','RUNNING','CANCELLING')
                           ORDER BY created_at"""
                    )
                ).fetchall()
                recovered = [row["id"] for row in rows if row["status"] == "RUNNING"]
                cancelled = [
                    row["id"] for row in rows if row["status"] == "CANCELLING"
                ]
                requeued = [
                    row["id"]
                    for row in rows
                    if row["status"] in {"QUEUED", "RUNNING"}
                ]
                await db.execute(
                    """UPDATE runs SET status='QUEUED', current_node=NULL,
                         message='Recovered after engine restart', started_at=NULL,
                         finished_at=NULL, error_code=NULL, error_message=NULL
                       WHERE status='RUNNING'"""
                )
                await db.execute(
                    """UPDATE runs SET status='CANCELLED', current_node=NULL,
                         message='Cancelled while engine was restarting', finished_at=?
                       WHERE status='CANCELLING'""",
                    (utc_now().isoformat(),),
                )
                await db.commit()
                return RecoveryPlan(
                    requeued=requeued,
                    recovered=recovered,
                    cancelled=cancelled,
                )
            finally:
                await db.close()

    async def claim_run(
        self, run_id: str, *, worker_index: int, started_at: datetime
    ) -> RunRecord | None:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    """UPDATE runs SET status=?,message=?,started_at=?
                       WHERE id=? AND status=?""",
                    (
                        RunStatus.RUNNING.value,
                        f"Worker {worker_index + 1} started",
                        started_at.isoformat(),
                        run_id,
                        RunStatus.QUEUED.value,
                    ),
                )
                await db.commit()
                if cursor.rowcount != 1:
                    return None
            finally:
                await db.close()
        return await self.get_run(run_id)

    async def finalize_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        run_message: str,
        event_type: str,
        event_level: str,
        event_message: str,
        event_data: dict[str, Any] | None = None,
        processed_items: int | None = None,
        total_items: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> tuple[RunRecord, EventRecord]:
        if not status.terminal:
            raise ValueError("final run status must be terminal")
        now = utc_now()
        event_id = str(uuid.uuid4())
        assignments = [
            "status=?",
            "current_node=NULL",
            "message=?",
            "finished_at=?",
            "error_code=?",
            "error_message=?",
        ]
        values: list[Any] = [
            status.value,
            run_message,
            now.isoformat(),
            error_code,
            error_message,
        ]
        if processed_items is not None:
            assignments.append("processed_items=?")
            values.append(processed_items)
        if total_items is not None:
            assignments.append("total_items=?")
            values.append(total_items)
        values.append(run_id)

        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    f"UPDATE runs SET {','.join(assignments)} WHERE id=?",
                    values,
                )
                if cursor.rowcount != 1:
                    raise KeyError(run_id)
                row = await (
                    await db.execute(
                        "SELECT COALESCE(MAX(sequence),0)+1 AS next FROM events WHERE run_id=?",
                        (run_id,),
                    )
                ).fetchone()
                sequence = int(row["next"])
                await db.execute(
                    """INSERT INTO events(
                         id,run_id,sequence,type,level,message,data_json,created_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        event_id,
                        run_id,
                        sequence,
                        event_type,
                        event_level,
                        event_message,
                        self._json(event_data or {}),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()

        run = await self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run, EventRecord(
            id=event_id,
            run_id=run_id,
            sequence=sequence,
            type=event_type,
            level=event_level,
            message=event_message,
            data=event_data or {},
            created_at=now,
        )

    async def update_run(self, run_id: str, **changes: Any) -> RunRecord:
        allowed = {
            "status",
            "current_node",
            "message",
            "processed_items",
            "total_items",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
        }
        if not changes or not set(changes).issubset(allowed):
            raise ValueError("unsupported run update")
        values = []
        assignments = []
        for name, value in changes.items():
            assignments.append(f"{name}=?")
            if isinstance(value, RunStatus):
                value = value.value
            if isinstance(value, datetime):
                value = value.isoformat()
            values.append(value)
        values.append(run_id)
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    f"UPDATE runs SET {','.join(assignments)} WHERE id=?", values
                )
                if cursor.rowcount != 1:
                    raise KeyError(run_id)
                await db.commit()
            finally:
                await db.close()
        run = await self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    async def save_checkpoint(
        self,
        run_id: str,
        node_id: str,
        outputs: dict[str, list[dict[str, Any]]],
        *,
        attempt_count: int,
        emitted_count: int,
    ) -> NodeCheckpoint:
        now = utc_now()
        raw = self._json(outputs).encode("utf-8")
        checksum = hashlib.sha256(raw).hexdigest()
        blob = zlib.compress(raw, level=6)
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    """INSERT INTO node_checkpoints(
                         run_id,node_id,status,output_blob,output_checksum,
                         attempt_count,emitted_count,created_at,updated_at
                       ) VALUES(?,?,'COMPLETED',?,?,?,?,?,?)
                       ON CONFLICT(run_id,node_id) DO UPDATE SET
                         status='COMPLETED',output_blob=excluded.output_blob,
                         output_checksum=excluded.output_checksum,
                         attempt_count=excluded.attempt_count,
                         emitted_count=excluded.emitted_count,
                         updated_at=excluded.updated_at""",
                    (
                        run_id,
                        node_id,
                        blob,
                        checksum,
                        attempt_count,
                        emitted_count,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        return NodeCheckpoint(
            run_id=run_id,
            node_id=node_id,
            outputs=outputs,
            attempt_count=attempt_count,
            emitted_count=emitted_count,
            checksum=checksum,
            created_at=now,
            updated_at=now,
        )

    async def load_checkpoints(self, run_id: str) -> dict[str, NodeCheckpoint]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    """SELECT * FROM node_checkpoints
                       WHERE run_id=? AND status='COMPLETED' ORDER BY created_at""",
                    (run_id,),
                )
            ).fetchall()
        finally:
            await db.close()
        checkpoints: dict[str, NodeCheckpoint] = {}
        for row in rows:
            try:
                raw = zlib.decompress(bytes(row["output_blob"]))
            except zlib.error as error:
                raise ValueError(
                    f"checkpoint payload is corrupt for node {row['node_id']}"
                ) from error
            checksum = hashlib.sha256(raw).hexdigest()
            if checksum != row["output_checksum"]:
                raise ValueError(
                    f"checkpoint checksum mismatch for node {row['node_id']}"
                )
            outputs = json.loads(raw.decode("utf-8"))
            if not isinstance(outputs, dict):
                raise ValueError(f"checkpoint output is invalid for node {row['node_id']}")
            checkpoints[row["node_id"]] = NodeCheckpoint(
                run_id=row["run_id"],
                node_id=row["node_id"],
                outputs=outputs,
                attempt_count=row["attempt_count"],
                emitted_count=row["emitted_count"],
                checksum=checksum,
                created_at=self._dt(row["created_at"]),
                updated_at=self._dt(row["updated_at"]),
            )
        return checkpoints

    async def count_items(self, run_id: str) -> int:
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT COUNT(*) AS total FROM items WHERE run_id=?", (run_id,)
                )
            ).fetchone()
            return int(row["total"])
        finally:
            await db.close()

    async def add_item(
        self,
        run_id: str,
        external_id: str,
        url: str,
        title: str,
        content: str,
        media_type: str,
        observed_at: datetime,
        metadata: dict[str, Any],
    ) -> tuple[ItemRecord, bool]:
        now = utc_now()
        item_id = str(uuid.uuid4())
        async with self._write_lock:
            db = await self._connect()
            try:
                existing = await (
                    await db.execute(
                        "SELECT * FROM items WHERE run_id=? AND external_id=?",
                        (run_id, external_id),
                    )
                ).fetchone()
                if existing:
                    return self._item(existing), False
                await db.execute(
                    """INSERT INTO items(
                         id,run_id,external_id,url,title,content,media_type,
                         observed_at,metadata_json,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item_id,
                        run_id,
                        external_id,
                        url,
                        title,
                        content,
                        media_type,
                        observed_at.isoformat(),
                        self._json(metadata),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        item = await self.get_item(item_id)
        if item is None:
            raise RuntimeError("item was not persisted")
        return item, True

    async def get_item(self, item_id: str) -> ItemRecord | None:
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT * FROM items WHERE id=?", (item_id,))).fetchone()
            return self._item(row) if row else None
        finally:
            await db.close()

    async def list_items(
        self, run_id: str, cursor: str | None, limit: int
    ) -> tuple[list[ItemRecord], str | None]:
        cap = max(1, min(limit, 500))
        db = await self._connect()
        try:
            if cursor:
                rows = await (
                    await db.execute(
                        """SELECT * FROM items WHERE run_id=? AND (created_at || id)>?
                           ORDER BY created_at,id LIMIT ?""",
                        (run_id, cursor, cap + 1),
                    )
                ).fetchall()
            else:
                rows = await (
                    await db.execute(
                        "SELECT * FROM items WHERE run_id=? ORDER BY created_at,id LIMIT ?",
                        (run_id, cap + 1),
                    )
                ).fetchall()
            has_more = len(rows) > cap
            rows = rows[:cap]
            items = [self._item(row) for row in rows]
            next_cursor = (
                f"{rows[-1]['created_at']}{rows[-1]['id']}" if has_more and rows else None
            )
            return items, next_cursor
        finally:
            await db.close()

    async def add_event(
        self,
        run_id: str,
        event_type: str,
        level: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> EventRecord:
        now = utc_now()
        event_id = str(uuid.uuid4())
        async with self._write_lock:
            db = await self._connect()
            try:
                row = await (
                    await db.execute(
                        "SELECT COALESCE(MAX(sequence),0)+1 AS next FROM events WHERE run_id=?",
                        (run_id,),
                    )
                ).fetchone()
                sequence = int(row["next"])
                await db.execute(
                    """INSERT INTO events(
                         id,run_id,sequence,type,level,message,data_json,created_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        event_id,
                        run_id,
                        sequence,
                        event_type,
                        level,
                        message,
                        self._json(data or {}),
                        now.isoformat(),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        return EventRecord(
            id=event_id,
            run_id=run_id,
            sequence=sequence,
            type=event_type,
            level=level,
            message=message,
            data=data or {},
            created_at=now,
        )

    async def list_events(self, run_id: str, after: int = 0) -> list[EventRecord]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    """SELECT * FROM events WHERE run_id=? AND sequence>?
                       ORDER BY sequence LIMIT 1000""",
                    (run_id, max(0, after)),
                )
            ).fetchall()
            return [self._event(row) for row in rows]
        finally:
            await db.close()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _dt(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    def _flow(self, row: aiosqlite.Row) -> FlowRecord:
        graph = json.loads(row["graph_json"])
        return FlowRecord(
            id=row["id"],
            owner_id=row["owner_id"],
            visibility=FlowVisibility(row["visibility"]),
            revision=row["revision"],
            created_at=self._dt(row["created_at"]),
            updated_at=self._dt(row["updated_at"]),
            **graph,
        )

    def _run(self, row: aiosqlite.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            flow_id=row["flow_id"],
            flow_name=row["flow_name"],
            flow_revision=int(row["flow_revision"] or 1),
            owner_id=row["owner_id"],
            visibility=FlowVisibility(row["visibility"]),
            created_by=row["created_by"],
            status=RunStatus(row["status"]),
            parameters=json.loads(row["parameters_json"]),
            idempotency_key=row["idempotency_key"],
            current_node=row["current_node"],
            message=row["message"],
            processed_items=row["processed_items"],
            total_items=row["total_items"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=self._dt(row["created_at"]),
            started_at=self._dt(row["started_at"]),
            finished_at=self._dt(row["finished_at"]),
        )

    def _item(self, row: aiosqlite.Row) -> ItemRecord:
        return ItemRecord(
            id=row["id"],
            run_id=row["run_id"],
            external_id=row["external_id"],
            url=row["url"],
            title=row["title"],
            content=row["content"],
            media_type=row["media_type"],
            observed_at=self._dt(row["observed_at"]),
            metadata=json.loads(row["metadata_json"]),
            created_at=self._dt(row["created_at"]),
        )

    def _event(self, row: aiosqlite.Row) -> EventRecord:
        return EventRecord(
            id=row["id"],
            run_id=row["run_id"],
            sequence=row["sequence"],
            type=row["type"],
            level=row["level"],
            message=row["message"],
            data=json.loads(row["data_json"]),
            created_at=self._dt(row["created_at"]),
        )

    def _schedule(self, row: aiosqlite.Row) -> ScheduleRecord:
        return ScheduleRecord(
            id=row["id"],
            owner_id=row["owner_id"],
            visibility=FlowVisibility(row["visibility"]),
            created_by=row["created_by"],
            flow_id=row["flow_id"],
            name=row["name"],
            cron=row["cron"],
            timezone=row["timezone"],
            enabled=bool(row["enabled"]),
            parameters=json.loads(row["parameters_json"]),
            revision=row["revision"],
            next_run_at=self._dt(row["next_run_at"]),
            last_run_at=self._dt(row["last_run_at"]),
            last_run_id=row["last_run_id"],
            last_error=row["last_error"],
            created_at=self._dt(row["created_at"]),
            updated_at=self._dt(row["updated_at"]),
        )

    def _user(self, row: aiosqlite.Row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role=UserRole(row["role"]),
            active=bool(row["active"]),
            created_at=self._dt(row["created_at"]),
            updated_at=self._dt(row["updated_at"]),
            last_login_at=self._dt(row["last_login_at"]),
        )

    def _audit(self, row: aiosqlite.Row) -> AuditRecord:
        return AuditRecord(
            id=row["id"],
            actor_user_id=row["actor_user_id"],
            actor_username=row["actor_username"],
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            outcome=row["outcome"],
            detail=json.loads(row["detail_json"]),
            created_at=self._dt(row["created_at"]),
        )


class RevisionConflict(RuntimeError):
    def __init__(self, actual_revision: int):
        super().__init__(f"flow revision conflict; current revision is {actual_revision}")
        self.actual_revision = actual_revision
