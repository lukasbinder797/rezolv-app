"""Database Backup & Restore Verification Engine for REZOLV MVP.

Uses SQLite's online atomic backup API (`sqlite3.Connection.backup`), computes SHA-256
checksum manifests, enforces retention limits, and tests actual restores into an isolated
database with `PRAGMA integrity_check` and row-count verification.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

from . import config


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def create_backup(db_path: str | None = None, backup_dir: str | None = None, max_keep: int = 10) -> dict:
    """Create a hot atomic backup of `db_path` along with a JSON metadata & SHA-256 manifest."""
    src_path = db_path or os.environ.get("REZOLV_DB") or config.DB_PATH
    target_dir = backup_dir or os.environ.get("REZOLV_BACKUP_DIR") or config.BACKUP_DIR
    os.makedirs(target_dir, exist_ok=True)

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_filename = f"rezolv_backup_{ts_str}_{os.getpid()}.db"
    backup_path = os.path.join(target_dir, backup_filename)

    src_conn = sqlite3.connect(src_path, timeout=10)
    dst_conn = sqlite3.connect(backup_path, timeout=10)
    try:
        src_conn.backup(dst_conn)
        counts = _table_counts(dst_conn)
        integrity = dst_conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst_conn.close()
        src_conn.close()

    checksum = _sha256_file(backup_path)
    size_bytes = os.path.getsize(backup_path)
    manifest = {
        "backup_file": backup_filename,
        "backup_path": backup_path,
        "source_db": src_path,
        "created_at_iso": ts_str,
        "size_bytes": size_bytes,
        "sha256": checksum,
        "integrity_check": integrity,
        "table_counts": counts,
    }
    manifest_path = backup_path + ".manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Rotate old backups beyond max_keep
    all_dbs = sorted(
        [os.path.join(target_dir, x) for x in os.listdir(target_dir) if x.endswith(".db")],
        key=os.path.getmtime,
        reverse=True,
    )
    for old_db in all_dbs[max_keep:]:
        for p in (old_db, old_db + ".manifest.json"):
            try:
                os.remove(p)
            except OSError:
                pass

    return manifest


def restore_backup(backup_path: str, target_db_path: str) -> dict:
    """Verify SHA-256 & SQLite integrity of `backup_path`, then atomically restore into `target_db_path`."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    manifest_path = backup_path + ".manifest.json"
    actual_sha = _sha256_file(backup_path)
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("sha256") and manifest["sha256"] != actual_sha:
            raise ValueError("SHA-256 checksum mismatch on backup file!")

    # Verify backup integrity before overwriting target
    chk_conn = sqlite3.connect(backup_path)
    try:
        integrity = chk_conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Backup integrity check failed: {integrity}")
    finally:
        chk_conn.close()

    os.makedirs(os.path.dirname(os.path.abspath(target_db_path)), exist_ok=True)
    src_conn = sqlite3.connect(backup_path, timeout=10)
    dst_conn = sqlite3.connect(target_db_path, timeout=10)
    try:
        src_conn.backup(dst_conn)
        dst_conn.execute("PRAGMA foreign_keys = ON")
        fk_errors = dst_conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise ValueError(f"Foreign key errors after restore: {fk_errors}")
        counts = _table_counts(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    return {
        "restored": True,
        "backup_path": backup_path,
        "target_db_path": target_db_path,
        "sha256": actual_sha,
        "integrity_check": "ok",
        "foreign_key_check": "ok",
        "table_counts": counts,
    }


def verify_backup_and_restore(db_path: str | None = None, backup_dir: str | None = None) -> dict:
    """End-to-end drill: create a live backup, restore it into a fresh temporary database,
    mutate/corrupt a scratch copy first to prove overwrite works, and verify 100% row parity."""
    manifest = create_backup(db_path=db_path, backup_dir=backup_dir)
    with tempfile.TemporaryDirectory() as tmpdir:
        restore_target = os.path.join(tmpdir, "restored_verify.db")
        # Create a dummy corrupted/empty DB at target first to prove restore overwrites cleanly
        dummy = sqlite3.connect(restore_target)
        dummy.execute("CREATE TABLE dummy_table (x INT)")
        dummy.commit()
        dummy.close()

        res = restore_backup(manifest["backup_path"], restore_target)
        matches = res["table_counts"] == manifest["table_counts"]

    return {
        "verified": matches and res["integrity_check"] == "ok",
        "backup_manifest": manifest,
        "restore_verification": res,
        "row_parity_match": matches,
    }
