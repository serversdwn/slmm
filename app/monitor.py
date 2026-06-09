"""
Per-device live monitor (fan-out hub).

ONE DOD poll loop per device, broadcast to many subscribers:
- browser WebSocket clients (live view) — they no longer each open their own
  device stream, so the NL43's single-connection limit stops causing the
  "second viewer sees nothing" contention.
- the alert evaluator (threshold alerts), which can keep a device's feed running
  even with no browser attached.
- persistence (each snapshot is written to NL43Status, like the poller does).

The device's one TCP connection is respected: every poll goes through the same
per-device lock + connection pool in services.py, so the monitor, the background
poller, and on-demand commands all serialize safely.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Optional, Set

from app.database import SessionLocal
from app.models import NL43Config, NL43Status
from app.services import NL43Client, persist_snapshot
from app.alerts import alert_evaluator

logger = logging.getLogger(__name__)

# Extra idle between DOD polls. The 1s device rate-limit already paces consecutive
# DOD? commands, so this just needs to be small — the rate-limit is the real floor.
MONITOR_POLL_INTERVAL = float(os.getenv("MONITOR_POLL_INTERVAL", "0.25"))

# How often to refresh the run state (Measure?). It changes rarely, so we cache it
# and skip that second rate-limited command on most polls — roughly halving the
# per-update latency (~2.5s -> ~1.3s).
MONITOR_STATE_REFRESH_S = float(os.getenv("MONITOR_STATE_REFRESH_S", "30"))

# Downsampled trail for the live-chart backfill: store one reading per
# TRAIL_SAMPLE_S and keep TRAIL_RETENTION_HOURS of it (pruned). Viewing only —
# reports use the device's FTP .rnd data, not this.
TRAIL_SAMPLE_S = float(os.getenv("MONITOR_TRAIL_SAMPLE_S", "60"))
TRAIL_RETENTION_HOURS = float(os.getenv("MONITOR_TRAIL_RETENTION_HOURS", "24"))

# If nothing has been broadcast in this many seconds (e.g. device offline and
# silent), send a keepalive frame so reverse proxies don't drop the idle WS.
MONITOR_HEARTBEAT_S = float(os.getenv("MONITOR_HEARTBEAT_S", "25"))


def _snapshot_payload(snap, unit_id: str, measurement_start_time) -> dict:
    """Build the broadcast payload — same shape as the DRD stream, but DOD-sourced
    so it carries ln1/ln2 (which DRD cannot)."""
    return {
        "unit_id": unit_id,
        "timestamp": datetime.utcnow().isoformat(),
        "measurement_state": snap.measurement_state,
        "measurement_start_time": measurement_start_time,
        "counter": snap.counter,
        "lp": snap.lp,
        "leq": snap.leq,
        "lmax": snap.lmax,
        "lmin": snap.lmin,
        "lpeak": snap.lpeak,
        "ln1": snap.ln1,
        "ln2": snap.ln2,
        "raw_payload": snap.raw_payload,
    }


class DeviceMonitor:
    """Owns a single DOD poll loop for one device and fans each snapshot out to
    all subscribers. Runs while it has at least one browser subscriber OR the
    server-side keep-alive (alerting) flag is set."""

    def __init__(self, unit_id: str):
        self.unit_id = unit_id
        self._subscribers: Set[asyncio.Queue] = set()
        self._keepalive = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._last_payload: Optional[dict] = None  # replayed to new subscribers
        self._consec_fail = 0
        self._reachable = True  # last broadcast reachability (for transition frames)
        self._cached_state: Optional[str] = None  # run state, refreshed periodically
        self._last_state_refresh = 0.0
        self._last_trail_store = 0.0  # downsample throttle for the backfill trail

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def _has_demand(self) -> bool:
        return bool(self._subscribers) or self._keepalive

    def _ensure_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5)
        async with self._lock:
            self._subscribers.add(q)
            # Replay the last frame so a client connecting mid-stream sees data
            # (or the current 'unreachable' state) immediately, not after a poll.
            if self._last_payload is not None:
                try:
                    q.put_nowait(self._last_payload)
                except asyncio.QueueFull:
                    pass
            self._ensure_task()
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    async def set_keepalive(self, on: bool) -> None:
        async with self._lock:
            self._keepalive = on
            if on:
                self._ensure_task()

    async def _run(self) -> None:
        logger.info(f"[MONITOR] {self.unit_id}: feed started")
        loop = asyncio.get_running_loop()
        last_send = loop.time()
        try:
            while self._has_demand():
                snap, mst = await self._poll_once()
                if snap is not None:
                    self._consec_fail = 0
                    self._reachable = True
                    payload = _snapshot_payload(snap, self.unit_id, mst)
                    payload["feed_status"] = "ok"
                    self._broadcast(payload)
                    last_send = loop.time()
                    try:
                        await alert_evaluator.evaluate(self.unit_id, snap)
                    except Exception as e:
                        logger.warning(f"[MONITOR] {self.unit_id}: alert eval failed: {e}")
                else:
                    # Tell clients the device went offline — once, on transition, after a
                    # few failures so a momentary blip doesn't flap the UI.
                    self._consec_fail += 1
                    if self._reachable and self._consec_fail >= 3:
                        self._reachable = False
                        self._broadcast({
                            "unit_id": self.unit_id,
                            "timestamp": datetime.utcnow().isoformat(),
                            "feed_status": "unreachable",
                        })
                        last_send = loop.time()

                # Heartbeat: during quiet/offline stretches, send a keepalive so an
                # idle WS isn't dropped by a reverse proxy. Not cached (new subscribers
                # should still get the last real frame, not a heartbeat).
                if loop.time() - last_send >= MONITOR_HEARTBEAT_S:
                    self._broadcast({
                        "unit_id": self.unit_id,
                        "timestamp": datetime.utcnow().isoformat(),
                        "feed_status": "ok" if self._reachable else "unreachable",
                        "heartbeat": True,
                    }, cache=False)
                    last_send = loop.time()

                await asyncio.sleep(MONITOR_POLL_INTERVAL)
        finally:
            logger.info(f"[MONITOR] {self.unit_id}: feed stopped")

    async def _poll_once(self):
        """One DOD poll: read, persist, return (snapshot, measurement_start_iso)."""
        db = SessionLocal()
        try:
            cfg = db.query(NL43Config).filter_by(unit_id=self.unit_id).first()
            if not cfg or not cfg.tcp_enabled:
                return None, None
            client = NL43Client(
                cfg.host, cfg.tcp_port,
                ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password,
                ftp_port=cfg.ftp_port or 21,
            )
            # Refresh the run state only every MONITOR_STATE_REFRESH_S; reuse the
            # cached state otherwise so most polls send just DOD? (one rate-limited
            # command) instead of DOD? + Measure?.
            now = asyncio.get_running_loop().time()
            refresh_state = (self._cached_state is None
                             or now - self._last_state_refresh >= MONITOR_STATE_REFRESH_S)
            snap = await client.request_dod(
                measurement_state=None if refresh_state else self._cached_state
            )
            if refresh_state:
                self._cached_state = snap.measurement_state
                self._last_state_refresh = now
            snap.unit_id = self.unit_id
            persist_snapshot(snap, db)
            db.commit()
            # Append to the downsampled backfill trail (~one row per TRAIL_SAMPLE_S).
            if now - self._last_trail_store >= TRAIL_SAMPLE_S:
                self._last_trail_store = now
                self._store_trail(snap, db)
            status = db.query(NL43Status).filter_by(unit_id=self.unit_id).first()
            mst = (status.measurement_start_time.isoformat()
                   if status and status.measurement_start_time else None)
            return snap, mst
        except Exception as e:
            logger.warning(f"[MONITOR] {self.unit_id}: poll failed: {e}")
            return None, None
        finally:
            db.close()

    def _store_trail(self, snap, db) -> None:
        """Append one downsampled reading to the backfill trail and prune old rows."""
        from datetime import datetime, timedelta
        from app.models import NL43Reading
        try:
            db.add(NL43Reading(
                unit_id=self.unit_id, timestamp=datetime.utcnow(),
                lp=snap.lp, leq=snap.leq, lmax=snap.lmax, ln1=snap.ln1, ln2=snap.ln2,
            ))
            cutoff = datetime.utcnow() - timedelta(hours=TRAIL_RETENTION_HOURS)
            db.query(NL43Reading).filter(
                NL43Reading.unit_id == self.unit_id,
                NL43Reading.timestamp < cutoff,
            ).delete()
            db.commit()
        except Exception as e:
            logger.warning(f"[MONITOR] {self.unit_id}: trail store failed: {e}")

    def _broadcast(self, payload: dict, cache: bool = True) -> None:
        if cache:
            self._last_payload = payload  # replayed to new subscribers
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer — drop this frame rather than stall the whole feed.
                pass


class MonitorManager:
    """Registry of per-device monitors (one per unit_id)."""

    def __init__(self):
        self._monitors: Dict[str, DeviceMonitor] = {}
        self._lock = asyncio.Lock()

    async def get(self, unit_id: str) -> DeviceMonitor:
        async with self._lock:
            m = self._monitors.get(unit_id)
            if m is None:
                m = DeviceMonitor(unit_id)
                self._monitors[unit_id] = m
            return m

    def is_active(self, unit_id: str) -> bool:
        """True if this unit has a running monitor feed (so the background poller
        can skip it — the monitor already polls it more often)."""
        m = self._monitors.get(unit_id)
        return m is not None and m.running

    def status(self) -> dict:
        return {
            uid: {
                "running": m.running,
                "subscribers": m.subscriber_count(),
                "keepalive": m._keepalive,
            }
            for uid, m in self._monitors.items()
        }


# Module-level singleton
monitor_manager = MonitorManager()
