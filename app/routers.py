from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models import NL43Config, NL43Status

router = APIRouter(prefix="/api/nl43", tags=["nl43"])


class ConfigPayload(BaseModel):
    tcp_port: int | None = None
    tcp_enabled: bool | None = None
    ftp_enabled: bool | None = None
    web_enabled: bool | None = None


@router.get("/{unit_id}/config")
def get_config(unit_id: str, db: Session = Depends(get_db)):
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")
    return {
        "unit_id": unit_id,
        "tcp_port": cfg.tcp_port,
        "tcp_enabled": cfg.tcp_enabled,
        "ftp_enabled": cfg.ftp_enabled,
        "web_enabled": cfg.web_enabled,
    }


@router.put("/{unit_id}/config")
def upsert_config(unit_id: str, payload: ConfigPayload, db: Session = Depends(get_db)):
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        cfg = NL43Config(unit_id=unit_id)
        db.add(cfg)

    if payload.tcp_port is not None:
        cfg.tcp_port = payload.tcp_port
    if payload.tcp_enabled is not None:
        cfg.tcp_enabled = payload.tcp_enabled
    if payload.ftp_enabled is not None:
        cfg.ftp_enabled = payload.ftp_enabled
    if payload.web_enabled is not None:
        cfg.web_enabled = payload.web_enabled

    db.commit()
    db.refresh(cfg)
    return {
        "unit_id": unit_id,
        "tcp_port": cfg.tcp_port,
        "tcp_enabled": cfg.tcp_enabled,
        "ftp_enabled": cfg.ftp_enabled,
        "web_enabled": cfg.web_enabled,
    }


@router.get("/{unit_id}/status")
def get_status(unit_id: str, db: Session = Depends(get_db)):
    status = db.query(NL43Status).filter_by(unit_id=unit_id).first()
    if not status:
        raise HTTPException(status_code=404, detail="No NL43 status recorded")
    return {
        "unit_id": unit_id,
        "last_seen": status.last_seen.isoformat() if status.last_seen else None,
        "measurement_state": status.measurement_state,
        "lp": status.lp,
        "leq": status.leq,
        "lmax": status.lmax,
        "lmin": status.lmin,
        "lpeak": status.lpeak,
        "battery_level": status.battery_level,
        "power_source": status.power_source,
        "sd_remaining_mb": status.sd_remaining_mb,
        "sd_free_ratio": status.sd_free_ratio,
        "raw_payload": status.raw_payload,
    }


class StatusPayload(BaseModel):
    measurement_state: str | None = None
    lp: str | None = None
    leq: str | None = None
    lmax: str | None = None
    lmin: str | None = None
    lpeak: str | None = None
    battery_level: str | None = None
    power_source: str | None = None
    sd_remaining_mb: str | None = None
    sd_free_ratio: str | None = None
    raw_payload: str | None = None


@router.post("/{unit_id}/status")
def upsert_status(unit_id: str, payload: StatusPayload, db: Session = Depends(get_db)):
    status = db.query(NL43Status).filter_by(unit_id=unit_id).first()
    if not status:
        status = NL43Status(unit_id=unit_id)
        db.add(status)

    status.last_seen = datetime.utcnow()
    for field, value in payload.dict().items():
        if value is not None:
            setattr(status, field, value)

    db.commit()
    db.refresh(status)
    return {
        "unit_id": unit_id,
        "last_seen": status.last_seen.isoformat(),
        "measurement_state": status.measurement_state,
        "lp": status.lp,
        "leq": status.leq,
        "lmax": status.lmax,
        "lmin": status.lmin,
        "lpeak": status.lpeak,
        "battery_level": status.battery_level,
        "power_source": status.power_source,
        "sd_remaining_mb": status.sd_remaining_mb,
        "sd_free_ratio": status.sd_free_ratio,
        "raw_payload": status.raw_payload,
    }
