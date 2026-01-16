# Standalone UI Update: Get ALL Settings Button

## What Was Added

A new **"Get ALL Settings"** button has been added to the standalone web UI at [templates/index.html](templates/index.html).

## Location

The button is located in the **Measurement Settings** fieldset, at the top before the individual frequency and time weighting controls.

## Visual Layout

```
┌─────────────────────────────────────────────────────┐
│ Measurement Settings                                 │
├─────────────────────────────────────────────────────┤
│                                                      │
│  [Get ALL Settings]  ← NEW BUTTON (bold styling)    │
│                                                      │
│  Frequency Weighting:                               │
│  [Get] [Set A] [Set C] [Set Z]                      │
│                                                      │
│  Time Weighting:                                    │
│  [Get] [Set Fast] [Set Slow] [Set Impulse]          │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Functionality

When clicked, the button:

1. **Shows loading message**: "Retrieving all device settings (this may take 10-15 seconds)..."

2. **Calls API**: `GET /api/nl43/{unit_id}/settings`

3. **Displays results in two places**:
   - **Status area** (top): Shows formatted JSON with all settings
   - **Log area** (bottom): Shows each setting on a separate line

## Example Output

### Status Area Display
```json
{
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
```

### Log Area Display
```
Retrieving all device settings (this may take 10-15 seconds)...
=== ALL DEVICE SETTINGS ===
measurement_state: Stop
frequency_weighting: A
time_weighting: F
measurement_time: 00:01:00
leq_interval: 1s
lp_interval: 125ms
index_number: 0
battery_level: 100%
clock: 2025/12/24,20:45:30
sleep_mode: Off
ftp_status: On
===========================
```

## Code Changes

### HTML Changes (Line 60)
```html
<button onclick="getAllSettings()" style="margin-bottom: 12px; font-weight: bold;">
  Get ALL Settings
</button>
```

### JavaScript Changes (Lines 284-305)
```javascript
async function getAllSettings() {
  const unitId = document.getElementById('unitId').value;
  log('Retrieving all device settings (this may take 10-15 seconds)...');

  const res = await fetch(`/api/nl43/${unitId}/settings`);
  const data = await res.json();

  if (!res.ok) {
    log(`Get All Settings failed: ${res.status} - ${data.detail || JSON.stringify(data)}`);
    return;
  }

  // Display in status area
  statusEl.textContent = JSON.stringify(data.settings, null, 2);

  // Log summary
  log('=== ALL DEVICE SETTINGS ===');
  Object.entries(data.settings).forEach(([key, value]) => {
    log(`${key}: ${value}`);
  });
  log('===========================');
}
```

## Usage Flow

1. **Configure device** using the "Unit Config" section
2. **Click "Get ALL Settings"** to retrieve current configuration
3. **Review settings** in the Status and Log areas
4. **Verify** critical settings match requirements before starting measurements

## Benefits

✓ **Quick verification** - One click to see all device settings
✓ **Pre-measurement check** - Ensure device is configured correctly
✓ **Debugging** - Identify misconfigured settings easily
✓ **Documentation** - Copy settings from status area for records
✓ **Comparison** - Compare settings across multiple devices

## Error Handling

If the request fails:
- Error message is displayed in the log
- Status code and details are shown
- Previous status display is preserved

Example error output:
```
Retrieving all device settings (this may take 10-15 seconds)...
Get All Settings failed: 502 - Failed to communicate with device
```

## Testing the Feature

1. **Start the SLMM server**:
   ```bash
   cd /home/serversdown/slmm
   uvicorn app.main:app --reload --port 8100
   ```

2. **Open the standalone UI**:
   ```
   http://localhost:8100
   ```

3. **Configure a device**:
   - Enter Unit ID (e.g., "nl43-1")
   - Enter Host IP (e.g., "192.168.1.100")
   - Enter Port (e.g., "80")
   - Click "Save Config"

4. **Test the new button**:
   - Click "Get ALL Settings"
   - Wait 10-15 seconds for results
   - Review settings in Status and Log areas

## Related Files

- [templates/index.html](templates/index.html) - Standalone UI (updated)
- [app/routers.py](app/routers.py#L728-L761) - Settings endpoint
- [app/services.py](app/services.py#L538-L606) - Client implementation
- [README.md](README.md) - Main documentation
- [SETTINGS_ENDPOINT.md](SETTINGS_ENDPOINT.md) - API documentation
