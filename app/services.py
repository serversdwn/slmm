"""
NL43 TCP connector and snapshot persistence.

Implements simple per-request TCP calls to avoid long-lived socket complexity.
Extend to pooled connections/DRD streaming later.
"""

import asyncio
import contextlib
import logging
import time
import os
import zipfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from ftplib import FTP
from pathlib import Path

from app.models import NL43Status

logger = logging.getLogger(__name__)

# Configurable timezone offset
# Set via environment variable TIMEZONE_OFFSET (hours from UTC)
# Default: -5 (EST - Eastern Standard Time, UTC-5)
# Examples: -5 for EST, -4 for EDT, 0 for UTC, +1 for CET
TIMEZONE_OFFSET_HOURS = float(os.getenv("TIMEZONE_OFFSET", "-5"))
TIMEZONE_OFFSET = timedelta(hours=TIMEZONE_OFFSET_HOURS)
TIMEZONE_NAME = os.getenv("TIMEZONE_NAME", f"UTC{TIMEZONE_OFFSET_HOURS:+.0f}")

logger.info(f"Using timezone: {TIMEZONE_NAME} (UTC{TIMEZONE_OFFSET_HOURS:+.0f})")


@dataclass
class NL43Snapshot:
    unit_id: str
    measurement_state: str = "unknown"
    counter: Optional[str] = None  # d0: Measurement interval counter (1-600)
    lp: Optional[str] = None    # Instantaneous sound pressure level
    leq: Optional[str] = None   # Equivalent continuous sound level
    lmax: Optional[str] = None  # Maximum level
    lmin: Optional[str] = None  # Minimum level
    lpeak: Optional[str] = None  # Peak level
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

        # Track measurement start time by detecting state transition
        previous_state = row.measurement_state
        new_state = s.measurement_state

        logger.info(f"State transition check for {s.unit_id}: '{previous_state}' -> '{new_state}'")

        # Device returns "Start" when measuring, "Stop" when stopped
        # Normalize to previous behavior for backward compatibility
        is_measuring = new_state == "Start"
        was_measuring = previous_state == "Start"

        if not was_measuring and is_measuring:
            # Measurement just started - record the start time
            row.measurement_start_time = datetime.utcnow()
            logger.info(f"✓ Measurement started on {s.unit_id} at {row.measurement_start_time}")
            # Log state change (lazy import to avoid circular dependency)
            try:
                from app.device_logger import log_device_event
                log_device_event(s.unit_id, "INFO", "STATE", f"Measurement STARTED at {row.measurement_start_time}", db)
            except Exception:
                pass
        elif was_measuring and not is_measuring:
            # Measurement stopped - clear the start time
            row.measurement_start_time = None
            logger.info(f"✓ Measurement stopped on {s.unit_id}")
            # Log state change
            try:
                from app.device_logger import log_device_event
                log_device_event(s.unit_id, "INFO", "STATE", "Measurement STOPPED", db)
            except Exception:
                pass

        row.measurement_state = new_state
        row.counter = s.counter
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


async def sync_measurement_start_time_from_ftp(
    unit_id: str,
    host: str,
    tcp_port: int,
    ftp_port: int,
    ftp_username: str,
    ftp_password: str,
    db: Session
) -> bool:
    """
    Sync measurement start time from the FTP folder timestamp.

    This is called when SLMM detects a device is already measuring but doesn't
    have a recorded start time (e.g., after service restart or if measurement
    was started before SLMM began polling).

    The workflow:
    1. Disable FTP (reset)
    2. Enable FTP
    3. List NL-43 folder to get measurement folder timestamps
    4. Use the most recent folder's timestamp as the start time
    5. Update the database

    Args:
        unit_id: Device identifier
        host: Device IP/hostname
        tcp_port: TCP control port
        ftp_port: FTP port (usually 21)
        ftp_username: FTP username (usually "USER")
        ftp_password: FTP password (usually "0000")
        db: Database session

    Returns:
        True if sync succeeded, False otherwise
    """
    logger.info(f"[FTP-SYNC] Attempting to sync measurement start time for {unit_id} via FTP")

    client = NL43Client(
        host, tcp_port,
        ftp_username=ftp_username,
        ftp_password=ftp_password,
        ftp_port=ftp_port
    )

    try:
        # Step 1: Disable FTP to reset it
        logger.info(f"[FTP-SYNC] Step 1: Disabling FTP on {unit_id}")
        await client.disable_ftp()
        await asyncio.sleep(1.5)  # Wait for device to process

        # Step 2: Enable FTP
        logger.info(f"[FTP-SYNC] Step 2: Enabling FTP on {unit_id}")
        await client.enable_ftp()
        await asyncio.sleep(2.0)  # Wait for FTP server to start

        # Step 3: List NL-43 folder
        logger.info(f"[FTP-SYNC] Step 3: Listing /NL-43 folder on {unit_id}")
        files = await client.list_ftp_files("/NL-43")

        # Filter for directories only (measurement folders)
        folders = [f for f in files if f.get('is_dir', False)]

        if not folders:
            logger.warning(f"[FTP-SYNC] No measurement folders found on {unit_id}")
            return False

        # Sort by modified timestamp (newest first)
        folders.sort(key=lambda f: f.get('modified_timestamp', ''), reverse=True)

        latest_folder = folders[0]
        folder_name = latest_folder['name']
        logger.info(f"[FTP-SYNC] Found latest measurement folder: {folder_name}")

        # Step 4: Parse timestamp
        if 'modified_timestamp' in latest_folder and latest_folder['modified_timestamp']:
            timestamp_str = latest_folder['modified_timestamp']
            # Parse ISO format timestamp (already in UTC from SLMM FTP listing)
            start_time = datetime.fromisoformat(timestamp_str.replace('Z', ''))

            # Step 5: Update database
            status = db.query(NL43Status).filter_by(unit_id=unit_id).first()
            if status:
                old_time = status.measurement_start_time
                status.measurement_start_time = start_time
                db.commit()

                logger.info(f"[FTP-SYNC] ✓ Successfully synced start time for {unit_id}")
                logger.info(f"[FTP-SYNC]   Folder: {folder_name}")
                logger.info(f"[FTP-SYNC]   Old start time: {old_time}")
                logger.info(f"[FTP-SYNC]   New start time: {start_time}")
                return True
            else:
                logger.warning(f"[FTP-SYNC] Status record not found for {unit_id}")
                return False
        else:
            logger.warning(f"[FTP-SYNC] Could not parse timestamp from folder {folder_name}")
            return False

    except Exception as e:
        logger.error(f"[FTP-SYNC] Failed to sync start time for {unit_id}: {e}")
        return False


# Rate limiting: NL43 requires ≥1 second between commands
_last_command_time = {}
_rate_limit_lock = asyncio.Lock()

# Per-device connection locks: NL43 devices only support one TCP connection at a time
# This prevents concurrent connections from fighting for the device
_device_locks: Dict[str, asyncio.Lock] = {}
_device_locks_lock = asyncio.Lock()


async def _get_device_lock(device_key: str) -> asyncio.Lock:
    """Get or create a lock for a specific device."""
    async with _device_locks_lock:
        if device_key not in _device_locks:
            _device_locks[device_key] = asyncio.Lock()
        return _device_locks[device_key]


class NL43Client:
    def __init__(self, host: str, port: int, timeout: float = 5.0, ftp_username: str = None, ftp_password: str = None, ftp_port: int = 21):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.ftp_username = ftp_username or "USER"
        self.ftp_password = ftp_password or "0000"
        self.ftp_port = ftp_port
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
        """Send ASCII command to NL43 device via TCP.

        NL43 protocol returns two lines for query commands:
        Line 1: Result code (R+0000 for success, error codes otherwise)
        Line 2: Actual data (for query commands ending with '?')

        This method acquires a per-device lock to ensure only one TCP connection
        is active at a time (NL43 devices only support single connections).
        """
        # Acquire per-device lock to prevent concurrent connections
        device_lock = await _get_device_lock(self.device_key)
        async with device_lock:
            return await self._send_command_unlocked(cmd)

    async def _send_command_unlocked(self, cmd: str) -> str:
        """Internal: send command without acquiring device lock (lock must be held by caller)."""
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

            # Read first line (result code)
            first_line_data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=self.timeout)
            result_code = first_line_data.decode(errors="ignore").strip()

            # Remove leading $ prompt if present
            if result_code.startswith("$"):
                result_code = result_code[1:].strip()

            logger.info(f"Result code from {self.device_key}: {result_code}")

            # Check result code
            if result_code == "R+0000":
                # Success - for query commands, read the second line with actual data
                is_query = cmd.strip().endswith("?")
                if is_query:
                    data_line = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=self.timeout)
                    response = data_line.decode(errors="ignore").strip()
                    logger.debug(f"Data line from {self.device_key}: {response}")
                    return response
                else:
                    # Setting command - return success code
                    return result_code
            elif result_code == "R+0001":
                raise ValueError("Command error - device did not recognize command")
            elif result_code == "R+0002":
                raise ValueError("Parameter error - invalid parameter value")
            elif result_code == "R+0003":
                raise ValueError("Spec/type error - command not supported by this device model")
            elif result_code == "R+0004":
                raise ValueError("Status error - device is in wrong state for this command")
            else:
                raise ValueError(f"Unknown result code: {result_code}")

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
        """Request DOD (Data Output Display) snapshot from device.

        Returns parsed measurement data from the device display.
        """
        # _send_command now handles result code validation and returns the data line
        resp = await self._send_command("DOD?\r\n")

        # Validate response format
        if not resp:
            logger.warning(f"Empty data response from DOD command on {self.device_key}")
            raise ValueError("Device returned empty data for DOD? command")

        # Remove leading $ prompt if present (shouldn't be there after _send_command, but be safe)
        if resp.startswith("$"):
            resp = resp[1:].strip()

        parts = [p.strip() for p in resp.split(",") if p.strip() != ""]

        # DOD should return at least some data points
        if len(parts) < 2:
            logger.error(f"Malformed DOD data from {self.device_key}: {resp}")
            raise ValueError(f"Malformed DOD data: expected comma-separated values, got: {resp}")

        logger.info(f"Parsed {len(parts)} data points from DOD response")

        # Query actual measurement state (DOD doesn't include this information)
        try:
            measurement_state = await self.get_measurement_state()
        except Exception as e:
            logger.warning(f"Failed to get measurement state, defaulting to 'Measure': {e}")
            measurement_state = "Measure"

        snap = NL43Snapshot(unit_id="", raw_payload=resp, measurement_state=measurement_state)

        # Parse known positions (based on NL43 communication guide - DRD format)
        # DRD format: d0=counter, d1=Lp, d2=Leq, d3=Lmax, d4=Lmin, d5=Lpeak, d6=LIeq, ...
        try:
            # Capture d0 (counter) for timer synchronization
            if len(parts) >= 1:
                snap.counter = parts[0]  # d0: Measurement interval counter (1-600)
            if len(parts) >= 2:
                snap.lp = parts[1]     # d1: Instantaneous sound pressure level
            if len(parts) >= 3:
                snap.leq = parts[2]    # d2: Equivalent continuous sound level
            if len(parts) >= 4:
                snap.lmax = parts[3]   # d3: Maximum level
            if len(parts) >= 5:
                snap.lmin = parts[4]   # d4: Minimum level
            if len(parts) >= 6:
                snap.lpeak = parts[5]  # d5: Peak level
        except (IndexError, ValueError) as e:
            logger.warning(f"Error parsing DOD data points: {e}")

        return snap

    async def start(self):
        """Start measurement on the device.

        According to NL43 protocol: Measure,Start (no $ prefix, capitalized param)
        """
        await self._send_command("Measure,Start\r\n")

    async def stop(self):
        """Stop measurement on the device.

        According to NL43 protocol: Measure,Stop (no $ prefix, capitalized param)
        """
        await self._send_command("Measure,Stop\r\n")

    async def set_store_mode_manual(self):
        """Set the device to Manual Store mode.

        According to NL43 protocol: Store Mode,Manual sets manual storage mode
        """
        await self._send_command("Store Mode,Manual\r\n")
        logger.info(f"Store mode set to Manual on {self.device_key}")

    async def manual_store(self):
        """Manually store the current measurement data.

        According to NL43 protocol: Manual Store,Start executes storing
        Parameter p1="Start" executes the storage operation
        Device must be in Manual Store mode first
        """
        await self._send_command("Manual Store,Start\r\n")
        logger.info(f"Manual store executed on {self.device_key}")

    async def pause(self):
        """Pause the current measurement."""
        await self._send_command("Pause,On\r\n")
        logger.info(f"Measurement paused on {self.device_key}")

    async def resume(self):
        """Resume a paused measurement."""
        await self._send_command("Pause,Off\r\n")
        logger.info(f"Measurement resumed on {self.device_key}")

    async def reset(self):
        """Reset the measurement data."""
        await self._send_command("Reset\r\n")
        logger.info(f"Measurement data reset on {self.device_key}")

    async def get_measurement_state(self) -> str:
        """Get the current measurement state.

        Returns: "Start" if measuring, "Stop" if stopped
        """
        resp = await self._send_command("Measure?\r\n")
        state = resp.strip()
        logger.info(f"Measurement state on {self.device_key}: {state}")
        return state

    async def get_battery_level(self) -> str:
        """Get the battery level."""
        resp = await self._send_command("Battery Level?\r\n")
        logger.info(f"Battery level on {self.device_key}: {resp}")
        return resp.strip()

    async def get_clock(self) -> str:
        """Get the device clock time."""
        resp = await self._send_command("Clock?\r\n")
        logger.info(f"Clock on {self.device_key}: {resp}")
        return resp.strip()

    async def set_clock(self, datetime_str: str):
        """Set the device clock time.

        Args:
            datetime_str: Time in format YYYY/MM/DD,HH:MM:SS or YYYY/MM/DD HH:MM:SS
        """
        # Device expects format: Clock,YYYY/MM/DD HH:MM:SS (space between date and time)
        # Replace comma with space if present to normalize format
        normalized = datetime_str.replace(',', ' ', 1)
        await self._send_command(f"Clock,{normalized}\r\n")
        logger.info(f"Clock set on {self.device_key} to {normalized}")

    async def get_frequency_weighting(self, channel: str = "Main") -> str:
        """Get frequency weighting (A, C, Z, etc.).

        Args:
            channel: Main, Sub1, Sub2, or Sub3
        """
        resp = await self._send_command(f"Frequency Weighting ({channel})?\r\n")
        logger.info(f"Frequency weighting ({channel}) on {self.device_key}: {resp}")
        return resp.strip()

    async def set_frequency_weighting(self, weighting: str, channel: str = "Main"):
        """Set frequency weighting.

        Args:
            weighting: A, C, or Z
            channel: Main, Sub1, Sub2, or Sub3
        """
        await self._send_command(f"Frequency Weighting ({channel}),{weighting}\r\n")
        logger.info(f"Frequency weighting ({channel}) set to {weighting} on {self.device_key}")

    async def get_time_weighting(self, channel: str = "Main") -> str:
        """Get time weighting (F, S, I).

        Args:
            channel: Main, Sub1, Sub2, or Sub3
        """
        resp = await self._send_command(f"Time Weighting ({channel})?\r\n")
        logger.info(f"Time weighting ({channel}) on {self.device_key}: {resp}")
        return resp.strip()

    async def set_time_weighting(self, weighting: str, channel: str = "Main"):
        """Set time weighting.

        Args:
            weighting: F (Fast), S (Slow), or I (Impulse)
            channel: Main, Sub1, Sub2, or Sub3
        """
        await self._send_command(f"Time Weighting ({channel}),{weighting}\r\n")
        logger.info(f"Time weighting ({channel}) set to {weighting} on {self.device_key}")

    async def request_dlc(self) -> dict:
        """Request DLC (Data Last Calculation) - final stored measurement results.

        This retrieves the complete calculation results from the last/current measurement,
        including all statistical data. Similar to DOD but for final results.

        Returns:
            Dict with parsed DLC data
        """
        resp = await self._send_command("DLC?\r\n")
        logger.info(f"DLC data received from {self.device_key}: {resp[:100]}...")

        # Parse DLC response - similar format to DOD
        # The exact format depends on device configuration
        # For now, return raw data - can be enhanced based on actual response format
        return {
            "raw_data": resp.strip(),
            "device_key": self.device_key,
        }

    async def sleep(self):
        """Put the device into sleep mode to conserve battery.

        Sleep mode is useful for battery conservation between scheduled measurements.
        Device can be woken up remotely via TCP command or by pressing a button.
        """
        await self._send_command("Sleep Mode,On\r\n")
        logger.info(f"Device {self.device_key} entering sleep mode")

    async def wake(self):
        """Wake the device from sleep mode.

        Note: This may not work if the device is in deep sleep.
        Physical button press might be required in some cases.
        """
        await self._send_command("Sleep Mode,Off\r\n")
        logger.info(f"Device {self.device_key} waking from sleep mode")

    async def get_sleep_status(self) -> str:
        """Get the current sleep mode status."""
        resp = await self._send_command("Sleep Mode?\r\n")
        logger.info(f"Sleep mode status on {self.device_key}: {resp}")
        return resp.strip()

    async def stream_drd(self, callback):
        """Stream continuous DRD output from the device.

        Opens a persistent connection and streams DRD data lines.
        Calls the provided callback function with each parsed snapshot.

        Args:
            callback: Async function that receives NL43Snapshot objects

        The stream continues until an exception occurs or the connection is closed.
        Send SUB character (0x1A) to stop the stream.

        NOTE: This method holds the device lock for the entire duration of streaming,
        blocking other commands to this device. This is intentional since NL43 devices
        only support one TCP connection at a time.
        """
        # Acquire per-device lock - held for entire streaming session
        device_lock = await _get_device_lock(self.device_key)
        async with device_lock:
            await self._enforce_rate_limit()

            logger.info(f"Starting DRD stream for {self.device_key}")

            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"DRD stream connection timeout to {self.device_key}")
                raise ConnectionError(f"Failed to connect to device at {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"DRD stream connection failed to {self.device_key}: {e}")
                raise ConnectionError(f"Failed to connect to device: {str(e)}")

            try:
                # Start DRD streaming
                writer.write(b"DRD?\r\n")
                await writer.drain()

                # Read initial result code
                first_line_data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=self.timeout)
                result_code = first_line_data.decode(errors="ignore").strip()

                if result_code.startswith("$"):
                    result_code = result_code[1:].strip()

                logger.debug(f"DRD stream result code from {self.device_key}: {result_code}")

                if result_code != "R+0000":
                    raise ValueError(f"DRD stream failed to start: {result_code}")

                logger.info(f"DRD stream started successfully for {self.device_key}")

                # Continuously read data lines
                while True:
                    try:
                        line_data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=30.0)
                        line = line_data.decode(errors="ignore").strip()

                        if not line:
                            continue

                        # Remove leading $ if present
                        if line.startswith("$"):
                            line = line[1:].strip()

                        # Parse the DRD data (same format as DOD)
                        parts = [p.strip() for p in line.split(",") if p.strip() != ""]

                        if len(parts) < 2:
                            logger.warning(f"Malformed DRD data from {self.device_key}: {line}")
                            continue

                        snap = NL43Snapshot(unit_id="", raw_payload=line, measurement_state="Measure")

                        # Parse known positions (DRD format - same as DOD)
                        # DRD format: d0=counter, d1=Lp, d2=Leq, d3=Lmax, d4=Lmin, d5=Lpeak, d6=LIeq, ...
                        try:
                            # Capture d0 (counter) for timer synchronization
                            if len(parts) >= 1:
                                snap.counter = parts[0]  # d0: Measurement interval counter (1-600)
                            if len(parts) >= 2:
                                snap.lp = parts[1]     # d1: Instantaneous sound pressure level
                            if len(parts) >= 3:
                                snap.leq = parts[2]    # d2: Equivalent continuous sound level
                            if len(parts) >= 4:
                                snap.lmax = parts[3]   # d3: Maximum level
                            if len(parts) >= 5:
                                snap.lmin = parts[4]   # d4: Minimum level
                            if len(parts) >= 6:
                                snap.lpeak = parts[5]  # d5: Peak level
                        except (IndexError, ValueError) as e:
                            logger.warning(f"Error parsing DRD data points: {e}")

                        # Call the callback with the snapshot
                        await callback(snap)

                    except asyncio.TimeoutError:
                        logger.warning(f"DRD stream timeout (no data for 30s) from {self.device_key}")
                        break
                    except asyncio.IncompleteReadError:
                        logger.info(f"DRD stream closed by device {self.device_key}")
                        break

            finally:
                # Send SUB character to stop streaming
                try:
                    writer.write(b"\x1A")
                    await writer.drain()
                except Exception:
                    pass

                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

                logger.info(f"DRD stream ended for {self.device_key}")

    async def set_measurement_time(self, preset: str):
        """Set measurement time preset.

        Args:
            preset: Time preset (10s, 1m, 5m, 10m, 15m, 30m, 1h, 8h, 24h, or custom like "00:05:30")
        """
        await self._send_command(f"Measurement Time Preset Manual,{preset}\r\n")
        logger.info(f"Set measurement time to {preset} on {self.device_key}")

    async def get_measurement_time(self) -> str:
        """Get current measurement time preset.

        Returns: Current time preset setting
        """
        resp = await self._send_command("Measurement Time Preset Manual?\r\n")
        return resp.strip()

    async def set_leq_interval(self, preset: str):
        """Set Leq calculation interval preset.

        Args:
            preset: Interval preset (Off, 10s, 1m, 5m, 10m, 15m, 30m, 1h, 8h, 24h, or custom like "00:05:30")
        """
        await self._send_command(f"Leq Calculation Interval Preset,{preset}\r\n")
        logger.info(f"Set Leq interval to {preset} on {self.device_key}")

    async def get_leq_interval(self) -> str:
        """Get current Leq calculation interval preset.

        Returns: Current interval preset setting
        """
        resp = await self._send_command("Leq Calculation Interval Preset?\r\n")
        return resp.strip()

    async def set_lp_interval(self, preset: str):
        """Set Lp store interval.

        Args:
            preset: Store interval (Off, 10ms, 25ms, 100ms, 200ms, 1s)
        """
        await self._send_command(f"Lp Store Interval,{preset}\r\n")
        logger.info(f"Set Lp interval to {preset} on {self.device_key}")

    async def get_lp_interval(self) -> str:
        """Get current Lp store interval.

        Returns: Current store interval setting
        """
        resp = await self._send_command("Lp Store Interval?\r\n")
        return resp.strip()

    async def set_index_number(self, index: int):
        """Set index number for file numbering (Store Name).

        Args:
            index: Index number (0000-9999)
        """
        if not 0 <= index <= 9999:
            raise ValueError("Index must be between 0000 and 9999")
        await self._send_command(f"Store Name,{index:04d}\r\n")
        logger.info(f"Set store name (index) to {index:04d} on {self.device_key}")

    async def get_index_number(self) -> str:
        """Get current index number (Store Name).

        Returns: Current index number
        """
        resp = await self._send_command("Store Name?\r\n")
        return resp.strip()

    async def get_overwrite_status(self) -> str:
        """Check if saved data exists at current store target.

        This command checks whether saved data exists in the set store target
        (store mode / store name / store address). Use this before storing
        to prevent accidentally overwriting data.

        Returns:
            "None" - No data exists (safe to store)
            "Exist" - Data exists (would overwrite)
        """
        resp = await self._send_command("Overwrite?\r\n")
        return resp.strip()

    async def get_all_settings(self) -> dict:
        """Query all device settings for verification.

        Returns: Dictionary with all current device settings
        """
        settings = {}

        # Measurement settings
        try:
            settings["measurement_state"] = await self.get_measurement_state()
        except Exception as e:
            settings["measurement_state"] = f"Error: {e}"

        try:
            settings["frequency_weighting"] = await self.get_frequency_weighting()
        except Exception as e:
            settings["frequency_weighting"] = f"Error: {e}"

        try:
            settings["time_weighting"] = await self.get_time_weighting()
        except Exception as e:
            settings["time_weighting"] = f"Error: {e}"

        # Timing/interval settings
        try:
            settings["measurement_time"] = await self.get_measurement_time()
        except Exception as e:
            settings["measurement_time"] = f"Error: {e}"

        try:
            settings["leq_interval"] = await self.get_leq_interval()
        except Exception as e:
            settings["leq_interval"] = f"Error: {e}"

        try:
            settings["lp_interval"] = await self.get_lp_interval()
        except Exception as e:
            settings["lp_interval"] = f"Error: {e}"

        try:
            settings["index_number"] = await self.get_index_number()
        except Exception as e:
            settings["index_number"] = f"Error: {e}"

        # Device info
        try:
            settings["battery_level"] = await self.get_battery_level()
        except Exception as e:
            settings["battery_level"] = f"Error: {e}"

        try:
            settings["clock"] = await self.get_clock()
        except Exception as e:
            settings["clock"] = f"Error: {e}"

        # Sleep mode
        try:
            settings["sleep_mode"] = await self.get_sleep_status()
        except Exception as e:
            settings["sleep_mode"] = f"Error: {e}"

        # FTP status
        try:
            settings["ftp_status"] = await self.get_ftp_status()
        except Exception as e:
            settings["ftp_status"] = f"Error: {e}"

        logger.info(f"Retrieved all settings for {self.device_key}")
        return settings

    async def enable_ftp(self):
        """Enable FTP server on the device.

        According to NL43 protocol: FTP,On enables the FTP server
        """
        await self._send_command("FTP,On\r\n")
        logger.info(f"FTP enabled on {self.device_key}")

    async def disable_ftp(self):
        """Disable FTP server on the device.

        According to NL43 protocol: FTP,Off disables the FTP server
        """
        await self._send_command("FTP,Off\r\n")
        logger.info(f"FTP disabled on {self.device_key}")

    async def get_ftp_status(self) -> str:
        """Query FTP server status on the device.

        Returns: "On" or "Off"
        """
        resp = await self._send_command("FTP?\r\n")
        logger.info(f"FTP status on {self.device_key}: {resp}")
        return resp.strip()

    async def list_ftp_files(self, remote_path: str = "/") -> List[dict]:
        """List files on the device via FTP.

        Args:
            remote_path: Directory path on the device (default: root)

        Returns:
            List of file info dicts with 'name', 'size', 'modified', 'is_dir'
        """
        logger.info(f"[FTP-LIST] === Starting FTP file listing for {self.device_key} ===")
        logger.info(f"[FTP-LIST] Target path: {remote_path}")
        logger.info(f"[FTP-LIST] Host: {self.host}, Port: {self.ftp_port}, User: {self.ftp_username}")

        def _list_ftp_sync():
            """Synchronous FTP listing using ftplib for NL-43 devices."""
            import socket
            ftp = FTP()
            ftp.set_debuglevel(2)  # Enable FTP debugging
            try:
                # Phase 1: TCP Connection
                logger.info(f"[FTP-LIST] Phase 1: Initiating TCP connection to {self.host}:{self.ftp_port}")
                logger.info(f"[FTP-LIST] Connection timeout: 10 seconds")
                try:
                    ftp.connect(self.host, self.ftp_port, timeout=10)
                    logger.info(f"[FTP-LIST] Phase 1 SUCCESS: TCP connection established")
                    # Log socket details
                    try:
                        local_addr = ftp.sock.getsockname()
                        remote_addr = ftp.sock.getpeername()
                        logger.info(f"[FTP-LIST] Control channel - Local: {local_addr[0]}:{local_addr[1]}, Remote: {remote_addr[0]}:{remote_addr[1]}")
                    except Exception as sock_info_err:
                        logger.warning(f"[FTP-LIST] Could not get socket info: {sock_info_err}")
                except socket.timeout as timeout_err:
                    logger.error(f"[FTP-LIST] Phase 1 FAILED: TCP connection TIMEOUT after 10s to {self.host}:{self.ftp_port}")
                    logger.error(f"[FTP-LIST] This means the device is unreachable or FTP port is blocked/closed")
                    raise
                except socket.error as sock_err:
                    logger.error(f"[FTP-LIST] Phase 1 FAILED: Socket error to {self.host}:{self.ftp_port}")
                    logger.error(f"[FTP-LIST] Socket error: {type(sock_err).__name__}: {sock_err}, errno={getattr(sock_err, 'errno', 'N/A')}")
                    raise
                except Exception as conn_err:
                    logger.error(f"[FTP-LIST] Phase 1 FAILED: {type(conn_err).__name__}: {conn_err}")
                    raise

                # Phase 2: Authentication
                logger.info(f"[FTP-LIST] Phase 2: Authenticating as '{self.ftp_username}'")
                try:
                    ftp.login(self.ftp_username, self.ftp_password)
                    logger.info(f"[FTP-LIST] Phase 2 SUCCESS: Authentication successful")
                except Exception as auth_err:
                    logger.error(f"[FTP-LIST] Phase 2 FAILED: Auth error for user '{self.ftp_username}': {auth_err}")
                    raise

                # Phase 3: Set Active Mode
                logger.info(f"[FTP-LIST] Phase 3: Setting ACTIVE mode (PASV=False)")
                logger.info(f"[FTP-LIST] NOTE: Active mode requires the NL-43 device to connect BACK to this server on a data port")
                logger.info(f"[FTP-LIST] If firewall blocks incoming connections, data transfer will timeout")
                ftp.set_pasv(False)
                logger.info(f"[FTP-LIST] Phase 3 SUCCESS: Active mode enabled")

                # Phase 4: Change directory
                if remote_path != "/":
                    logger.info(f"[FTP-LIST] Phase 4: Changing to directory: {remote_path}")
                    try:
                        ftp.cwd(remote_path)
                        logger.info(f"[FTP-LIST] Phase 4 SUCCESS: Changed to {remote_path}")
                    except Exception as cwd_err:
                        logger.error(f"[FTP-LIST] Phase 4 FAILED: Could not change to '{remote_path}': {cwd_err}")
                        raise
                else:
                    logger.info(f"[FTP-LIST] Phase 4: Staying in root directory")

                # Phase 5: Get directory listing (THIS IS WHERE DATA CHANNEL IS USED)
                logger.info(f"[FTP-LIST] Phase 5: Sending LIST command (data channel required)")
                logger.info(f"[FTP-LIST] This step opens a data channel - device must connect back in active mode")
                files = []
                lines = []
                try:
                    ftp.retrlines('LIST', lines.append)
                    logger.info(f"[FTP-LIST] Phase 5 SUCCESS: LIST command completed, received {len(lines)} lines")
                except socket.timeout as list_timeout:
                    logger.error(f"[FTP-LIST] Phase 5 FAILED: DATA CHANNEL TIMEOUT during LIST command")
                    logger.error(f"[FTP-LIST] This usually means:")
                    logger.error(f"[FTP-LIST]   1. Firewall is blocking incoming data connections from the NL-43")
                    logger.error(f"[FTP-LIST]   2. NAT is preventing the device from connecting back")
                    logger.error(f"[FTP-LIST]   3. Network route between device and server is blocked")
                    logger.error(f"[FTP-LIST] In active FTP mode, the server sends PORT command with its IP:port,")
                    logger.error(f"[FTP-LIST] and the device initiates a connection TO the server for data transfer")
                    raise
                except Exception as list_err:
                    logger.error(f"[FTP-LIST] Phase 5 FAILED: Error during LIST: {type(list_err).__name__}: {list_err}")
                    raise

                for line in lines:
                    # Parse Unix-style ls output
                    parts = line.split(None, 8)
                    if len(parts) < 9:
                        continue

                    is_dir = parts[0].startswith('d')
                    size = int(parts[4]) if not is_dir else 0
                    name = parts[8]

                    # Skip . and ..
                    if name in ('.', '..'):
                        continue

                    # Parse modification time
                    # Format: "Jan 07 14:23" or "Dec 25 2025"
                    modified_str = f"{parts[5]} {parts[6]} {parts[7]}"
                    modified_timestamp = None
                    try:
                        from datetime import datetime
                        # Get current time in configured timezone for year comparison
                        now_local = datetime.utcnow() + TIMEZONE_OFFSET

                        # Try parsing with time (recent files: "Jan 07 14:23")
                        try:
                            dt = datetime.strptime(modified_str, "%b %d %H:%M")
                            # Add current year since it's not in the format
                            # Assume FTP timestamp is in the configured timezone
                            dt = dt.replace(year=now_local.year)

                            # If the resulting date is in the future, it's actually from last year
                            if dt > now_local:
                                dt = dt.replace(year=dt.year - 1)

                            # Convert local timezone to UTC
                            dt_utc = dt - TIMEZONE_OFFSET

                            modified_timestamp = dt_utc.isoformat()
                        except ValueError:
                            # Try parsing with year (older files: "Dec 25 2025")
                            dt = datetime.strptime(modified_str, "%b %d %Y")
                            # Convert local timezone to UTC
                            dt_utc = dt - TIMEZONE_OFFSET
                            modified_timestamp = dt_utc.isoformat()
                    except Exception as e:
                        logger.warning(f"Failed to parse timestamp '{modified_str}': {e}")

                    file_info = {
                        "name": name,
                        "path": f"{remote_path.rstrip('/')}/{name}",
                        "size": size,
                        "modified": modified_str,  # Keep original string
                        "modified_timestamp": modified_timestamp,  # Add parsed timestamp
                        "is_dir": is_dir,
                    }
                    files.append(file_info)
                    logger.debug(f"Found file: {file_info}")

                logger.info(f"[FTP-LIST] === COMPLETE: Found {len(files)} files/directories on {self.device_key} ===")
                return files

            finally:
                logger.info(f"[FTP-LIST] Closing FTP connection")
                try:
                    ftp.quit()
                    logger.info(f"[FTP-LIST] FTP connection closed cleanly")
                except Exception as quit_err:
                    logger.warning(f"[FTP-LIST] Error during FTP quit (non-fatal): {quit_err}")

        try:
            # Run synchronous FTP in thread pool
            return await asyncio.to_thread(_list_ftp_sync)
        except Exception as e:
            logger.error(f"[FTP-LIST] === FAILED: {self.device_key} - {type(e).__name__}: {e} ===")
            import traceback
            logger.error(f"[FTP-LIST] Full traceback:\n{traceback.format_exc()}")
            raise ConnectionError(f"FTP connection failed: {str(e)}")

    async def download_ftp_file(self, remote_path: str, local_path: str):
        """Download a file from the device via FTP.

        Args:
            remote_path: Full path to file on the device
            local_path: Local path where file will be saved
        """
        logger.info(f"[FTP-DOWNLOAD] === Starting FTP download for {self.device_key} ===")
        logger.info(f"[FTP-DOWNLOAD] Remote path: {remote_path}")
        logger.info(f"[FTP-DOWNLOAD] Local path: {local_path}")
        logger.info(f"[FTP-DOWNLOAD] Host: {self.host}, Port: {self.ftp_port}, User: {self.ftp_username}")

        def _download_ftp_sync():
            """Synchronous FTP download using ftplib (supports active mode)."""
            import socket
            ftp = FTP()
            ftp.set_debuglevel(2)  # Enable verbose FTP debugging
            try:
                # Phase 1: TCP Connection
                logger.info(f"[FTP-DOWNLOAD] Phase 1: Connecting to {self.host}:{self.ftp_port}")
                try:
                    ftp.connect(self.host, self.ftp_port, timeout=10)
                    logger.info(f"[FTP-DOWNLOAD] Phase 1 SUCCESS: TCP connection established")
                    try:
                        local_addr = ftp.sock.getsockname()
                        remote_addr = ftp.sock.getpeername()
                        logger.info(f"[FTP-DOWNLOAD] Control channel - Local: {local_addr[0]}:{local_addr[1]}, Remote: {remote_addr[0]}:{remote_addr[1]}")
                    except Exception as sock_info_err:
                        logger.warning(f"[FTP-DOWNLOAD] Could not get socket info: {sock_info_err}")
                except socket.timeout as timeout_err:
                    logger.error(f"[FTP-DOWNLOAD] Phase 1 FAILED: TCP connection TIMEOUT to {self.host}:{self.ftp_port}")
                    raise
                except socket.error as sock_err:
                    logger.error(f"[FTP-DOWNLOAD] Phase 1 FAILED: Socket error: {type(sock_err).__name__}: {sock_err}")
                    raise
                except Exception as conn_err:
                    logger.error(f"[FTP-DOWNLOAD] Phase 1 FAILED: {type(conn_err).__name__}: {conn_err}")
                    raise

                # Phase 2: Authentication
                logger.info(f"[FTP-DOWNLOAD] Phase 2: Authenticating as '{self.ftp_username}'")
                try:
                    ftp.login(self.ftp_username, self.ftp_password)
                    logger.info(f"[FTP-DOWNLOAD] Phase 2 SUCCESS: Authentication successful")
                except Exception as auth_err:
                    logger.error(f"[FTP-DOWNLOAD] Phase 2 FAILED: Auth error: {auth_err}")
                    raise

                # Phase 3: Set Active Mode
                logger.info(f"[FTP-DOWNLOAD] Phase 3: Setting ACTIVE mode (PASV=False)")
                ftp.set_pasv(False)
                logger.info(f"[FTP-DOWNLOAD] Phase 3 SUCCESS: Active mode enabled")

                # Phase 4: Download file (THIS IS WHERE DATA CHANNEL IS USED)
                logger.info(f"[FTP-DOWNLOAD] Phase 4: Starting RETR {remote_path}")
                logger.info(f"[FTP-DOWNLOAD] Data channel will be established - device connects back in active mode")
                try:
                    with open(local_path, 'wb') as f:
                        ftp.retrbinary(f'RETR {remote_path}', f.write)
                    import os
                    file_size = os.path.getsize(local_path)
                    logger.info(f"[FTP-DOWNLOAD] Phase 4 SUCCESS: Downloaded {file_size} bytes to {local_path}")
                except socket.timeout as dl_timeout:
                    logger.error(f"[FTP-DOWNLOAD] Phase 4 FAILED: DATA CHANNEL TIMEOUT during download")
                    logger.error(f"[FTP-DOWNLOAD] This usually means firewall/NAT is blocking the data connection")
                    raise
                except Exception as dl_err:
                    logger.error(f"[FTP-DOWNLOAD] Phase 4 FAILED: {type(dl_err).__name__}: {dl_err}")
                    raise

                logger.info(f"[FTP-DOWNLOAD] === COMPLETE: {remote_path} downloaded successfully ===")

            finally:
                logger.info(f"[FTP-DOWNLOAD] Closing FTP connection")
                try:
                    ftp.quit()
                    logger.info(f"[FTP-DOWNLOAD] FTP connection closed cleanly")
                except Exception as quit_err:
                    logger.warning(f"[FTP-DOWNLOAD] Error during FTP quit (non-fatal): {quit_err}")

        try:
            # Run synchronous FTP in thread pool
            await asyncio.to_thread(_download_ftp_sync)
        except Exception as e:
            logger.error(f"[FTP-DOWNLOAD] === FAILED: {self.device_key} - {type(e).__name__}: {e} ===")
            import traceback
            logger.error(f"[FTP-DOWNLOAD] Full traceback:\n{traceback.format_exc()}")
            raise ConnectionError(f"FTP download failed: {str(e)}")

    async def download_ftp_folder(self, remote_path: str, zip_path: str):
        """Download an entire folder from the device via FTP as a ZIP archive.

        Recursively downloads all files and subdirectories in the specified folder
        and packages them into a ZIP file. This is useful for downloading complete
        measurement sessions (e.g., Auto_0000 folders with all their contents).

        Args:
            remote_path: Full path to folder on the device (e.g., "/NL-43/Auto_0000")
            zip_path: Local path where the ZIP file will be saved
        """
        logger.info(f"[FTP-FOLDER] === Starting FTP folder download for {self.device_key} ===")
        logger.info(f"[FTP-FOLDER] Remote folder: {remote_path}")
        logger.info(f"[FTP-FOLDER] ZIP destination: {zip_path}")
        logger.info(f"[FTP-FOLDER] Host: {self.host}, Port: {self.ftp_port}, User: {self.ftp_username}")

        def _download_folder_sync():
            """Synchronous FTP folder download and ZIP creation."""
            import socket
            ftp = FTP()
            ftp.set_debuglevel(2)  # Enable verbose FTP debugging
            files_downloaded = 0
            folders_processed = 0

            # Create a temporary directory for downloaded files
            with tempfile.TemporaryDirectory() as temp_dir:
                try:
                    # Phase 1: Connect and authenticate
                    logger.info(f"[FTP-FOLDER] Phase 1: Connecting to {self.host}:{self.ftp_port}")
                    try:
                        ftp.connect(self.host, self.ftp_port, timeout=10)
                        logger.info(f"[FTP-FOLDER] Phase 1 SUCCESS: TCP connection established")
                        try:
                            local_addr = ftp.sock.getsockname()
                            remote_addr = ftp.sock.getpeername()
                            logger.info(f"[FTP-FOLDER] Control channel - Local: {local_addr[0]}:{local_addr[1]}, Remote: {remote_addr[0]}:{remote_addr[1]}")
                        except Exception as sock_info_err:
                            logger.warning(f"[FTP-FOLDER] Could not get socket info: {sock_info_err}")
                    except socket.timeout as timeout_err:
                        logger.error(f"[FTP-FOLDER] Phase 1 FAILED: TCP connection TIMEOUT")
                        raise
                    except Exception as conn_err:
                        logger.error(f"[FTP-FOLDER] Phase 1 FAILED: {type(conn_err).__name__}: {conn_err}")
                        raise

                    logger.info(f"[FTP-FOLDER] Authenticating as '{self.ftp_username}'")
                    ftp.login(self.ftp_username, self.ftp_password)
                    logger.info(f"[FTP-FOLDER] Authentication successful")

                    ftp.set_pasv(False)  # Force active mode
                    logger.info(f"[FTP-FOLDER] Active mode enabled (PASV=False)")

                    def download_recursive(ftp_path: str, local_path: str):
                        """Recursively download files and directories."""
                        nonlocal files_downloaded, folders_processed
                        folders_processed += 1
                        logger.info(f"[FTP-FOLDER] Processing folder #{folders_processed}: {ftp_path}")

                        # Create local directory
                        os.makedirs(local_path, exist_ok=True)

                        # List contents
                        try:
                            items = []
                            logger.info(f"[FTP-FOLDER] Changing to directory: {ftp_path}")
                            ftp.cwd(ftp_path)
                            logger.info(f"[FTP-FOLDER] Listing contents of {ftp_path}")
                            ftp.retrlines('LIST', items.append)
                            logger.info(f"[FTP-FOLDER] Found {len(items)} items in {ftp_path}")
                        except socket.timeout as list_timeout:
                            logger.error(f"[FTP-FOLDER] TIMEOUT listing {ftp_path} - data channel issue")
                            return
                        except Exception as e:
                            logger.error(f"[FTP-FOLDER] Failed to list {ftp_path}: {type(e).__name__}: {e}")
                            return

                        for item in items:
                            # Parse FTP LIST output (Unix-style)
                            parts = item.split(None, 8)
                            if len(parts) < 9:
                                continue

                            permissions = parts[0]
                            name = parts[8]

                            # Skip . and .. entries
                            if name in ['.', '..']:
                                continue

                            is_dir = permissions.startswith('d')
                            full_remote_path = f"{ftp_path}/{name}".replace('//', '/')
                            full_local_path = os.path.join(local_path, name)

                            if is_dir:
                                # Recursively download subdirectory
                                download_recursive(full_remote_path, full_local_path)
                            else:
                                # Download file
                                try:
                                    logger.info(f"[FTP-FOLDER] Downloading file #{files_downloaded + 1}: {full_remote_path}")
                                    with open(full_local_path, 'wb') as f:
                                        ftp.retrbinary(f'RETR {full_remote_path}', f.write)
                                    files_downloaded += 1
                                    file_size = os.path.getsize(full_local_path)
                                    logger.info(f"[FTP-FOLDER] Downloaded: {full_remote_path} ({file_size} bytes)")
                                except socket.timeout as dl_timeout:
                                    logger.error(f"[FTP-FOLDER] TIMEOUT downloading {full_remote_path}")
                                except Exception as e:
                                    logger.error(f"[FTP-FOLDER] Failed to download {full_remote_path}: {type(e).__name__}: {e}")

                    # Download entire folder structure
                    folder_name = os.path.basename(remote_path.rstrip('/'))
                    local_folder = os.path.join(temp_dir, folder_name)
                    download_recursive(remote_path, local_folder)

                    logger.info(f"[FTP-FOLDER] Download complete: {files_downloaded} files from {folders_processed} folders")

                    # Create ZIP archive
                    logger.info(f"[FTP-FOLDER] Creating ZIP archive: {zip_path}")
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(local_folder):
                            for file in files:
                                file_path = os.path.join(root, file)
                                # Calculate relative path for ZIP archive
                                arcname = os.path.relpath(file_path, temp_dir)
                                zipf.write(file_path, arcname)
                                logger.debug(f"[FTP-FOLDER] Added to ZIP: {arcname}")

                    zip_size = os.path.getsize(zip_path)
                    logger.info(f"[FTP-FOLDER] === COMPLETE: ZIP created ({zip_size} bytes) ===")

                finally:
                    logger.info(f"[FTP-FOLDER] Closing FTP connection")
                    try:
                        ftp.quit()
                        logger.info(f"[FTP-FOLDER] FTP connection closed cleanly")
                    except Exception as quit_err:
                        logger.warning(f"[FTP-FOLDER] Error during FTP quit (non-fatal): {quit_err}")

        try:
            # Run synchronous FTP folder download in thread pool
            await asyncio.to_thread(_download_folder_sync)
        except Exception as e:
            logger.error(f"[FTP-FOLDER] === FAILED: {self.device_key} - {type(e).__name__}: {e} ===")
            import traceback
            logger.error(f"[FTP-FOLDER] Full traceback:\n{traceback.format_exc()}")
            raise ConnectionError(f"FTP folder download failed: {str(e)}")

    # ========================================================================
    # Cycle Commands (for scheduled automation)
    # ========================================================================

    async def start_cycle(self, sync_clock: bool = True, max_index_attempts: int = 100) -> dict:
        """
        Execute complete start cycle for scheduled automation:
        1. Sync device clock to server time
        2. Find next safe index (increment, check overwrite, repeat if needed)
        3. Start measurement

        Args:
            sync_clock: Whether to sync device clock to server time (default: True)
            max_index_attempts: Maximum attempts to find an unused index (default: 100)

        Returns:
            dict with clock_synced, old_index, new_index, attempts_made, started
        """
        logger.info(f"[START-CYCLE] === Starting measurement cycle on {self.device_key} ===")

        result = {
            "clock_synced": False,
            "server_time": None,
            "old_index": None,
            "new_index": None,
            "attempts_made": 0,
            "started": False,
        }

        # Step 1: Sync clock to server time
        if sync_clock:
            # Use configured timezone
            server_now = datetime.now(timezone.utc) + TIMEZONE_OFFSET
            server_time = server_now.strftime("%Y/%m/%d %H:%M:%S")
            logger.info(f"[START-CYCLE] Step 1: Syncing clock to {server_time} ({TIMEZONE_NAME})")
            await self.set_clock(server_time)
            result["clock_synced"] = True
            result["server_time"] = server_time
            logger.info(f"[START-CYCLE] Clock synced successfully")
        else:
            logger.info(f"[START-CYCLE] Step 1: Skipping clock sync (sync_clock=False)")

        # Step 2: Find next safe index with overwrite protection
        logger.info(f"[START-CYCLE] Step 2: Finding safe index with overwrite protection")
        current_index_str = await self.get_index_number()
        current_index = int(current_index_str)
        result["old_index"] = current_index
        logger.info(f"[START-CYCLE] Current index: {current_index}")

        test_index = current_index + 1
        attempts = 0

        while attempts < max_index_attempts:
            test_index = test_index % 10000  # Wrap at 9999
            await self.set_index_number(test_index)
            attempts += 1

            # Check if this index is safe (no existing data)
            overwrite_status = await self.get_overwrite_status()
            logger.info(f"[START-CYCLE] Index {test_index:04d}: overwrite status = {overwrite_status}")

            if overwrite_status == "None":
                # Safe to use this index
                result["new_index"] = test_index
                result["attempts_made"] = attempts
                logger.info(f"[START-CYCLE] Found safe index {test_index:04d} after {attempts} attempt(s)")
                break

            # Data exists, try next index
            test_index += 1

            if test_index == current_index:
                # Wrapped around completely - all indices have data
                logger.error(f"[START-CYCLE] All indices have data! Device storage is full.")
                raise Exception("All indices have data. Download and clear device storage.")

        if result["new_index"] is None:
            logger.error(f"[START-CYCLE] Could not find empty index after {max_index_attempts} attempts")
            raise Exception(f"Could not find empty index after {max_index_attempts} attempts")

        # Step 3: Start measurement
        logger.info(f"[START-CYCLE] Step 3: Starting measurement")
        await self.start()
        result["started"] = True
        logger.info(f"[START-CYCLE] === Measurement started successfully ===")

        return result

    async def stop_cycle(self, download: bool = True, download_path: str = None) -> dict:
        """
        Execute complete stop cycle for scheduled automation:
        1. Stop measurement
        2. Enable FTP
        3. Download measurement folder (matching current index)
        4. Verify download succeeded

        Args:
            download: Whether to download measurement data (default: True)
            download_path: Custom path for ZIP file (default: data/downloads/{device_key}/Auto_XXXX.zip)

        Returns:
            dict with stopped, ftp_enabled, download_attempted, download_success, etc.
        """
        logger.info(f"[STOP-CYCLE] === Stopping measurement cycle on {self.device_key} ===")

        result = {
            "stopped": False,
            "ftp_enabled": False,
            "download_attempted": False,
            "download_success": False,
            "downloaded_folder": None,
            "local_path": None,
        }

        # Step 1: Stop measurement
        logger.info(f"[STOP-CYCLE] Step 1: Stopping measurement")
        await self.stop()
        result["stopped"] = True
        logger.info(f"[STOP-CYCLE] Measurement stopped")

        # Step 2: Reset FTP (disable then enable) to clear any stale state
        logger.info(f"[STOP-CYCLE] Step 2: Resetting FTP (disable then enable)")
        try:
            await self.disable_ftp()
            logger.info(f"[STOP-CYCLE] FTP disabled")
        except Exception as e:
            logger.warning(f"[STOP-CYCLE] FTP disable failed (may already be off): {e}")
        await self.enable_ftp()
        logger.info(f"[STOP-CYCLE] FTP enable command sent")

        # Step 2b: Wait and verify FTP is ready (NL-43 needs time to start FTP server)
        ftp_ready_timeout = 30  # seconds
        ftp_check_interval = 2  # seconds
        ftp_ready = False
        elapsed = 0

        logger.info(f"[STOP-CYCLE] Step 2b: Waiting up to {ftp_ready_timeout}s for FTP server to be ready")
        while elapsed < ftp_ready_timeout:
            await asyncio.sleep(ftp_check_interval)
            elapsed += ftp_check_interval
            try:
                ftp_status = await self.get_ftp_status()
                logger.info(f"[STOP-CYCLE] FTP status check at {elapsed}s: {ftp_status}")
                if ftp_status.lower() == "on":
                    ftp_ready = True
                    logger.info(f"[STOP-CYCLE] FTP server confirmed ready after {elapsed}s")
                    break
            except Exception as e:
                logger.warning(f"[STOP-CYCLE] FTP status check failed at {elapsed}s: {e}")

        if ftp_ready:
            result["ftp_enabled"] = True
            logger.info(f"[STOP-CYCLE] FTP enabled and verified")
        else:
            logger.warning(f"[STOP-CYCLE] FTP not confirmed ready after {ftp_ready_timeout}s, proceeding anyway")
            result["ftp_enabled"] = True  # Command was sent, just not verified

        if not download:
            logger.info(f"[STOP-CYCLE] === Cycle complete (download=False) ===")
            return result

        # Step 3: Get current index to know which folder to download
        logger.info(f"[STOP-CYCLE] Step 3: Determining folder to download")
        current_index_str = await self.get_index_number()
        # Pad to 4 digits for folder name
        folder_name = f"Auto_{current_index_str.zfill(4)}"
        remote_path = f"/NL-43/{folder_name}"
        result["downloaded_folder"] = folder_name
        result["download_attempted"] = True
        logger.info(f"[STOP-CYCLE] Will download folder: {remote_path}")

        # Step 4: Download the folder
        if download_path is None:
            # Default path: data/downloads/{device_key}/Auto_XXXX.zip
            download_dir = f"data/downloads/{self.device_key}"
            os.makedirs(download_dir, exist_ok=True)
            download_path = os.path.join(download_dir, f"{folder_name}.zip")

        logger.info(f"[STOP-CYCLE] Step 4: Downloading to {download_path}")
        try:
            await self.download_ftp_folder(remote_path, download_path)
            result["download_success"] = True
            result["local_path"] = download_path
            logger.info(f"[STOP-CYCLE] Download successful: {download_path}")
        except Exception as e:
            logger.error(f"[STOP-CYCLE] Download failed: {e}")
            # Don't raise - the stop was successful, just the download failed
            result["download_error"] = str(e)

        logger.info(f"[STOP-CYCLE] === Cycle complete ===")
        return result
