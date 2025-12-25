#!/usr/bin/env python3
"""
Test script to demonstrate the GET /api/nl43/{unit_id}/settings endpoint.

This endpoint retrieves all current device settings for verification purposes.
"""

import asyncio
import sys


async def test_settings_retrieval():
    """Test the settings retrieval functionality."""
    from app.services import NL43Client

    # Example configuration - adjust these to match your actual device
    host = "192.168.1.100"  # Replace with your NL43 device IP
    port = 80
    unit_id = "NL43-001"

    print(f"Connecting to NL43 device at {host}:{port}...")
    print(f"Unit ID: {unit_id}\n")

    client = NL43Client(host, port)

    try:
        print("Retrieving all device settings...")
        settings = await client.get_all_settings()

        print("\n" + "="*60)
        print("DEVICE SETTINGS SUMMARY")
        print("="*60)

        for key, value in settings.items():
            print(f"{key:.<30} {value}")

        print("="*60)
        print(f"\nTotal settings retrieved: {len(settings)}")
        print("\n✓ Settings retrieval successful!")

    except ConnectionError as e:
        print(f"\n✗ Connection Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Verify the device IP address and port")
        print("  2. Ensure the device is powered on and connected to the network")
        print("  3. Check firewall settings")
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


async def test_api_endpoint():
    """Demonstrate how to call the API endpoint."""
    print("\n" + "="*60)
    print("API ENDPOINT USAGE")
    print("="*60)
    print("\nTo retrieve all settings via the API, use:")
    print("\n  GET /api/nl43/{unit_id}/settings")
    print("\nExample with curl:")
    print("\n  curl http://localhost:8000/api/nl43/NL43-001/settings")
    print("\nExample response:")
    print("""
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
""")
    print("="*60)


if __name__ == "__main__":
    print("NL43 Settings Retrieval Test")
    print("="*60)
    print("\nThis test demonstrates the new /api/nl43/{unit_id}/settings endpoint")
    print("which allows you to view all current device settings for verification.\n")

    # Show API usage
    asyncio.run(test_api_endpoint())

    # Uncomment below to test actual device connection
    # asyncio.run(test_settings_retrieval())

    print("\n✓ Test completed!")
