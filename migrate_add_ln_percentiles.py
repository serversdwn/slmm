#!/usr/bin/env python3
"""
Migration script to add ln1 and ln2 percentile columns to the nl43_status table.

The NL-43 DOD response carries percentile slots LN1-LN5; the live SLM display
(Terra-View) shows two of them (default L1/L10). This adds storage for the two
surfaced slots. Run once per database to update existing schema.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "slmm.db"


def migrate():
    """Add ln1 and ln2 columns to the nl43_status table."""

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("No migration needed - database will be created with new schema")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(nl43_status)")
        columns = [row[1] for row in cursor.fetchall()]

        if "ln1" in columns and "ln2" in columns:
            print("✓ ln1/ln2 columns already exist, no migration needed")
            return

        if "ln1" not in columns:
            print("Adding ln1 column...")
            cursor.execute("ALTER TABLE nl43_status ADD COLUMN ln1 TEXT")
            print("✓ Added ln1 column")

        if "ln2" not in columns:
            print("Adding ln2 column...")
            cursor.execute("ALTER TABLE nl43_status ADD COLUMN ln2 TEXT")
            print("✓ Added ln2 column")

        conn.commit()
        print("\n✓ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
