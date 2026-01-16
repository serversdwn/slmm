# Device Settings Verification Endpoint

## Overview

The new `GET /api/nl43/{unit_id}/settings` endpoint provides a comprehensive view of all current device settings. This allows you to quickly verify the configuration of your NL43/NL53 sound level meter before starting measurements, ensuring the device is configured correctly for your testing requirements.

## Endpoint Details

**URL:** `GET /api/nl43/{unit_id}/settings`

**Description:** Retrieves all queryable settings from the device in a single request.

**Response Time:** Approximately 10-15 seconds (due to required 1-second delay between device commands)

## Settings Retrieved

The endpoint queries the following categories of settings:

### Measurement Configuration
- **measurement_state**: Current state (Measure, Stop, Pause)
- **frequency_weighting**: Frequency weighting (A, C, or Z)
- **time_weighting**: Time weighting (F=Fast, S=Slow, I=Impulse)

### Timing and Intervals
- **measurement_time**: Total measurement duration setting
- **leq_interval**: Leq calculation interval
- **lp_interval**: Lp sampling interval
- **index_number**: Current index/file number for storage

### Device Information
- **battery_level**: Current battery percentage
- **clock**: Device clock time (format: YYYY/MM/DD,HH:MM:SS)

### Operational Status
- **sleep_mode**: Sleep mode status (On/Off)
- **ftp_status**: FTP server status (On/Off)

## Usage Examples

### Basic Request

```bash
curl http://localhost:8100/api/nl43/NL43-001/settings
```

### Response Format

```json
{
  "status": "ok",
  "unit_id": "NL43-001",
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

### Error Handling

Individual settings that fail to query will show an error message instead of a value:

```json
{
  "status": "ok",
  "unit_id": "NL43-001",
  "settings": {
    "measurement_state": "Stop",
    "frequency_weighting": "A",
    "time_weighting": "Error: Status error - device is in wrong state for this command",
    ...
  }
}
```

This partial error handling ensures you get as much information as possible even if some settings fail to query.

## Common Use Cases

### Pre-Measurement Verification

Before starting a measurement session, verify all critical settings:

```bash
# Get all settings
SETTINGS=$(curl -s http://localhost:8100/api/nl43/meter-001/settings)

# Extract specific values (using jq)
FREQ_WEIGHT=$(echo $SETTINGS | jq -r '.settings.frequency_weighting')
TIME_WEIGHT=$(echo $SETTINGS | jq -r '.settings.time_weighting')

echo "Frequency: $FREQ_WEIGHT, Time: $TIME_WEIGHT"
```

### Configuration Audit

Document device configuration for quality assurance:

```bash
# Save settings snapshot
curl http://localhost:8100/api/nl43/meter-001/settings > config_snapshot_$(date +%Y%m%d_%H%M%S).json
```

### Multi-Device Comparison

Compare settings across multiple devices:

```bash
# Compare two devices
curl http://localhost:8100/api/nl43/meter-001/settings > device1.json
curl http://localhost:8100/api/nl43/meter-002/settings > device2.json
diff device1.json device2.json
```

## Integration Examples

### Python

```python
import requests

def verify_device_settings(unit_id: str) -> dict:
    """Retrieve and verify device settings."""
    response = requests.get(f"http://localhost:8100/api/nl43/{unit_id}/settings")
    response.raise_for_status()

    data = response.json()
    settings = data["settings"]

    # Verify critical settings
    assert settings["frequency_weighting"] == "A", "Wrong frequency weighting!"
    assert settings["time_weighting"] == "F", "Wrong time weighting!"

    return settings

# Usage
settings = verify_device_settings("NL43-001")
print(f"Battery: {settings['battery_level']}")
print(f"Clock: {settings['clock']}")
```

### JavaScript/TypeScript

```typescript
interface DeviceSettings {
  measurement_state: string;
  frequency_weighting: string;
  time_weighting: string;
  measurement_time: string;
  leq_interval: string;
  lp_interval: string;
  index_number: string;
  battery_level: string;
  clock: string;
  sleep_mode: string;
  ftp_status: string;
}

async function getDeviceSettings(unitId: string): Promise<DeviceSettings> {
  const response = await fetch(`http://localhost:8100/api/nl43/${unitId}/settings`);
  const data = await response.json();

  if (data.status !== "ok") {
    throw new Error("Failed to retrieve settings");
  }

  return data.settings;
}

// Usage
const settings = await getDeviceSettings("NL43-001");
console.log(`Frequency weighting: ${settings.frequency_weighting}`);
console.log(`Battery level: ${settings.battery_level}`);
```

## Performance Considerations

### Query Duration

The endpoint queries multiple settings sequentially with required 1-second delays between commands. Total query time depends on:
- Number of settings queried (~10-12 settings)
- Network latency
- Device response time

**Expected duration:** 10-15 seconds

### Caching Strategy

For applications that need frequent access to settings:

1. **Cache results** - Settings don't change frequently unless you modify them
2. **Refresh periodically** - Query every 5-10 minutes or on-demand
3. **Track changes** - Re-query after sending configuration commands

### Rate Limiting

The endpoint respects device rate limiting (1-second delay between commands). Concurrent requests to the same device will be serialized automatically.

## Best Practices

1. **Pre-flight check**: Always verify settings before starting critical measurements
2. **Document configuration**: Save settings snapshots for audit trails
3. **Monitor battery**: Check battery level to avoid measurement interruption
4. **Sync clocks**: Verify device clock is accurate for timestamped data
5. **Error handling**: Check for "Error:" prefixes in individual setting values

## Related Endpoints

- `GET /api/nl43/{unit_id}/frequency-weighting` - Get single frequency weighting setting
- `PUT /api/nl43/{unit_id}/frequency-weighting` - Set frequency weighting
- `GET /api/nl43/{unit_id}/time-weighting` - Get single time weighting setting
- `PUT /api/nl43/{unit_id}/time-weighting` - Set time weighting
- `GET /api/nl43/{unit_id}/battery` - Get battery level only
- `GET /api/nl43/{unit_id}/clock` - Get device clock only

## Troubleshooting

### Slow Response

**Problem:** Endpoint takes longer than expected

**Solutions:**
- Normal behavior due to rate limiting (1 second between commands)
- Check network connectivity
- Verify device is not in sleep mode

### Partial Errors

**Problem:** Some settings show "Error:" messages

**Solutions:**
- Device may be in wrong state for certain queries
- Check if measurement is running (some settings require stopped state)
- Verify firmware version supports all queried commands

### Connection Timeout

**Problem:** 504 Gateway Timeout error

**Solutions:**
- Verify device IP address and port in configuration
- Check if device is powered on and connected
- Ensure TCP communication is enabled in device config

## See Also

- [README.md](README.md) - Main documentation
- [API.md](API.md) - Complete API reference
- [COMMUNICATION_GUIDE.md](COMMUNICATION_GUIDE.md) - NL43 protocol details
