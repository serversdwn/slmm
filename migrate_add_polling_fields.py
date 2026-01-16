#!/usr/bin/env python3
"""
Migration script to add polling-related fields to nl43_config and nl43_status tables.

Adds to nl43_config:
- poll_interval_seconds (INTEGER, default 60)
- poll_enabled (BOOLEAN, default 1/True)

Adds to nl43_status:
- is_reachable (BOOLEAN, default 1/True)
- consecutive_failures (INTEGER, default 0)
- last_poll_attempt (DATETIME, nullable)
- last_success (DATETIME, nullable)
- last_error (TEXT, nullable)

Usage:
    python migrate_add_polling_fields.py
"""

import sqlite3
import sys
from pathlib import Path


def migrate():
    db_path = Path("data/slmm.db")

    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        print("   Run this script from the slmm directory")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check nl43_config columns
        cursor.execute("PRAGMA table_info(nl43_config)")
        config_columns = [row[1] for row in cursor.fetchall()]

        # Check nl43_status columns
        cursor.execute("PRAGMA table_info(nl43_status)")
        status_columns = [row[1] for row in cursor.fetchall()]

        changes_made = False

        # Add nl43_config columns
        if "poll_interval_seconds" not in config_columns:
            print("Adding poll_interval_seconds to nl43_config...")
            cursor.execute("""
                ALTER TABLE nl43_config
                ADD COLUMN poll_interval_seconds INTEGER DEFAULT 60
            """)
            changes_made = True
        else:
            print("✓ poll_interval_seconds already exists in nl43_config")

        if "poll_enabled" not in config_columns:
            print("Adding poll_enabled to nl43_config...")
            cursor.execute("""
                ALTER TABLE nl43_config
                ADD COLUMN poll_enabled BOOLEAN DEFAULT 1
            """)
            changes_made = True
        else:
            print("✓ poll_enabled already exists in nl43_config")

        # Add nl43_status columns
        if "is_reachable" not in status_columns:
            print("Adding is_reachable to nl43_status...")
            cursor.execute("""
                ALTER TABLE nl43_status
                ADD COLUMN is_reachable BOOLEAN DEFAULT 1
            """)
            changes_made = True
        else:
            print("✓ is_reachable already exists in nl43_status")

        if "consecutive_failures" not in status_columns:
            print("Adding consecutive_failures to nl43_status...")
            cursor.execute("""
                ALTER TABLE nl43_status
                ADD COLUMN consecutive_failures INTEGER DEFAULT 0
            """)
            changes_made = True
        else:
            print("✓ consecutive_failures already exists in nl43_status")

        if "last_poll_attempt" not in status_columns:
            print("Adding last_poll_attempt to nl43_status...")
            cursor.execute("""
                ALTER TABLE nl43_status
                ADD COLUMN last_poll_attempt DATETIME
            """)
            changes_made = True
        else:
            print("✓ last_poll_attempt already exists in nl43_status")

        if "last_success" not in status_columns:
            print("Adding last_success to nl43_status...")
            cursor.execute("""
                ALTER TABLE nl43_status
                ADD COLUMN last_success DATETIME
            """)
            changes_made = True
        else:
            print("✓ last_success already exists in nl43_status")

        if "last_error" not in status_columns:
            print("Adding last_error to nl43_status...")
            cursor.execute("""
                ALTER TABLE nl43_status
                ADD COLUMN last_error TEXT
            """)
            changes_made = True
        else:
            print("✓ last_error already exists in nl43_status")

        if changes_made:
            conn.commit()
            print("\n✓ Migration completed successfully")
            print("  Added polling-related fields to nl43_config and nl43_status")
        else:
            print("\n✓ All polling fields already exist - no changes needed")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
