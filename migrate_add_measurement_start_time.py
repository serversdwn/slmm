#!/usr/bin/env python3
"""
Database migration: Add measurement_start_time field to nl43_status table

This tracks when a measurement session started by detecting the state transition
from "Stop" to "Measure", enabling accurate elapsed time display even for
manually-started measurements.
"""

import sqlite3
import sys

DB_PATH = "data/slmm.db"

def migrate():
    print(f"Adding measurement_start_time field to: {DB_PATH}")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if measurement_start_time column already exists
        cursor.execute("PRAGMA table_info(nl43_status)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'measurement_start_time' in columns:
            print("✓ measurement_start_time column already exists, no migration needed")
            conn.close()
            return

        print("Starting migration...")

        # Add measurement_start_time column
        cursor.execute("""
            ALTER TABLE nl43_status
            ADD COLUMN measurement_start_time TEXT
        """)

        conn.commit()
        print("✓ Added measurement_start_time column")

        # Verify
        cursor.execute("PRAGMA table_info(nl43_status)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'measurement_start_time' not in columns:
            raise Exception("measurement_start_time column was not added successfully")

        print("✓ Migration completed successfully")

        conn.close()

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
