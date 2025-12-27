# SLMM API Documentation

REST API for controlling Rion NL-43/NL-53 Sound Level Meters via TCP and FTP.

Base URL: `http://localhost:8000/api/nl43`

All endpoints require a `unit_id` parameter identifying the device.

## Device Configuration

### Get Device Config
```
GET /{unit_id}/config
```
Returns the device configuration including host, port, and enabled protocols.

**Response:**
```json
{
  "status": "ok",
  "data": {
    "unit_id": "nl43-1",
    "host": "192.168.1.100",
    "tcp_port": 2255,
    "tcp_enabled": true,
    "ftp_enabled": false,
    "web_enabled": false
  }
}
```

### Update Device Config
```
PUT /{unit_id}/config
```
Update device configuration.

**Request Body:**
```json
{
  "host": "192.168.1.100",
  "tcp_port": 2255,
  "tcp_enabled": true,
  "ftp_enabled": false,
  "ftp_username": "admin",
  "ftp_password": "password",
  "web_enabled": false
}
```

## Device Status

### Get Cached Status
```
GET /{unit_id}/status
```
Returns the last cached measurement snapshot from the database.

### Get Live Status
```
GET /{unit_id}/live
```
Requests fresh DOD (Display On Demand) data from the device and returns current measurements.

**Response:**
```json
{
  "status": "ok",
  "data": {
    "unit_id": "nl43-1",
    "measurement_state": "Measure",
    "lp": "65.2",
    "leq": "68.4",
    "lmax": "82.1",
    "lmin": "42.3",
    "lpeak": "89.5",
    "battery_level": "80",
    "power_source": "Battery",
    "sd_remaining_mb": "2048",
    "sd_free_ratio": "50"
  }
}
```

### Stream Live Data (WebSocket)
```
WS /{unit_id}/live
```
Opens a WebSocket connection and streams continuous DRD (Display Real-time Data) from the device.

## Measurement Control

### Start Measurement
```
POST /{unit_id}/start
```
Starts measurement on the device.

### Stop Measurement
```
POST /{unit_id}/stop
```
Stops measurement on the device.

### Pause Measurement
```
POST /{unit_id}/pause
```
Pauses the current measurement.

### Resume Measurement
```
POST /{unit_id}/resume
```
Resumes a paused measurement.

### Reset Measurement
```
POST /{unit_id}/reset
```
Resets the measurement data.

### Get Measurement State
```
GET /{unit_id}/measurement-state
```
Gets the current measurement state to determine if the device is actively measuring.

**Response:**
```json
{
  "status": "ok",
  "measurement_state": "Start",
  "is_measuring": true
}
```

**Values:**
- `measurement_state`: "Start" (measuring) or "Stop" (not measuring)
- `is_measuring`: Boolean convenience field (true if measuring, false otherwise)

**Note:** Elapsed time and interval counts are displayed on the device OSD but not available via command. Track elapsed time in your application by recording the start time when you call the `/start` endpoint.

### Manual Store
```
POST /{unit_id}/store
```
Manually stores the current measurement data.

## Device Information

### Get Battery Level
```
GET /{unit_id}/battery
```
Returns the battery level.

**Response:**
```json
{
  "status": "ok",
  "battery_level": "80"
}
```

### Get Clock
```
GET /{unit_id}/clock
```
Returns the device clock time.

**Response:**
```json
{
  "status": "ok",
  "clock": "2025/12/24,02:30:15"
}
```

### Set Clock
```
PUT /{unit_id}/clock
```
Sets the device clock time.

**Request Body:**
```json
{
  "datetime": "2025/12/24,02:30:15"
}
```

## Measurement Settings

### Get Frequency Weighting
```
GET /{unit_id}/frequency-weighting?channel=Main
```
Gets the frequency weighting (A, C, or Z) for a channel.

**Query Parameters:**
- `channel` (optional): Main, Sub1, Sub2, or Sub3 (default: Main)

**Response:**
```json
{
  "status": "ok",
  "frequency_weighting": "A",
  "channel": "Main"
}
```

### Set Frequency Weighting
```
PUT /{unit_id}/frequency-weighting
```
Sets the frequency weighting.

**Request Body:**
```json
{
  "weighting": "A",
  "channel": "Main"
}
```

### Get Time Weighting
```
GET /{unit_id}/time-weighting?channel=Main
```
Gets the time weighting (F, S, or I) for a channel.

**Query Parameters:**
- `channel` (optional): Main, Sub1, Sub2, or Sub3 (default: Main)

**Response:**
```json
{
  "status": "ok",
  "time_weighting": "F",
  "channel": "Main"
}
```

### Set Time Weighting
```
PUT /{unit_id}/time-weighting
```
Sets the time weighting.

**Request Body:**
```json
{
  "weighting": "F",
  "channel": "Main"
}
```

**Values:**
- `F` - Fast (125ms)
- `S` - Slow (1s)
- `I` - Impulse (35ms)

## Timing and Interval Configuration

### Get Measurement Time
```
GET /{unit_id}/measurement-time
```
Gets the current measurement time preset.

**Response:**
```json
{
  "status": "ok",
  "measurement_time": "1h"
}
```

### Set Measurement Time
```
PUT /{unit_id}/measurement-time
```
Sets the measurement time preset.

**Request Body:**
```json
{
  "preset": "1h"
}
```

**Preset Values:**
- `10s`, `1m`, `5m`, `10m`, `15m`, `30m`, `1h`, `8h`, `24h`
- Custom format: `HH:MM:SS` (e.g., `00:05:30` for 5.5 minutes)

### Get Leq Calculation Interval
```
GET /{unit_id}/leq-interval
```
Gets the current Leq calculation interval.

**Response:**
```json
{
  "status": "ok",
  "leq_interval": "1m"
}
```

### Set Leq Calculation Interval
```
PUT /{unit_id}/leq-interval
```
Sets the Leq calculation interval preset.

**Request Body:**
```json
{
  "preset": "1m"
}
```

**Preset Values:**
- `Off`, `10s`, `1m`, `5m`, `10m`, `15m`, `30m`, `1h`, `8h`, `24h`
- Custom format: `HH:MM:SS` (e.g., `00:05:30` for 5.5 minutes)

### Get Lp Store Interval
```
GET /{unit_id}/lp-interval
```
Gets the current Lp store interval.

**Response:**
```json
{
  "status": "ok",
  "lp_interval": "1s"
}
```

### Set Lp Store Interval
```
PUT /{unit_id}/lp-interval
```
Sets the Lp store interval.

**Request Body:**
```json
{
  "preset": "1s"
}
```

**Preset Values:**
- `Off`, `10ms`, `25ms`, `100ms`, `200ms`, `1s`

### Get Index Number
```
GET /{unit_id}/index-number
```
Gets the current index number for file numbering.

**Response:**
```json
{
  "status": "ok",
  "index_number": "0042"
}
```

### Set Index Number
```
PUT /{unit_id}/index-number
```
Sets the index number for file numbering. This number is incremented with each measurement and used in file names.

**Request Body:**
```json
{
  "index": 42
}
```

**Valid Range:** 0000 to 9999

## Device Settings Query

### Get All Settings
```
GET /{unit_id}/settings/all
```
Retrieves all current device settings for verification. This is useful for confirming device configuration before starting measurements.

**Response:**
```json
{
  "status": "ok",
  "settings": {
    "measurement_state": "Stop",
    "frequency_weighting": "A",
    "time_weighting": "F",
    "measurement_time": "1h",
    "leq_interval": "1m",
    "lp_interval": "1s",
    "index_number": "0042",
    "battery_level": "80",
    "clock": "2025/12/24,02:30:15",
    "sleep_mode": "Off",
    "ftp_status": "Off"
  }
}
```

**Note:** If any setting query fails, the error message will be included in the response for that setting (e.g., `"frequency_weighting": "Error: Connection timeout"`).

## Data Retrieval

### Get Final Results
```
GET /{unit_id}/results
```
Retrieves the final calculation results (DLC) from the last completed measurement.

**Response:**
```json
{
  "status": "ok",
  "data": {
    "leq": "68.4",
    "lmax": "82.1",
    "lmin": "42.3",
    "lpeak": "89.5"
  }
}
```

## Power Management

### Sleep Device
```
POST /{unit_id}/sleep
```
Enables Sleep Mode on the device. When enabled, the device will automatically enter sleep mode between Timer Auto measurements.

**Note:** This is a SETTING, not a command to sleep immediately. Sleep Mode only applies when using Timer Auto measurements.

### Wake Device
```
POST /{unit_id}/wake
```
Disables Sleep Mode on the device.

### Get Sleep Status
```
GET /{unit_id}/sleep/status
```
Gets the current Sleep Mode status.

**Response:**
```json
{
  "status": "ok",
  "sleep_mode": "Off"
}
```

## FTP File Management

### Enable FTP
```
POST /{unit_id}/ftp/enable
```
Enables FTP server on the device.

**Note:** FTP and TCP are mutually exclusive. Enabling FTP will temporarily disable TCP control.

### Disable FTP
```
POST /{unit_id}/ftp/disable
```
Disables FTP server on the device.

### Get FTP Status
```
GET /{unit_id}/ftp/status
```
Checks if FTP is enabled on the device.

**Response:**
```json
{
  "status": "ok",
  "ftp_status": "On",
  "ftp_enabled": true
}
```

### List Files
```
GET /{unit_id}/ftp/files?path=/
```
Lists files and directories at the specified path.

**Query Parameters:**
- `path` (optional): Directory path to list (default: /)

**Response:**
```json
{
  "status": "ok",
  "path": "/NL43_DATA/",
  "count": 3,
  "files": [
    {
      "name": "measurement_001.wav",
      "path": "/NL43_DATA/measurement_001.wav",
      "size": 102400,
      "modified": "Dec 24 2025",
      "is_dir": false
    },
    {
      "name": "folder1",
      "path": "/NL43_DATA/folder1",
      "size": 0,
      "modified": "Dec 23 2025",
      "is_dir": true
    }
  ]
}
```

### Download File
```
POST /{unit_id}/ftp/download
```
Downloads a file from the device via FTP.

**Request Body:**
```json
{
  "remote_path": "/NL43_DATA/measurement_001.wav"
}
```

**Response:**
Returns the file as a binary download with appropriate `Content-Disposition` header.

## Error Responses

All endpoints return standard HTTP status codes:

- `200` - Success
- `404` - Device config not found
- `403` - TCP communication is disabled
- `502` - Failed to communicate with device
- `504` - Device communication timeout
- `500` - Internal server error

**Error Response Format:**
```json
{
  "detail": "Error message"
}
```

## Common Patterns

### Terra-view Integration Example

```javascript
const devices = ['nl43-1', 'nl43-2', 'nl43-3'];

// Configure all devices before measurement
for (const device of devices) {
  // Set measurement time to 12 hours
  await fetch(`http://localhost:8000/api/nl43/${device}/measurement-time`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset: '12h' })
  });

  // Set Leq interval to 1 minute
  await fetch(`http://localhost:8000/api/nl43/${device}/leq-interval`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset: '1m' })
  });

  // Set index number for daily file organization
  const dayNumber = new Date().getDate();
  await fetch(`http://localhost:8000/api/nl43/${device}/index-number`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index: dayNumber })
  });

  // Verify all settings are correct
  const settings = await fetch(`http://localhost:8000/api/nl43/${device}/settings/all`)
    .then(r => r.json());
  console.log(`Device ${device} settings:`, settings.settings);
}

// Start measurement on all devices at 7pm
await Promise.all(
  devices.map(id =>
    fetch(`http://localhost:8000/api/nl43/${id}/start`, { method: 'POST' })
  )
);

// Get live status from all devices
const statuses = await Promise.all(
  devices.map(id =>
    fetch(`http://localhost:8000/api/nl43/${id}/live`)
      .then(r => r.json())
  )
);

// Download files from all devices the next morning
for (const device of devices) {
  // Enable FTP
  await fetch(`http://localhost:8000/api/nl43/${device}/ftp/enable`, {
    method: 'POST'
  });

  // List files in device data directory
  const res = await fetch(`http://localhost:8000/api/nl43/${device}/ftp/files?path=/NL43_DATA`);
  const { files } = await res.json();

  // Download latest measurement file
  const latestFile = files
    .filter(f => !f.is_dir)
    .sort((a, b) => b.modified - a.modified)[0];

  if (latestFile) {
    const download = await fetch(`http://localhost:8000/api/nl43/${device}/ftp/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remote_path: latestFile.path })
    });

    const blob = await download.blob();
    // Save to local storage or process...
  }

  // Disable FTP to re-enable TCP
  await fetch(`http://localhost:8000/api/nl43/${device}/ftp/disable`, {
    method: 'POST'
  });
}
```

## Rate Limiting

The NL43 protocol requires ≥1 second between commands to the same device. The API automatically enforces this rate limit.

## Notes

- TCP and FTP protocols are mutually exclusive on the device
- FTP uses active mode (requires device to connect back to server)
- WebSocket streaming keeps a persistent connection - limit concurrent streams
- All measurements are stored in the database for quick access via `/status` endpoint
