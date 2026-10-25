#!/usr/bin/env python3
"""CLI utility for REZOLV Database Backups and Actual Restore Drills.

Usage:
  python3 scripts/backup_restore.py --backup          # Create atomic backup + SHA-256 manifest
  python3 scripts/backup_restore.py --verify-drill    # Backup + restore into temp DB + verify 100% row parity
  python3 scripts/backup_restore.py --restore-latest  # Restore the latest verified backup
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from rezolv import backup, config, db, seed  # noqa: E402


def ensure_db_initialized():
    db.init_db(config.DB_PATH)
    conn = db.connect(config.DB_PATH)
    try:
        seed.seed(conn)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="REZOLV Database Backup & Restore Verification")
    parser.add_argument("--backup", action="store_true", help="Create a hot backup")
    parser.add_argument("--verify-drill", action="store_true", help="Run full backup + restore verification drill")
    parser.add_argument("--restore-latest", action="store_true", help="Restore the most recent backup to DB_PATH")
    args = parser.parse_args()

    ensure_db_initialized()

    if args.restore_latest:
        all_dbs = sorted(glob.glob(os.path.join(config.BACKUP_DIR, "*.db")), key=os.path.getmtime, reverse=True)
        matched_files = []
        for f in all_dbs:
            m_path = f + ".manifest.json"
            if os.path.exists(m_path):
                try:
                    with open(m_path, "r", encoding="utf-8") as mf:
                        m = json.load(mf)
                        src = os.path.abspath(m.get("source_db", ""))
                        if src == os.path.abspath(config.DB_PATH) or os.path.basename(src) == os.path.basename(config.DB_PATH):
                            matched_files.append(f)
                except Exception:
                    pass
        target_files = matched_files or all_dbs
        if not target_files:
            print("No backup files found in", config.BACKUP_DIR)
            sys.exit(1)
        res = backup.restore_backup(target_files[0], config.DB_PATH)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    if args.backup:
        manifest = backup.create_backup()
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return

    # Default or --verify-drill
    report = backup.verify_backup_and_restore()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report.get("verified"):
        sys.exit(1)


if __name__ == "__main__":
    main()
