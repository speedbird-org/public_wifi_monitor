# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a WiFi/Internet connectivity monitoring script for macOS and Linux that generates ISP-ready reports. The main script is `wifi_monitor.py`.

**Project Structure:**
- `wifi_monitor.py` - Main Python monitoring script
- `requirements.txt` - Python dependencies 
- `logs/` - Active log files (Python implementation)
- `archive/` - Legacy shell script implementation and old logs
- `CLAUDE.md` - This documentation file

## Development Commands

### Running the Script
```bash
# Single monitoring run (for cron)
python3 wifi_monitor.py --monitor

# Single monitoring run with debug output
python3 wifi_monitor.py --monitor --debug

# Generate analysis report
python3 wifi_monitor.py --analyze

# Analyze specific time period
python3 wifi_monitor.py --analyze --days 1
```

### Cron Setup for macOS

**Important**: The script works when run manually but may return empty SSID/connection_type when run from cron due to environment and permission issues.

#### 1. Fix PATH Issues
Add to your crontab:
```bash
PATH=/usr/sbin:/usr/bin:/bin:/usr/local/bin
*/5 * * * * /usr/bin/python3 /path/to/wifi_monitor.py --monitor >> /tmp/wifi_monitor.log 2>&1
```

#### 2. macOS Permissions Required
- **System Preferences → Security & Privacy → Privacy → Full Disk Access**
- Add `/usr/sbin/cron` to the list
- Add Terminal (if editing crontab fails)

#### 3. Debugging Cron Issues
```bash
# Test with debug mode
*/5 * * * * /usr/bin/python3 /path/to/wifi_monitor.py --monitor --debug >> /tmp/wifi_debug.log 2>&1

# Check cron environment
* * * * * env > /tmp/cron-env.log 2>&1
```

#### 4. Alternative: Use launchd (Recommended by Apple)
Create `~/Library/LaunchAgents/com.user.wifi_monitor.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.wifi_monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/full/path/to/wifi_monitor.py</string>
        <string>--monitor</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>StandardOutPath</key>
    <string>/tmp/wifi_monitor.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/wifi_monitor_error.log</string>
</dict>
</plist>
```

Then load it:
```bash
launchctl load ~/Library/LaunchAgents/com.user.wifi_monitor.plist
```

## Architecture Overview

### Core Components
- `ConnectivityMonitor`: Main class handling all connectivity tests
- Network detection methods for macOS and Linux
- Parallel connectivity testing (ping, HTTP, HTTPS, DNS)
- JSON and CSV logging with ISP-ready reports

### Key Files
- `wifi_monitor.py`: Main Python script
- `logs/connectivity_python.log`: Detailed JSON logs  
- `logs/connectivity_summary.csv`: Summary data for analysis (newest entries at top)
- `logs/wifi_monitor_debug.log`: Debug output (when --debug used)
- `archive/`: Legacy shell script implementation and old log files

### Data Flow
1. Detect network interface and WiFi SSID
2. Run parallel connectivity tests
3. Generate summary statistics
4. Log to both JSON and CSV formats
5. Optionally analyze historical data

## Troubleshooting

### Empty SSID/Connection Type in Cron
- **Cause**: PATH environment missing `/usr/sbin`
- **Fix**: Use full paths in script (already implemented) or set PATH in crontab
- **Debug**: Run with `--debug` flag to see detailed command execution

### Permission Denied Errors
- **Cause**: macOS security restrictions
- **Fix**: Add cron to Full Disk Access in System Preferences

### Command Not Found Errors
- **Cause**: Commands not in PATH
- **Fix**: Script uses full paths (`/usr/sbin/networksetup`, `/usr/sbin/system_profiler`)

## Notes

- Script automatically detects macOS vs Linux and uses appropriate network detection methods
- Uses multiple fallback methods for robust network detection
- All system commands use full paths to avoid PATH issues in cron
- Debug logging available with `--debug` flag for troubleshooting