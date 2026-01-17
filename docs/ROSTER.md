# SLMM Roster Management

The SLMM standalone application now includes a roster management interface for viewing and configuring all Sound Level Meter devices.

## Features

### Web Interface

Access the roster at: **http://localhost:8100/roster**

The roster page provides:

- **Device List Table**: View all configured SLMs with their connection details
- **Real-time Status**: See device connectivity status (Online/Offline/Stale)
- **Add Device**: Create new device configurations with a user-friendly modal form
- **Edit Device**: Modify existing device configurations
- **Delete Device**: Remove device configurations (does not affect physical devices)
- **Test Connection**: Run diagnostics on individual devices

### Table Columns

| Column | Description |
|--------|-------------|
| Unit ID | Unique identifier for the device |
| Host / IP | Device IP address or hostname |
| TCP Port | TCP control port (default: 2255) |
| FTP Port | FTP file transfer port (default: 21) |
| TCP | Whether TCP control is enabled |
| FTP | Whether FTP file transfer is enabled |
| Polling | Whether background polling is enabled |
| Status | Device connectivity status (Online/Offline/Stale) |
| Actions | Test, Edit, Delete buttons |

### Status Indicators

- **Online** (green): Device responded within the last 5 minutes
- **Stale** (yellow): Device hasn't responded recently but was seen before
- **Offline** (red): Device is unreachable or has consecutive failures
- **Unknown** (gray): No status data available yet

## API Endpoints

### List All Devices

```bash
GET /api/nl43/roster
```

Returns all configured devices with their status information.

**Response:**
```json
{
  "status": "ok",
  "devices": [
    {
      "unit_id": "SLM-43-01",
      "host": "192.168.1.100",
      "tcp_port": 2255,
      "ftp_port": 21,
      "tcp_enabled": true,
      "ftp_enabled": true,
      "ftp_username": "USER",
      "ftp_password": "0000",
      "web_enabled": false,
      "poll_enabled": true,
      "poll_interval_seconds": 60,
      "status": {
        "last_seen": "2026-01-16T20:00:00",
        "measurement_state": "Start",
        "is_reachable": true,
        "consecutive_failures": 0,
        "last_success": "2026-01-16T20:00:00",
        "last_error": null
      }
    }
  ],
  "total": 1
}
```

### Create New Device

```bash
POST /api/nl43/roster
Content-Type: application/json

{
  "unit_id": "SLM-43-01",
  "host": "192.168.1.100",
  "tcp_port": 2255,
  "ftp_port": 21,
  "tcp_enabled": true,
  "ftp_enabled": false,
  "poll_enabled": true,
  "poll_interval_seconds": 60
}
```

**Required Fields:**
- `unit_id`: Unique device identifier
- `host`: IP address or hostname

**Optional Fields:**
- `tcp_port`: TCP control port (default: 2255)
- `ftp_port`: FTP port (default: 21)
- `tcp_enabled`: Enable TCP control (default: true)
- `ftp_enabled`: Enable FTP transfers (default: false)
- `ftp_username`: FTP username (only if ftp_enabled)
- `ftp_password`: FTP password (only if ftp_enabled)
- `poll_enabled`: Enable background polling (default: true)
- `poll_interval_seconds`: Polling interval 10-3600 seconds (default: 60)

**Response:**
```json
{
  "status": "ok",
  "message": "Device SLM-43-01 created successfully",
  "data": {
    "unit_id": "SLM-43-01",
    "host": "192.168.1.100",
    "tcp_port": 2255,
    "tcp_enabled": true,
    "ftp_enabled": false,
    "poll_enabled": true,
    "poll_interval_seconds": 60
  }
}
```

### Update Device

```bash
PUT /api/nl43/{unit_id}/config
Content-Type: application/json

{
  "host": "192.168.1.101",
  "tcp_port": 2255,
  "poll_interval_seconds": 120
}
```

All fields are optional. Only include fields you want to update.

### Delete Device

```bash
DELETE /api/nl43/{unit_id}/config
```

Removes the device configuration and associated status data. Does not affect the physical device.

**Response:**
```json
{
  "status": "ok",
  "message": "Deleted device SLM-43-01"
}
```

## Usage Examples

### Via Web Interface

1. Navigate to http://localhost:8100/roster
2. Click "Add Device" to create a new configuration
3. Fill in the device details (unit ID, IP address, ports)
4. Configure TCP, FTP, and polling settings
5. Click "Save Device"
6. Use "Test" button to verify connectivity
7. Edit or delete devices as needed

### Via API (curl)

**Add a new device:**
```bash
curl -X POST http://localhost:8100/api/nl43/roster \
  -H "Content-Type: application/json" \
  -d '{
    "unit_id": "slm-site-a",
    "host": "192.168.1.100",
    "tcp_port": 2255,
    "tcp_enabled": true,
    "ftp_enabled": true,
    "ftp_username": "USER",
    "ftp_password": "0000",
    "poll_enabled": true,
    "poll_interval_seconds": 60
  }'
```

**Update device host:**
```bash
curl -X PUT http://localhost:8100/api/nl43/slm-site-a/config \
  -H "Content-Type: application/json" \
  -d '{"host": "192.168.1.101"}'
```

**Delete device:**
```bash
curl -X DELETE http://localhost:8100/api/nl43/slm-site-a/config
```

**List all devices:**
```bash
curl http://localhost:8100/api/nl43/roster | python3 -m json.tool
```

## Integration with Terra-View

When SLMM is used as a module within Terra-View:

1. Terra-View manages device configurations in its own database
2. Terra-View syncs configurations to SLMM via `PUT /api/nl43/{unit_id}/config`
3. Terra-View can query device status via `GET /api/nl43/{unit_id}/status`
4. SLMM's roster page can be used for standalone testing and diagnostics

## Background Polling

Devices with `poll_enabled: true` are automatically polled at their configured interval:

- Polls device status every `poll_interval_seconds` (10-3600 seconds)
- Updates `NL43Status` table with latest measurements
- Tracks device reachability and failure counts
- Provides real-time status updates in the roster

**Note**: Polling respects the NL43 protocol's 1-second rate limit between commands.

## Validation

The roster system validates:

- **Unit ID**: Must be unique across all devices
- **Host**: Valid IP address or hostname format
- **Ports**: Must be between 1-65535
- **Poll Interval**: Must be between 10-3600 seconds
- **Duplicate Check**: Returns 409 Conflict if unit_id already exists

## Notes

- Deleting a device from the roster does NOT affect the physical device
- Device configurations are stored in the SLMM database (`data/slmm.db`)
- Status information is updated by the background polling system
- The roster page auto-refreshes status indicators
- Test button runs full diagnostics (connectivity, TCP, FTP if enabled)
