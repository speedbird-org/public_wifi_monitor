#!/bin/bash

# WiFi Monitor Cron Uninstallation Script
# Removes WiFi monitor cron jobs from the user's crontab

set -e

echo "Uninstalling WiFi Monitor cron job..."

# Get current crontab (if any)
CURRENT_CRONTAB=$(crontab -l 2>/dev/null || echo "")

# Check if there's no crontab at all
if [ -z "$CURRENT_CRONTAB" ]; then
    echo "✓ No crontab found. Nothing to uninstall."
    exit 0
fi

# Check if WiFi monitor entries exist
WIFI_MONITOR_ENTRIES=$(echo "$CURRENT_CRONTAB" | grep "wifi_monitor.py" || echo "")

if [ -z "$WIFI_MONITOR_ENTRIES" ]; then
    echo "✓ No WiFi monitor cron jobs found. Nothing to uninstall."
    exit 0
fi

echo "Found WiFi monitor cron job(s):"
echo "$WIFI_MONITOR_ENTRIES"
echo ""

# Create a temporary file for the new crontab
TEMP_CRONTAB=$(mktemp)

# Filter out WiFi monitor entries
echo "$CURRENT_CRONTAB" | grep -v "wifi_monitor.py" > "$TEMP_CRONTAB" || true

# Check if the filtered crontab is empty
if [ ! -s "$TEMP_CRONTAB" ]; then
    # Empty crontab - remove it entirely
    crontab -r 2>/dev/null || true
    echo "✓ WiFi monitor cron job removed. Crontab is now empty and has been cleared."
else
    # Install the filtered crontab
    crontab "$TEMP_CRONTAB"
    echo "✓ WiFi monitor cron job removed successfully!"
    echo ""
    echo "Remaining cron jobs:"
    crontab -l
fi

# Clean up temporary file
rm -f "$TEMP_CRONTAB"

echo ""
echo "WiFi Monitor has been uninstalled from cron."
echo "To verify removal, run: crontab -l"