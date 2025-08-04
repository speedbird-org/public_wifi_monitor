# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`wifi_monitor.py` is an Internet connectivity monitoring tool for macOS and Linux that performs comprehensive network testing and generates ISP-ready reports.

## What wifi_monitor.py Does

### Core Functionality
- **Network Detection**: Automatically detects WiFi SSID and connection type (WiFi/Ethernet)
- **Parallel Connectivity Testing**: Tests ping, HTTP, HTTPS, and DNS connectivity simultaneously
- **Performance Measurement**: Measures latency, response times, and success rates
- **ISP Reporting**: Generates detailed analysis reports suitable for ISP communications

### Key Features
- Cross-platform support (macOS and Linux)
- Multiple fallback methods for robust network interface detection
- Parallel test execution for faster results
- CSV logging with newest entries at top
- Historical data analysis and trend reporting
- Debug mode for troubleshooting

### Usage Commands
```bash
# Run single connectivity test
python3 wifi_monitor.py --monitor

# Generate analysis report from historical data
python3 wifi_monitor.py --analyze

# Analyze specific time period
python3 wifi_monitor.py --analyze --days 1

# Enable debug output
python3 wifi_monitor.py --monitor --debug
```

## Architecture

### Main Class: ConnectivityMonitor
- Handles all connectivity testing operations
- Manages network interface detection for different platforms
- Performs parallel test execution using ThreadPoolExecutor
- Logs results to CSV format

### Test Types
1. **Ping Tests**: Tests packet loss and latency to DNS servers and gateway
2. **HTTP Tests**: Tests web connectivity to multiple endpoints
3. **HTTPS Tests**: Tests secure web connectivity 
4. **DNS Tests**: Tests domain name resolution performance

### Output Files
- `logs/connectivity_summary.csv`: Summary data with newest entries first
- `logs/wifi_monitor_debug.log`: Debug output (when --debug flag used)

## Project Structure
- `wifi_monitor.py` - Main Python monitoring script
- `requirements.txt` - Python dependencies
- `logs/` - Log files directory
- `archive/` - Legacy implementations