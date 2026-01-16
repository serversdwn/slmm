# SLMM Archive

This directory contains legacy scripts that are no longer needed for normal operation but are preserved for reference.

## Legacy Migrations (`legacy_migrations/`)

These migration scripts were used during SLMM development (v0.1.x) to incrementally add database fields. They are **no longer needed** because:

1. **Fresh databases** get the complete schema automatically from `app/models.py`
2. **Existing databases** should already have these fields from previous runs
3. **Current migration** is `migrate_add_polling_fields.py` (v0.2.0) in the parent directory

### Archived Migration Files

- `migrate_add_counter.py` - Added `counter` field to NL43Status
- `migrate_add_measurement_start_time.py` - Added `measurement_start_time` field
- `migrate_add_ftp_port.py` - Added `ftp_port` field to NL43Config
- `migrate_field_names.py` - Renamed fields for consistency (one-time fix)
- `migrate_revert_field_names.py` - Rollback for the rename migration

**Do not delete** - These provide historical context for database schema evolution.

---

## Legacy Tools

### `nl43_dod_poll.py`

Manual polling script that queries a single NL-43 device for DOD (Device On-Demand) data.

**Status**: Replaced by background polling system in v0.2.0

**Why archived**:
- Background poller (`app/background_poller.py`) now handles continuous polling automatically
- No need for manual polling scripts
- Kept for reference in case manual querying is needed for debugging

**How to use** (if needed):
```bash
cd /home/serversdown/tmi/slmm/archive
python3 nl43_dod_poll.py <host> <port> <unit_id>
```

---

## Active Scripts (Still in Parent Directory)

These scripts are **actively used** and documented in the main README:

### Migrations
- `migrate_add_polling_fields.py` - **v0.2.0 migration** - Adds background polling fields
- `migrate_add_ftp_credentials.py` - **Legacy FTP migration** - Adds FTP auth fields

### Testing
- `test_polling.sh` - Comprehensive test suite for background polling features
- `test_settings_endpoint.py` - Tests device settings API
- `test_sleep_mode_auto_disable.py` - Tests automatic sleep mode handling

### Utilities
- `set_ftp_credentials.py` - Command-line tool to set FTP credentials for a device

---

## Version History

- **v0.2.0** (2026-01-15) - Background polling system added, manual polling scripts archived
- **v0.1.0** (2025-12-XX) - Initial release with incremental migrations
