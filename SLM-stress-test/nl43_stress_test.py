#!/usr/bin/env python3
"""
NL-43 TCP Wedge Stress Test Tool

Standalone diagnostic tool for determining what causes the NL-43 sound level
meter's TCP port to become "wedged" (connection refused). Communicates directly
with the device over raw TCP sockets - zero SLMM dependencies.

Usage:
    python nl43_stress_test.py --host 192.168.1.100 --port 2255 --phase 1
    python nl43_stress_test.py --host 192.168.1.100 --phase all --dry-run

Test Phases:
    1 - Baseline Connection Count: How many commands before it dies?
    2 - Rate Variation: Does spacing between commands matter?
    3 - Command Variety: Do certain commands wedge faster?
    4 - Connection Duration: Does holding connections open matter?
    5 - Sustained Soak: Simulate real SLMM polling over hours
"""

import asyncio
import argparse
import csv
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev


# ─── Constants ───────────────────────────────────────────────────────────────

DEFAULT_PORT = 2255
DEFAULT_TIMEOUT = 5.0
CRLF = b"\r\n"
SUB_BYTE = b"\x1a"

# NL-43 result codes
RESULT_OK = "R+0000"
RESULT_CMD_ERROR = "R+0001"
RESULT_PARAM_ERROR = "R+0002"
RESULT_SPEC_ERROR = "R+0003"
RESULT_STATUS_ERROR = "R+0004"


# ─── Global state ────────────────────────────────────────────────────────────

_abort_requested = False


def _signal_handler(sig, frame):
    global _abort_requested
    _abort_requested = True
    print("\n\n!!! Ctrl+C detected - finishing current command and writing summary...\n")


signal.signal(signal.SIGINT, _signal_handler)


# ─── Packet Capture ──────────────────────────────────────────────────────────

class PacketCapture:
    """
    Manages a tcpdump subprocess that captures all traffic to/from the NL-43.
    Saves a .pcap file in the run directory for Wireshark analysis.
    """

    def __init__(self, host: str, port: int, pcap_path: Path):
        self.host = host
        self.port = port
        self.pcap_path = pcap_path
        self.process: subprocess.Popen | None = None
        self.available = False

    def _try_start_tcpdump(self, cmd: list[str], label: str) -> bool:
        """Attempt to start tcpdump with the given command. Returns True if successful."""
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Give it a moment to start or fail
            time.sleep(1.0)

            if self.process.poll() is not None:
                # Process exited immediately
                stderr = self.process.stderr.read().decode(errors="ignore")
                print(f"[PCAP] {label} tcpdump exited immediately: {stderr.strip()}")
                self.process = None
                return False

            # Process is running - check stderr for warnings (non-blocking read)
            # tcpdump writes "listening on ..." to stderr on success
            import select
            ready, _, _ = select.select([self.process.stderr], [], [], 0.5)
            if ready:
                # Read available stderr without blocking
                import os
                stderr_bytes = os.read(self.process.stderr.fileno(), 4096)
                stderr_text = stderr_bytes.decode(errors="ignore")
                if "listening on" in stderr_text.lower():
                    print(f"[PCAP] {label} tcpdump started: {stderr_text.strip()}")
                    self.available = True
                    return True
                elif "permission" in stderr_text.lower() or "operation not permitted" in stderr_text.lower():
                    print(f"[PCAP] {label} tcpdump permission denied: {stderr_text.strip()}")
                    self.process.terminate()
                    self.process.wait(timeout=3)
                    self.process = None
                    return False
                else:
                    # Some other output - might be OK, might not
                    print(f"[PCAP] {label} tcpdump stderr: {stderr_text.strip()}")

            # Process is still running - assume OK
            self.available = True
            return True

        except FileNotFoundError:
            print(f"[PCAP] {label} tcpdump binary not found")
            self.process = None
            return False
        except Exception as e:
            print(f"[PCAP] {label} failed to start: {e}")
            if self.process:
                try:
                    self.process.kill()
                    self.process.wait(timeout=3)
                except Exception:
                    pass
            self.process = None
            return False

    def start(self) -> bool:
        """Start tcpdump capture. Returns True if started successfully."""
        if not shutil.which("tcpdump"):
            print("[PCAP] tcpdump not found in PATH - packet capture disabled")
            print("[PCAP] Install with: sudo apt install tcpdump")
            return False

        # Capture all TCP traffic to/from the device on the specified port
        # -i any: all interfaces
        # -nn: no name resolution
        # -s 0: full packets, no truncation
        # -w: write raw pcap to file
        # -U: packet-buffered output (flush after each packet)
        cmd = [
            "tcpdump",
            "-i", "any",
            "-nn",
            "-s", "0",
            "-U",
            "-w", str(self.pcap_path),
            f"host {self.host} and tcp port {self.port}",
        ]

        # Try with sudo first (tcpdump almost always needs root for raw capture)
        print("[PCAP] Starting packet capture (requires sudo for raw interface access)...")
        if self._try_start_tcpdump(["sudo", "-n"] + cmd, "sudo"):
            print(f"[PCAP] ✓ Capturing to: {self.pcap_path}")
            print(f"[PCAP]   Filter: host {self.host} and tcp port {self.port}")
            return True

        # Fallback: try without sudo (works if user has CAP_NET_RAW capability)
        print("[PCAP] sudo failed, trying without sudo...")
        if self._try_start_tcpdump(cmd, "non-sudo"):
            print(f"[PCAP] ✓ Capturing to: {self.pcap_path}")
            print(f"[PCAP]   Filter: host {self.host} and tcp port {self.port}")
            return True

        print("[PCAP] ✗ Could not start packet capture")
        print("[PCAP]   To enable, run the stress test with sudo:")
        print(f"[PCAP]   sudo python3 nl43_stress_test.py --host {self.host} --port {self.port} ...")
        print("[PCAP]   Or run tcpdump separately in another terminal:")
        print(f"[PCAP]   sudo tcpdump -i any -nn -s 0 -U -w capture.pcap host {self.host} and tcp port {self.port}")
        return False

    def stop(self) -> dict:
        """Stop tcpdump and return capture stats."""
        stats = {
            "pcap_file": str(self.pcap_path),
            "packets_captured": 0,
            "file_size_bytes": 0,
        }

        if not self.process:
            return stats

        try:
            # SIGTERM for graceful shutdown (tcpdump prints stats on exit)
            self.process.terminate()
            try:
                _, stderr = self.process.communicate(timeout=5)
                stderr_text = stderr.decode(errors="ignore")
                for line in stderr_text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if "packets captured" in line:
                        try:
                            stats["packets_captured"] = int(line.split()[0])
                        except (ValueError, IndexError):
                            pass
                    # Print all tcpdump stats lines
                    if any(k in line for k in ["captured", "received", "dropped"]):
                        print(f"[PCAP] {line}")
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        except Exception as e:
            print(f"[PCAP] Error stopping tcpdump: {e}")

        # Report file size
        if self.pcap_path.exists():
            stats["file_size_bytes"] = self.pcap_path.stat().st_size
            size_mb = stats["file_size_bytes"] / (1024 * 1024)
            print(f"[PCAP] Saved: {self.pcap_path} ({size_mb:.2f} MB)")
            print(f"[PCAP] Open with: wireshark {self.pcap_path}")
            print(f"[PCAP]    or: tcpdump -nn -r {self.pcap_path}")
        else:
            print(f"[PCAP] Warning: pcap file not found at {self.pcap_path}")

        self.process = None
        return stats


# ─── Logger ──────────────────────────────────────────────────────────────────

class StressTestLogger:
    """Dual-output logger: console + file, with CSV data writers."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.log_file = open(run_dir / "full_log.txt", "w", buffering=1)
        self.summary_file = open(run_dir / "summary.txt", "w", buffering=1)

        # Raw wire log - every byte sent/received in hex + ascii
        self.wire_log = open(run_dir / "wire_log.txt", "w", buffering=1)

        # CSV for timing data
        self.timing_csv_path = run_dir / "timing_data.csv"
        self.timing_csv = open(self.timing_csv_path, "w", newline="")
        self.timing_writer = csv.writer(self.timing_csv)
        self.timing_writer.writerow([
            "phase", "cmd_num", "command", "connect_ms", "response_ms",
            "total_ms", "success", "error_type", "result_code", "data_length",
            "local_port", "timestamp"
        ])

    def log(self, message: str, also_print: bool = True):
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        line = f"[{ts}] {message}"
        self.log_file.write(line + "\n")
        if also_print:
            print(line)

    def wire(self, direction: str, raw_bytes: bytes, label: str = ""):
        """Log raw wire data - every byte in hex and ascii representation."""
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        hex_str = raw_bytes.hex(" ")
        ascii_str = raw_bytes.decode("ascii", errors="replace")
        # Show control characters explicitly
        readable = ""
        for b in raw_bytes:
            if b == 0x0d:
                readable += "\\r"
            elif b == 0x0a:
                readable += "\\n"
            elif b == 0x1a:
                readable += "\\x1a[SUB]"
            elif b == 0x24:
                readable += "$"
            elif 32 <= b < 127:
                readable += chr(b)
            else:
                readable += f"\\x{b:02x}"
        self.wire_log.write(f"[{ts}] {label} {direction} ({len(raw_bytes)} bytes)\n")
        self.wire_log.write(f"  HEX:   {hex_str}\n")
        self.wire_log.write(f"  ASCII: {readable}\n")
        self.wire_log.flush()

    def summary(self, message: str):
        self.summary_file.write(message + "\n")
        self.log_file.write(message + "\n")
        print(message)

    def record_timing(self, phase: str, cmd_num: int, command: str,
                      connect_ms: float, response_ms: float, total_ms: float,
                      success: bool, error_type: str = "", result_code: str = "",
                      data_length: int = 0, local_port: int = 0):
        self.timing_writer.writerow([
            phase, cmd_num, command, f"{connect_ms:.1f}", f"{response_ms:.1f}",
            f"{total_ms:.1f}", success, error_type, result_code, data_length,
            local_port,
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        ])
        self.timing_csv.flush()

    def close(self):
        self.log_file.close()
        self.summary_file.close()
        self.timing_csv.close()
        self.wire_log.close()


# ─── Raw TCP Communication ──────────────────────────────────────────────────

async def send_command(host: str, port: int, command: str, timeout: float,
                       is_query: bool = True, hold_seconds: float = 0,
                       logger: "StressTestLogger | None" = None,
                       label: str = "") -> dict:
    """
    Send a single command to the NL-43 over a fresh TCP connection.

    Returns dict with timing and result info:
        connect_ms, response_ms, total_ms, success, result_code, data,
        data_length, raw_result_bytes, raw_data_bytes, local_port,
        error, error_type
    """
    result = {
        "connect_ms": 0.0,
        "response_ms": 0.0,
        "total_ms": 0.0,
        "success": False,
        "result_code": None,
        "data": None,
        "data_length": 0,
        "raw_result_bytes": None,
        "raw_data_bytes": None,
        "local_port": 0,
        "error": None,
        "error_type": None,
    }

    t_start = time.monotonic()
    reader = None
    writer = None

    try:
        # Connect
        t_conn_start = time.monotonic()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        result["connect_ms"] = (time.monotonic() - t_conn_start) * 1000

        # Grab local socket info (source IP:port)
        sockname = writer.get_extra_info("sockname")
        if sockname:
            result["local_port"] = sockname[1]

        if logger:
            logger.log(f"{label} CONNECT {host}:{port} from :{result['local_port']} "
                       f"in {result['connect_ms']:.1f}ms", also_print=False)

        # Send command
        cmd_bytes = command.encode("ascii")
        if not cmd_bytes.endswith(CRLF):
            cmd_bytes += CRLF
        writer.write(cmd_bytes)
        await writer.drain()

        if logger:
            logger.wire("SEND>>>", cmd_bytes, label)

        # Read result code (first line)
        t_resp_start = time.monotonic()
        first_line_raw = await asyncio.wait_for(
            reader.readuntil(b"\n"),
            timeout=timeout
        )
        result["raw_result_bytes"] = first_line_raw

        if logger:
            logger.wire("<<<RECV", first_line_raw, f"{label} result_code")

        result_code = first_line_raw.decode("ascii", errors="ignore").strip()

        # Strip leading $ if present
        if result_code.startswith("$"):
            result_code = result_code[1:].strip()

        result["result_code"] = result_code

        # Read data line for queries
        if result_code == RESULT_OK and is_query:
            data_line_raw = await asyncio.wait_for(
                reader.readuntil(b"\n"),
                timeout=timeout
            )
            result["raw_data_bytes"] = data_line_raw
            result["data"] = data_line_raw.decode("ascii", errors="ignore").strip()
            result["data_length"] = len(result["data"])

            if logger:
                logger.wire("<<<RECV", data_line_raw, f"{label} data ({result['data_length']} chars)")

        result["response_ms"] = (time.monotonic() - t_resp_start) * 1000

        # Optionally hold connection open
        if hold_seconds > 0:
            if logger:
                logger.log(f"{label} HOLDING connection open for {hold_seconds}s...",
                           also_print=False)
            await asyncio.sleep(hold_seconds)

        result["success"] = result_code == RESULT_OK

        if result_code != RESULT_OK:
            result["error"] = f"Device returned {result_code}"
            result["error_type"] = "DeviceError"

    except ConnectionRefusedError:
        result["error"] = "Connection refused"
        result["error_type"] = "ConnectionRefused"
        if logger:
            logger.log(f"{label} CONNECTION REFUSED by {host}:{port}", also_print=False)
    except asyncio.TimeoutError:
        result["error"] = f"Timeout after {timeout}s"
        result["error_type"] = "Timeout"
        if logger:
            logger.log(f"{label} TIMEOUT after {timeout}s connecting to {host}:{port}",
                       also_print=False)
    except ConnectionResetError as e:
        result["error"] = f"Connection reset: {e}"
        result["error_type"] = "ConnectionReset"
        if logger:
            logger.log(f"{label} CONNECTION RESET by {host}:{port}: {e}", also_print=False)
    except OSError as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["error_type"] = type(e).__name__
        if logger:
            logger.log(f"{label} OS ERROR: {type(e).__name__}: {e}", also_print=False)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["error_type"] = type(e).__name__
        if logger:
            logger.log(f"{label} UNEXPECTED ERROR: {type(e).__name__}: {e}", also_print=False)
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        result["total_ms"] = (time.monotonic() - t_start) * 1000

        if logger:
            logger.log(f"{label} CLOSE total={result['total_ms']:.1f}ms "
                       f"local_port={result['local_port']}", also_print=False)

    return result


async def stream_drd(host: str, port: int, duration_seconds: float,
                     timeout: float,
                     logger: "StressTestLogger | None" = None) -> dict:
    """
    Open a DRD? streaming connection and hold it for the specified duration.

    Returns dict with timing and streaming stats.
    """
    result = {
        "connect_ms": 0.0,
        "total_ms": 0.0,
        "success": False,
        "lines_received": 0,
        "error": None,
        "error_type": None,
        "clean_shutdown": False,
    }

    t_start = time.monotonic()
    writer = None

    try:
        t_conn_start = time.monotonic()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        result["connect_ms"] = (time.monotonic() - t_conn_start) * 1000

        # Grab local port
        sockname = writer.get_extra_info("sockname")
        local_port = sockname[1] if sockname else 0
        result["local_port"] = local_port

        if logger:
            logger.log(f"DRD CONNECT :{local_port} → {host}:{port} "
                       f"in {result['connect_ms']:.1f}ms", also_print=False)

        # Send DRD?
        cmd_bytes = b"DRD?\r\n"
        writer.write(cmd_bytes)
        await writer.drain()

        if logger:
            logger.wire("SEND>>>", cmd_bytes, "DRD")

        # Read result code
        first_line = await asyncio.wait_for(
            reader.readuntil(b"\n"),
            timeout=timeout
        )

        if logger:
            logger.wire("<<<RECV", first_line, "DRD result_code")

        code = first_line.decode("ascii", errors="ignore").strip()
        if code.startswith("$"):
            code = code[1:].strip()

        if code != RESULT_OK:
            result["error"] = f"DRD? returned {code}"
            result["error_type"] = "DeviceError"
            return result

        # Stream for the specified duration
        stream_end = time.monotonic() + duration_seconds
        while time.monotonic() < stream_end and not _abort_requested:
            try:
                line = await asyncio.wait_for(
                    reader.readuntil(b"\n"),
                    timeout=30.0
                )
                result["lines_received"] += 1

                # Log every 10th stream line to wire log (full verbosity but manageable)
                if logger and (result["lines_received"] <= 5 or result["lines_received"] % 10 == 0):
                    logger.wire("<<<RECV", line,
                                f"DRD stream line#{result['lines_received']}")
            except asyncio.TimeoutError:
                result["error"] = "Stream timeout (no data for 30s)"
                result["error_type"] = "StreamTimeout"
                break

        # Clean shutdown with SUB byte
        try:
            writer.write(SUB_BYTE)
            await writer.drain()
            result["clean_shutdown"] = True
            if logger:
                logger.wire("SEND>>>", SUB_BYTE, "DRD shutdown")
        except Exception:
            pass

        result["success"] = True

    except ConnectionRefusedError:
        result["error"] = "Connection refused"
        result["error_type"] = "ConnectionRefused"
    except asyncio.TimeoutError:
        result["error"] = f"Connect timeout after {timeout}s"
        result["error_type"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        result["total_ms"] = (time.monotonic() - t_start) * 1000

    return result


# ─── Health Check ────────────────────────────────────────────────────────────

async def health_check(host: str, port: int, timeout: float,
                       logger: StressTestLogger, label: str = "") -> bool:
    """
    Quick connectivity test. Returns True if device responds to DOD?.
    """
    prefix = f"HEALTH [{label}]" if label else "HEALTH"
    logger.log(f"{prefix} Checking device at {host}:{port}...")

    r = await send_command(host, port, "DOD?", timeout, is_query=True,
                           logger=logger, label=prefix)

    if r["success"]:
        logger.log(f"{prefix} OK - connect={r['connect_ms']:.0f}ms "
                   f"response={r['response_ms']:.0f}ms "
                   f"local_port={r['local_port']} "
                   f"data_len={r['data_length']}")
        return True
    else:
        logger.log(f"{prefix} FAIL - {r['error_type']}: {r['error']}")
        return False


async def wait_for_recovery(host: str, port: int, timeout: float,
                            logger: StressTestLogger, max_wait: int = 300,
                            label: str = "") -> dict:
    """
    Wait for the device to recover after a wedge.
    Tries every 10 seconds for up to max_wait seconds.

    Returns dict with recovery info.
    """
    prefix = f"RECOVERY [{label}]" if label else "RECOVERY"
    logger.log(f"{prefix} Device unresponsive. Monitoring for recovery (max {max_wait}s)...")

    t_start = time.monotonic()
    attempts = 0

    while (time.monotonic() - t_start) < max_wait and not _abort_requested:
        attempts += 1
        elapsed = time.monotonic() - t_start
        logger.log(f"{prefix} Attempt #{attempts} at {elapsed:.0f}s...")

        r = await send_command(host, port, "DOD?", timeout, is_query=True,
                               logger=logger, label=f"{prefix} attempt#{attempts}")

        if r["success"]:
            recovery_time = time.monotonic() - t_start
            logger.log(f"{prefix} *** DEVICE RECOVERED after {recovery_time:.1f}s ({attempts} attempts) ***")
            return {
                "recovered": True,
                "recovery_seconds": recovery_time,
                "attempts": attempts,
            }

        logger.log(f"{prefix} Still down: {r['error_type']}: {r['error']}")
        await asyncio.sleep(10)

    total_time = time.monotonic() - t_start
    logger.log(f"{prefix} Device did NOT recover within {total_time:.0f}s ({attempts} attempts)")
    return {
        "recovered": False,
        "recovery_seconds": total_time,
        "attempts": attempts,
    }


# ─── Phase Summaries ────────────────────────────────────────────────────────

def compute_phase_summary(phase_name: str, timings: list, logger: StressTestLogger,
                          extra_info: str = ""):
    """Compute and log summary statistics for a phase."""
    total = len(timings)
    successes = [t for t in timings if t["success"]]
    failures = [t for t in timings if not t["success"]]

    logger.summary(f"\n{'=' * 60}")
    logger.summary(f"=== {phase_name} SUMMARY ===")
    logger.summary(f"{'=' * 60}")
    logger.summary(f"Total commands sent:    {total}")
    logger.summary(f"Total successful:       {len(successes)}")
    logger.summary(f"Total failed:           {len(failures)}")

    if failures:
        error_types = {}
        for f in failures:
            et = f.get("error_type", "Unknown")
            error_types[et] = error_types.get(et, 0) + 1
        for et, count in error_types.items():
            logger.summary(f"  {et}: {count}")

    if successes:
        connect_times = [t["connect_ms"] for t in successes]
        response_times = [t["response_ms"] for t in successes]
        total_times = [t["total_ms"] for t in successes]

        logger.summary(f"\nConnect time (ms):     avg={mean(connect_times):.1f}  "
                       f"med={median(connect_times):.1f}  "
                       f"min={min(connect_times):.1f}  max={max(connect_times):.1f}")
        logger.summary(f"Response time (ms):    avg={mean(response_times):.1f}  "
                       f"med={median(response_times):.1f}  "
                       f"min={min(response_times):.1f}  max={max(response_times):.1f}")
        logger.summary(f"Total time (ms):       avg={mean(total_times):.1f}  "
                       f"med={median(total_times):.1f}  "
                       f"min={min(total_times):.1f}  max={max(total_times):.1f}")

        if len(connect_times) > 1:
            logger.summary(f"Connect stdev (ms):    {stdev(connect_times):.1f}")
            logger.summary(f"Response stdev (ms):   {stdev(response_times):.1f}")

        # Trend analysis - compare first 20% vs last 20%
        if len(response_times) >= 10:
            bucket = max(1, len(response_times) // 5)
            first_bucket = response_times[:bucket]
            last_bucket = response_times[-bucket:]
            first_avg = mean(first_bucket)
            last_avg = mean(last_bucket)
            change_pct = ((last_avg - first_avg) / first_avg) * 100 if first_avg > 0 else 0

            if change_pct > 20:
                trend = "INCREASING"
            elif change_pct < -20:
                trend = "DECREASING"
            else:
                trend = "STABLE"

            logger.summary(f"\nResponse time trend:   {trend} "
                           f"(first {bucket}: {first_avg:.1f}ms → last {bucket}: {last_avg:.1f}ms, "
                           f"{change_pct:+.1f}%)")

    if failures:
        # Time/command number of first failure
        first_fail = failures[0]
        fail_idx = timings.index(first_fail)
        elapsed_at_fail = sum(t["total_ms"] for t in timings[:fail_idx + 1]) / 1000
        logger.summary(f"\nFirst failure at:      command #{fail_idx + 1} "
                       f"after {elapsed_at_fail:.1f}s ({elapsed_at_fail / 60:.1f} min)")
        logger.summary(f"Failure type:          {first_fail['error_type']}: {first_fail['error']}")

    if extra_info:
        logger.summary(f"\n{extra_info}")

    logger.summary(f"{'=' * 60}\n")


# ─── Test Phases ─────────────────────────────────────────────────────────────

async def phase_1_baseline(host: str, port: int, timeout: float,
                           max_commands: int, logger: StressTestLogger) -> list:
    """
    Phase 1: Baseline Connection Count
    How many DOD? commands at 1-second spacing before the device wedges?
    """
    logger.summary(f"\n{'#' * 60}")
    logger.summary("### PHASE 1: Baseline Connection Count ###")
    logger.summary(f"### Sending up to {max_commands} DOD? commands at 1.0s spacing ###")
    logger.summary(f"{'#' * 60}\n")

    timings = []
    wedge_detected = False
    phase_start = time.monotonic()

    for i in range(max_commands):
        if _abort_requested:
            logger.log("PHASE1 Abort requested by user")
            break

        cmd_num = i + 1
        elapsed_total = time.monotonic() - phase_start

        cmd_label = f"PHASE1 CMD#{cmd_num:04d}"
        r = await send_command(host, port, "DOD?", timeout, is_query=True,
                               logger=logger, label=cmd_label)

        # Log every command with FULL data
        if r["success"]:
            logger.log(f"PHASE1 CMD#{cmd_num:04d} OK  "
                       f"conn={r['connect_ms']:.0f}ms resp={r['response_ms']:.0f}ms "
                       f"total={r['total_ms']:.0f}ms elapsed={elapsed_total:.1f}s "
                       f"port=:{r['local_port']} code={r['result_code']} "
                       f"data_len={r['data_length']}\n"
                       f"  FULL DATA: {r['data']}")
        else:
            logger.log(f"PHASE1 CMD#{cmd_num:04d} FAIL  "
                       f"{r['error_type']}: {r['error']} "
                       f"conn={r['connect_ms']:.0f}ms total={r['total_ms']:.0f}ms "
                       f"elapsed={elapsed_total:.1f}s port=:{r['local_port']}")

        logger.record_timing("phase1", cmd_num, "DOD?",
                             r["connect_ms"], r["response_ms"], r["total_ms"],
                             r["success"], r.get("error_type", ""),
                             r.get("result_code", ""), r.get("data_length", 0),
                             r.get("local_port", 0))

        timings.append(r)

        # Check for wedge
        if r["error_type"] == "ConnectionRefused":
            logger.log(f"PHASE1 *** WEDGE DETECTED at command #{cmd_num} "
                       f"after {elapsed_total:.1f}s ({elapsed_total / 60:.1f} min) ***")
            wedge_detected = True
            break

        # Wait 1 second before next command
        if cmd_num < max_commands:
            await asyncio.sleep(1.0)

    extra = ""
    if not wedge_detected and not _abort_requested:
        extra = f"Device survived all {max_commands} commands without wedging."
    elif wedge_detected:
        recovery = await wait_for_recovery(host, port, timeout, logger, label="PHASE1")
        if recovery["recovered"]:
            extra = f"Device recovered after {recovery['recovery_seconds']:.1f}s"
        else:
            extra = "Device did NOT recover within monitoring window"

    compute_phase_summary("PHASE 1: Baseline Connection Count", timings, logger, extra)
    return timings


async def phase_2_rate_variation(host: str, port: int, timeout: float,
                                 commands_per_round: int, pause_between: int,
                                 logger: StressTestLogger) -> list:
    """
    Phase 2: Rate Variation
    Does the spacing between commands affect when/if the device wedges?
    """
    rates = [1.0, 2.0, 5.0, 10.0, 30.0]

    logger.summary(f"\n{'#' * 60}")
    logger.summary("### PHASE 2: Rate Variation ###")
    logger.summary(f"### {commands_per_round} commands per round at rates: {rates}s ###")
    logger.summary(f"{'#' * 60}\n")

    all_timings = []

    for rate in rates:
        if _abort_requested:
            break

        # Health check before each round
        logger.log(f"PHASE2 Checking device health before {rate}s rate round...")
        healthy = await health_check(host, port, timeout, logger, label=f"PHASE2-{rate}s")

        if not healthy:
            logger.log(f"PHASE2 Device unhealthy before {rate}s round - attempting recovery")
            recovery = await wait_for_recovery(host, port, timeout, logger,
                                               label=f"PHASE2-{rate}s")
            if not recovery["recovered"]:
                logger.log(f"PHASE2 Device not recovered - skipping remaining rates")
                break

        logger.log(f"\nPHASE2 === Starting {rate}s rate round ({commands_per_round} commands) ===")
        round_timings = []
        wedge_in_round = False

        for i in range(commands_per_round):
            if _abort_requested:
                break

            cmd_num = i + 1

            cmd_label = f"PHASE2 [{rate}s] CMD#{cmd_num:03d}"
            r = await send_command(host, port, "DOD?", timeout, is_query=True,
                                   logger=logger, label=cmd_label)

            status = "OK" if r["success"] else f"FAIL:{r['error_type']}"
            logger.log(f"PHASE2 [{rate}s] CMD#{cmd_num:03d} {status}  "
                       f"conn={r['connect_ms']:.0f}ms resp={r['response_ms']:.0f}ms "
                       f"total={r['total_ms']:.0f}ms port=:{r['local_port']} "
                       f"data_len={r['data_length']}\n"
                       f"  FULL DATA: {r['data']}")

            logger.record_timing(f"phase2_{rate}s", cmd_num, "DOD?",
                                 r["connect_ms"], r["response_ms"], r["total_ms"],
                                 r["success"], r.get("error_type", ""),
                                 r.get("result_code", ""), r.get("data_length", 0),
                                 r.get("local_port", 0))

            round_timings.append(r)

            if r["error_type"] == "ConnectionRefused":
                logger.log(f"PHASE2 *** WEDGE at {rate}s rate, command #{cmd_num} ***")
                wedge_in_round = True
                break

            if cmd_num < commands_per_round:
                await asyncio.sleep(rate)

        compute_phase_summary(f"PHASE 2: Rate {rate}s ({commands_per_round} commands)",
                              round_timings, logger)
        all_timings.extend(round_timings)

        if wedge_in_round:
            recovery = await wait_for_recovery(host, port, timeout, logger,
                                               label=f"PHASE2-{rate}s-recovery")

        # Pause between rounds
        if rate != rates[-1] and not _abort_requested:
            logger.log(f"PHASE2 Pausing {pause_between}s between rounds...")
            for _ in range(pause_between):
                if _abort_requested:
                    break
                await asyncio.sleep(1)

    return all_timings


async def phase_3_command_variety(host: str, port: int, timeout: float,
                                  commands_per_type: int, pause_between: int,
                                  logger: StressTestLogger) -> list:
    """
    Phase 3: Command Variety
    Do certain commands cause the device to wedge faster?
    """
    test_commands = [
        ("DOD?", True),
        ("Measure?", True),
        ("Battery Level?", True),
        ("Clock?", True),
        ("Sleep Mode?", True),
    ]

    logger.summary(f"\n{'#' * 60}")
    logger.summary("### PHASE 3: Command Variety ###")
    logger.summary(f"### {commands_per_type} commands of each type at 1.0s spacing ###")
    logger.summary(f"{'#' * 60}\n")

    all_timings = []

    for cmd, is_query in test_commands:
        if _abort_requested:
            break

        # Health check
        healthy = await health_check(host, port, timeout, logger, label=f"PHASE3-{cmd}")
        if not healthy:
            recovery = await wait_for_recovery(host, port, timeout, logger,
                                               label=f"PHASE3-{cmd}")
            if not recovery["recovered"]:
                logger.log(f"PHASE3 Device not recovered - skipping remaining commands")
                break

        logger.log(f"\nPHASE3 === Testing command: {cmd} ({commands_per_type} times) ===")
        round_timings = []
        wedge_in_round = False

        for i in range(commands_per_type):
            if _abort_requested:
                break

            cmd_num = i + 1
            cmd_label = f"PHASE3 [{cmd}] CMD#{cmd_num:03d}"
            r = await send_command(host, port, cmd, timeout, is_query=is_query,
                                   logger=logger, label=cmd_label)

            status = "OK" if r["success"] else f"FAIL:{r['error_type']}"
            logger.log(f"PHASE3 [{cmd}] CMD#{cmd_num:03d} {status}  "
                       f"conn={r['connect_ms']:.0f}ms resp={r['response_ms']:.0f}ms "
                       f"port=:{r['local_port']} data_len={r['data_length']}\n"
                       f"  FULL DATA: {r['data']}")

            logger.record_timing("phase3", cmd_num, cmd,
                                 r["connect_ms"], r["response_ms"], r["total_ms"],
                                 r["success"], r.get("error_type", ""),
                                 r.get("result_code", ""), r.get("data_length", 0),
                                 r.get("local_port", 0))

            round_timings.append(r)

            if r["error_type"] == "ConnectionRefused":
                logger.log(f"PHASE3 *** WEDGE on {cmd}, command #{cmd_num} ***")
                wedge_in_round = True
                break

            if cmd_num < commands_per_type:
                await asyncio.sleep(1.0)

        compute_phase_summary(f"PHASE 3: Command '{cmd}' ({commands_per_type} cmds)",
                              round_timings, logger)
        all_timings.extend(round_timings)

        if wedge_in_round:
            recovery = await wait_for_recovery(host, port, timeout, logger,
                                               label=f"PHASE3-{cmd}-recovery")

        # Pause between command types
        if cmd != test_commands[-1][0] and not _abort_requested:
            logger.log(f"PHASE3 Pausing {pause_between}s between command types...")
            for _ in range(pause_between):
                if _abort_requested:
                    break
                await asyncio.sleep(1)

    return all_timings


async def phase_4_connection_duration(host: str, port: int, timeout: float,
                                      pause_between: int,
                                      logger: StressTestLogger) -> list:
    """
    Phase 4: Connection Duration
    Does holding connections open longer or shorter affect stability?
    """
    logger.summary(f"\n{'#' * 60}")
    logger.summary("### PHASE 4: Connection Duration ###")
    logger.summary("### Testing various connection hold times ###")
    logger.summary(f"{'#' * 60}\n")

    all_timings = []

    # Round A: Hold connection open 5s after command
    rounds = [
        ("A", "Hold 5s after response", 50, 5.0, False),
        ("B", "Close immediately", 50, 0.0, False),
        ("C", "Hold 30s (no command)", 10, 30.0, True),
    ]

    for round_id, desc, count, hold_time, hold_only in rounds:
        if _abort_requested:
            break

        healthy = await health_check(host, port, timeout, logger,
                                     label=f"PHASE4-Round{round_id}")
        if not healthy:
            recovery = await wait_for_recovery(host, port, timeout, logger,
                                               label=f"PHASE4-Round{round_id}")
            if not recovery["recovered"]:
                logger.log(f"PHASE4 Device not recovered - skipping remaining rounds")
                break

        logger.log(f"\nPHASE4 === Round {round_id}: {desc} ({count} connections) ===")
        round_timings = []
        wedge_in_round = False

        for i in range(count):
            if _abort_requested:
                break

            cmd_num = i + 1

            cmd_label = f"PHASE4 [Round{round_id}] #{cmd_num:03d}"

            if hold_only:
                # Just open connection, hold, close (no command)
                r = {"connect_ms": 0, "response_ms": 0, "total_ms": 0,
                     "success": False, "error": None, "error_type": None,
                     "local_port": 0, "data": None, "data_length": 0,
                     "result_code": ""}
                t_start = time.monotonic()
                writer = None
                try:
                    t_conn = time.monotonic()
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), timeout=timeout
                    )
                    r["connect_ms"] = (time.monotonic() - t_conn) * 1000
                    sockname = writer.get_extra_info("sockname")
                    if sockname:
                        r["local_port"] = sockname[1]

                    logger.log(f"{cmd_label} CONNECT :{r['local_port']} → {host}:{port} "
                               f"in {r['connect_ms']:.1f}ms, holding {hold_time}s (no command)...",
                               also_print=False)

                    # Hold without sending
                    await asyncio.sleep(hold_time)
                    r["success"] = True

                except ConnectionRefusedError:
                    r["error"] = "Connection refused"
                    r["error_type"] = "ConnectionRefused"
                    logger.log(f"{cmd_label} CONNECTION REFUSED", also_print=False)
                except asyncio.TimeoutError:
                    r["error"] = "Timeout"
                    r["error_type"] = "Timeout"
                except ConnectionResetError as e:
                    r["error"] = f"Connection reset: {e}"
                    r["error_type"] = "ConnectionReset"
                except Exception as e:
                    r["error"] = str(e)
                    r["error_type"] = type(e).__name__
                finally:
                    if writer:
                        try:
                            writer.close()
                            await writer.wait_closed()
                        except Exception:
                            pass
                    r["total_ms"] = (time.monotonic() - t_start) * 1000
            else:
                r = await send_command(host, port, "DOD?", timeout,
                                       is_query=True, hold_seconds=hold_time,
                                       logger=logger, label=cmd_label)

            status = "OK" if r["success"] else f"FAIL:{r.get('error_type', '?')}"
            cmd_desc = f"DOD?(hold={hold_time}s)" if not hold_only else f"connect_only(hold={hold_time}s)"
            logger.log(f"PHASE4 [Round{round_id}] #{cmd_num:03d} {status}  "
                       f"conn={r['connect_ms']:.0f}ms total={r['total_ms']:.0f}ms "
                       f"port=:{r.get('local_port', 0)}")

            logger.record_timing(f"phase4_{round_id}", cmd_num, cmd_desc,
                                 r["connect_ms"], r.get("response_ms", 0),
                                 r["total_ms"], r["success"],
                                 r.get("error_type", ""),
                                 r.get("result_code", ""), r.get("data_length", 0),
                                 r.get("local_port", 0))

            round_timings.append(r)

            if r.get("error_type") == "ConnectionRefused":
                logger.log(f"PHASE4 *** WEDGE in Round {round_id}, connection #{cmd_num} ***")
                wedge_in_round = True
                break

            # 1s spacing between connections (plus any hold time already elapsed)
            remaining_wait = max(0, 1.0 - hold_time)
            if remaining_wait > 0 and cmd_num < count:
                await asyncio.sleep(remaining_wait)

        compute_phase_summary(f"PHASE 4 Round {round_id}: {desc}",
                              round_timings, logger)
        all_timings.extend(round_timings)

        if wedge_in_round:
            await wait_for_recovery(host, port, timeout, logger,
                                    label=f"PHASE4-Round{round_id}-recovery")

        if round_id != rounds[-1][0] and not _abort_requested:
            logger.log(f"PHASE4 Pausing {pause_between}s between rounds...")
            for _ in range(pause_between):
                if _abort_requested:
                    break
                await asyncio.sleep(1)

    # Round D: DRD? stream
    if not _abort_requested:
        healthy = await health_check(host, port, timeout, logger, label="PHASE4-RoundD")
        if healthy:
            logger.log(f"\nPHASE4 === Round D: DRD? stream for 60 seconds ===")

            stream_result = await stream_drd(host, port, 60.0, timeout, logger=logger)

            if stream_result["success"]:
                logger.log(f"PHASE4 [RoundD] DRD stream OK - "
                           f"{stream_result['lines_received']} lines in "
                           f"{stream_result['total_ms']:.0f}ms, "
                           f"clean_shutdown={stream_result['clean_shutdown']}")
            else:
                logger.log(f"PHASE4 [RoundD] DRD stream FAIL - "
                           f"{stream_result['error_type']}: {stream_result['error']}")

            # Health check after stream
            logger.log("PHASE4 Checking health after DRD stream...")
            await asyncio.sleep(2)  # Brief pause
            post_stream = await health_check(host, port, timeout, logger,
                                             label="PHASE4-post-DRD")
            if not post_stream:
                logger.log("PHASE4 *** Device unhealthy after DRD stream ***")
                await wait_for_recovery(host, port, timeout, logger,
                                        label="PHASE4-RoundD-recovery")

            logger.summary(f"\nPHASE 4 Round D: DRD Stream (60s)")
            logger.summary(f"  Lines received: {stream_result['lines_received']}")
            logger.summary(f"  Clean shutdown: {stream_result['clean_shutdown']}")
            logger.summary(f"  Duration: {stream_result['total_ms']:.0f}ms")
            logger.summary(f"  Post-stream health: {'OK' if post_stream else 'FAILED'}")

    return all_timings


async def phase_5_soak(host: str, port: int, timeout: float,
                       duration_minutes: int, logger: StressTestLogger) -> list:
    """
    Phase 5: Sustained Soak
    Simulate real SLMM polling: DOD? every 60s, with extras every 10th poll.
    """
    logger.summary(f"\n{'#' * 60}")
    logger.summary("### PHASE 5: Sustained Soak ###")
    logger.summary(f"### Simulating SLMM polling for {duration_minutes} minutes ###")
    logger.summary(f"### DOD? every 60s, +Battery/Measure every 10th poll ###")
    logger.summary(f"{'#' * 60}\n")

    timings = []
    poll_count = 0
    phase_start = time.monotonic()
    end_time = phase_start + (duration_minutes * 60)
    wedge_detected = False

    while time.monotonic() < end_time and not _abort_requested:
        poll_count += 1
        elapsed_min = (time.monotonic() - phase_start) / 60

        # Primary poll: DOD?
        poll_label = f"PHASE5 POLL#{poll_count:04d}"
        r = await send_command(host, port, "DOD?", timeout, is_query=True,
                               logger=logger, label=poll_label)

        status = "OK" if r["success"] else f"FAIL:{r['error_type']}"
        logger.log(f"PHASE5 POLL#{poll_count:04d} DOD? {status}  "
                   f"conn={r['connect_ms']:.0f}ms resp={r['response_ms']:.0f}ms "
                   f"elapsed={elapsed_min:.1f}min port=:{r['local_port']} "
                   f"data_len={r['data_length']}\n"
                   f"  FULL DATA: {r['data']}")

        logger.record_timing("phase5", poll_count, "DOD?",
                             r["connect_ms"], r["response_ms"], r["total_ms"],
                             r["success"], r.get("error_type", ""),
                             r.get("result_code", ""), r.get("data_length", 0),
                             r.get("local_port", 0))
        timings.append(r)

        if r["error_type"] == "ConnectionRefused":
            logger.log(f"PHASE5 *** WEDGE DETECTED at poll #{poll_count} "
                       f"after {elapsed_min:.1f} minutes ***")
            wedge_detected = True
            break

        # Every 10th poll, also check battery and measurement state
        if poll_count % 10 == 0 and r["success"]:
            await asyncio.sleep(1.0)

            for extra_cmd in ["Battery Level?", "Measure?"]:
                if _abort_requested:
                    break

                extra_label = f"PHASE5 POLL#{poll_count:04d} {extra_cmd}"
                r2 = await send_command(host, port, extra_cmd, timeout, is_query=True,
                                        logger=logger, label=extra_label)
                s2 = "OK" if r2["success"] else f"FAIL:{r2['error_type']}"
                logger.log(f"PHASE5 POLL#{poll_count:04d} {extra_cmd} {s2}  "
                           f"conn={r2['connect_ms']:.0f}ms resp={r2['response_ms']:.0f}ms "
                           f"port=:{r2['local_port']} data_len={r2['data_length']}\n"
                           f"  FULL DATA: {r2['data']}")

                logger.record_timing("phase5_extra", poll_count, extra_cmd,
                                     r2["connect_ms"], r2["response_ms"], r2["total_ms"],
                                     r2["success"], r2.get("error_type", ""),
                                     r2.get("result_code", ""), r2.get("data_length", 0),
                                     r2.get("local_port", 0))
                timings.append(r2)

                if r2["error_type"] == "ConnectionRefused":
                    logger.log(f"PHASE5 *** WEDGE on extra command {extra_cmd} ***")
                    wedge_detected = True
                    break

                await asyncio.sleep(1.0)

            if wedge_detected:
                break

        # Wait 60 seconds before next poll
        for _ in range(60):
            if _abort_requested or time.monotonic() >= end_time:
                break
            await asyncio.sleep(1)

    extra = ""
    if wedge_detected:
        recovery = await wait_for_recovery(host, port, timeout, logger, label="PHASE5")
        if recovery["recovered"]:
            extra = f"Device recovered after {recovery['recovery_seconds']:.1f}s"
        else:
            extra = "Device did NOT recover within monitoring window"
    elif not _abort_requested:
        elapsed_min = (time.monotonic() - phase_start) / 60
        extra = f"Device survived full {elapsed_min:.1f} minute soak without wedging"

    compute_phase_summary("PHASE 5: Sustained Soak", timings, logger, extra)
    return timings


# ─── Dry Run ─────────────────────────────────────────────────────────────────

def dry_run(args):
    """Show what would be tested without connecting to any device."""
    print(f"\n{'=' * 60}")
    print("DRY RUN - No connections will be made")
    print(f"{'=' * 60}")
    print(f"\nTarget: {args.host}:{args.port}")
    print(f"Timeout: {args.timeout}s")
    print(f"Phase(s): {args.phase}")
    print(f"Log directory: {args.log_dir}")
    print(f"Recovery pause: {args.pause}s")

    phases = args.phase if args.phase != "all" else "1,2,3,4,5"
    phase_list = [p.strip() for p in phases.split(",")]

    total_commands = 0
    total_time_est = 0

    for p in phase_list:
        print(f"\n--- Phase {p} ---")

        if p == "1":
            n = args.max_commands
            t = n * 1  # 1s spacing
            print(f"  Baseline: up to {n} DOD? commands at 1.0s spacing")
            print(f"  Estimated time: {t}s ({t / 60:.1f} min)")
            total_commands += n
            total_time_est += t

        elif p == "2":
            rates = [1.0, 2.0, 5.0, 10.0, 30.0]
            n = args.rate_rounds
            for rate in rates:
                t = n * rate
                print(f"  Rate {rate}s: {n} DOD? commands ({t:.0f}s per round)")
            pause_time = 4 * args.pause  # 4 pauses between 5 rounds
            total_commands += n * len(rates)
            total_time_est += sum(n * r for r in rates) + pause_time
            print(f"  + {args.pause}s pause between rounds")

        elif p == "3":
            cmds = ["DOD?", "Measure?", "Battery Level?", "Clock?", "Sleep Mode?"]
            n = 100
            print(f"  {n} commands each of: {', '.join(cmds)}")
            print(f"  Estimated: {n * len(cmds)}s + {(len(cmds) - 1) * args.pause}s pauses")
            total_commands += n * len(cmds)
            total_time_est += n * len(cmds) + (len(cmds) - 1) * args.pause

        elif p == "4":
            print("  Round A: 50x DOD? with 5s hold = ~250s")
            print("  Round B: 50x DOD? close immediately = ~50s")
            print("  Round C: 10x connect+30s hold (no command) = ~300s")
            print("  Round D: DRD? stream for 60s")
            total_commands += 110
            total_time_est += 250 + 50 + 300 + 60 + 3 * args.pause

        elif p == "5":
            dur = args.soak_duration
            polls = dur  # 1 poll per minute
            extras = (polls // 10) * 2  # 2 extra commands every 10th poll
            print(f"  Soak for {dur} minutes")
            print(f"  ~{polls} DOD? polls + ~{extras} extra commands")
            total_commands += polls + extras
            total_time_est += dur * 60

    print(f"\n{'=' * 60}")
    print(f"Total estimated commands: ~{total_commands}")
    print(f"Total estimated time: ~{total_time_est}s ({total_time_est / 60:.0f} min, "
          f"{total_time_est / 3600:.1f} hr)")
    print(f"{'=' * 60}\n")


# ─── Main ────────────────────────────────────────────────────────────────────

async def run(args):
    """Main test runner."""
    # Create run directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.log_dir) / f"run_{timestamp}"
    logger = StressTestLogger(run_dir)

    logger.summary(f"NL-43 TCP Stress Test")
    logger.summary(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.summary(f"Target: {args.host}:{args.port}")
    logger.summary(f"Timeout: {args.timeout}s")
    logger.summary(f"Phase(s): {args.phase}")

    # Start packet capture
    pcap = None
    if not args.no_pcap:
        pcap_path = run_dir / "capture.pcap"
        pcap = PacketCapture(args.host, args.port, pcap_path)
        pcap_started = pcap.start()
        if pcap_started:
            logger.summary(f"Packet capture: {pcap_path}")
        else:
            logger.summary("Packet capture: DISABLED (tcpdump unavailable or no permissions)")
            pcap = None

    # Initial health check
    logger.log("\n=== Initial Health Check ===")
    healthy = await health_check(args.host, args.port, args.timeout, logger, label="INITIAL")
    if not healthy:
        logger.log("WARNING: Device is not responding at test start!")
        logger.log("Waiting for device to become available...")
        recovery = await wait_for_recovery(args.host, args.port, args.timeout,
                                           logger, label="INITIAL")
        if not recovery["recovered"]:
            logger.summary("ABORTED: Device unreachable at test start and did not recover")
            if pcap:
                pcap.stop()
            logger.close()
            return

    phases = args.phase if args.phase != "all" else "1,2,3,4,5"
    phase_list = [p.strip() for p in phases.split(",")]

    for phase_num in phase_list:
        if _abort_requested:
            break

        # Recovery pause between phases
        if phase_num != phase_list[0]:
            logger.log(f"\n--- Recovery pause ({args.pause}s) before Phase {phase_num} ---")
            for _ in range(args.pause):
                if _abort_requested:
                    break
                await asyncio.sleep(1)

            healthy = await health_check(args.host, args.port, args.timeout, logger,
                                         label=f"pre-phase{phase_num}")
            if not healthy:
                logger.log(f"Device unhealthy before Phase {phase_num} - waiting for recovery")
                recovery = await wait_for_recovery(args.host, args.port, args.timeout,
                                                   logger, label=f"pre-phase{phase_num}")
                if not recovery["recovered"]:
                    logger.log(f"Device not recovered - skipping Phase {phase_num} and remaining")
                    break

        if phase_num == "1":
            await phase_1_baseline(args.host, args.port, args.timeout,
                                   args.max_commands, logger)
        elif phase_num == "2":
            await phase_2_rate_variation(args.host, args.port, args.timeout,
                                        args.rate_rounds, args.pause, logger)
        elif phase_num == "3":
            await phase_3_command_variety(args.host, args.port, args.timeout,
                                         100, args.pause, logger)
        elif phase_num == "4":
            await phase_4_connection_duration(args.host, args.port, args.timeout,
                                             args.pause, logger)
        elif phase_num == "5":
            await phase_5_soak(args.host, args.port, args.timeout,
                               args.soak_duration, logger)

    # Stop packet capture
    if pcap:
        logger.summary("\nStopping packet capture...")
        pcap_stats = pcap.stop()
        logger.summary(f"Packets captured: {pcap_stats['packets_captured']}")
        logger.summary(f"PCAP file: {pcap_stats['pcap_file']}")
        logger.summary(f"PCAP size: {pcap_stats['file_size_bytes']} bytes")

    # Final summary
    logger.summary(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.summary(f"Logs saved to: {run_dir}")
    logger.close()

    print(f"\nResults saved to: {run_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="NL-43 TCP Wedge Stress Test Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Phases:
  1  Baseline Connection Count - DOD? at 1s until wedge or max
  2  Rate Variation - DOD? at 1s, 2s, 5s, 10s, 30s spacing
  3  Command Variety - Different commands to see if type matters
  4  Connection Duration - Hold connections open various durations
  5  Sustained Soak - Simulate real SLMM polling for hours

Examples:
  %(prog)s --host 192.168.1.100 --phase 1 --max-commands 500
  %(prog)s --host 192.168.1.100 --phase 5 --soak-duration 240
  %(prog)s --host 192.168.1.100 --phase all --dry-run
  %(prog)s --host 10.0.0.50 --phase 1,2 --timeout 10
        """
    )

    parser.add_argument("--host", required=True, help="NL-43 IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"TCP port (default: {DEFAULT_PORT})")
    parser.add_argument("--phase", default="all",
                        help="Phase(s) to run: 1,2,3,4,5 or 'all' (default: all)")
    parser.add_argument("--max-commands", type=int, default=2000,
                        help="Phase 1: max commands before stopping (default: 2000)")
    parser.add_argument("--rate-rounds", type=int, default=50,
                        help="Phase 2: commands per rate round (default: 50)")
    parser.add_argument("--soak-duration", type=int, default=120,
                        help="Phase 5: soak duration in minutes (default: 120)")
    parser.add_argument("--log-dir", default="./stress_test_logs",
                        help="Log output directory (default: ./stress_test_logs)")
    parser.add_argument("--pause", type=int, default=60,
                        help="Recovery pause between phases in seconds (default: 60)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"TCP timeout in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show test plan without connecting")
    parser.add_argument("--no-pcap", action="store_true",
                        help="Disable built-in tcpdump packet capture")

    args = parser.parse_args()

    if args.dry_run:
        dry_run(args)
        return

    print(f"\nNL-43 TCP Stress Test Tool")
    print(f"Target: {args.host}:{args.port}")
    print(f"Phase(s): {args.phase}")
    print(f"Press Ctrl+C at any time to stop safely\n")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
