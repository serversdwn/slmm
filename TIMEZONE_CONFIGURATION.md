# Timezone Configuration for SLMM

## Overview

The SLMM system now supports configurable timezone settings. All timestamps are stored internally in UTC for consistency, but the system can interpret FTP timestamps and display times in your local timezone.

## Configuration

### Environment Variables

Set the following environment variables to configure your timezone:

#### `TIMEZONE_OFFSET` (required)
The number of hours offset from UTC. Use negative numbers for zones west of UTC, positive for east.

**Examples:**
- `-5` = EST (Eastern Standard Time, UTC-5)
- `-4` = EDT (Eastern Daylight Time, UTC-4)
- `0` = UTC (Coordinated Universal Time)
- `+1` = CET (Central European Time, UTC+1)
- `-8` = PST (Pacific Standard Time, UTC-8)

**Default:** `-5` (EST)

#### `TIMEZONE_NAME` (optional)
A friendly name for your timezone, used in log messages.

**Examples:**
- `EST`
- `EDT`
- `UTC`
- `PST`

**Default:** Auto-generated from offset (e.g., "UTC-5")

### Setup Instructions

#### Option 1: Using .env file (Recommended)

1. Copy the example file:
   ```bash
   cd /home/serversdown/slmm
   cp .env.example .env
   ```

2. Edit `.env` and set your timezone:
   ```bash
   TIMEZONE_OFFSET=-5
   TIMEZONE_NAME=EST
   ```

3. Make sure your application loads the .env file (you may need to install `python-dotenv`):
   ```bash
   pip install python-dotenv
   ```

4. Update `app/main.py` to load the .env file (add at the top):
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```

#### Option 2: System Environment Variables

Set the environment variables in your shell or service configuration:

```bash
export TIMEZONE_OFFSET=-5
export TIMEZONE_NAME=EST
```

Or add to your systemd service file if running as a service.

#### Option 3: Docker/Docker Compose

If using Docker, add to your `docker-compose.yml`:

```yaml
services:
  slmm:
    environment:
      - TIMEZONE_OFFSET=-5
      - TIMEZONE_NAME=EST
```

Or pass via command line:
```bash
docker run -e TIMEZONE_OFFSET=-5 -e TIMEZONE_NAME=EST ...
```

## How It Works

### Data Flow

1. **FTP Timestamps**: When the system reads file timestamps via FTP from the NL43 device, they are assumed to be in your configured timezone
2. **Conversion**: Timestamps are immediately converted to UTC for internal storage
3. **Database**: All timestamps in the database are stored in UTC
4. **API Responses**: Timestamps are sent to the frontend as UTC ISO strings
5. **Frontend Display**: The browser automatically converts UTC timestamps to the user's local timezone for display

### Example

If you're in EST (UTC-5) and the FTP shows a file timestamp of "Jan 11 21:57":

1. System interprets: `Jan 11 21:57 EST`
2. Converts to UTC: `Jan 12 02:57 UTC` (adds 5 hours)
3. Stores in database: `2026-01-12T02:57:00`
4. Sends to frontend: `2026-01-12T02:57:00` (with 'Z' added = UTC)
5. Browser displays: `Jan 11, 9:57 PM EST` (converts back to user's local time)

### Timer Calculation

The measurement timer calculates elapsed time correctly because:
- `measurement_start_time` is stored in UTC
- FTP folder timestamps are converted to UTC
- Frontend calculates `Date.now() - startTime` using UTC milliseconds
- All timezone offsets cancel out, giving accurate elapsed time

## Troubleshooting

### Timer shows wrong elapsed time

1. **Check your timezone setting**: Make sure `TIMEZONE_OFFSET` matches your actual timezone
   ```bash
   # Check current setting in logs when SLMM starts:
   grep "Using timezone" data/slmm.log
   ```

2. **Verify FTP timestamps**: FTP timestamps from the device should be in your local timezone
   - If the device is configured for a different timezone, adjust `TIMEZONE_OFFSET` accordingly

3. **Restart the service**: Changes to environment variables require restarting the SLMM service

### Logs show unexpected timezone

Check the startup logs:
```bash
tail -f data/slmm.log | grep timezone
```

You should see:
```
Using timezone: EST (UTC-5)
```

If not, the environment variable may not be loaded correctly.

## Daylight Saving Time (DST)

**Important:** This configuration uses a fixed offset. If you need to account for Daylight Saving Time:

- **During DST (summer)**: Set `TIMEZONE_OFFSET=-4` (EDT)
- **During standard time (winter)**: Set `TIMEZONE_OFFSET=-5` (EST)
- You'll need to manually update the setting when DST changes (typically March and November)

**Future Enhancement:** Automatic DST handling could be implemented using Python's `zoneinfo` module with named timezones (e.g., "America/New_York").

## Default Behavior

If no environment variables are set:
- **TIMEZONE_OFFSET**: Defaults to `-5` (EST)
- **TIMEZONE_NAME**: Defaults to `UTC-5`

This means the system will work correctly for EST deployments out of the box.
