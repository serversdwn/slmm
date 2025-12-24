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
from typing import Optional, List
from sqlalchemy.orm import Session
import aioftp

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
    def __init__(self, host: str, port: int, timeout: float = 5.0, ftp_username: str = None, ftp_password: str = None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.ftp_username = ftp_username or "anonymous"
        self.ftp_password = ftp_password or ""
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
        """
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

            logger.debug(f"Result code from {self.device_key}: {result_code}")

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

        snap = NL43Snapshot(unit_id="", raw_payload=resp, measurement_state="Measure")

        # Parse known positions (based on NL43 communication guide)
        # DOD format: Main Lp, Main Leq, Main LE, Main Lmax, Main Lmin, LN1-5, Lpeak, LIeq, Leq,mov, Ltm5, flags...
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

    async def stream_drd(self, callback):
        """Stream continuous DRD output from the device.

        Opens a persistent connection and streams DRD data lines.
        Calls the provided callback function with each parsed snapshot.

        Args:
            callback: Async function that receives NL43Snapshot objects

        The stream continues until an exception occurs or the connection is closed.
        Send SUB character (0x1A) to stop the stream.
        """
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

                    # Parse known positions
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
        logger.info(f"Listing FTP files on {self.device_key} at {remote_path}")

        try:
            # FTP uses standard port 21, not the TCP control port
            async with aioftp.Client.context(
                self.host,
                port=21,
                user=self.ftp_username,
                password=self.ftp_password,
                socket_timeout=10
            ) as client:
                files = []
                async for path, info in client.list(remote_path):
                    file_info = {
                        "name": path.name,
                        "path": str(path),
                        "size": info.get("size", 0),
                        "modified": info.get("modify", ""),
                        "is_dir": info["type"] == "dir",
                    }
                    files.append(file_info)
                    logger.debug(f"Found file: {file_info}")

                logger.info(f"Found {len(files)} files/directories on {self.device_key}")
                return files

        except Exception as e:
            logger.error(f"Failed to list FTP files on {self.device_key}: {e}")
            raise ConnectionError(f"FTP connection failed: {str(e)}")

    async def download_ftp_file(self, remote_path: str, local_path: str):
        """Download a file from the device via FTP.

        Args:
            remote_path: Full path to file on the device
            local_path: Local path where file will be saved
        """
        logger.info(f"Downloading {remote_path} from {self.device_key} to {local_path}")

        try:
            # FTP uses standard port 21, not the TCP control port
            async with aioftp.Client.context(
                self.host,
                port=21,
                user=self.ftp_username,
                password=self.ftp_password,
                socket_timeout=10
            ) as client:
                await client.download(remote_path, local_path, write_into=True)
                logger.info(f"Successfully downloaded {remote_path} to {local_path}")

        except Exception as e:
            logger.error(f"Failed to download {remote_path} from {self.device_key}: {e}")
            raise ConnectionError(f"FTP download failed: {str(e)}")
