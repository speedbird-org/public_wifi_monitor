#!/bin/bash

# WiFi Monitor Cron Installation Script
# Adds a cron job to run wifi_monitor.py every minute during business hours (9 AM - 7 PM, Monday-Friday)

set -e

# Get the absolute path to the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define the cron job
CRON_JOB="* 9-19 * * 1-5 cd $SCRIPT_DIR && python3 wifi_monitor.py --monitor >> logs/cron.log 2>&1"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not in PATH"
    exit 1
fi

# Check if wifi_monitor.py exists
if [ ! -f "$SCRIPT_DIR/wifi_monitor.py" ]; then
    echo "Error: wifi_monitor.py not found in $SCRIPT_DIR"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

echo "Installing WiFi Monitor cron job..."
echo "Script directory: $SCRIPT_DIR"
echo "Cron job: $CRON_JOB"

# Get current crontab (if any)
CURRENT_CRONTAB=$(crontab -l 2>/dev/null || echo "")

# Check if the job already exists
if echo "$CURRENT_CRONTAB" | grep -q "wifi_monitor.py --monitor"; then
    echo "Warning: A WiFi monitor cron job already exists. Checking if it matches..."
    
    if echo "$CURRENT_CRONTAB" | grep -q -F "$CRON_JOB"; then
        echo "✓ Exact cron job already exists. No changes needed."
        exit 0
    else
        echo "✗ Different WiFi monitor cron job found. Please remove it manually and run this script again."
        echo "Current WiFi monitor entries in crontab:"
        echo "$CURRENT_CRONTAB" | grep "wifi_monitor.py"
        exit 1
    fi
fi

# Add the new cron job
if [ -z "$CURRENT_CRONTAB" ]; then
    # No existing crontab
    echo "$CRON_JOB" | crontab -
else
    # Append to existing crontab
    (echo "$CURRENT_CRONTAB"; echo "$CRON_JOB") | crontab -
fi

echo "✓ WiFi Monitor cron job installed successfully!"
echo ""
echo "The monitor will run every minute during business hours (9 AM - 7 PM, Monday-Friday)."
echo "Logs will be written to: $SCRIPT_DIR/logs/cron.log"
echo ""
echo "To verify the installation, run: crontab -l"
echo "To uninstall, run: crontab -e and remove the wifi_monitor.py line"
echo ""
echo "Note: On macOS, you may need to grant Full Disk Access to cron in System Preferences > Security & Privacy > Privacy."