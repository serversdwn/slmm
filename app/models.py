from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, func
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
