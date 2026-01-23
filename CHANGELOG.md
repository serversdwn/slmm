# Changelog

All notable changes to SLMM (Sound Level Meter Manager) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-01-23

### Added
- **Roster management**: UI and API endpoints for managing device rosters.
- **Delete config endpoint**: Remove device configuration alongside cached status data.
- **Scheduler hooks**: `start_cycle` and `stop_cycle` helpers for Terra-View scheduling integration.

### Changed
- **FTP logging**: Connection, authentication, and transfer phases now log explicitly.
- **Documentation**: Reorganized docs/scripts and updated API notes for FTP/TCP verification.

## [0.2.0] - 2026-01-15

### Added

#### Background Polling System
- **Continuous automatic device polling** - Background service that continuously polls configured devices
- **Per-device configurable intervals** - Each device can have custom polling interval (10-3600 seconds, default 60)
- **Automatic offline detection** - Devices automatically marked unreachable after 3 consecutive failures
- **Reachability tracking** - Database fields track device health with failure counters and error messages
- **Dynamic sleep scheduling** - Polling service adjusts sleep intervals based on device configurations
- **Graceful lifecycle management** - Background poller starts on application startup and stops cleanly on shutdown

#### New API Endpoints
- `GET /api/nl43/{unit_id}/polling/config` - Get device polling configuration
- `PUT /api/nl43/{unit_id}/polling/config` - Update polling interval and enable/disable per-device polling
- `GET /api/nl43/_polling/status` - Get global polling status for all devices with reachability info

#### Database Schema Changes
- **NL43Config table**:
  - `poll_interval_seconds` (Integer, default 60) - Polling interval in seconds
  - `poll_enabled` (Boolean, default true) - Enable/disable background polling per device

- **NL43Status table**:
  - `is_reachable` (Boolean, default true) - Current device reachability status
  - `consecutive_failures` (Integer, default 0) - Count of consecutive poll failures
  - `last_poll_attempt` (DateTime) - Last time background poller attempted to poll
  - `last_success` (DateTime) - Last successful poll timestamp
  - `last_error` (Text) - Last error message (truncated to 500 chars)

#### New Files
- `app/background_poller.py` - Background polling service implementation
- `migrate_add_polling_fields.py` - Database migration script for v0.2.0 schema changes
- `test_polling.sh` - Comprehensive test script for polling functionality
- `CHANGELOG.md` - This changelog file

### Changed
- **Enhanced status endpoint** - `GET /api/nl43/{unit_id}/status` now includes polling-related fields (is_reachable, consecutive_failures, last_poll_attempt, last_success, last_error)
- **Application startup** - Added lifespan context manager in `app/main.py` to manage background poller lifecycle
- **Performance improvement** - Terra-View requests now return cached data instantly (<100ms) instead of waiting for device queries (1-2 seconds)

### Technical Details

#### Architecture
- Background poller runs as async task using `asyncio.create_task()`
- Uses existing `NL43Client` and `persist_snapshot()` functions - no code duplication
- Respects existing 1-second rate limiting per device
- Efficient resource usage - skips work when no devices configured
- WebSocket streaming remains unaffected - separate real-time data path

#### Default Behavior
- Existing devices automatically get 60-second polling interval
- Existing status records default to `is_reachable=true`
- Migration is additive-only - no data loss
- Polling can be disabled per-device via `poll_enabled=false`

#### Recommended Intervals
- Critical monitoring: 30 seconds
- Normal monitoring: 60 seconds (default)
- Battery conservation: 300 seconds (5 minutes)
- Development/testing: 10 seconds (minimum allowed)

### Migration Notes

To upgrade from v0.1.x to v0.2.0:

1. **Stop the service** (if running):
   ```bash
   docker compose down slmm
   # OR
   # Stop your uvicorn process
   ```

2. **Update code**:
   ```bash
   git pull
   # OR copy new files
   ```

3. **Run migration**:
   ```bash
   cd slmm
   python3 migrate_add_polling_fields.py
   ```

4. **Restart service**:
   ```bash
   docker compose up -d --build slmm
   # OR
   uvicorn app.main:app --host 0.0.0.0 --port 8100
   ```

5. **Verify polling is active**:
   ```bash
   curl http://localhost:8100/api/nl43/_polling/status | jq '.'
   ```

You should see `"poller_running": true` and all configured devices listed.

### Breaking Changes
None. This release is fully backward-compatible with v0.1.x. All existing endpoints and functionality remain unchanged.

---

## [0.1.0] - 2025-12-XX

### Added
- Initial release
- REST API for NL43/NL53 sound level meter control
- TCP command protocol implementation
- FTP file download support
- WebSocket streaming for real-time data (DRD)
- Device configuration management
- Measurement control (start, stop, pause, resume, reset, store)
- Device information endpoints (battery, clock, results)
- Measurement settings management (frequency/time weighting)
- Sleep mode control
- Rate limiting (1-second minimum between commands)
- SQLite database for device configs and status cache
- Health check endpoints
- Comprehensive API documentation
- NL43 protocol documentation

### Database Schema (v0.1.0)
- **NL43Config table** - Device connection configuration
- **NL43Status table** - Measurement snapshot cache

---

## Version History Summary

- **v0.2.1** (2026-01-23) - Roster management, scheduler hooks, FTP logging, doc cleanup
- **v0.2.0** (2026-01-15) - Background Polling System
- **v0.1.0** (2025-12-XX) - Initial Release
