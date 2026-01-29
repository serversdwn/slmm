"""
Per-device logging system.

Provides dual output: database entries for structured queries and file logs for backup.
Each device gets its own log file in data/logs/{unit_id}.log with rotation.
"""

import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import DeviceLog

# Configure base logger
logger = logging.getLogger(__name__)

# Log directory (persisted in Docker volume)
LOG_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Per-device file loggers (cached)
_device_file_loggers: dict = {}

# Log retention (days)
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))


def _get_file_logger(unit_id: str) -> logging.Logger:
    """Get or create a file logger for a specific device."""
    if unit_id in _device_file_loggers:
        return _device_file_loggers[unit_id]

    # Create device-specific logger
    device_logger = logging.getLogger(f"device.{unit_id}")
    device_logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if not device_logger.handlers:
        # Create rotating file handler (5 MB max, keep 3 backups)
        log_file = LOG_DIR / f"{unit_id}.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        handler.setLevel(logging.DEBUG)

        # Format: timestamp [LEVEL] [CATEGORY] message
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(category)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        device_logger.addHandler(handler)

        # Don't propagate to root logger
        device_logger.propagate = False

    _device_file_loggers[unit_id] = device_logger
    return device_logger


def log_device_event(
    unit_id: str,
    level: str,
    category: str,
    message: str,
    db: Optional[Session] = None
):
    """
    Log an event for a specific device.

    Writes to both:
    1. Database (DeviceLog table) for structured queries
    2. File (data/logs/{unit_id}.log) for backup/debugging

    Args:
        unit_id: Device identifier
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        category: Event category (TCP, FTP, POLL, COMMAND, STATE, SYNC)
        message: Log message
        db: Optional database session (creates one if not provided)
    """
    timestamp = datetime.utcnow()

    # Write to file log
    try:
        file_logger = _get_file_logger(unit_id)
        log_func = getattr(file_logger, level.lower(), file_logger.info)
        # Pass category as extra for formatter
        log_func(message, extra={"category": category})
    except Exception as e:
        logger.warning(f"Failed to write file log for {unit_id}: {e}")

    # Write to database
    close_db = False
    try:
        if db is None:
            db = SessionLocal()
            close_db = True

        log_entry = DeviceLog(
            unit_id=unit_id,
            timestamp=timestamp,
            level=level.upper(),
            category=category.upper(),
            message=message
        )
        db.add(log_entry)
        db.commit()

    except Exception as e:
        logger.warning(f"Failed to write DB log for {unit_id}: {e}")
        if db:
            db.rollback()
    finally:
        if close_db and db:
            db.close()


def cleanup_old_logs(retention_days: Optional[int] = None, db: Optional[Session] = None):
    """
    Delete log entries older than retention period.

    Args:
        retention_days: Days to retain (default: LOG_RETENTION_DAYS env var or 7)
        db: Optional database session
    """
    if retention_days is None:
        retention_days = LOG_RETENTION_DAYS

    cutoff = datetime.utcnow() - timedelta(days=retention_days)

    close_db = False
    try:
        if db is None:
            db = SessionLocal()
            close_db = True

        deleted = db.query(DeviceLog).filter(DeviceLog.timestamp < cutoff).delete()
        db.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} log entries older than {retention_days} days")

    except Exception as e:
        logger.error(f"Failed to cleanup old logs: {e}")
        if db:
            db.rollback()
    finally:
        if close_db and db:
            db.close()


def get_device_logs(
    unit_id: str,
    limit: int = 100,
    offset: int = 0,
    level: Optional[str] = None,
    category: Optional[str] = None,
    since: Optional[datetime] = None,
    db: Optional[Session] = None
) -> list:
    """
    Query log entries for a specific device.

    Args:
        unit_id: Device identifier
        limit: Max entries to return (default: 100)
        offset: Number of entries to skip (default: 0)
        level: Filter by level (DEBUG, INFO, WARNING, ERROR)
        category: Filter by category (TCP, FTP, POLL, COMMAND, STATE, SYNC)
        since: Filter entries after this timestamp
        db: Optional database session

    Returns:
        List of log entries as dicts
    """
    close_db = False
    try:
        if db is None:
            db = SessionLocal()
            close_db = True

        query = db.query(DeviceLog).filter(DeviceLog.unit_id == unit_id)

        if level:
            query = query.filter(DeviceLog.level == level.upper())
        if category:
            query = query.filter(DeviceLog.category == category.upper())
        if since:
            query = query.filter(DeviceLog.timestamp >= since)

        # Order by newest first
        query = query.order_by(DeviceLog.timestamp.desc())

        # Apply pagination
        entries = query.offset(offset).limit(limit).all()

        return [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() + "Z",
                "level": e.level,
                "category": e.category,
                "message": e.message
            }
            for e in entries
        ]

    finally:
        if close_db and db:
            db.close()


def get_log_stats(unit_id: str, db: Optional[Session] = None) -> dict:
    """
    Get log statistics for a device.

    Returns:
        Dict with counts by level and category
    """
    close_db = False
    try:
        if db is None:
            db = SessionLocal()
            close_db = True

        total = db.query(DeviceLog).filter(DeviceLog.unit_id == unit_id).count()

        # Count by level
        level_counts = {}
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            count = db.query(DeviceLog).filter(
                DeviceLog.unit_id == unit_id,
                DeviceLog.level == level
            ).count()
            if count > 0:
                level_counts[level] = count

        # Count by category
        category_counts = {}
        for category in ["TCP", "FTP", "POLL", "COMMAND", "STATE", "SYNC", "GENERAL"]:
            count = db.query(DeviceLog).filter(
                DeviceLog.unit_id == unit_id,
                DeviceLog.category == category
            ).count()
            if count > 0:
                category_counts[category] = count

        # Get oldest and newest
        oldest = db.query(DeviceLog).filter(
            DeviceLog.unit_id == unit_id
        ).order_by(DeviceLog.timestamp.asc()).first()

        newest = db.query(DeviceLog).filter(
            DeviceLog.unit_id == unit_id
        ).order_by(DeviceLog.timestamp.desc()).first()

        return {
            "total": total,
            "by_level": level_counts,
            "by_category": category_counts,
            "oldest": oldest.timestamp.isoformat() + "Z" if oldest else None,
            "newest": newest.timestamp.isoformat() + "Z" if newest else None
        }

    finally:
        if close_db and db:
            db.close()
