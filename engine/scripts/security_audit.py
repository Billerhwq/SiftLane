from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


def tracked_secret_scan(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    patterns = [
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"ghp_[A-Za-z0-9]{36}"),
        re.compile(re.escape(private_key_marker)),
    ]
    findings: list[str] = []
    for raw_name in completed.stdout.split(b"\0"):
        if not raw_name:
            continue
        relative = raw_name.decode("utf-8")
        path = repo_root / relative
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(pattern.search(content) for pattern in patterns):
            findings.append(relative)
    return findings


def archive_members(path: Path) -> list[str]:
    if path.suffix not in {".whl", ".zip"}:
        return []
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def audit_artifacts(artifacts_dir: Path) -> list[str]:
    findings: list[str] = []
    manifest_file = artifacts_dir / "manifest.json"
    if not manifest_file.is_file():
        return ["manifest.json is missing"]
    manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
    for artifact in manifest.get("artifacts", []):
        path = artifacts_dir / artifact["name"]
        if not path.is_file():
            findings.append(f"missing artifact: {path.name}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            findings.append(f"hash mismatch: {path.name}")
        for member in archive_members(path):
            pure = PurePosixPath(member)
            lowered = member.lower()
            if pure.is_absolute() or ".." in pure.parts:
                findings.append(f"unsafe archive path: {path.name}:{member}")
            if lowered.endswith((".env", ".db", ".db-wal", ".db-shm", ".pyc")):
                findings.append(f"forbidden archive member: {path.name}:{member}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path)
    arguments = parser.parse_args()
    findings = tracked_secret_scan(arguments.repo_root.resolve())
    if arguments.artifacts_dir:
        findings.extend(audit_artifacts(arguments.artifacts_dir.resolve()))
    report = {"passed": not findings, "findings": findings}
    print(json.dumps(report))
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
