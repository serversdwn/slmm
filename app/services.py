"""
Placeholder for NL43 TCP connector.
Implement TCP session management, command serialization, and DOD/DRD parsing here,
then call persist_snapshot to store the latest values.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.database import get_db_session
from app.models import NL43Status


@dataclass
class NL43Snapshot:
    unit_id: str
    measurement_state: str = "unknown"
    lp: Optional[str] = None
    leq: Optional[str] = None
    lmax: Optional[str] = None
    lmin: Optional[str] = None
    lpeak: Optional[str] = None
    battery_level: Optional[str] = None
    power_source: Optional[str] = None
    sd_remaining_mb: Optional[str] = None
    sd_free_ratio: Optional[str] = None
    raw_payload: Optional[str] = None


def persist_snapshot(s: NL43Snapshot):
    """Persist the latest snapshot for API/dashboard use."""
    db = get_db_session()
    try:
        row = db.query(NL43Status).filter_by(unit_id=s.unit_id).first()
        if not row:
            row = NL43Status(unit_id=s.unit_id)
            db.add(row)

        row.last_seen = datetime.utcnow()
        row.measurement_state = s.measurement_state
        row.lp = s.lp
        row.leq = s.leq
        row.lmax = s.lmax
        row.lmin = s.lmin
        row.lpeak = s.lpeak
        row.battery_level = s.battery_level
        row.power_source = s.power_source
        row.sd_remaining_mb = s.sd_remaining_mb
        row.sd_free_ratio = s.sd_free_ratio
        row.raw_payload = s.raw_payload

        db.commit()
    finally:
        db.close()
