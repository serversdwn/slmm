#!/usr/bin/env python3
"""
Migration script to add FTP username and password columns to nl43_config table.
Run this once to update existing database schema.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "slmm.db"


def migrate():
    """Add ftp_username and ftp_password columns to nl43_config table."""

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("No migration needed - database will be created with new schema")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(nl43_config)")
        columns = [row[1] for row in cursor.fetchall()]

        if "ftp_username" in columns and "ftp_password" in columns:
            print("✓ FTP credential columns already exist, no migration needed")
            return

        # Add ftp_username column if it doesn't exist
        if "ftp_username" not in columns:
            print("Adding ftp_username column...")
            cursor.execute("ALTER TABLE nl43_config ADD COLUMN ftp_username TEXT")
            print("✓ Added ftp_username column")

        # Add ftp_password column if it doesn't exist
        if "ftp_password" not in columns:
            print("Adding ftp_password column...")
            cursor.execute("ALTER TABLE nl43_config ADD COLUMN ftp_password TEXT")
            print("✓ Added ftp_password column")

        conn.commit()
        print("\n✓ Migration completed successfully!")
        print("\nYou can now set FTP credentials via the web UI or database.")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
