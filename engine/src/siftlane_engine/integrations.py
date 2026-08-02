from __future__ import annotations

import asyncio
import base64
import configparser
import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import sys
import uuid
import zipfile
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import aiosqlite
import httpx
from cryptography.fernet import Fernet, InvalidToken
from siftlane_connector_sdk import ConnectorManifest, ConnectorOperationRequest, ConnectorOperationResult

from .config import Settings
from .connectors import MAX_CONNECTOR_OUTPUT_BYTES, ConnectorContractError, ConnectorProcessError, _connector_environment
from .models import (
    ConnectorInstallRequest,
    ConnectorState,
    DeliveryAuthScheme,
    DeliveryCreate,
    DeliveryRecord,
    DeliveryStatus,
    DeliveryTargetDefinition,
    DeliveryTargetRecord,
    DeliveryTargetType,
    FlowVisibility,
    ManagedConnectorRecord,
    SecretCreate,
    SecretRecord,
    SecretScope,
    utc_now,
)
from .storage import Storage


P4_SCHEMA = """
CREATE TABLE IF NOT EXISTS managed_connectors (
  id TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  previous_version TEXT,
  state TEXT NOT NULL,
  source TEXT NOT NULL,
  entry_point TEXT NOT NULL,
  package_path TEXT,
  previous_entry_point TEXT,
  previous_package_path TEXT,
  manifest_json TEXT NOT NULL,
  previous_manifest_json TEXT,
  installed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scoped_secrets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  ciphertext TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  created_by TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(scope_type, scope_id, name)
);
CREATE INDEX IF NOT EXISTS idx_secrets_scope ON scoped_secrets(scope_type, scope_id);
CREATE TABLE IF NOT EXISTS delivery_targets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  visibility TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  url TEXT,
  auth_scheme TEXT NOT NULL,
  secret_id TEXT REFERENCES scoped_secrets(id) ON DELETE RESTRICT,
  max_attempts INTEGER NOT NULL,
  backoff_seconds REAL NOT NULL,
  owner_id TEXT NOT NULL,
  created_by TEXT NOT NULL,
  revision INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
  id TEXT PRIMARY KEY,
  target_id TEXT NOT NULL REFERENCES delivery_targets(id) ON DELETE RESTRICT,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL,
  next_attempt_at TEXT,
  response_status INTEGER,
  error TEXT,
  artifact_path TEXT,
  payload_sha256 TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  UNIQUE(target_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_deliveries_due ON deliveries(status, next_attempt_at);
"""


class IntegrationConflict(RuntimeError):
    pass


def contains_secret_material(value: object, secrets: list[str]) -> bool:
    if isinstance(value, str):
        return any(secret and secret in value for secret in secrets)
    if isinstance(value, dict):
        return any(
            contains_secret_material(key, secrets)
            or contains_secret_material(item, secrets)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret_material(item, secrets) for item in value)
    return False


class SecretCipher:
    def __init__(self, key: str):
        if len(key) < 32:
            raise ValueError("engine secret key must contain at least 32 characters")
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode("utf-8")).digest())
        self._fernet = Fernet(derived)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as error:
            raise RuntimeError("secret cannot be decrypted with the configured engine key") from error


class IntegrationStorage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.database_path
        self._write_lock = asyncio.Lock()
        key = settings.secret_key.get_secret_value()
        self.cipher = SecretCipher(key) if key else None

    async def _connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        return db

    async def initialize(self) -> None:
        for directory in (
            self.settings.connector_inbox_path,
            self.settings.connector_packages_path,
            self.settings.export_path,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(P4_SCHEMA)
            now = utc_now().isoformat()
            manifest = ConnectorManifest.model_validate(
                {
                    "id": "io.siftlane.json-feed",
                    "name": "JSON Feed",
                    "version": "1.0.0",
                    "description": "Collects items from a JSON Feed 1.0 or 1.1 endpoint.",
                    "capabilities": [
                        {
                            "id": "fetch",
                            "label": "Fetch feed",
                            "description": "Fetch and normalize one page of a JSON Feed.",
                            "input_schema": {
                                "type": "object",
                                "properties": {"url": {"type": "string"}},
                                "required": ["url"],
                                "additionalProperties": False,
                            },
                            "supports_cursor": True,
                        }
                    ],
                }
            )
            await db.execute(
                """INSERT OR IGNORE INTO managed_connectors(
                     id,version,state,source,entry_point,manifest_json,installed_at,updated_at
                   ) VALUES(?,?,'enabled','builtin','builtin.json-feed',?,?,?)""",
                (manifest.id, manifest.version, self._json(manifest.model_dump(mode="json")), now, now),
            )
            await db.commit()

    async def list_connectors(self) -> list[ManagedConnectorRecord]:
        db = await self._connect()
        try:
            rows = await (await db.execute("SELECT * FROM managed_connectors ORDER BY id")).fetchall()
            return [self._connector(row) for row in rows]
        finally:
            await db.close()

    async def get_connector(self, connector_id: str) -> ManagedConnectorRecord | None:
        row = await self._connector_row(connector_id)
        return self._connector(row) if row else None

    async def _connector_row(self, connector_id: str) -> aiosqlite.Row | None:
        db = await self._connect()
        try:
            return await (await db.execute("SELECT * FROM managed_connectors WHERE id=?", (connector_id,))).fetchone()
        finally:
            await db.close()

    async def save_connector(
        self,
        manifest: ConnectorManifest,
        *,
        entry_point: str,
        package_path: str,
        upgrade: bool,
    ) -> ManagedConnectorRecord:
        now = utc_now().isoformat()
        async with self._write_lock:
            db = await self._connect()
            try:
                existing = await (await db.execute("SELECT * FROM managed_connectors WHERE id=?", (manifest.id,))).fetchone()
                if existing and not upgrade:
                    raise IntegrationConflict("connector is already installed")
                if not existing and upgrade:
                    raise KeyError(manifest.id)
                if existing:
                    if existing["version"] == manifest.version:
                        raise IntegrationConflict("connector version is already installed")
                    await db.execute(
                        """UPDATE managed_connectors SET
                             version=?,previous_version=version,state='enabled',source='wheel',
                             entry_point=?,package_path=?,previous_entry_point=entry_point,
                             previous_package_path=package_path,manifest_json=?,
                             previous_manifest_json=manifest_json,updated_at=? WHERE id=?""",
                        (
                            manifest.version,
                            entry_point,
                            package_path,
                            self._json(manifest.model_dump(mode="json")),
                            now,
                            manifest.id,
                        ),
                    )
                else:
                    await db.execute(
                        """INSERT INTO managed_connectors(
                             id,version,state,source,entry_point,package_path,manifest_json,
                             installed_at,updated_at
                           ) VALUES(?,?,'enabled','wheel',?,?,?,?,?)""",
                        (
                            manifest.id,
                            manifest.version,
                            entry_point,
                            package_path,
                            self._json(manifest.model_dump(mode="json")),
                            now,
                            now,
                        ),
                    )
                await db.commit()
            finally:
                await db.close()
        connector = await self.get_connector(manifest.id)
        if connector is None:
            raise RuntimeError("connector was not persisted")
        return connector

    async def set_connector_state(self, connector_id: str, state: ConnectorState) -> ManagedConnectorRecord:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    "UPDATE managed_connectors SET state=?,updated_at=? WHERE id=?",
                    (state.value, utc_now().isoformat(), connector_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(connector_id)
                await db.commit()
            finally:
                await db.close()
        connector = await self.get_connector(connector_id)
        if connector is None:
            raise KeyError(connector_id)
        return connector

    async def rollback_connector(self, connector_id: str) -> ManagedConnectorRecord:
        async with self._write_lock:
            db = await self._connect()
            try:
                row = await (await db.execute("SELECT * FROM managed_connectors WHERE id=?", (connector_id,))).fetchone()
                if row is None:
                    raise KeyError(connector_id)
                if not row["previous_version"]:
                    raise IntegrationConflict("connector has no previous version")
                await db.execute(
                    """UPDATE managed_connectors SET
                         version=previous_version,previous_version=version,state='enabled',
                         entry_point=previous_entry_point,previous_entry_point=entry_point,
                         package_path=previous_package_path,previous_package_path=package_path,
                         manifest_json=previous_manifest_json,previous_manifest_json=manifest_json,
                         updated_at=? WHERE id=?""",
                    (utc_now().isoformat(), connector_id),
                )
                await db.commit()
            finally:
                await db.close()
        connector = await self.get_connector(connector_id)
        if connector is None:
            raise KeyError(connector_id)
        return connector

    async def uninstall_connector(self, connector_id: str) -> bool:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute("DELETE FROM managed_connectors WHERE id=?", (connector_id,))
                await db.commit()
                return cursor.rowcount == 1
            finally:
                await db.close()

    async def create_secret(self, definition: SecretCreate, actor_id: str) -> SecretRecord:
        if self.cipher is None:
            raise RuntimeError("engine secret key is not configured")
        now = utc_now().isoformat()
        encrypted = self.cipher.encrypt(definition.value.get_secret_value())
        async with self._write_lock:
            db = await self._connect()
            try:
                existing = await (
                    await db.execute(
                        "SELECT id,created_at,version FROM scoped_secrets WHERE scope_type=? AND scope_id=? AND name=?",
                        (definition.scope_type.value, definition.scope_id, definition.name),
                    )
                ).fetchone()
                secret_id = existing["id"] if existing else str(uuid.uuid4())
                if existing:
                    await db.execute(
                        """UPDATE scoped_secrets SET ciphertext=?,version=version+1,
                             updated_at=?,created_by=? WHERE id=?""",
                        (encrypted, now, actor_id, secret_id),
                    )
                else:
                    await db.execute(
                        """INSERT INTO scoped_secrets(
                             id,name,scope_type,scope_id,ciphertext,owner_id,created_by,
                             version,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,1,?,?)""",
                        (
                            secret_id,
                            definition.name,
                            definition.scope_type.value,
                            definition.scope_id,
                            encrypted,
                            actor_id,
                            actor_id,
                            now,
                            now,
                        ),
                    )
                await db.commit()
            finally:
                await db.close()
        secret = await self.get_secret(secret_id)
        if secret is None:
            raise RuntimeError("secret was not persisted")
        return secret

    async def list_secrets(self) -> list[SecretRecord]:
        db = await self._connect()
        try:
            rows = await (await db.execute("SELECT * FROM scoped_secrets ORDER BY scope_type,scope_id,name")).fetchall()
            return [self._secret(row) for row in rows]
        finally:
            await db.close()

    async def get_secret(self, secret_id: str) -> SecretRecord | None:
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT * FROM scoped_secrets WHERE id=?", (secret_id,))).fetchone()
            return self._secret(row) if row else None
        finally:
            await db.close()

    async def resolve_secret(self, secret_id: str) -> str:
        if self.cipher is None:
            raise RuntimeError("engine secret key is not configured")
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT ciphertext FROM scoped_secrets WHERE id=?", (secret_id,))).fetchone()
            if row is None:
                raise KeyError(secret_id)
            return self.cipher.decrypt(row["ciphertext"])
        finally:
            await db.close()

    async def resolve_scoped_secret(self, scope_type: SecretScope, scope_id: str, name: str) -> str:
        if self.cipher is None:
            raise RuntimeError("engine secret key is not configured")
        db = await self._connect()
        try:
            row = await (
                await db.execute(
                    "SELECT ciphertext FROM scoped_secrets WHERE scope_type=? AND scope_id=? AND name=?",
                    (scope_type.value, scope_id, name),
                )
            ).fetchone()
            if row is None:
                raise KeyError(name)
            return self.cipher.decrypt(row["ciphertext"])
        finally:
            await db.close()

    async def delete_secret(self, secret_id: str) -> bool:
        async with self._write_lock:
            db = await self._connect()
            try:
                try:
                    cursor = await db.execute("DELETE FROM scoped_secrets WHERE id=?", (secret_id,))
                    await db.commit()
                except aiosqlite.IntegrityError as error:
                    raise IntegrationConflict("secret is still referenced by a delivery target") from error
                return cursor.rowcount == 1
            finally:
                await db.close()

    async def create_target(self, definition: DeliveryTargetDefinition, actor_id: str) -> DeliveryTargetRecord:
        target_id = str(uuid.uuid4())
        now = utc_now().isoformat()
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    """INSERT INTO delivery_targets(
                         id,name,type,visibility,enabled,url,auth_scheme,secret_id,
                         max_attempts,backoff_seconds,owner_id,created_by,revision,
                         created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                    (
                        target_id,
                        definition.name,
                        definition.type.value,
                        definition.visibility.value,
                        int(definition.enabled),
                        definition.url,
                        definition.auth_scheme.value,
                        definition.secret_id,
                        definition.max_attempts,
                        definition.backoff_seconds,
                        actor_id,
                        actor_id,
                        now,
                        now,
                    ),
                )
                await db.commit()
            except aiosqlite.IntegrityError as error:
                raise IntegrationConflict("delivery target references an unknown secret") from error
            finally:
                await db.close()
        target = await self.get_target(target_id)
        if target is None:
            raise RuntimeError("delivery target was not persisted")
        return target

    async def update_target(
        self,
        target_id: str,
        definition: DeliveryTargetDefinition,
        expected_revision: int | None,
    ) -> DeliveryTargetRecord:
        async with self._write_lock:
            db = await self._connect()
            try:
                values: list[object] = [
                    definition.name,
                    definition.type.value,
                    definition.visibility.value,
                    int(definition.enabled),
                    definition.url,
                    definition.auth_scheme.value,
                    definition.secret_id,
                    definition.max_attempts,
                    definition.backoff_seconds,
                    utc_now().isoformat(),
                    target_id,
                ]
                condition = "id=?"
                if expected_revision is not None:
                    condition += " AND revision=?"
                    values.append(expected_revision)
                cursor = await db.execute(
                    f"""UPDATE delivery_targets SET name=?,type=?,visibility=?,enabled=?,
                          url=?,auth_scheme=?,secret_id=?,max_attempts=?,backoff_seconds=?,
                          revision=revision+1,updated_at=? WHERE {condition}""",
                    values,
                )
                if cursor.rowcount != 1:
                    exists = await (await db.execute("SELECT revision FROM delivery_targets WHERE id=?", (target_id,))).fetchone()
                    if exists:
                        raise IntegrationConflict(f"delivery target revision conflict; current revision is {exists['revision']}")
                    raise KeyError(target_id)
                await db.commit()
            except aiosqlite.IntegrityError as error:
                raise IntegrationConflict("delivery target references an unknown secret") from error
            finally:
                await db.close()
        target = await self.get_target(target_id)
        if target is None:
            raise KeyError(target_id)
        return target

    async def list_targets(self) -> list[DeliveryTargetRecord]:
        db = await self._connect()
        try:
            rows = await (await db.execute("SELECT * FROM delivery_targets ORDER BY created_at DESC")).fetchall()
            return [self._target(row) for row in rows]
        finally:
            await db.close()

    async def get_target(self, target_id: str) -> DeliveryTargetRecord | None:
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT * FROM delivery_targets WHERE id=?", (target_id,))).fetchone()
            return self._target(row) if row else None
        finally:
            await db.close()

    async def delete_target(self, target_id: str) -> bool:
        async with self._write_lock:
            db = await self._connect()
            try:
                try:
                    cursor = await db.execute("DELETE FROM delivery_targets WHERE id=?", (target_id,))
                    await db.commit()
                except aiosqlite.IntegrityError as error:
                    raise IntegrationConflict("delivery target has delivery history and cannot be deleted") from error
                return cursor.rowcount == 1
            finally:
                await db.close()

    async def create_delivery(self, request: DeliveryCreate, actor_id: str) -> tuple[DeliveryRecord, bool]:
        now = utc_now().isoformat()
        delivery_id = str(uuid.uuid4())
        async with self._write_lock:
            db = await self._connect()
            try:
                existing = await (
                    await db.execute(
                        "SELECT * FROM deliveries WHERE target_id=? AND idempotency_key=?",
                        (request.target_id, request.idempotency_key),
                    )
                ).fetchone()
                if existing:
                    return self._delivery(existing), False
                await db.execute(
                    """INSERT INTO deliveries(
                         id,target_id,run_id,idempotency_key,status,attempt_count,
                         next_attempt_at,created_by,created_at,updated_at
                       ) VALUES(?,?,?,?,'queued',0,?,?,?,?)""",
                    (
                        delivery_id,
                        request.target_id,
                        request.run_id,
                        request.idempotency_key,
                        now,
                        actor_id,
                        now,
                        now,
                    ),
                )
                await db.commit()
            except aiosqlite.IntegrityError as error:
                raise IntegrationConflict("delivery references an unknown run or target") from error
            finally:
                await db.close()
        delivery = await self.get_delivery(delivery_id)
        if delivery is None:
            raise RuntimeError("delivery was not persisted")
        return delivery, True

    async def list_deliveries(self, limit: int = 200) -> list[DeliveryRecord]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute("SELECT * FROM deliveries ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),))
            ).fetchall()
            return [self._delivery(row) for row in rows]
        finally:
            await db.close()

    async def get_delivery(self, delivery_id: str) -> DeliveryRecord | None:
        db = await self._connect()
        try:
            row = await (await db.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,))).fetchone()
            return self._delivery(row) if row else None
        finally:
            await db.close()

    async def claim_delivery(self, delivery_id: str) -> DeliveryRecord | None:
        now = utc_now().isoformat()
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    """UPDATE deliveries SET status='delivering',attempt_count=attempt_count+1,
                         next_attempt_at=NULL,updated_at=?
                       WHERE id=? AND status IN ('queued','retrying')
                         AND (next_attempt_at IS NULL OR next_attempt_at<=?)""",
                    (now, delivery_id, now),
                )
                await db.commit()
                if cursor.rowcount != 1:
                    return None
            finally:
                await db.close()
        return await self.get_delivery(delivery_id)

    async def due_delivery_ids(self, limit: int = 20) -> list[str]:
        now = utc_now().isoformat()
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    """SELECT id FROM deliveries WHERE status IN ('queued','retrying')
                       AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                       ORDER BY created_at LIMIT ?""",
                    (now, limit),
                )
            ).fetchall()
            return [row["id"] for row in rows]
        finally:
            await db.close()

    async def finish_delivery(
        self,
        delivery_id: str,
        *,
        success: bool,
        max_attempts: int,
        backoff_seconds: float,
        response_status: int | None = None,
        error: str | None = None,
        artifact_path: str | None = None,
        payload_sha256: str | None = None,
    ) -> DeliveryRecord:
        current = await self.get_delivery(delivery_id)
        if current is None:
            raise KeyError(delivery_id)
        now = utc_now()
        if success:
            status = DeliveryStatus.SUCCEEDED
            next_attempt = None
            finished = now.isoformat()
        elif current.attempt_count >= max_attempts:
            status = DeliveryStatus.DEAD_LETTER
            next_attempt = None
            finished = now.isoformat()
        else:
            status = DeliveryStatus.RETRYING
            delay = min(300.0, backoff_seconds * (2 ** max(0, current.attempt_count - 1)))
            next_attempt = (now + timedelta(seconds=delay)).isoformat()
            finished = None
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(
                    """UPDATE deliveries SET status=?,next_attempt_at=?,response_status=?,
                         error=?,artifact_path=?,payload_sha256=?,updated_at=?,finished_at=? WHERE id=?""",
                    (
                        status.value,
                        next_attempt,
                        response_status,
                        error[:1000] if error else None,
                        artifact_path,
                        payload_sha256,
                        now.isoformat(),
                        finished,
                        delivery_id,
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        delivery = await self.get_delivery(delivery_id)
        if delivery is None:
            raise KeyError(delivery_id)
        return delivery

    async def replay_delivery(self, delivery_id: str) -> DeliveryRecord:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    """UPDATE deliveries SET status='queued',attempt_count=0,next_attempt_at=?,
                         error=NULL,response_status=NULL,finished_at=NULL,updated_at=?
                       WHERE id=? AND status IN ('dead_letter','cancelled')""",
                    (utc_now().isoformat(), utc_now().isoformat(), delivery_id),
                )
                if cursor.rowcount != 1:
                    raise IntegrationConflict("only dead-letter or cancelled deliveries can be replayed")
                await db.commit()
            finally:
                await db.close()
        delivery = await self.get_delivery(delivery_id)
        if delivery is None:
            raise KeyError(delivery_id)
        return delivery

    async def cancel_delivery(self, delivery_id: str) -> DeliveryRecord:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(
                    """UPDATE deliveries SET status='cancelled',next_attempt_at=NULL,
                         updated_at=?,finished_at=? WHERE id=? AND status IN ('queued','retrying')""",
                    (utc_now().isoformat(), utc_now().isoformat(), delivery_id),
                )
                if cursor.rowcount != 1:
                    raise IntegrationConflict("delivery cannot be cancelled in its current state")
                await db.commit()
            finally:
                await db.close()
        delivery = await self.get_delivery(delivery_id)
        if delivery is None:
            raise KeyError(delivery_id)
        return delivery

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _dt(value: str | None):
        from datetime import datetime

        return datetime.fromisoformat(value) if value else None

    def _connector(self, row: aiosqlite.Row) -> ManagedConnectorRecord:
        return ManagedConnectorRecord(
            id=row["id"],
            version=row["version"],
            previous_version=row["previous_version"],
            state=ConnectorState(row["state"]),
            source=row["source"],
            manifest=json.loads(row["manifest_json"]),
            installed_at=self._dt(row["installed_at"]),
            updated_at=self._dt(row["updated_at"]),
        )

    def _secret(self, row: aiosqlite.Row) -> SecretRecord:
        return SecretRecord(
            id=row["id"],
            name=row["name"],
            scope_type=SecretScope(row["scope_type"]),
            scope_id=row["scope_id"],
            owner_id=row["owner_id"],
            created_by=row["created_by"],
            version=row["version"],
            created_at=self._dt(row["created_at"]),
            updated_at=self._dt(row["updated_at"]),
        )

    def _target(self, row: aiosqlite.Row) -> DeliveryTargetRecord:
        return DeliveryTargetRecord(
            id=row["id"],
            name=row["name"],
            type=DeliveryTargetType(row["type"]),
            visibility=FlowVisibility(row["visibility"]),
            enabled=bool(row["enabled"]),
            url=row["url"],
            auth_scheme=DeliveryAuthScheme(row["auth_scheme"]),
            secret_id=row["secret_id"],
            max_attempts=row["max_attempts"],
            backoff_seconds=row["backoff_seconds"],
            owner_id=row["owner_id"],
            created_by=row["created_by"],
            revision=row["revision"],
            created_at=self._dt(row["created_at"]),
            updated_at=self._dt(row["updated_at"]),
        )

    def _delivery(self, row: aiosqlite.Row) -> DeliveryRecord:
        return DeliveryRecord(
            id=row["id"],
            target_id=row["target_id"],
            run_id=row["run_id"],
            idempotency_key=row["idempotency_key"],
            status=DeliveryStatus(row["status"]),
            attempt_count=row["attempt_count"],
            next_attempt_at=self._dt(row["next_attempt_at"]),
            response_status=row["response_status"],
            error=row["error"],
            artifact_path=row["artifact_path"],
            payload_sha256=row["payload_sha256"],
            created_by=row["created_by"],
            created_at=self._dt(row["created_at"]),
            updated_at=self._dt(row["updated_at"]),
            finished_at=self._dt(row["finished_at"]),
        )


class ConnectorManager:
    def __init__(self, settings: Settings, storage: IntegrationStorage):
        self.settings = settings
        self.storage = storage

    async def install(self, request: ConnectorInstallRequest, *, upgrade_id: str | None = None) -> ManagedConnectorRecord:
        inbox = self.settings.connector_inbox_path.resolve()
        wheel = (inbox / request.filename).resolve()
        if wheel.parent != inbox or not wheel.is_file():
            raise FileNotFoundError(request.filename)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if not hmac.compare_digest(digest, request.sha256.lower()):
            raise ConnectorContractError("connector package SHA-256 does not match")
        package_root = self.settings.connector_packages_path.resolve()
        target = package_root / digest
        created_target = False
        if not target.exists():
            staging = package_root / f".{digest}.staging-{uuid.uuid4().hex}"
            staging.mkdir(parents=True)
            try:
                with zipfile.ZipFile(wheel) as archive:
                    for member in archive.infolist():
                        destination = (staging / member.filename).resolve()
                        if staging not in destination.parents and destination != staging:
                            raise ConnectorContractError("connector wheel contains an unsafe path")
                    archive.extractall(staging)
                staging.rename(target)
                created_target = True
            except Exception:
                if staging.exists() and staging.parent == package_root:
                    shutil.rmtree(staging)
                raise
        try:
            entry_point = self._wheel_entry_point(target)
            manifest = await self._describe(entry_point, target)
            if upgrade_id is not None and manifest.id != upgrade_id:
                raise ConnectorContractError("upgrade package connector id does not match")
            return await self.storage.save_connector(
                manifest,
                entry_point=entry_point,
                package_path=str(target),
                upgrade=upgrade_id is not None,
            )
        except Exception:
            if created_target and target.exists() and target.parent == package_root:
                shutil.rmtree(target)
            raise

    async def uninstall(self, connector_id: str) -> bool:
        row = await self.storage._connector_row(connector_id)
        if row is None:
            return False
        deleted = await self.storage.uninstall_connector(connector_id)
        if not deleted:
            return False
        package_root = self.settings.connector_packages_path.resolve()
        for value in {row["package_path"], row["previous_package_path"]}:
            if not value:
                continue
            path = Path(value).resolve()
            if path.parent == package_root and path.is_dir():
                shutil.rmtree(path)
        return True

    @staticmethod
    def _wheel_entry_point(path: Path) -> str:
        candidates: list[str] = []
        for entry_file in path.glob("*.dist-info/entry_points.txt"):
            parser = configparser.ConfigParser()
            parser.read(entry_file, encoding="utf-8")
            if parser.has_section("siftlane.connectors"):
                candidates.extend(name for name, _ in parser.items("siftlane.connectors"))
        if len(candidates) != 1:
            raise ConnectorContractError("connector wheel must define exactly one siftlane.connectors entry point")
        return candidates[0]

    async def _describe(self, entry_point: str, path: Path) -> ConnectorManifest:
        result = await self._run_worker("describe", entry_point, path, {})
        return ConnectorManifest.model_validate(result)

    async def execute(self, connector_id: str, request: ConnectorOperationRequest) -> ConnectorOperationResult:
        row = await self.storage._connector_row(connector_id)
        if row is None:
            raise KeyError(connector_id)
        if row["state"] != ConnectorState.ENABLED.value:
            raise IntegrationConflict("connector is disabled")
        secrets: dict[str, str] = {}
        if request.credential is not None:
            secrets[request.credential.key] = await self.storage.resolve_scoped_secret(
                SecretScope.CONNECTOR,
                connector_id,
                request.credential.key,
            )
        payload = {
            "request": request.model_dump(mode="json"),
            "secrets": secrets,
            "http_policy": {
                "allow_private_networks": self.settings.allow_private_networks,
                "timeout_seconds": self.settings.request_timeout_seconds,
                "max_response_bytes": self.settings.max_response_bytes,
            },
        }
        path = Path(row["package_path"]) if row["package_path"] else None
        result = await self._run_worker("execute", row["entry_point"], path, payload)
        if contains_secret_material(result, list(secrets.values())):
            raise ConnectorProcessError("connector response included credential material")
        return ConnectorOperationResult.model_validate(result)

    async def _run_worker(self, command: str, entry_point: str, path: Path | None, payload: dict) -> dict:
        args = [sys.executable, "-m", "siftlane_engine.connector_worker", command, entry_point]
        if path is not None:
            args.append(str(path))
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_connector_environment(),
        )
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(encoded),
                timeout=self.settings.connector_timeout_seconds,
            )
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise ConnectorProcessError("connector execution timed out") from error
        if process.returncode != 0:
            raise ConnectorProcessError(f"connector exited with {process.returncode}")
        if len(stdout) > MAX_CONNECTOR_OUTPUT_BYTES:
            raise ConnectorProcessError("connector response exceeded the output limit")
        try:
            result = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConnectorProcessError("connector returned invalid JSON") from error
        if not isinstance(result, dict):
            raise ConnectorProcessError("connector response must be an object")
        return result


class DeliveryService:
    def __init__(self, settings: Settings, storage: IntegrationStorage, run_storage: Storage):
        self.settings = settings
        self.storage = storage
        self.run_storage = run_storage
        self._worker: asyncio.Task[None] | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(settings.delivery_timeout_seconds),
            headers={"User-Agent": settings.user_agent},
        )

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._loop(), name="delivery-worker")

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        await self._client.aclose()

    async def create(self, request: DeliveryCreate, actor_id: str) -> DeliveryRecord:
        delivery, created = await self.storage.create_delivery(request, actor_id)
        if created:
            return await self.process(delivery.id)
        return delivery

    async def process(self, delivery_id: str) -> DeliveryRecord:
        lock = self._locks.setdefault(delivery_id, asyncio.Lock())
        async with lock:
            delivery = await self.storage.claim_delivery(delivery_id)
            if delivery is None:
                current = await self.storage.get_delivery(delivery_id)
                if current is None:
                    raise KeyError(delivery_id)
                return current
            target = await self.storage.get_target(delivery.target_id)
            if target is None:
                return await self.storage.finish_delivery(
                    delivery_id,
                    success=False,
                    max_attempts=1,
                    backoff_seconds=0,
                    error="delivery target no longer exists",
                )
            if not target.enabled:
                return await self.storage.finish_delivery(
                    delivery_id,
                    success=False,
                    max_attempts=target.max_attempts,
                    backoff_seconds=target.backoff_seconds,
                    error="delivery target is disabled",
                )
            try:
                payload = await self._payload(delivery.run_id, delivery.id)
                digest = hashlib.sha256(payload).hexdigest()
                if len(payload) > self.settings.max_delivery_bytes:
                    raise RuntimeError("delivery payload exceeds the configured size limit")
                if target.type == DeliveryTargetType.NDJSON:
                    artifact = self.settings.export_path / target.id / f"{delivery.id}.ndjson"
                    artifact.parent.mkdir(parents=True, exist_ok=True)
                    temporary = artifact.with_suffix(".tmp")
                    temporary.write_bytes(payload)
                    os.replace(temporary, artifact)
                    relative = artifact.relative_to(self.settings.data_dir.expanduser().resolve()).as_posix()
                    return await self.storage.finish_delivery(
                        delivery_id,
                        success=True,
                        max_attempts=target.max_attempts,
                        backoff_seconds=target.backoff_seconds,
                        artifact_path=relative,
                        payload_sha256=digest,
                    )
                await self._validate_webhook_url(target.url or "")
                headers = {
                    "Content-Type": "application/x-ndjson",
                    "Idempotency-Key": delivery.idempotency_key,
                    "X-Siftlane-Delivery": delivery.id,
                }
                if target.secret_id:
                    secret = await self.storage.resolve_secret(target.secret_id)
                    if target.auth_scheme == DeliveryAuthScheme.BEARER:
                        headers["Authorization"] = f"Bearer {secret}"
                    elif target.auth_scheme == DeliveryAuthScheme.HMAC_SHA256:
                        signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
                        headers["X-Siftlane-Signature"] = f"sha256={signature}"
                response = await self._client.post(target.url or "", content=payload, headers=headers)
                success = 200 <= response.status_code < 300
                return await self.storage.finish_delivery(
                    delivery_id,
                    success=success,
                    max_attempts=target.max_attempts,
                    backoff_seconds=target.backoff_seconds,
                    response_status=response.status_code,
                    error=None if success else f"webhook returned HTTP {response.status_code}",
                    payload_sha256=digest,
                )
            except Exception as error:
                return await self.storage.finish_delivery(
                    delivery_id,
                    success=False,
                    max_attempts=target.max_attempts,
                    backoff_seconds=target.backoff_seconds,
                    error=str(error),
                )

    async def _payload(self, run_id: str, delivery_id: str) -> bytes:
        lines: list[bytes] = []
        cursor: str | None = None
        while True:
            items, cursor = await self.run_storage.list_items(run_id, cursor, 500)
            for item in items:
                value = item.model_dump(mode="json")
                value["delivery_id"] = delivery_id
                lines.append(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
            if cursor is None:
                break
        return b"".join(lines)

    async def _validate_webhook_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("webhook URL must use HTTP or HTTPS")
        if parsed.username or parsed.password:
            raise RuntimeError("webhook URL user information is not allowed")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM),
        )
        if not self.settings.allow_private_networks:
            import ipaddress

            for address in addresses:
                ip = ipaddress.ip_address(address[4][0])
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                    or ip.is_unspecified
                ):
                    raise RuntimeError("webhook target is not publicly routable")

    async def _loop(self) -> None:
        while True:
            try:
                for delivery_id in await self.storage.due_delivery_ids():
                    await self.process(delivery_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(self.settings.delivery_poll_seconds)
