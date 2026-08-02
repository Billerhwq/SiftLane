from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from siftlane_engine.operations import create_backup, database_integrity, restore_backup, verify_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-rto-seconds", type=float, default=60)
    arguments = parser.parse_args()
    source = arguments.data_dir.resolve() / "crawler.db"
    backup = arguments.work_dir.resolve() / "capacity-backup.sqlite3"
    restored = arguments.work_dir.resolve() / "restored" / "crawler.db"
    started = time.perf_counter()
    manifest = create_backup(source, backup)
    verified = verify_backup(backup)
    restore = restore_backup(backup, restored)
    elapsed = time.perf_counter() - started
    source_integrity = database_integrity(source)
    restored_integrity = database_integrity(restored)
    passed = bool(
        elapsed <= arguments.max_rto_seconds
        and verified["verified"]
        and restore["restored"]
        and source_integrity["counts"] == restored_integrity["counts"]
        and restored_integrity["integrity"] == "ok"
    )
    report = {
        "format": "siftlane.backup-drill/v1",
        "sourceBytes": source.stat().st_size,
        "backupBytes": manifest["bytes"],
        "backupSha256": manifest["sha256"],
        "schemaVersion": manifest["schemaVersion"],
        "counts": restored_integrity["counts"],
        "elapsedSeconds": round(elapsed, 6),
        "maxRtoSeconds": arguments.max_rto_seconds,
        "integrity": restored_integrity["integrity"],
        "passed": passed,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
