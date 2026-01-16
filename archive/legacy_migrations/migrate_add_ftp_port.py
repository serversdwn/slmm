#!/usr/bin/env python3
"""
Migration script to add ftp_port column to nl43_config table.

Usage:
    python migrate_add_ftp_port.py
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

        # Check if column already exists
        cursor.execute("PRAGMA table_info(nl43_config)")
        columns = [row[1] for row in cursor.fetchall()]

        if "ftp_port" in columns:
            print("✓ ftp_port column already exists")
            conn.close()
            return True

        print("Adding ftp_port column to nl43_config table...")

        # Add the ftp_port column with default value of 21
        cursor.execute("""
            ALTER TABLE nl43_config
            ADD COLUMN ftp_port INTEGER DEFAULT 21
        """)

        conn.commit()
        print("✓ Migration completed successfully")
        print("  Added ftp_port column (default: 21)")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
