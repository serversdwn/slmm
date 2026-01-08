#!/usr/bin/env python3
"""
Database migration: Add counter field to nl43_status table

This adds the d0 (measurement interval counter) field to track the device's
actual measurement progress for accurate timer synchronization.
"""

import sqlite3
import sys

DB_PATH = "data/slmm.db"

def migrate():
    print(f"Adding counter field to: {DB_PATH}")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if counter column already exists
        cursor.execute("PRAGMA table_info(nl43_status)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'counter' in columns:
            print("✓ Counter column already exists, no migration needed")
            conn.close()
            return

        print("Starting migration...")

        # Add counter column
        cursor.execute("""
            ALTER TABLE nl43_status
            ADD COLUMN counter TEXT
        """)

        conn.commit()
        print("✓ Added counter column")

        # Verify
        cursor.execute("PRAGMA table_info(nl43_status)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'counter' not in columns:
            raise Exception("Counter column was not added successfully")

        print("✓ Migration completed successfully")

        conn.close()

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
