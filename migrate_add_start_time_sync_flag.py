#!/usr/bin/env python3
"""
Database migration: Add start_time_sync_attempted field to nl43_status table.

This field tracks whether FTP sync has been attempted for the current measurement,
preventing repeated sync attempts when FTP fails.

Run this once to add the new column.
"""

import sqlite3
import os

# Path to the SLMM database
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "slmm.db")


def migrate():
    print(f"Adding start_time_sync_attempted field to: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print("Database does not exist yet. Column will be created automatically.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(nl43_status)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'start_time_sync_attempted' in columns:
            print("✓ start_time_sync_attempted column already exists, no migration needed")
            return

        # Add the column
        print("Adding start_time_sync_attempted column...")
        cursor.execute("""
            ALTER TABLE nl43_status
            ADD COLUMN start_time_sync_attempted BOOLEAN DEFAULT 0
        """)
        conn.commit()
        print("✓ Added start_time_sync_attempted column")

        # Verify
        cursor.execute("PRAGMA table_info(nl43_status)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'start_time_sync_attempted' not in columns:
            raise Exception("start_time_sync_attempted column was not added successfully")

        print("✓ Migration completed successfully")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
