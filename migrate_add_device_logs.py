#!/usr/bin/env python3
"""
Database migration: Add device_logs table.

This table stores per-device log entries for debugging and audit trail.

Run this once to add the new table.
"""

import sqlite3
import os

# Path to the SLMM database
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "slmm.db")


def migrate():
    print(f"Adding device_logs table to: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print("Database does not exist yet. Table will be created automatically on first run.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='device_logs'
        """)
        if cursor.fetchone():
            print("✓ device_logs table already exists, no migration needed")
            return

        # Create the table
        print("Creating device_logs table...")
        cursor.execute("""
            CREATE TABLE device_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id VARCHAR NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                level VARCHAR DEFAULT 'INFO',
                category VARCHAR DEFAULT 'GENERAL',
                message TEXT NOT NULL
            )
        """)

        # Create indexes for efficient querying
        print("Creating indexes...")
        cursor.execute("CREATE INDEX ix_device_logs_unit_id ON device_logs (unit_id)")
        cursor.execute("CREATE INDEX ix_device_logs_timestamp ON device_logs (timestamp)")

        conn.commit()
        print("✓ Created device_logs table with indexes")

        # Verify
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='device_logs'
        """)
        if not cursor.fetchone():
            raise Exception("device_logs table was not created successfully")

        print("✓ Migration completed successfully")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
