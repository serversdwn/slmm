# Changelog

All notable changes to SLMM (Sound Level Meter Manager) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-06-22

### Added

#### Live Monitor (fan-out feed)
- **Per-device fan-out monitor** - one shared, cached live feed per device. Multiple clients (dashboards, portal, charts) subscribe to the same stream instead of each fighting for the NL-43's single TCP connection: one poller reads the device, all subscribers get the same frames.
- **WebSocket monitor** - `WS /api/nl43/{unit_id}/monitor` delivers an instant first frame from cache, then live updates.
- **Monitor control** - `POST /api/nl43/{unit_id}/monitor/{start|stop}`, `GET /api/nl43/_monitor/status`. A persistent `monitor_enabled` flag auto-starts the keepalive on boot.
- **Adaptive polling** - poll rate adapts to demand; unreachable devices back off; a device-offline alert fires when a monitored unit drops.
- **De-duplication** - the background poller skips units already covered by an active monitor (no double-polling); a heartbeat keeps the feed warm.
- **Lower latency** - the monitor caches run state, roughly halving live-feed latency; fan-out emits an instant first frame + offline status to new clients.

#### Alert Engine
- **Threshold rules** - per-device alert rules (metric + threshold + cooldown) with full CRUD: `POST/GET/PUT/DELETE /api/nl43/{unit_id}/alerts/rules[/{rule_id}]`.
- **Events + state machine** - onset/clear tracking via `GET /api/nl43/{unit_id}/alerts/events`; acknowledge with `POST .../events/{event_id}/ack`. A `cooldown_s` is enforced between onsets.
- **24/7 evaluation** - enabled rules pin the monitor on, so rules evaluate continuously even with no UI client connected.
- **Resilience** - editing or deleting a rule resets its state and closes any open event; device-offline events are raised when a monitored unit goes unreachable.

#### Data & History
- **Live-chart backfill** - a downsampled DOD trail is persisted to a new `nl43_readings` table, exposed via `GET /api/nl43/{unit_id}/history` so charts can backfill recent history on load.
- **LN1/LN2 percentiles** - L1/L10 (configurable percentiles) surfaced through SLMM in the status and live-feed payloads.
- **measurement_start_time** included in the cached `/status` response.

#### Device control
- **Per-device disconnect** - `POST /api/nl43/{unit_id}/disconnect` drops a device's pooled connection.
- **Deactivate / standby** - `POST /api/nl43/{unit_id}/deactivate` and global `POST /api/nl43/_system/standby` to quiesce polling/monitoring.

### Changed
- **DRD streaming reuses the pooled connection** rather than opening a separate socket, avoiding contention with the persistent pool on a single-connection device.
- **Connection pool** - idle-TTL / max-age checks can now be disabled; pool status is logged periodically.

### Fixed
- **Measurement-start confirmation** - `/start` now recognizes the device's `Start` state. It previously waited for `Measure`, which never matched, so the start cycle ran the full retry loop and Terra-View's proxy timed out with a misleading "Unknown error" even though the device had started.
- **Garbled reads** - corrupted measurement-state reads that produced phantom STOPPED/STARTED transitions are now ignored.
- **DOD parsing** - corrected field parsing and stopped spurious measurement-time resets.
- **Monitor WebSocket** - quieted a send-after-close race on client disconnect.

### Database
- **New tables** (auto-created on startup via `Base.metadata.create_all`): `alert_rules`, `alert_events`, `nl43_readings`.
- **Migrations for existing tables** (run once per database): `migrate_add_ln_percentiles.py` (LN1/LN2 on `nl43_status`), `migrate_add_monitor_enabled.py` (`monitor_enabled` on `nl43_config`).

### Notes
- Pairs with the matching Terra-View `dev` build, which reads SLMM's `/monitor` fan-out feed for live SLM dashboards (L1/L10 lines, live-chart backfill). Ship the two together.

---

## [0.3.0] - 2026-02-17

### Added

#### Persistent TCP Connection Pool
- **Connection reuse** - TCP connections are cached per device and reused across commands, eliminating repeated TCP handshakes over cellular modems
- **OS-level TCP keepalive** - Configurable keepalive probes keep cellular NAT tables alive and detect dead connections early (default: probe after 15s idle, every 10s, 3 failures = dead)
- **Transparent retry** - If a cached connection goes stale, the system automatically retries with a fresh connection so failures are never visible to the caller
- **Stale connection detection** - Multi-layer detection via idle TTL, max age, transport state, and reader EOF checks
- **Background cleanup** - Periodic task (every 30s) evicts expired connections from the pool
- **Master switch** - Set `TCP_PERSISTENT_ENABLED=false` to revert to per-request connection behavior

#### Connection Pool Diagnostics
- `GET /api/nl43/_connections/status` - View pool configuration, active connections, age/idle times, and keepalive settings
- `POST /api/nl43/_connections/flush` - Force-close all cached connections (useful for debugging)
- **Connections tab on roster page** - Live UI showing pool config, active connections with age/idle/alive status, auto-refreshes every 5s, and flush button

#### Environment Variables
- `TCP_PERSISTENT_ENABLED` (default: `true`) - Master switch for persistent connections
- `TCP_IDLE_TTL` (default: `300`) - Close idle connections after N seconds
- `TCP_MAX_AGE` (default: `1800`) - Force reconnect after N seconds
- `TCP_KEEPALIVE_IDLE` (default: `15`) - Seconds idle before keepalive probes start
- `TCP_KEEPALIVE_INTERVAL` (default: `10`) - Seconds between keepalive probes
- `TCP_KEEPALIVE_COUNT` (default: `3`) - Failed probes before declaring connection dead

### Changed
- **Health check endpoint** (`/health/devices`) - Now uses connection pool instead of opening throwaway TCP connections; checks for existing live connections first (zero-cost), only opens new connection through pool if needed
- **Diagnostics endpoint** - Removed separate port 443 modem check (extra handshake waste); TCP reachability test now uses connection pool
- **DRD streaming** - Streaming connections now get TCP keepalive options set; cached connections are evicted before opening dedicated streaming socket
- **Default timeouts tuned for cellular** - Idle TTL raised to 300s (5 min), max age raised to 1800s (30 min) to survive typical polling intervals over cellular links

### Technical Details

#### Architecture
- `ConnectionPool` class in `services.py` manages a single cached connection per device key (NL-43 only supports one TCP connection at a time)
- Uses existing per-device asyncio locks and rate limiting — no changes to concurrency model
- Pool is a module-level singleton initialized from environment variables at import time
- Lifecycle managed via FastAPI lifespan: cleanup task starts on startup, all connections closed on shutdown
- `_send_command_unlocked()` refactored to use acquire/release/discard pattern with single-retry fallback
- Command parsing extracted to `_execute_command()` method for reuse between primary and retry paths

#### Cellular Modem Optimizations
- Keepalive probes at 15s prevent cellular NAT tables from expiring (typically 30-60s timeout)
- 300s idle TTL ensures connections survive between polling cycles (default 60s interval)
- 1800s max age allows a single socket to serve ~30 minutes of polling before forced reconnect
- Health checks and diagnostics produce zero additional TCP handshakes when a pooled connection exists
- Stale `$` prompt bytes drained from idle connections before command reuse

### Breaking Changes
None. This release is fully backward-compatible with v0.2.x. Set `TCP_PERSISTENT_ENABLED=false` for identical behavior to previous versions.

---

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

- **v0.3.0** (2026-02-17) - Persistent TCP connections with keepalive for cellular modem reliability
- **v0.2.1** (2026-01-23) - Roster management, scheduler hooks, FTP logging, doc cleanup
- **v0.2.0** (2026-01-15) - Background Polling System
- **v0.1.0** (2025-12-XX) - Initial Release
