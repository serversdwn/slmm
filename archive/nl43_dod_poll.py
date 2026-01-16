#!/usr/bin/env python3
"""
Diagnostic poller for NL-43 TCP connectivity.

Every interval, open a TCP connection, send DOD?, read response, and log results.
"""

from __future__ import annotations

import datetime as dt
import socket
import time
from pathlib import Path

# ---- Configuration (edit as needed) ----
HOST = "192.168.0.10"
PORT = 2255
INTERVAL_SECONDS = 5 * 60
CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 5.0
LOG_PATH = Path("nl43_dod_poll.log")
# ---------------------------------------


def _timestamp() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _read_line(sock_file) -> str:
    line = sock_file.readline()
    if not line:
        raise ConnectionError("Socket closed before full response")
    return line.decode("ascii", errors="ignore").strip()


def _poll_once() -> tuple[bool, str, str, str, str]:
    sock = None
    result_code = ""
    data_line = ""
    try:
        sock = socket.create_connection((HOST, PORT), timeout=CONNECT_TIMEOUT_SECONDS)
        sock.settimeout(READ_TIMEOUT_SECONDS)

        sock.sendall(b"DOD?\r\n")

        with sock.makefile("rb") as sock_file:
            result_code = _read_line(sock_file)
            if result_code.startswith("$"):
                result_code = result_code[1:].strip()

            if result_code != "R+0000":
                return False, "other", f"device_result={result_code}", result_code, data_line

            data_line = _read_line(sock_file)
            if data_line.startswith("$"):
                data_line = data_line[1:].strip()

        return True, "none", "ok", result_code, data_line
    except socket.timeout:
        return False, "timeout", "socket_timeout", result_code, data_line
    except ConnectionRefusedError:
        return False, "refused", "connection_refused", result_code, data_line
    except OSError as exc:
        return False, "other", f"os_error={exc.__class__.__name__}", result_code, data_line
    except Exception as exc:
        return False, "other", f"error={exc.__class__.__name__}", result_code, data_line
    finally:
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()


def _log_line(text: str) -> None:
    print(text, flush=True)
    with LOG_PATH.open("a", encoding="ascii") as handle:
        handle.write(text + "\n")


def main() -> None:
    while True:
        start = time.monotonic()
        ok, error_type, detail, result_code, data_line = _poll_once()

        status = "success" if ok else "failure"
        msg = (
            f"ts={_timestamp()} status={status} error_type={error_type} "
            f"detail={detail} result_code={result_code} data={data_line}"
        )
        _log_line(msg)

        elapsed = time.monotonic() - start
        sleep_for = max(0.0, INTERVAL_SECONDS - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
