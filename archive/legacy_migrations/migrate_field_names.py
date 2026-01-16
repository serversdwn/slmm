#!/usr/bin/env python3
"""
Migration script to rename NL43 measurement field names to match actual device output.

Changes:
- lp -> laeq (A-weighted equivalent continuous sound level)
- leq -> lae (A-weighted sound exposure level)
- lmax -> lasmax (A-weighted slow maximum)
- lmin -> lasmin (A-weighted slow minimum)
- lpeak -> lapeak (A-weighted peak)
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str):
    """Migrate the database schema to use correct field names."""

    print(f"Migrating database: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # Check if migration is needed
        cur.execute("PRAGMA table_info(nl43_status)")
        columns = [row[1] for row in cur.fetchall()]

        if 'laeq' in columns:
            print("✓ Database already migrated")
            return

        if 'lp' not in columns:
            print("✗ Database schema does not match expected format")
            sys.exit(1)

        print("Starting migration...")

        # SQLite doesn't support column renaming directly, so we need to:
        # 1. Create new table with correct column names
        # 2. Copy data from old table
        # 3. Drop old table
        # 4. Rename new table

        # Create new table with correct column names
        cur.execute("""
            CREATE TABLE nl43_status_new (
                unit_id VARCHAR PRIMARY KEY,
                last_seen DATETIME,
                measurement_state VARCHAR,
                laeq VARCHAR,
                lae VARCHAR,
                lasmax VARCHAR,
                lasmin VARCHAR,
                lapeak VARCHAR,
                battery_level VARCHAR,
                power_source VARCHAR,
                sd_remaining_mb VARCHAR,
                sd_free_ratio VARCHAR,
                raw_payload TEXT
            )
        """)
        print("✓ Created new table with correct column names")

        # Copy data from old table to new table
        cur.execute("""
            INSERT INTO nl43_status_new
            (unit_id, last_seen, measurement_state, laeq, lae, lasmax, lasmin, lapeak,
             battery_level, power_source, sd_remaining_mb, sd_free_ratio, raw_payload)
            SELECT
                unit_id, last_seen, measurement_state, lp, leq, lmax, lmin, lpeak,
                battery_level, power_source, sd_remaining_mb, sd_free_ratio, raw_payload
            FROM nl43_status
        """)
        rows_copied = cur.rowcount
        print(f"✓ Copied {rows_copied} rows from old table")

        # Drop old table
        cur.execute("DROP TABLE nl43_status")
        print("✓ Dropped old table")

        # Rename new table
        cur.execute("ALTER TABLE nl43_status_new RENAME TO nl43_status")
        print("✓ Renamed new table to nl43_status")

        # Commit changes
        conn.commit()
        print("✓ Migration completed successfully")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    # Default database path
    db_path = Path(__file__).parent / "data" / "slmm.db"

    # Allow custom path as command line argument
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"✗ Database not found: {db_path}")
        sys.exit(1)

    migrate_database(str(db_path))
