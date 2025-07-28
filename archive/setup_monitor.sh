#!/bin/bash

# Setup script for Internet Connectivity Monitor
# Configures the monitoring script to run every minute via cron

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_SCRIPT="$SCRIPT_DIR/connectivity_monitor.sh"
CRON_COMMENT="# Internet Connectivity Monitor"
CRON_JOB="* * * * * $MONITOR_SCRIPT"

echo "Internet Connectivity Monitor Setup"
echo "==================================="

# Check if monitor script exists
if [[ ! -f "$MONITOR_SCRIPT" ]]; then
    echo "❌ Error: connectivity_monitor.sh not found in $SCRIPT_DIR"
    exit 1
fi

# Make monitor script executable
echo "📝 Making monitor script executable..."
chmod +x "$MONITOR_SCRIPT"

# Detect OS for platform-specific instructions
detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macOS" ;;
        Linux) echo "linux" ;;
        *) echo "unknown" ;;
    esac
}

OS=$(detect_os)
echo "🖥️  Detected OS: $OS"

# Check for required dependencies
echo "🔍 Checking dependencies..."

check_dependency() {
    if command -v "$1" >/dev/null 2>&1; then
        echo "  ✅ $1 is available"
        return 0
    else
        echo "  ❌ $1 is missing"
        return 1
    fi
}

# Common dependencies
check_dependency "ping"
check_dependency "date"

# OS-specific dependencies
case "$OS" in
    "macOS")
        check_dependency "networksetup"
        ;;
    "linux")
        echo "  📋 Checking Linux network tools..."
        if ! (check_dependency "iwgetid" || check_dependency "nmcli" || check_dependency "iw"); then
            echo "  ⚠️  Warning: No WiFi detection tools found. Install wireless-tools, network-manager, or iw"
            echo "     Ubuntu/Debian: sudo apt install wireless-tools network-manager"
            echo "     RHEL/CentOS: sudo yum install wireless-tools NetworkManager"
        fi
        ;;
esac

# Check if curl is available (optional but recommended)
if ! check_dependency "curl"; then
    echo "  ℹ️  curl is recommended for fallback connectivity testing"
fi

# Create logs directory
echo "📁 Creating logs directory..."
mkdir -p "$SCRIPT_DIR/logs"

# Setup cron job
echo "⏰ Setting up cron job..."

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -F "$MONITOR_SCRIPT" >/dev/null; then
    echo "  ⚠️  Cron job already exists. Removing old entry..."
    crontab -l 2>/dev/null | grep -v "$MONITOR_SCRIPT" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null || true; echo "$CRON_COMMENT"; echo "$CRON_JOB") | crontab -

if [[ $? -eq 0 ]]; then
    echo "  ✅ Cron job added successfully"
else
    echo "  ❌ Failed to add cron job"
    exit 1
fi

# Verify cron job
echo "🔍 Verifying cron job..."
if crontab -l 2>/dev/null | grep -F "$MONITOR_SCRIPT" >/dev/null; then
    echo "  ✅ Cron job verified"
else
    echo "  ❌ Cron job verification failed"
    exit 1
fi

# Test the monitor script once
echo "🧪 Testing monitor script..."
if "$MONITOR_SCRIPT"; then
    echo "  ✅ Monitor script test successful"
    
    # Show log file location and sample entry
    LOG_FILE="$SCRIPT_DIR/logs/connectivity.log"
    if [[ -f "$LOG_FILE" ]]; then
        echo "📋 Log file: $LOG_FILE"
        echo "📋 Latest entry:"
        tail -1 "$LOG_FILE" | sed 's/^/    /'
    fi
else
    echo "  ❌ Monitor script test failed"
    exit 1
fi

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📊 Monitor Information:"
echo "   Script: $MONITOR_SCRIPT"
echo "   Log file: $SCRIPT_DIR/logs/connectivity.log"
echo "   Frequency: Every minute"
echo ""
echo "🔧 Management Commands:"
echo "   View logs: tail -f $SCRIPT_DIR/logs/connectivity.log"
echo "   Stop monitoring: crontab -e (remove the line with $MONITOR_SCRIPT)"
echo "   Check cron status: crontab -l | grep connectivity_monitor"
echo ""

# OS-specific final instructions
case "$OS" in
    "macOS")
        echo "🍎 macOS Notes:"
        echo "   - Ensure Terminal has Full Disk Access in System Preferences > Security & Privacy"
        echo "   - The script will automatically detect WiFi networks on en0/en1 interfaces"
        ;;
    "linux")
        echo "🐧 Linux Notes:"
        echo "   - Ensure cron service is running: sudo systemctl status cron"
        echo "   - For WiFi detection, install wireless-tools or network-manager if needed"
        ;;
esac

echo ""
echo "✨ The connectivity monitor is now running every minute!"