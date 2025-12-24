#!/usr/bin/env python3
"""
Helper script to set FTP credentials for a device.
Usage: python3 set_ftp_credentials.py <unit_id> <username> <password>
"""

import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "slmm.db"


def set_credentials(unit_id: str, username: str, password: str):
    """Set FTP credentials for a device."""

    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if unit exists
        cursor.execute("SELECT unit_id FROM nl43_config WHERE unit_id = ?", (unit_id,))
        if not cursor.fetchone():
            print(f"Error: Unit '{unit_id}' not found in database")
            print("\nAvailable units:")
            cursor.execute("SELECT unit_id FROM nl43_config")
            for row in cursor.fetchall():
                print(f"  - {row[0]}")
            sys.exit(1)

        # Update credentials
        cursor.execute(
            "UPDATE nl43_config SET ftp_username = ?, ftp_password = ? WHERE unit_id = ?",
            (username, password, unit_id)
        )
        conn.commit()

        print(f"✓ FTP credentials updated for unit '{unit_id}'")
        print(f"  Username: {username}")
        print(f"  Password: {'*' * len(password)}")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 set_ftp_credentials.py <unit_id> <username> <password>")
        print("\nExample:")
        print("  python3 set_ftp_credentials.py nl43-1 admin mypassword")
        sys.exit(1)

    unit_id = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]

    set_credentials(unit_id, username, password)
