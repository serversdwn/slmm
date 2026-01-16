# SLMM - Sound Level Meter Manager

**Version 0.2.0**

Backend API service for controlling and monitoring Rion NL-43/NL-53 Sound Level Meters via TCP and FTP protocols.

## Overview

SLMM is a standalone backend module that provides REST API routing and command translation for NL43/NL53 sound level meters. This service acts as a bridge between the hardware devices and frontend applications, handling all device communication, data persistence, and protocol management.

**Note:** This is a backend-only service. Actual user interfacing is done via [SFM/Terra-View](https://github.com/your-org/terra-view) frontend applications.

## Features

- **Background Polling** ⭐ NEW: Continuous automatic polling of devices with configurable intervals
- **Offline Detection** ⭐ NEW: Automatic device reachability tracking with failure counters
- **Device Management**: Configure and manage multiple NL43/NL53 devices
- **Real-time Monitoring**: Stream live measurement data via WebSocket
- **Measurement Control**: Start, stop, pause, resume, and reset measurements
- **Data Retrieval**: Access current and historical measurement snapshots
- **FTP Integration**: Download measurement files directly from devices
- **Device Configuration**: Manage frequency/time weighting, clock sync, and more
- **Rate Limiting**: Automatic 1-second delay enforcement between device commands
- **Persistent Storage**: SQLite database for device configs and measurement cache

## Architecture

```
┌─────────────────┐         ┌──────────────────────────────┐         ┌─────────────────┐
│  Terra-View UI  │◄───────►│  SLMM API                    │◄───────►│  NL43/NL53      │
│  (Frontend)     │  HTTP   │  • REST Endpoints            │  TCP    │  Sound Meters   │
└─────────────────┘         │  • WebSocket Streaming       │         └─────────────────┘
                            │  • Background Poller ⭐ NEW  │                ▲
                            └──────────────────────────────┘                │
                                          │                         Continuous
                                          ▼                          Polling
                                  ┌──────────────┐                      │
                                  │  SQLite DB   │◄─────────────────────┘
                                  │  • Config    │
                                  │  • Status    │
                                  └──────────────┘
```

### Background Polling (v0.2.0)

SLMM now includes a background polling service that continuously queries devices and updates the status cache:

- **Automatic Updates**: Devices are polled at configurable intervals (10-3600 seconds)
- **Offline Detection**: Devices marked unreachable after 3 consecutive failures
- **Per-Device Configuration**: Each device can have a custom polling interval
- **Resource Efficient**: Dynamic sleep intervals and smart scheduling
- **Graceful Shutdown**: Background task stops cleanly on service shutdown

This makes Terra-View significantly more responsive - status requests return cached data instantly (<100ms) instead of waiting for device queries (1-2 seconds).

## Quick Start

### Prerequisites

- Python 3.10+
- pip package manager

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd slmm
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the Server

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --port 8100

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

The API will be available at `http://localhost:8100`

### API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8100/docs`
- ReDoc: `http://localhost:8100/redoc`
- Health Check: `http://localhost:8100/health`

## Configuration

### Environment Variables

- `PORT`: Server port (default: 8100)
- `CORS_ORIGINS`: Comma-separated list of allowed origins (default: "*")

### Database

The SQLite database is automatically created at [data/slmm.db](data/slmm.db) on first run.

### Logging

Logs are written to:
- Console output (stdout)
- [data/slmm.log](data/slmm.log) file

## API Endpoints

### Device Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nl43/{unit_id}/config` | Get device configuration |
| PUT | `/api/nl43/{unit_id}/config` | Update device configuration |

### Device Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nl43/{unit_id}/status` | Get cached measurement snapshot (updated by background poller) |
| GET | `/api/nl43/{unit_id}/live` | Request fresh DOD data from device (bypasses cache) |
| WS | `/api/nl43/{unit_id}/stream` | WebSocket stream for real-time DRD data |

### Background Polling Configuration ⭐ NEW

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nl43/{unit_id}/polling/config` | Get device polling configuration |
| PUT | `/api/nl43/{unit_id}/polling/config` | Update polling interval and enable/disable polling |
| GET | `/api/nl43/_polling/status` | Get global polling status for all devices |

### Measurement Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/nl43/{unit_id}/start` | Start measurement |
| POST | `/api/nl43/{unit_id}/stop` | Stop measurement |
| POST | `/api/nl43/{unit_id}/pause` | Pause measurement |
| POST | `/api/nl43/{unit_id}/resume` | Resume paused measurement |
| POST | `/api/nl43/{unit_id}/reset` | Reset measurement data |
| POST | `/api/nl43/{unit_id}/store` | Manually store data to SD card |

### Device Information

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nl43/{unit_id}/battery` | Get battery level |
| GET | `/api/nl43/{unit_id}/clock` | Get device clock time |
| PUT | `/api/nl43/{unit_id}/clock` | Set device clock time |
| GET | `/api/nl43/{unit_id}/results` | Get final calculation results (DLC) |

### Measurement Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nl43/{unit_id}/settings` | Get all current device settings for verification |
| GET | `/api/nl43/{unit_id}/frequency-weighting` | Get frequency weighting (A/C/Z) |
| PUT | `/api/nl43/{unit_id}/frequency-weighting` | Set frequency weighting |
| GET | `/api/nl43/{unit_id}/time-weighting` | Get time weighting (F/S/I) |
| PUT | `/api/nl43/{unit_id}/time-weighting` | Set time weighting |

### Sleep Mode

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/nl43/{unit_id}/sleep` | Put device into sleep mode |
| POST | `/api/nl43/{unit_id}/wake` | Wake device from sleep |
| GET | `/api/nl43/{unit_id}/sleep/status` | Get sleep mode status |

### FTP File Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/nl43/{unit_id}/ftp/enable` | Enable FTP server on device |
| POST | `/api/nl43/{unit_id}/ftp/disable` | Disable FTP server on device |
| GET | `/api/nl43/{unit_id}/ftp/status` | Get FTP server status |
| GET | `/api/nl43/{unit_id}/ftp/files` | List files on device |
| POST | `/api/nl43/{unit_id}/ftp/download` | Download file from device |

For detailed API documentation and examples, see [API.md](API.md).

## Project Structure

```
slmm/
├── app/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # FastAPI application and startup
│   ├── routers.py           # API route definitions
│   ├── models.py            # SQLAlchemy database models
│   ├── services.py          # NL43Client and business logic
│   ├── background_poller.py # Background polling service ⭐ NEW
│   └── database.py          # Database configuration
├── data/
│   ├── slmm.db              # SQLite database (auto-created)
│   ├── slmm.log             # Application logs
│   └── downloads/           # Downloaded files from devices
├── templates/
│   └── index.html           # Simple web interface (optional)
├── manuals/                 # Device documentation
├── migrate_add_polling_fields.py  # Database migration for v0.2.0 ⭐ NEW
├── test_polling.sh          # Polling feature test script ⭐ NEW
├── API.md                   # Detailed API documentation
├── COMMUNICATION_GUIDE.md   # NL43 protocol documentation
├── NL43_COMMANDS.md         # Command reference
├── CHANGELOG.md             # Version history ⭐ NEW
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Database Schema

### NL43Config Table
Stores device connection configuration:
- `unit_id` (PK): Unique device identifier
- `host`: Device IP address or hostname
- `tcp_port`: TCP control port (default: 80)
- `tcp_enabled`: Enable/disable TCP communication
- `ftp_enabled`: Enable/disable FTP functionality
- `ftp_username`: FTP authentication username
- `ftp_password`: FTP authentication password
- `web_enabled`: Enable/disable web interface access
- `poll_interval_seconds`: Polling interval in seconds (10-3600, default: 60) ⭐ NEW
- `poll_enabled`: Enable/disable background polling for this device ⭐ NEW

### NL43Status Table
Caches latest measurement snapshot:
- `unit_id` (PK): Unique device identifier
- `last_seen`: Timestamp of last update
- `measurement_state`: Current state (Measure/Stop)
- `measurement_start_time`: When measurement started (UTC)
- `counter`: Measurement interval counter (1-600)
- `lp`: Instantaneous sound pressure level
- `leq`: Equivalent continuous sound level
- `lmax`: Maximum sound level
- `lmin`: Minimum sound level
- `lpeak`: Peak sound level
- `battery_level`: Battery percentage
- `power_source`: Current power source
- `sd_remaining_mb`: Free SD card space (MB)
- `sd_free_ratio`: SD card free space ratio
- `raw_payload`: Raw device response data
- `is_reachable`: Device reachability status (Boolean) ⭐ NEW
- `consecutive_failures`: Count of consecutive poll failures ⭐ NEW
- `last_poll_attempt`: Last time background poller attempted to poll ⭐ NEW
- `last_success`: Last successful poll timestamp ⭐ NEW
- `last_error`: Last error message (truncated to 500 chars) ⭐ NEW

## Protocol Details

### TCP Communication
- Uses ASCII command protocol over TCP
- Enforces ≥1 second delay between commands to same device
- Two-line response format:
  - Line 1: Result code (R+0000 for success)
  - Line 2: Data payload (for query commands)

### FTP Communication
- Uses active mode FTP (requires device to connect back)
- TCP and FTP are mutually exclusive on the device
- Credentials configurable per device
- **Default NL43 FTP Credentials**: Username: `USER`, Password: `0000`

### Data Formats

**DOD (Data Output Display)**: Snapshot of current display values
**DRD (Data Real-time Display)**: Continuous streaming data
**DLC (Data Last Calculation)**: Final stored measurement results

## Example Usage

### Configure a Device
```bash
curl -X PUT http://localhost:8100/api/nl43/meter-001/config \
  -H "Content-Type: application/json" \
  -d '{
    "host": "192.168.1.100",
    "tcp_port": 2255,
    "tcp_enabled": true,
    "ftp_enabled": true,
    "ftp_username": "USER",
    "ftp_password": "0000"
  }'
```

### Start Measurement
```bash
curl -X POST http://localhost:8100/api/nl43/meter-001/start
```

### Get Cached Status (Fast - from background poller)
```bash
curl http://localhost:8100/api/nl43/meter-001/status
```

### Get Live Status (Bypasses cache)
```bash
curl http://localhost:8100/api/nl43/meter-001/live
```

### Configure Background Polling ⭐ NEW
```bash
# Set polling interval to 30 seconds
curl -X PUT http://localhost:8100/api/nl43/meter-001/polling/config \
  -H "Content-Type: application/json" \
  -d '{
    "poll_interval_seconds": 30,
    "poll_enabled": true
  }'

# Get polling configuration
curl http://localhost:8100/api/nl43/meter-001/polling/config

# Check global polling status
curl http://localhost:8100/api/nl43/_polling/status
```

### Verify Device Settings
```bash
curl http://localhost:8100/api/nl43/meter-001/settings
```

This returns all current device configuration:
```json
{
  "status": "ok",
  "unit_id": "meter-001",
  "settings": {
    "measurement_state": "Stop",
    "frequency_weighting": "A",
    "time_weighting": "F",
    "measurement_time": "00:01:00",
    "leq_interval": "1s",
    "lp_interval": "125ms",
    "index_number": "0",
    "battery_level": "100%",
    "clock": "2025/12/24,20:45:30",
    "sleep_mode": "Off",
    "ftp_status": "On"
  }
}
```

### Stream Real-time Data (JavaScript)
```javascript
const ws = new WebSocket('ws://localhost:8100/api/nl43/meter-001/stream');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Live measurement:', data);
};
```

### Download Files via FTP
```bash
# Enable FTP
curl -X POST http://localhost:8100/api/nl43/meter-001/ftp/enable

# List files
curl http://localhost:8100/api/nl43/meter-001/ftp/files?path=/NL43_DATA

# Download file
curl -X POST http://localhost:8100/api/nl43/meter-001/ftp/download \
  -H "Content-Type: application/json" \
  -d '{"remote_path": "/NL43_DATA/measurement.wav"}' \
  --output measurement.wav

# Disable FTP
curl -X POST http://localhost:8100/api/nl43/meter-001/ftp/disable
```

## Integration with Terra-View

This backend is designed to be consumed by the Terra-View frontend application. The frontend should:

1. Use the config endpoints to register and configure devices
2. Poll or stream live status for real-time monitoring
3. Use control endpoints to manage measurements
4. Download files via FTP endpoints for analysis

See [API.md](API.md) for detailed integration examples.

## Troubleshooting

### Connection Issues
- Verify device IP address and port in configuration
- Ensure device is on the same network
- Check firewall rules allow TCP/FTP connections
- Verify RX55 network adapter is properly configured on device

### Rate Limiting
- API automatically enforces 1-second delay between commands
- If experiencing delays, this is normal device behavior
- Multiple devices can be controlled in parallel

### FTP Active Mode
- Ensure server can accept incoming connections from device
- FTP uses active mode (device connects back to server)
- May require firewall configuration for data channel

### WebSocket Disconnects
- WebSocket streams maintain persistent connection
- Limit concurrent streams to avoid device overload
- Connection will auto-close if device stops responding

## Development

### Running Tests
```bash
# Add test commands when implemented
pytest
```

### Database Migrations
```bash
# Migrate to v0.2.0 (add background polling fields)
python3 migrate_add_polling_fields.py

# Legacy: Migrate to add FTP credentials
python migrate_add_ftp_credentials.py

# Set FTP credentials for a device
python set_ftp_credentials.py <unit_id> <username> <password>
```

### Testing Background Polling
```bash
# Run comprehensive polling tests
./test_polling.sh [unit_id]

# Test settings endpoint
python3 test_settings_endpoint.py <unit_id>

# Test sleep mode auto-disable
python3 test_sleep_mode_auto_disable.py <unit_id>
```

### Legacy Scripts
Old migration scripts and manual polling tools have been moved to `archive/` for reference. See [archive/README.md](archive/README.md) for details.

## Contributing

This is a standalone module kept separate from the SFM/Terra-View codebase. When contributing:

1. Maintain separation from frontend code
2. Follow existing API patterns and error handling
3. Update API documentation for new endpoints
4. Ensure rate limiting is enforced for device commands

## License

[Specify license here]

## Related Documentation

- [API.md](API.md) - Complete API reference with examples
- [COMMUNICATION_GUIDE.md](COMMUNICATION_GUIDE.md) - NL43 protocol details
- [NL43_COMMANDS.md](NL43_COMMANDS.md) - Device command reference
- [manuals/](manuals/) - Device manufacturer documentation

## Support

For issues and questions:
- Backend API issues: This repository
- Frontend/UI issues: Terra-View repository
- Device protocol questions: See COMMUNICATION_GUIDE.md
