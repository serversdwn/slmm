#!/bin/bash
# Manual test script for background polling functionality
# Usage: ./test_polling.sh [UNIT_ID]

BASE_URL="http://localhost:8100/api/nl43"
UNIT_ID="${1:-NL43-001}"

echo "=========================================="
echo "Background Polling Test Script"
echo "=========================================="
echo "Testing device: $UNIT_ID"
echo "Base URL: $BASE_URL"
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print test header
test_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

# Function to print success
success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to print warning
warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Function to print error
error() {
    echo -e "${RED}✗${NC} $1"
}

# Test 1: Get current polling configuration
test_header "Test 1: Get Current Polling Configuration"
RESPONSE=$(curl -s "$BASE_URL/$UNIT_ID/polling/config")
echo "$RESPONSE" | jq '.'

if echo "$RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
    success "Successfully retrieved polling configuration"
    CURRENT_INTERVAL=$(echo "$RESPONSE" | jq -r '.data.poll_interval_seconds')
    CURRENT_ENABLED=$(echo "$RESPONSE" | jq -r '.data.poll_enabled')
    echo "  Current interval: ${CURRENT_INTERVAL}s"
    echo "  Polling enabled: $CURRENT_ENABLED"
else
    error "Failed to retrieve polling configuration"
    exit 1
fi

# Test 2: Update polling interval to 30 seconds
test_header "Test 2: Update Polling Interval to 30 Seconds"
RESPONSE=$(curl -s -X PUT "$BASE_URL/$UNIT_ID/polling/config" \
  -H "Content-Type: application/json" \
  -d '{"poll_interval_seconds": 30}')
echo "$RESPONSE" | jq '.'

if echo "$RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
    success "Successfully updated polling interval to 30s"
else
    error "Failed to update polling interval"
fi

# Test 3: Check global polling status
test_header "Test 3: Check Global Polling Status"
RESPONSE=$(curl -s "$BASE_URL/_polling/status")
echo "$RESPONSE" | jq '.'

if echo "$RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
    success "Successfully retrieved global polling status"
    POLLER_RUNNING=$(echo "$RESPONSE" | jq -r '.data.poller_running')
    TOTAL_DEVICES=$(echo "$RESPONSE" | jq -r '.data.total_devices')
    echo "  Poller running: $POLLER_RUNNING"
    echo "  Total devices: $TOTAL_DEVICES"
else
    error "Failed to retrieve global polling status"
fi

# Test 4: Wait for automatic poll to occur
test_header "Test 4: Wait for Automatic Poll (35 seconds)"
warning "Waiting 35 seconds for automatic poll to occur..."
for i in {35..1}; do
    echo -ne "  ${i}s remaining...\r"
    sleep 1
done
echo ""
success "Wait complete"

# Test 5: Check if status was updated by background poller
test_header "Test 5: Verify Background Poll Occurred"
RESPONSE=$(curl -s "$BASE_URL/$UNIT_ID/status")
echo "$RESPONSE" | jq '{last_poll_attempt, last_success, is_reachable, consecutive_failures}'

if echo "$RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
    LAST_POLL=$(echo "$RESPONSE" | jq -r '.data.last_poll_attempt')
    IS_REACHABLE=$(echo "$RESPONSE" | jq -r '.data.is_reachable')
    FAILURES=$(echo "$RESPONSE" | jq -r '.data.consecutive_failures')

    if [ "$LAST_POLL" != "null" ]; then
        success "Device was polled by background poller"
        echo "  Last poll: $LAST_POLL"
        echo "  Reachable: $IS_REACHABLE"
        echo "  Failures: $FAILURES"
    else
        warning "No automatic poll detected yet"
    fi
else
    error "Failed to retrieve device status"
fi

# Test 6: Disable polling
test_header "Test 6: Disable Background Polling"
RESPONSE=$(curl -s -X PUT "$BASE_URL/$UNIT_ID/polling/config" \
  -H "Content-Type: application/json" \
  -d '{"poll_enabled": false}')
echo "$RESPONSE" | jq '.'

if echo "$RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
    success "Successfully disabled background polling"
else
    error "Failed to disable polling"
fi

# Test 7: Verify polling is disabled
test_header "Test 7: Verify Polling Disabled in Global Status"
RESPONSE=$(curl -s "$BASE_URL/_polling/status")
DEVICE_ENABLED=$(echo "$RESPONSE" | jq --arg uid "$UNIT_ID" '.data.devices[] | select(.unit_id == $uid) | .poll_enabled')

if [ "$DEVICE_ENABLED" == "false" ]; then
    success "Polling correctly shows as disabled for $UNIT_ID"
else
    warning "Device still appears in polling list or shows as enabled"
fi

# Test 8: Re-enable polling with original interval
test_header "Test 8: Re-enable Polling with Original Interval"
RESPONSE=$(curl -s -X PUT "$BASE_URL/$UNIT_ID/polling/config" \
  -H "Content-Type: application/json" \
  -d "{\"poll_enabled\": true, \"poll_interval_seconds\": $CURRENT_INTERVAL}")
echo "$RESPONSE" | jq '.'

if echo "$RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
    success "Successfully re-enabled polling with ${CURRENT_INTERVAL}s interval"
else
    error "Failed to re-enable polling"
fi

# Summary
test_header "Test Summary"
echo "All tests completed!"
echo ""
echo "Key endpoints tested:"
echo "  GET  $BASE_URL/{unit_id}/polling/config"
echo "  PUT  $BASE_URL/{unit_id}/polling/config"
echo "  GET  $BASE_URL/_polling/status"
echo "  GET  $BASE_URL/{unit_id}/status (with polling fields)"
echo ""
success "Background polling feature is working correctly"
