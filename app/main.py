import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import Base, engine
from app import routers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/slmm.log"),
    ],
)
logger = logging.getLogger(__name__)

# Ensure database tables exist for the addon
Base.metadata.create_all(bind=engine)
logger.info("Database tables initialized")

app = FastAPI(
    title="SLMM NL43 Addon",
    description="Standalone module for NL43 configuration and status APIs",
    version="0.1.0",
)

# CORS configuration - use environment variable for allowed origins
# Default to "*" for development, but should be restricted in production
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
logger.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

app.include_router(routers.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    """Basic health check endpoint."""
    return {"status": "ok", "service": "slmm-nl43-addon"}


@app.get("/health/devices")
async def health_devices():
    """Enhanced health check that tests device connectivity."""
    from sqlalchemy.orm import Session
    from app.database import SessionLocal
    from app.services import NL43Client
    from app.models import NL43Config

    db: Session = SessionLocal()
    device_status = []

    try:
        configs = db.query(NL43Config).filter_by(tcp_enabled=True).all()

        for cfg in configs:
            client = NL43Client(cfg.host, cfg.tcp_port, timeout=2.0)
            status = {
                "unit_id": cfg.unit_id,
                "host": cfg.host,
                "port": cfg.tcp_port,
                "reachable": False,
                "error": None,
            }

            try:
                # Try to connect (don't send command to avoid rate limiting issues)
                import asyncio
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(cfg.host, cfg.tcp_port), timeout=2.0
                )
                writer.close()
                await writer.wait_closed()
                status["reachable"] = True
            except Exception as e:
                status["error"] = str(type(e).__name__)
                logger.warning(f"Device {cfg.unit_id} health check failed: {e}")

            device_status.append(status)

    finally:
        db.close()

    all_reachable = all(d["reachable"] for d in device_status) if device_status else True

    return {
        "status": "ok" if all_reachable else "degraded",
        "devices": device_status,
        "total_devices": len(device_status),
        "reachable_devices": sum(1 for d in device_status if d["reachable"]),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8100")), reload=True)
