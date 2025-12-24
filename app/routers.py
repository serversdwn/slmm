from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel, field_validator
import logging
import ipaddress
import json
import os

from app.database import get_db
from app.models import NL43Config, NL43Status
from app.services import NL43Client, persist_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nl43", tags=["nl43"])


class ConfigPayload(BaseModel):
    host: str | None = None
    tcp_port: int | None = None
    tcp_enabled: bool | None = None
    ftp_enabled: bool | None = None
    ftp_username: str | None = None
    ftp_password: str | None = None
    web_enabled: bool | None = None

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        if v is None:
            return v
        # Try to parse as IP address or hostname
        try:
            ipaddress.ip_address(v)
        except ValueError:
            # Not an IP, check if it's a valid hostname format
            if not v or len(v) > 253:
                raise ValueError("Invalid hostname length")
            # Allow hostnames (basic validation)
            if not all(c.isalnum() or c in ".-" for c in v):
                raise ValueError("Host must be a valid IP address or hostname")
        return v

    @field_validator("tcp_port")
    @classmethod
    def validate_port(cls, v):
        if v is None:
            return v
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v


@router.get("/{unit_id}/config")
def get_config(unit_id: str, db: Session = Depends(get_db)):
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")
    return {
        "status": "ok",
        "data": {
            "unit_id": unit_id,
            "host": cfg.host,
            "tcp_port": cfg.tcp_port,
            "tcp_enabled": cfg.tcp_enabled,
            "ftp_enabled": cfg.ftp_enabled,
            "web_enabled": cfg.web_enabled,
        },
    }


@router.put("/{unit_id}/config")
def upsert_config(unit_id: str, payload: ConfigPayload, db: Session = Depends(get_db)):
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        cfg = NL43Config(unit_id=unit_id)
        db.add(cfg)

    if payload.host is not None:
        cfg.host = payload.host
    if payload.tcp_port is not None:
        cfg.tcp_port = payload.tcp_port
    if payload.tcp_enabled is not None:
        cfg.tcp_enabled = payload.tcp_enabled
    if payload.ftp_enabled is not None:
        cfg.ftp_enabled = payload.ftp_enabled
    if payload.ftp_username is not None:
        cfg.ftp_username = payload.ftp_username
    if payload.ftp_password is not None:
        cfg.ftp_password = payload.ftp_password
    if payload.web_enabled is not None:
        cfg.web_enabled = payload.web_enabled

    db.commit()
    db.refresh(cfg)
    logger.info(f"Updated config for unit {unit_id}")
    return {
        "status": "ok",
        "data": {
            "unit_id": unit_id,
            "host": cfg.host,
            "tcp_port": cfg.tcp_port,
            "tcp_enabled": cfg.tcp_enabled,
            "ftp_enabled": cfg.ftp_enabled,
            "web_enabled": cfg.web_enabled,
        },
    }


@router.get("/{unit_id}/status")
def get_status(unit_id: str, db: Session = Depends(get_db)):
    status = db.query(NL43Status).filter_by(unit_id=unit_id).first()
    if not status:
        raise HTTPException(status_code=404, detail="No NL43 status recorded")
    return {
        "status": "ok",
        "data": {
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
        },
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
    for field, value in payload.model_dump().items():
        if value is not None:
            setattr(status, field, value)

    db.commit()
    db.refresh(status)
    return {
        "status": "ok",
        "data": {
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
        },
    }


@router.post("/{unit_id}/start")
async def start_measurement(unit_id: str, db: Session = Depends(get_db)):
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.start()
        logger.info(f"Started measurement on unit {unit_id}")
    except ConnectionError as e:
        logger.error(f"Failed to start measurement on {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with device")
    except TimeoutError:
        logger.error(f"Timeout starting measurement on {unit_id}")
        raise HTTPException(status_code=504, detail="Device communication timeout")
    except Exception as e:
        logger.error(f"Unexpected error starting measurement on {unit_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    return {"status": "ok", "message": "Measurement started"}


@router.post("/{unit_id}/stop")
async def stop_measurement(unit_id: str, db: Session = Depends(get_db)):
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.stop()
        logger.info(f"Stopped measurement on unit {unit_id}")
    except ConnectionError as e:
        logger.error(f"Failed to stop measurement on {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with device")
    except TimeoutError:
        logger.error(f"Timeout stopping measurement on {unit_id}")
        raise HTTPException(status_code=504, detail="Device communication timeout")
    except Exception as e:
        logger.error(f"Unexpected error stopping measurement on {unit_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    return {"status": "ok", "message": "Measurement stopped"}


@router.post("/{unit_id}/store")
async def manual_store(unit_id: str, db: Session = Depends(get_db)):
    """Manually store measurement data to SD card."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.manual_store()
        logger.info(f"Manual store executed on unit {unit_id}")
        return {"status": "ok", "message": "Data stored to SD card"}
    except ConnectionError as e:
        logger.error(f"Failed to store data on {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with device")
    except TimeoutError:
        logger.error(f"Timeout storing data on {unit_id}")
        raise HTTPException(status_code=504, detail="Device communication timeout")
    except Exception as e:
        logger.error(f"Unexpected error storing data on {unit_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{unit_id}/pause")
async def pause_measurement(unit_id: str, db: Session = Depends(get_db)):
    """Pause the current measurement."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.pause()
        logger.info(f"Paused measurement on unit {unit_id}")
        return {"status": "ok", "message": "Measurement paused"}
    except Exception as e:
        logger.error(f"Failed to pause measurement on {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{unit_id}/resume")
async def resume_measurement(unit_id: str, db: Session = Depends(get_db)):
    """Resume a paused measurement."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.resume()
        logger.info(f"Resumed measurement on unit {unit_id}")
        return {"status": "ok", "message": "Measurement resumed"}
    except Exception as e:
        logger.error(f"Failed to resume measurement on {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{unit_id}/reset")
async def reset_measurement(unit_id: str, db: Session = Depends(get_db)):
    """Reset the measurement data."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.reset()
        logger.info(f"Reset measurement data on unit {unit_id}")
        return {"status": "ok", "message": "Measurement data reset"}
    except Exception as e:
        logger.error(f"Failed to reset measurement on {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{unit_id}/battery")
async def get_battery(unit_id: str, db: Session = Depends(get_db)):
    """Get battery level."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        level = await client.get_battery_level()
        return {"status": "ok", "battery_level": level}
    except Exception as e:
        logger.error(f"Failed to get battery level for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{unit_id}/clock")
async def get_clock(unit_id: str, db: Session = Depends(get_db)):
    """Get device clock time."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        clock = await client.get_clock()
        return {"status": "ok", "clock": clock}
    except Exception as e:
        logger.error(f"Failed to get clock for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


class ClockPayload(BaseModel):
    datetime: str  # Format: YYYY/MM/DD,HH:MM:SS


@router.put("/{unit_id}/clock")
async def set_clock(unit_id: str, payload: ClockPayload, db: Session = Depends(get_db)):
    """Set device clock time."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.set_clock(payload.datetime)
        return {"status": "ok", "message": f"Clock set to {payload.datetime}"}
    except Exception as e:
        logger.error(f"Failed to set clock for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


class WeightingPayload(BaseModel):
    weighting: str
    channel: str = "Main"


@router.get("/{unit_id}/frequency-weighting")
async def get_frequency_weighting(unit_id: str, channel: str = "Main", db: Session = Depends(get_db)):
    """Get frequency weighting (A, C, Z)."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        weighting = await client.get_frequency_weighting(channel)
        return {"status": "ok", "frequency_weighting": weighting, "channel": channel}
    except Exception as e:
        logger.error(f"Failed to get frequency weighting for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/{unit_id}/frequency-weighting")
async def set_frequency_weighting(unit_id: str, payload: WeightingPayload, db: Session = Depends(get_db)):
    """Set frequency weighting (A, C, Z)."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.set_frequency_weighting(payload.weighting, payload.channel)
        return {"status": "ok", "message": f"Frequency weighting set to {payload.weighting} on {payload.channel}"}
    except Exception as e:
        logger.error(f"Failed to set frequency weighting for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{unit_id}/time-weighting")
async def get_time_weighting(unit_id: str, channel: str = "Main", db: Session = Depends(get_db)):
    """Get time weighting (F, S, I)."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        weighting = await client.get_time_weighting(channel)
        return {"status": "ok", "time_weighting": weighting, "channel": channel}
    except Exception as e:
        logger.error(f"Failed to get time weighting for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/{unit_id}/time-weighting")
async def set_time_weighting(unit_id: str, payload: WeightingPayload, db: Session = Depends(get_db)):
    """Set time weighting (F, S, I)."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.set_time_weighting(payload.weighting, payload.channel)
        return {"status": "ok", "message": f"Time weighting set to {payload.weighting} on {payload.channel}"}
    except Exception as e:
        logger.error(f"Failed to set time weighting for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{unit_id}/live")
async def live_status(unit_id: str, db: Session = Depends(get_db)):
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        snap = await client.request_dod()
        snap.unit_id = unit_id

        # Persist snapshot with database session
        persist_snapshot(snap, db)

        logger.info(f"Retrieved live status for unit {unit_id}")
        return {"status": "ok", "data": snap.__dict__}

    except ConnectionError as e:
        logger.error(f"Failed to get live status for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with device")
    except TimeoutError:
        logger.error(f"Timeout getting live status for {unit_id}")
        raise HTTPException(status_code=504, detail="Device communication timeout")
    except ValueError as e:
        logger.error(f"Invalid response from device {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Device returned invalid data")
    except Exception as e:
        logger.error(f"Unexpected error getting live status for {unit_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{unit_id}/results")
async def get_results(unit_id: str, db: Session = Depends(get_db)):
    """Get final calculation results (DLC) from the last measurement."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        results = await client.request_dlc()
        logger.info(f"Retrieved measurement results for unit {unit_id}")
        return {"status": "ok", "data": results}

    except ConnectionError as e:
        logger.error(f"Failed to get results for {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with device")
    except TimeoutError:
        logger.error(f"Timeout getting results for {unit_id}")
        raise HTTPException(status_code=504, detail="Device communication timeout")
    except Exception as e:
        logger.error(f"Unexpected error getting results for {unit_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.websocket("/{unit_id}/stream")
async def stream_live(websocket: WebSocket, unit_id: str):
    """WebSocket endpoint for real-time DRD streaming from NL43 device.

    Connects to the device, starts DRD streaming, and pushes updates to the WebSocket client.
    The stream continues until the client disconnects or an error occurs.
    """
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for unit {unit_id}")

    from app.database import SessionLocal

    db: Session = SessionLocal()

    try:
        # Get device configuration
        cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
        if not cfg:
            await websocket.send_json({"error": "NL43 config not found", "unit_id": unit_id})
            await websocket.close()
            return

        if not cfg.tcp_enabled:
            await websocket.send_json(
                {"error": "TCP communication is disabled for this device", "unit_id": unit_id}
            )
            await websocket.close()
            return

        # Create client and define callback
        client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)

        async def send_snapshot(snap):
            """Callback that sends each snapshot to the WebSocket client."""
            snap.unit_id = unit_id

            # Persist to database
            try:
                persist_snapshot(snap, db)
            except Exception as e:
                logger.error(f"Failed to persist snapshot during stream: {e}")

            # Send to WebSocket client
            try:
                await websocket.send_json({
                    "unit_id": unit_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "measurement_state": snap.measurement_state,
                    "lp": snap.lp,
                    "leq": snap.leq,
                    "lmax": snap.lmax,
                    "lmin": snap.lmin,
                    "lpeak": snap.lpeak,
                    "raw_payload": snap.raw_payload,
                })
            except Exception as e:
                logger.error(f"Failed to send snapshot via WebSocket: {e}")
                raise

        # Start DRD streaming
        logger.info(f"Starting DRD stream for unit {unit_id}")
        await client.stream_drd(send_snapshot)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for unit {unit_id}")
    except ConnectionError as e:
        logger.error(f"Failed to connect to device {unit_id}: {e}")
        try:
            await websocket.send_json({"error": "Failed to communicate with device", "detail": str(e)})
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket stream for {unit_id}: {e}")
        try:
            await websocket.send_json({"error": "Internal server error", "detail": str(e)})
        except Exception:
            pass
    finally:
        db.close()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"WebSocket stream closed for unit {unit_id}")


@router.post("/{unit_id}/ftp/enable")
async def enable_ftp(unit_id: str, db: Session = Depends(get_db)):
    """Enable FTP server on the device."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.enable_ftp()
        logger.info(f"Enabled FTP on unit {unit_id}")
        return {"status": "ok", "message": "FTP enabled"}
    except Exception as e:
        logger.error(f"Failed to enable FTP on {unit_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable FTP: {str(e)}")


@router.post("/{unit_id}/ftp/disable")
async def disable_ftp(unit_id: str, db: Session = Depends(get_db)):
    """Disable FTP server on the device."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.disable_ftp()
        logger.info(f"Disabled FTP on unit {unit_id}")
        return {"status": "ok", "message": "FTP disabled"}
    except Exception as e:
        logger.error(f"Failed to disable FTP on {unit_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable FTP: {str(e)}")


@router.get("/{unit_id}/ftp/status")
async def get_ftp_status(unit_id: str, db: Session = Depends(get_db)):
    """Get FTP server status from the device."""
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    if not cfg.tcp_enabled:
        raise HTTPException(status_code=403, detail="TCP communication is disabled for this device")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        status = await client.get_ftp_status()
        return {"status": "ok", "ftp_enabled": status.lower() == "on", "ftp_status": status}
    except Exception as e:
        logger.error(f"Failed to get FTP status from {unit_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get FTP status: {str(e)}")


@router.get("/{unit_id}/ftp/files")
async def list_ftp_files(unit_id: str, path: str = "/", db: Session = Depends(get_db)):
    """List files on the device via FTP.

    Query params:
        path: Directory path on the device (default: root)
    """
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        files = await client.list_ftp_files(path)
        return {"status": "ok", "path": path, "files": files, "count": len(files)}
    except ConnectionError as e:
        logger.error(f"Failed to list FTP files on {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with device")
    except Exception as e:
        logger.error(f"Unexpected error listing FTP files on {unit_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class DownloadRequest(BaseModel):
    remote_path: str


@router.post("/{unit_id}/ftp/download")
async def download_ftp_file(unit_id: str, payload: DownloadRequest, db: Session = Depends(get_db)):
    """Download a file from the device via FTP.

    The file is saved to data/downloads/{unit_id}/ and can be retrieved via the response.
    """
    cfg = db.query(NL43Config).filter_by(unit_id=unit_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="NL43 config not found")

    # Create download directory
    download_dir = f"data/downloads/{unit_id}"
    os.makedirs(download_dir, exist_ok=True)

    # Extract filename from remote path
    filename = os.path.basename(payload.remote_path)
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid remote path")

    local_path = os.path.join(download_dir, filename)

    client = NL43Client(cfg.host, cfg.tcp_port, ftp_username=cfg.ftp_username, ftp_password=cfg.ftp_password)
    try:
        await client.download_ftp_file(payload.remote_path, local_path)
        logger.info(f"Downloaded {payload.remote_path} from {unit_id} to {local_path}")

        # Return the file
        return FileResponse(
            path=local_path,
            filename=filename,
            media_type="application/octet-stream",
        )
    except ConnectionError as e:
        logger.error(f"Failed to download file from {unit_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with device")
    except Exception as e:
        logger.error(f"Unexpected error downloading file from {unit_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
