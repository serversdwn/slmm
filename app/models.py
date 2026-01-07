from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, func
from app.database import Base


class NL43Config(Base):
    """
    NL43 connection/config metadata for the standalone SLMM addon.
    """

    __tablename__ = "nl43_config"

    unit_id = Column(String, primary_key=True, index=True)
    host = Column(String, default="127.0.0.1")
    tcp_port = Column(Integer, default=80)  # NL43 TCP control port (via RX55)
    tcp_enabled = Column(Boolean, default=True)
    ftp_enabled = Column(Boolean, default=False)
    ftp_username = Column(String, nullable=True)  # FTP login username
    ftp_password = Column(String, nullable=True)  # FTP login password
    web_enabled = Column(Boolean, default=False)


class NL43Status(Base):
    """
    Latest NL43 status snapshot for quick dashboard/API access.
    """

    __tablename__ = "nl43_status"

    unit_id = Column(String, primary_key=True, index=True)
    last_seen = Column(DateTime, default=func.now())
    measurement_state = Column(String, default="unknown")  # Measure/Stop
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
