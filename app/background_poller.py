"""
Background polling service for NL43 devices.

This module provides continuous, automatic polling of configured NL43 devices
at configurable intervals. Status snapshots are persisted to the database
for fast API access without querying devices on every request.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import NL43Config, NL43Status
from app.services import NL43Client, persist_snapshot, sync_measurement_start_time_from_ftp
from app.device_logger import log_device_event, cleanup_old_logs

logger = logging.getLogger(__name__)


class BackgroundPoller:
    """
    Background task that continuously polls NL43 devices and updates status cache.

    Features:
    - Per-device configurable poll intervals (30 seconds to 6 hours)
    - Automatic offline detection (marks unreachable after 3 consecutive failures)
    - Dynamic sleep intervals based on device configurations
    - Graceful shutdown on application stop
    - Respects existing rate limiting (1-second minimum between commands)
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._logger = logger
        self._last_cleanup = None  # Track last log cleanup time

    async def start(self):
        """Start the background polling task."""
        if self._running:
            self._logger.warning("Background poller already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        self._logger.info("Background poller task created")

    async def stop(self):
        """Gracefully stop the background polling task."""
        if not self._running:
            return

        self._logger.info("Stopping background poller...")
        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._logger.warning("Background poller task did not stop gracefully, cancelling...")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        self._logger.info("Background poller stopped")

    async def _poll_loop(self):
        """Main polling loop that runs continuously."""
        self._logger.info("Background polling loop started")

        while self._running:
            try:
                await self._poll_all_devices()
            except Exception as e:
                self._logger.error(f"Error in poll loop: {e}", exc_info=True)

            # Run log cleanup once per hour
            try:
                now = datetime.utcnow()
                if self._last_cleanup is None or (now - self._last_cleanup).total_seconds() > 3600:
                    cleanup_old_logs()
                    self._last_cleanup = now
            except Exception as e:
                self._logger.warning(f"Log cleanup failed: {e}")

            # Calculate dynamic sleep interval
            sleep_time = self._calculate_sleep_interval()
            self._logger.debug(f"Sleeping for {sleep_time} seconds until next poll cycle")

            # Sleep in small intervals to allow graceful shutdown
            for _ in range(int(sleep_time)):
                if not self._running:
                    break
                await asyncio.sleep(1)

        self._logger.info("Background polling loop exited")

    async def _poll_all_devices(self):
        """Poll all configured devices that are due for polling."""
        db: Session = SessionLocal()
        try:
            # Get all devices with TCP and polling enabled
            configs = db.query(NL43Config).filter_by(
                tcp_enabled=True,
                poll_enabled=True
            ).all()

            if not configs:
                self._logger.debug("No devices configured for polling")
                return

            self._logger.debug(f"Checking {len(configs)} devices for polling")
            now = datetime.utcnow()
            polled_count = 0

            for cfg in configs:
                if not self._running:
                    break

                # Get current status
                status = db.query(NL43Status).filter_by(unit_id=cfg.unit_id).first()

                # Check if device should be polled
                if self._should_poll(cfg, status, now):
                    await self._poll_device(cfg, db)
                    polled_count += 1
                else:
                    self._logger.debug(f"Skipping {cfg.unit_id} - interval not elapsed")

            if polled_count > 0:
                self._logger.info(f"Polled {polled_count}/{len(configs)} devices")

        finally:
            db.close()

    def _should_poll(self, cfg: NL43Config, status: Optional[NL43Status], now: datetime) -> bool:
        """
        Determine if a device should be polled based on interval and last poll time.

        Args:
            cfg: Device configuration
            status: Current device status (may be None if never polled)
            now: Current UTC timestamp

        Returns:
            True if device should be polled, False otherwise
        """
        # If never polled before, poll now
        if not status or not status.last_poll_attempt:
            self._logger.debug(f"Device {cfg.unit_id} never polled, polling now")
            return True

        # Calculate elapsed time since last poll attempt
        interval = cfg.poll_interval_seconds or 60
        elapsed = (now - status.last_poll_attempt).total_seconds()

        should_poll = elapsed >= interval

        if should_poll:
            self._logger.debug(
                f"Device {cfg.unit_id} due for polling: {elapsed:.1f}s elapsed, interval={interval}s"
            )

        return should_poll

    async def _poll_device(self, cfg: NL43Config, db: Session):
        """
        Poll a single device and update its status in the database.

        Args:
            cfg: Device configuration
            db: Database session
        """
        unit_id = cfg.unit_id
        self._logger.info(f"Polling device {unit_id} at {cfg.host}:{cfg.tcp_port}")

        # Get or create status record
        status = db.query(NL43Status).filter_by(unit_id=unit_id).first()
        if not status:
            status = NL43Status(unit_id=unit_id)
            db.add(status)

        # Update last_poll_attempt immediately
        status.last_poll_attempt = datetime.utcnow()
        db.commit()

        # Create client and attempt to poll
        client = NL43Client(
            cfg.host,
            cfg.tcp_port,
            timeout=5.0,
            ftp_username=cfg.ftp_username,
            ftp_password=cfg.ftp_password,
            ftp_port=cfg.ftp_port or 21
        )

        try:
            # Send DOD? command to get device status
            snap = await client.request_dod()
            snap.unit_id = unit_id

            # Success - persist snapshot and reset failure counter
            persist_snapshot(snap, db)

            status.is_reachable = True
            status.consecutive_failures = 0
            status.last_success = datetime.utcnow()
            status.last_error = None

            db.commit()
            self._logger.info(f"✓ Successfully polled {unit_id}")

            # Log to device log
            log_device_event(
                unit_id, "INFO", "POLL",
                f"Poll success: state={snap.measurement_state}, Leq={snap.leq}, Lp={snap.lp}",
                db
            )

            # Check if device is measuring but has no start time recorded
            # This happens if measurement was started before SLMM began polling
            # or after a service restart
            status = db.query(NL43Status).filter_by(unit_id=unit_id).first()

            # Reset the sync flag when measurement stops (so next measurement can sync)
            if status and status.measurement_state != "Start":
                if status.start_time_sync_attempted:
                    status.start_time_sync_attempted = False
                    db.commit()
                    self._logger.debug(f"Reset FTP sync flag for {unit_id} (measurement stopped)")
                    log_device_event(unit_id, "DEBUG", "STATE", "Measurement stopped, reset FTP sync flag", db)

            # Attempt FTP sync if:
            # - Device is measuring
            # - No start time recorded
            # - FTP sync not already attempted for this measurement
            # - FTP is configured
            if (status and
                status.measurement_state == "Start" and
                status.measurement_start_time is None and
                not status.start_time_sync_attempted and
                cfg.ftp_enabled and
                cfg.ftp_username and
                cfg.ftp_password):

                self._logger.info(
                    f"Device {unit_id} is measuring but has no start time - "
                    f"attempting FTP sync"
                )
                log_device_event(unit_id, "INFO", "SYNC", "Attempting FTP sync for measurement start time", db)

                # Mark that we attempted sync (prevents repeated attempts on failure)
                status.start_time_sync_attempted = True
                db.commit()

                try:
                    synced = await sync_measurement_start_time_from_ftp(
                        unit_id=unit_id,
                        host=cfg.host,
                        tcp_port=cfg.tcp_port,
                        ftp_port=cfg.ftp_port or 21,
                        ftp_username=cfg.ftp_username,
                        ftp_password=cfg.ftp_password,
                        db=db
                    )
                    if synced:
                        self._logger.info(f"✓ FTP sync succeeded for {unit_id}")
                        log_device_event(unit_id, "INFO", "SYNC", "FTP sync succeeded - measurement start time updated", db)
                    else:
                        self._logger.warning(f"FTP sync returned False for {unit_id}")
                        log_device_event(unit_id, "WARNING", "SYNC", "FTP sync returned False", db)
                except Exception as sync_err:
                    self._logger.warning(
                        f"FTP sync failed for {unit_id}: {sync_err}"
                    )
                    log_device_event(unit_id, "ERROR", "SYNC", f"FTP sync failed: {sync_err}", db)

        except Exception as e:
            # Failure - increment counter and potentially mark offline
            status.consecutive_failures += 1
            error_msg = str(e)[:500]  # Truncate to prevent bloat
            status.last_error = error_msg

            # Mark unreachable after 3 consecutive failures
            if status.consecutive_failures >= 3:
                if status.is_reachable:  # Only log transition
                    self._logger.warning(
                        f"Device {unit_id} marked unreachable after {status.consecutive_failures} failures: {error_msg}"
                    )
                    log_device_event(unit_id, "ERROR", "POLL", f"Device marked UNREACHABLE after {status.consecutive_failures} failures: {error_msg}", db)
                status.is_reachable = False
            else:
                self._logger.warning(
                    f"Poll failed for {unit_id} (attempt {status.consecutive_failures}/3): {error_msg}"
                )
                log_device_event(unit_id, "WARNING", "POLL", f"Poll failed (attempt {status.consecutive_failures}/3): {error_msg}", db)

            db.commit()

    def _calculate_sleep_interval(self) -> int:
        """
        Calculate the next sleep interval based on all device poll intervals.

        Returns a dynamic sleep time that ensures responsive polling:
        - Minimum 30 seconds (prevents tight loops)
        - Maximum 300 seconds / 5 minutes (ensures reasonable responsiveness for long intervals)
        - Generally half the minimum device interval

        Returns:
            Sleep interval in seconds
        """
        db: Session = SessionLocal()
        try:
            configs = db.query(NL43Config).filter_by(
                tcp_enabled=True,
                poll_enabled=True
            ).all()

            if not configs:
                return 60  # Default sleep when no devices configured

            # Get all intervals
            intervals = [cfg.poll_interval_seconds or 60 for cfg in configs]
            min_interval = min(intervals)

            # Use half the minimum interval, but cap between 30-300 seconds
            # This allows longer sleep times when polling intervals are long (e.g., hourly)
            sleep_time = max(30, min(300, min_interval // 2))

            return sleep_time

        finally:
            db.close()


# Global singleton instance
poller = BackgroundPoller()
