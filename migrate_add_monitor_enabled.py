#!/usr/bin/env python3
"""
Migration: add monitor_enabled column to nl43_config.

Controls whether the live fan-out DOD monitor is kept alive 24/7 for a unit
(which is what makes alerting continuous). Defaults to enabled. Run once per DB.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "slmm.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("No migration needed - database will be created with new schema")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(nl43_config)")
        columns = [row[1] for row in cursor.fetchall()]

        if "monitor_enabled" in columns:
            print("✓ monitor_enabled column already exists, no migration needed")
            return

        print("Adding monitor_enabled column (default enabled)...")
        # SQLite stores booleans as 0/1; default 1 = enabled.
        cursor.execute("ALTER TABLE nl43_config ADD COLUMN monitor_enabled BOOLEAN DEFAULT 1")
        conn.commit()
        print("✓ Added monitor_enabled column")
        print("\n✓ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
