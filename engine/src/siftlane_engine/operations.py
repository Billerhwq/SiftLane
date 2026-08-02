from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .storage import MIN_COMPATIBLE_SCHEMA_VERSION, SCHEMA_VERSION


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(backup_path: Path) -> Path:
    return backup_path.with_name(f"{backup_path.name}.manifest.json")


def database_integrity(path: Path) -> dict[str, Any]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as database:
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
        meta_exists = database.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        schema_version = 0
        if meta_exists:
            row = database.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            schema_version = int(row[0]) if row else 0
        counts = {
            table: int(database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("flows", "runs", "items", "events")
            if database.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        }
    return {"integrity": integrity, "schemaVersion": schema_version, "counts": counts}


def create_backup(database_path: Path, output_path: Path) -> dict[str, Any]:
    database_path = database_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"database does not exist: {database_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() or manifest_path(output_path).exists():
        raise FileExistsError("backup output already exists")
    temporary = output_path.with_name(f".{output_path.name}.tmp-{uuid.uuid4().hex}")
    started = time.perf_counter()
    try:
        with closing(sqlite3.connect(database_path)) as source, closing(sqlite3.connect(temporary)) as destination:
            source.backup(destination, pages=256, sleep=0.01)
        integrity = database_integrity(temporary)
        if integrity["integrity"] != "ok":
            raise RuntimeError(f"backup integrity check failed: {integrity['integrity']}")
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    elapsed = time.perf_counter() - started
    manifest = {
        "format": "siftlane.backup/v1",
        "engineVersion": __version__,
        "schemaVersion": integrity["schemaVersion"],
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "database": output_path.name,
        "bytes": output_path.stat().st_size,
        "sha256": file_sha256(output_path),
        "integrity": integrity["integrity"],
        "counts": integrity["counts"],
        "elapsedSeconds": round(elapsed, 6),
    }
    manifest_file = manifest_path(output_path)
    temporary_manifest = manifest_file.with_name(f".{manifest_file.name}.tmp-{uuid.uuid4().hex}")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, manifest_file)
    return manifest


def verify_backup(backup_path: Path, supplied_manifest: Path | None = None) -> dict[str, Any]:
    backup_path = backup_path.expanduser().resolve()
    supplied_manifest = (supplied_manifest or manifest_path(backup_path)).expanduser().resolve()
    if not backup_path.is_file() or not supplied_manifest.is_file():
        raise FileNotFoundError("backup database or manifest is missing")
    manifest = json.loads(supplied_manifest.read_text(encoding="utf-8"))
    if manifest.get("format") != "siftlane.backup/v1":
        raise ValueError("unsupported backup manifest format")
    if manifest.get("database") != backup_path.name:
        raise ValueError("backup file name does not match the manifest")
    actual_hash = file_sha256(backup_path)
    if not isinstance(manifest.get("sha256"), str) or not hmac_compare(actual_hash, manifest["sha256"]):
        raise ValueError("backup SHA-256 does not match the manifest")
    integrity = database_integrity(backup_path)
    if integrity["integrity"] != "ok":
        raise ValueError(f"backup integrity check failed: {integrity['integrity']}")
    if integrity["schemaVersion"] != int(manifest.get("schemaVersion", -1)):
        raise ValueError("backup schema version does not match the manifest")
    if integrity["schemaVersion"] > SCHEMA_VERSION:
        raise ValueError("backup schema is newer than this engine")
    if integrity["schemaVersion"] < MIN_COMPATIBLE_SCHEMA_VERSION:
        raise ValueError("backup schema is older than the supported restore range")
    return {**manifest, "verified": True}


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.lower(), right.lower())


def restore_backup(
    backup_path: Path,
    database_path: Path,
    *,
    supplied_manifest: Path | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    verified = verify_backup(backup_path, supplied_manifest)
    database_path = database_path.expanduser().resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists() and not replace:
        raise FileExistsError("target database exists; stop the engine and pass --replace")
    safety_copy: Path | None = None
    if database_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safety_copy = database_path.with_name(f"{database_path.name}.pre-restore-{stamp}")
        with closing(sqlite3.connect(database_path)) as source, closing(sqlite3.connect(safety_copy)) as destination:
            source.backup(destination)
    temporary = database_path.with_name(f".{database_path.name}.restore-{uuid.uuid4().hex}")
    try:
        shutil.copy2(backup_path, temporary)
        if file_sha256(temporary) != verified["sha256"]:
            raise RuntimeError("restored temporary copy failed SHA-256 verification")
        if database_integrity(temporary)["integrity"] != "ok":
            raise RuntimeError("restored temporary copy failed integrity verification")
        os.replace(temporary, database_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "restored": True,
        "database": str(database_path),
        "schemaVersion": verified["schemaVersion"],
        "sha256": verified["sha256"],
        "safetyCopy": str(safety_copy) if safety_copy else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="siftlane-ops")
    commands = root.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--data-dir", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--backup", type=Path, required=True)
    verify.add_argument("--manifest", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("--data-dir", type=Path, required=True)
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--manifest", type=Path)
    restore.add_argument("--replace", action="store_true")
    return root


def main() -> None:
    arguments = parser().parse_args()
    try:
        if arguments.command == "backup":
            result = create_backup(arguments.data_dir / "crawler.db", arguments.output)
        elif arguments.command == "verify":
            result = verify_backup(arguments.backup, arguments.manifest)
        else:
            result = restore_backup(
                arguments.backup,
                arguments.data_dir / "crawler.db",
                supplied_manifest=arguments.manifest,
                replace=arguments.replace,
            )
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        raise SystemExit(2) from error
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
