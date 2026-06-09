from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, Text, func
from app.database import Base


class NL43Config(Base):
    """
    NL43 connection/config metadata for the standalone SLMM addon.
    """

    __tablename__ = "nl43_config"

    unit_id = Column(String, primary_key=True, index=True)
    host = Column(String, default="127.0.0.1")
    tcp_port = Column(Integer, default=2255)  # NL43 TCP control port (standard: 2255)
    tcp_enabled = Column(Boolean, default=True)
    ftp_enabled = Column(Boolean, default=False)
    ftp_port = Column(Integer, default=21)  # FTP port (standard: 21)
    ftp_username = Column(String, nullable=True)  # FTP login username
    ftp_password = Column(String, nullable=True)  # FTP login password
    web_enabled = Column(Boolean, default=False)

    # Background polling configuration
    poll_interval_seconds = Column(Integer, nullable=True, default=60)  # Polling interval (10-3600 seconds)
    poll_enabled = Column(Boolean, default=True)  # Enable/disable background polling for this device

    # Live monitor (fan-out DOD feed). Keepalive runs it 24/7 even with no viewer,
    # which is what makes alerting continuous. On by default; toggleable from the UI.
    monitor_enabled = Column(Boolean, default=True)


class NL43Status(Base):
    """
    Latest NL43 status snapshot for quick dashboard/API access.
    """

    __tablename__ = "nl43_status"

    unit_id = Column(String, primary_key=True, index=True)
    last_seen = Column(DateTime, default=func.now())
    measurement_state = Column(String, default="unknown")  # Measure/Stop
    measurement_start_time = Column(DateTime, nullable=True)  # When measurement started (UTC)
    counter = Column(String, nullable=True)  # d0: Measurement interval counter (1-600)
    lp = Column(String, nullable=True)    # Instantaneous sound pressure level
    leq = Column(String, nullable=True)   # Equivalent continuous sound level
    lmax = Column(String, nullable=True)  # Maximum level
    lmin = Column(String, nullable=True)  # Minimum level
    lpeak = Column(String, nullable=True)  # Peak level
    ln1 = Column(String, nullable=True)  # Percentile slot LN1 (configurable; device default L5, contract L1)
    ln2 = Column(String, nullable=True)  # Percentile slot LN2 (configurable; device default L10)
    battery_level = Column(String, nullable=True)
    power_source = Column(String, nullable=True)
    sd_remaining_mb = Column(String, nullable=True)
    sd_free_ratio = Column(String, nullable=True)
    raw_payload = Column(Text, nullable=True)

    # Background polling status
    is_reachable = Column(Boolean, default=True)  # Device reachability status
    consecutive_failures = Column(Integer, default=0)  # Count of consecutive poll failures
    last_poll_attempt = Column(DateTime, nullable=True)  # Last time background poller attempted to poll
    last_success = Column(DateTime, nullable=True)  # Last successful poll timestamp
    last_error = Column(Text, nullable=True)  # Last error message (truncated to 500 chars)

    # FTP start time sync tracking
    start_time_sync_attempted = Column(Boolean, default=False)  # True if FTP sync was attempted for current measurement


class DeviceLog(Base):
    """
    Per-device log entries for debugging and audit trail.
    Stores events like commands, state changes, errors, and FTP operations.
    """

    __tablename__ = "device_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, default=func.now(), index=True)
    level = Column(String, default="INFO")  # DEBUG, INFO, WARNING, ERROR
    category = Column(String, default="GENERAL")  # TCP, FTP, POLL, COMMAND, STATE, SYNC
    message = Column(Text, nullable=False)


class AlertRule(Base):
    """A threshold-alert rule evaluated against a unit's live monitor feed.

    Source-agnostic: today it runs over the DOD monitor; the same rule transfers
    unchanged if a unit's feed is later sourced from FTP intervals.
    """

    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False, default="Alert")
    metric = Column(String, nullable=False, default="lp")  # lp/leq/lmax/lmin/lpeak/ln1/ln2
    comparison = Column(String, nullable=False, default="above")  # above | below
    threshold_db = Column(Float, nullable=False)
    duration_s = Column(Integer, nullable=False, default=0)       # sustained seconds (0 = instant)
    clear_margin_db = Column(Float, nullable=False, default=2.0)  # hysteresis band
    cooldown_s = Column(Integer, nullable=False, default=300)     # min seconds between onsets
    # Optional time-of-day scoping (local time). schedule_start/end as "HH:MM";
    # null = always active. schedule_days = CSV of 0-6 (Mon=0); null = every day.
    schedule_start = Column(String, nullable=True)
    schedule_end = Column(String, nullable=True)
    schedule_days = Column(String, nullable=True)
    channels = Column(String, nullable=False, default="log")  # CSV: log,email,sms
    recipients = Column(Text, nullable=True)                  # CSV of emails/phones
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())


class AlertEvent(Base):
    """A fired alert (onset → clear), for history / inbox / acknowledgement."""

    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, index=True, nullable=False)
    unit_id = Column(String, index=True, nullable=False)
    rule_name = Column(String, nullable=True)
    metric = Column(String, nullable=False)
    threshold_db = Column(Float, nullable=False)
    onset_at = Column(DateTime, default=func.now(), index=True)
    onset_value = Column(Float, nullable=True)
    peak_value = Column(Float, nullable=True)
    clear_at = Column(DateTime, nullable=True)
    status = Column(String, default="active")  # active | cleared
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
