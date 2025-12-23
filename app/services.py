"""
NL43 TCP connector and snapshot persistence.

Implements simple per-request TCP calls to avoid long-lived socket complexity.
Extend to pooled connections/DRD streaming later.
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models import NL43Status

logger = logging.getLogger(__name__)


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


def persist_snapshot(s: NL43Snapshot, db: Session):
    """Persist the latest snapshot for API/dashboard use."""
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
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to persist snapshot for unit {s.unit_id}: {e}")
        raise


# Rate limiting: NL43 requires ≥1 second between commands
_last_command_time = {}
_rate_limit_lock = asyncio.Lock()


class NL43Client:
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.device_key = f"{host}:{port}"

    async def _enforce_rate_limit(self):
        """Ensure ≥1 second between commands to the same device."""
        async with _rate_limit_lock:
            last_time = _last_command_time.get(self.device_key, 0)
            elapsed = time.time() - last_time
            if elapsed < 1.0:
                wait_time = 1.0 - elapsed
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s for {self.device_key}")
                await asyncio.sleep(wait_time)
            _last_command_time[self.device_key] = time.time()

    async def _send_command(self, cmd: str) -> str:
        """Send ASCII command to NL43 device via TCP."""
        await self._enforce_rate_limit()

        logger.info(f"Sending command to {self.device_key}: {cmd.strip()}")

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout to {self.device_key}")
            raise ConnectionError(f"Failed to connect to device at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Connection failed to {self.device_key}: {e}")
            raise ConnectionError(f"Failed to connect to device: {str(e)}")

        try:
            writer.write(cmd.encode("ascii"))
            await writer.drain()
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=self.timeout)
            response = data.decode(errors="ignore").strip()
            logger.debug(f"Received response from {self.device_key}: {response}")
            return response
        except asyncio.TimeoutError:
            logger.error(f"Response timeout from {self.device_key}")
            raise TimeoutError(f"Device did not respond within {self.timeout}s")
        except Exception as e:
            logger.error(f"Communication error with {self.device_key}: {e}")
            raise
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def request_dod(self) -> NL43Snapshot:
        """Request DOD (Data Output Display) snapshot from device."""
        resp = await self._send_command("DOD?\r\n")

        # Validate response format
        if not resp:
            logger.warning(f"Empty response from DOD command on {self.device_key}")
            raise ValueError("Device returned empty response to DOD? command")

        # Remove leading $ prompt if present
        if resp.startswith("$"):
            resp = resp[1:].strip()

        parts = [p.strip() for p in resp.split(",") if p.strip() != ""]

        # DOD should return at least some data points
        if len(parts) < 2:
            logger.error(f"Malformed DOD response from {self.device_key}: {resp}")
            raise ValueError(f"Malformed DOD response: expected comma-separated values, got: {resp}")

        logger.info(f"Parsed {len(parts)} data points from DOD response")

        snap = NL43Snapshot(unit_id="", raw_payload=resp, measurement_state="Measure")

        # Parse known positions (based on NL43 communication guide)
        try:
            if len(parts) >= 1:
                snap.lp = parts[0]
            if len(parts) >= 2:
                snap.leq = parts[1]
            if len(parts) >= 4:
                snap.lmax = parts[3]
            if len(parts) >= 5:
                snap.lmin = parts[4]
            if len(parts) >= 11:
                snap.lpeak = parts[10]
        except (IndexError, ValueError) as e:
            logger.warning(f"Error parsing DOD data points: {e}")

        return snap

    async def start(self):
        await self._send_command("$Measure, Start\r\n")

    async def stop(self):
        await self._send_command("$Measure, Stop\r\n")
