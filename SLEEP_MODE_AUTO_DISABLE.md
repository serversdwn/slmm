# Sleep Mode Auto-Disable Feature

## Problem Statement

NL-43/NL-53 sound level meters have a sleep/eco mode feature that conserves battery power. However, when these devices enter sleep mode, **they turn off TCP communications**, which completely breaks remote monitoring and control capabilities. This makes it impossible to:

- Query device status remotely
- Start/stop measurements
- Stream real-time data
- Download files via FTP
- Perform any remote management tasks

This is particularly problematic in deployed scenarios where physical access to devices is limited or impossible.

## Solution

SLMM now automatically disables sleep mode in two key scenarios:

### 1. Device Configuration
When a device configuration is created or updated with TCP enabled, SLMM automatically:
- Checks the current sleep mode status on the device
- Disables sleep mode if it's enabled
- Logs the operation for visibility

**Endpoint:** `PUT /api/nl43/{unit_id}/config`

### 2. Measurement Start
Before starting any measurement, SLMM:
- Proactively disables sleep mode
- Ensures TCP remains active throughout the measurement session
- Allows remote monitoring to work reliably

**Endpoint:** `POST /api/nl43/{unit_id}/start`

## Implementation Details

### Helper Function
A new async helper function was added to [app/routers.py](app/routers.py:21-38):

```python
async def ensure_sleep_mode_disabled(client: NL43Client, unit_id: str):
    """
    Helper function to ensure sleep mode is disabled on the device.
    Sleep/eco mode turns off TCP communications, preventing remote monitoring.
    This should be called when configuring a device or starting measurements.
    """
    try:
        current_status = await client.get_sleep_status()
        logger.info(f"Current sleep mode status for {unit_id}: {current_status}")

        # If sleep mode is on, disable it
        if "On" in current_status or "on" in current_status:
            logger.info(f"Sleep mode is enabled on {unit_id}, disabling it to maintain TCP connectivity")
            await client.wake()
            logger.info(f"Successfully disabled sleep mode on {unit_id}")
        else:
            logger.info(f"Sleep mode already disabled on {unit_id}")
    except Exception as e:
        logger.warning(f"Could not verify/disable sleep mode on {unit_id}: {e}")
        # Don't raise - we want configuration to succeed even if sleep mode check fails
```

### Non-Blocking Design
The sleep mode check is **non-blocking**:
- If the device is unreachable, the operation logs a warning but continues
- Configuration updates succeed even if sleep mode can't be verified
- Measurement starts proceed even if sleep mode check fails
- This prevents device communication issues from blocking critical operations

### Logging
All sleep mode operations are logged with appropriate levels:
- **INFO**: Successful operations and status checks
- **WARNING**: Failed operations (device unreachable, timeout, etc.)

Example logs:
```
2026-01-14 18:37:12,889 - app.routers - INFO - TCP enabled for test-nl43-001, ensuring sleep mode is disabled
2026-01-14 18:37:12,889 - app.services - INFO - Sending command to 192.168.1.100:2255: Sleep Mode?
2026-01-14 18:37:17,890 - app.routers - WARNING - Could not verify/disable sleep mode on test-nl43-001: Failed to connect to device at 192.168.1.100:2255
```

## Testing

A comprehensive test script is available: [test_sleep_mode_auto_disable.py](test_sleep_mode_auto_disable.py)

Run it with:
```bash
python3 test_sleep_mode_auto_disable.py
```

The test verifies:
1. Config updates trigger sleep mode check
2. Config retrieval works correctly
3. Start measurement triggers sleep mode check
4. Operations succeed even without a physical device (non-blocking)

## API Documentation Updates

The following documentation files were updated to reflect this feature:

### [docs/API.md](docs/API.md)
- Updated config endpoint documentation with sleep mode auto-disable note
- Added warning to start measurement endpoint
- Enhanced power management section with detailed warnings about sleep mode behavior

Key additions:
- Configuration section now explains that sleep mode is automatically disabled when TCP is enabled
- Measurement control section notes that sleep mode is disabled before starting measurements
- Power management section includes comprehensive warnings about sleep mode affecting TCP connectivity

## Usage Notes

### For Operators
- You no longer need to manually disable sleep mode before starting remote monitoring
- Sleep mode will be automatically disabled when you configure a device or start measurements
- Check logs to verify sleep mode operations if experiencing connectivity issues

### For Developers
- The `ensure_sleep_mode_disabled()` helper can be called from any endpoint that requires reliable TCP connectivity
- Always use it before long-running operations that depend on continuous device communication
- The function is designed to fail gracefully - don't worry about exception handling

### Battery Conservation
If battery conservation is a concern:
- Consider using Timer Auto mode with scheduled measurements
- Sleep mode can be manually re-enabled between measurements using `POST /{unit_id}/sleep`
- Be aware that TCP connectivity will be lost until the device wakes or is physically accessed

## Deployment

The feature is automatically included when building the SLMM container:

```bash
cd /home/serversdown/tmi/terra-view
docker compose build slmm
docker compose up -d slmm
```

No configuration changes are required - the feature is active by default.

## Future Enhancements

Potential improvements for future versions:
- Add a user preference to optionally skip sleep mode disable
- Implement smart sleep mode scheduling (enable between measurements, disable during)
- Add sleep mode status to device health checks
- Create alerts when sleep mode is detected as enabled

## References

- NL-43 Command Reference: [docs/nl43_Command_ref.md](docs/nl43_Command_ref.md)
- Communication Guide: [docs/COMMUNICATION_GUIDE.md](docs/COMMUNICATION_GUIDE.md) (page 65, Sleep Mode)
- API Documentation: [docs/API.md](docs/API.md)
- SLMM Services: [app/services.py](app/services.py:395-417) (sleep mode commands)
