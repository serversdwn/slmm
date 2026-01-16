#!/usr/bin/env python3
"""
Migration script to revert NL43 measurement field names back to correct DRD format.

The previous migration was incorrect. According to NL43 DRD documentation:
- d0 = counter (1-600) - NOT a measurement!
- d1 = Lp (instantaneous sound pressure level)
- d2 = Leq (equivalent continuous sound level)
- d3 = Lmax (maximum level)
- d4 = Lmin (minimum level)
- d5 = Lpeak (peak level)

Changes:
- laeq -> lp (was incorrectly mapped to counter field!)
- lae -> leq
- lasmax -> lmax
- lasmin -> lmin
- lapeak -> lpeak
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str):
    """Revert database schema to correct DRD field names."""

    print(f"Reverting database migration: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # Check if migration is needed
        cur.execute("PRAGMA table_info(nl43_status)")
        columns = [row[1] for row in cur.fetchall()]

        if 'lp' in columns:
            print("✓ Database already has correct field names")
            return

        if 'laeq' not in columns:
            print("✗ Database schema does not match expected format")
            sys.exit(1)

        print("Starting revert migration...")

        # Create new table with correct column names
        cur.execute("""
            CREATE TABLE nl43_status_new (
                unit_id VARCHAR PRIMARY KEY,
                last_seen DATETIME,
                measurement_state VARCHAR,
                lp VARCHAR,
                leq VARCHAR,
                lmax VARCHAR,
                lmin VARCHAR,
                lpeak VARCHAR,
                battery_level VARCHAR,
                power_source VARCHAR,
                sd_remaining_mb VARCHAR,
                sd_free_ratio VARCHAR,
                raw_payload TEXT
            )
        """)
        print("✓ Created new table with correct DRD field names")

        # Copy data from old table to new table
        # Note: laeq was incorrectly mapped to d0 (counter), so we discard it
        # The actual measurements start from d1
        cur.execute("""
            INSERT INTO nl43_status_new
            (unit_id, last_seen, measurement_state, lp, leq, lmax, lmin, lpeak,
             battery_level, power_source, sd_remaining_mb, sd_free_ratio, raw_payload)
            SELECT
                unit_id, last_seen, measurement_state, lae, lasmax, lasmin, lapeak, NULL,
                battery_level, power_source, sd_remaining_mb, sd_free_ratio, raw_payload
            FROM nl43_status
        """)
        rows_copied = cur.rowcount
        print(f"✓ Copied {rows_copied} rows (note: discarded incorrect 'laeq' counter field)")

        # Drop old table
        cur.execute("DROP TABLE nl43_status")
        print("✓ Dropped old table")

        # Rename new table
        cur.execute("ALTER TABLE nl43_status_new RENAME TO nl43_status")
        print("✓ Renamed new table to nl43_status")

        # Commit changes
        conn.commit()
        print("✓ Revert migration completed successfully")
        print("\nNote: The 'lp' field will be populated correctly on next device measurement")

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
