#!/bin/bash

# Internet Connectivity Monitor Script
# Works on macOS and Linux systems
# Logs connectivity status with WiFi SSID and timestamp every minute

# Set PATH for cron environment (includes system directories)
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/connectivity.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Get current timestamp in IST format
get_timestamp() {
    TZ="Asia/Kolkata" date +"%Y-%m-%d %H:%M:%S%z"
}

# Detect operating system
detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macOS" ;;
        Linux) echo "linux" ;;
        *) echo "unknown" ;;
    esac
}

# Get username@hostname for user identification
get_user_host() {
    echo "$(whoami)@$(hostname)"
}

# Get default gateway IP address
get_gateway_ip() {
    local os="$(detect_os)"
    case "$os" in
        "macOS")
            route -n get default 2>/dev/null | grep 'gateway:' | awk '{print $2}' | head -1
            ;;
        "linux")
            ip route show default 2>/dev/null | grep 'via' | awk '{print $3}' | head -1
            ;;
        *)
            echo ""
            ;;
    esac
}

# Get connection type and WiFi SSID based on OS
get_connection_info() {
    local os="$(detect_os)"
    local ssid=""
    local connection_type=""
    
    case "$os" in
        "macOS")
            # Method 1: Try system_profiler for more reliable WiFi detection
            local wifi_ssid=$(system_profiler SPAirPortDataType 2>/dev/null | grep -A3 "Current Network Information:" | grep -E "^\s{10,}[A-Za-z0-9_-]+:" | head -1 | sed 's/^\s*\([^:]*\):.*/\1/' | tr -d ' ')
            if [[ -n "$wifi_ssid" ]]; then
                echo "WiFi:$wifi_ssid"
                return
            fi
            
            # Method 2: Try networksetup as fallback
            for interface in en0 en1 en2; do
                local wifi_result=$(networksetup -getairportnetwork "$interface" 2>/dev/null)
                if [[ -n "$wifi_result" ]] && [[ "$wifi_result" != *"You are not associated with an AirPort network"* ]] && [[ "$wifi_result" != *"is not a Wi-Fi interface"* ]] && [[ "$wifi_result" != *"Error"* ]]; then
                    ssid=$(echo "$wifi_result" | sed 's/Current Wi-Fi Network: //')
                    if [[ -n "$ssid" ]]; then
                        echo "WiFi:$ssid"
                        return
                    fi
                fi
            done
            
            # Check active network services to determine connection type
            local active_service=$(networksetup -listnetworkserviceorder | grep -E "Hardware Port.*Device: (en[0-9]|eth[0-9])" | head -1)
            if [[ -n "$active_service" ]]; then
                if echo "$active_service" | grep -i "ethernet" >/dev/null; then
                    echo "Ethernet"
                    return
                elif echo "$active_service" | grep -i "usb" >/dev/null; then
                    echo "USB"
                    return
                else
                    # Check if any interface has an IP
                    local active_interfaces=$(ifconfig | grep "flags=.*UP.*RUNNING" | grep -E "^(en|eth)" | cut -d: -f1)
                    for interface in $active_interfaces; do
                        if ifconfig "$interface" | grep "inet " >/dev/null 2>&1; then
                            echo "Wired"
                            return
                        fi
                    done
                fi
            fi
            ;;
        "linux")
            # Try multiple methods on Linux for WiFi
            # Method 1: iwgetid
            if command -v iwgetid >/dev/null 2>&1; then
                ssid=$(iwgetid -r 2>/dev/null)
                if [[ -n "$ssid" ]]; then
                    echo "WiFi:$ssid"
                    return
                fi
            fi
            
            # Method 2: nmcli
            if command -v nmcli >/dev/null 2>&1; then
                ssid=$(nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2)
                if [[ -n "$ssid" ]]; then
                    echo "WiFi:$ssid"
                    return
                fi
            fi
            
            # Method 3: iw (requires root, fallback)
            if command -v iw >/dev/null 2>&1; then
                ssid=$(iw dev 2>/dev/null | grep ssid | head -1 | sed 's/.*ssid //')
                if [[ -n "$ssid" ]]; then
                    echo "WiFi:$ssid"
                    return
                fi
            fi
            
            # Check for wired connections
            local active_interfaces=$(ip link show up 2>/dev/null | grep -E "^[0-9]+: (eth|enp|eno|ens)" | cut -d: -f2 | tr -d ' ')
            if [[ -n "$active_interfaces" ]]; then
                echo "Ethernet"
                return
            fi
            ;;
    esac
    
    echo "Not Connected"
}

# Test internet connectivity
test_connectivity() {
    local response_time=""
    local status="Disconnected"
    
    # Test with ping to Google DNS
    if ping_result=$(ping -c 1 -W 3000 8.8.8.8 2>/dev/null); then
        response_time=$(echo "$ping_result" | grep 'time=' | sed 's/.*time=\([0-9.]*\).*/\1/')
        if [[ -n "$response_time" ]]; then
            status="Connected"
            response_time="${response_time}ms"
        fi
    fi
    
    # Fallback test with Cloudflare DNS if first test failed
    if [[ "$status" == "Disconnected" ]]; then
        if ping_result=$(ping -c 1 -W 3000 1.1.1.1 2>/dev/null); then
            response_time=$(echo "$ping_result" | grep 'time=' | sed 's/.*time=\([0-9.]*\).*/\1/')
            if [[ -n "$response_time" ]]; then
                status="Connected"
                response_time="${response_time}ms"
            fi
        fi
    fi
    
    # Final fallback with curl test
    if [[ "$status" == "Disconnected" ]] && command -v curl >/dev/null 2>&1; then
        if curl -s --max-time 5 --connect-timeout 3 http://www.google.com >/dev/null 2>&1; then
            status="Connected"
            response_time="curl-ok"
        fi
    fi
    
    echo "$status|$response_time"
}

# Test small file download to measure throughput
test_small_download() {
    local download_status="Failed"
    local download_speed="-"
    
    # Test URLs for 250KB file downloads
    local test_urls=(
        "http://httpbin.org/bytes/256000"
        "https://speed.cloudflare.com/__down?bytes=256000"
        "http://ipv4.download.thinkbroadband.com/256KB.zip"
    )
    
    if command -v curl >/dev/null 2>&1; then
        for url in "${test_urls[@]}"; do
            # Use curl to download with timing, timeout after 10 seconds for 250KB
            if curl_result=$(curl -s -m 10 -w "speed_download:%{speed_download}" -o /dev/null "$url" 2>/dev/null); then
                # Extract download speed in bytes per second
                local speed_bps=$(echo "$curl_result" | grep 'speed_download:' | cut -d':' -f2)
                if [[ -n "$speed_bps" ]] && [[ "$speed_bps" != "0" ]]; then
                    # Convert to KB/s for readability
                    local speed_kbs=$(echo "$speed_bps" | awk '{printf "%.1f", $1/1024}')
                    download_status="Success"
                    download_speed="${speed_kbs}KB/s"
                    break
                fi
            fi
        done
    fi
    
    echo "$download_status|$download_speed"
}

# Test multiple endpoints for connection diversity
test_multiple_endpoints() {
    local endpoints=(
        "8.8.8.8"           # Google DNS
        "1.1.1.1"           # Cloudflare DNS
        "9.9.9.9"           # Quad9 DNS
        "google.com"        # Google web
        "github.com"        # GitHub
    )
    
    # Add gateway if available
    local gateway_ip=$(get_gateway_ip)
    if [[ -n "$gateway_ip" ]]; then
        endpoints+=("$gateway_ip")
    fi
    
    local successful_count=0
    local total_count=${#endpoints[@]}
    
    for endpoint in "${endpoints[@]}"; do
        # Use ping with shorter timeout for faster testing
        if ping -c 1 -W 1000 "$endpoint" >/dev/null 2>&1; then
            ((successful_count++))
        fi
    done
    
    echo "$successful_count/$total_count"
}

# Main execution
main() {
    local timestamp=$(get_timestamp)
    local connection_info=$(get_connection_info)
    local os=$(detect_os)
    local user_host=$(get_user_host)
    local connectivity_result=$(test_connectivity)
    local status=$(echo "$connectivity_result" | cut -d'|' -f1)
    local response_time=$(echo "$connectivity_result" | cut -d'|' -f2)
    
    # New robustness tests
    local download_result=$(test_small_download)
    local download_status=$(echo "$download_result" | cut -d'|' -f1)
    local download_speed=$(echo "$download_result" | cut -d'|' -f2)
    local endpoints_result=$(test_multiple_endpoints)
    
    # Format response time for display
    if [[ "$status" == "Disconnected" ]] || [[ -z "$response_time" ]]; then
        response_time="-"
    fi
    
    # Log entry format: timestamp | user@host | connection_info | ping_status | ping_time | download_status | download_speed | endpoints_ok | platform
    log_entry="$timestamp | $user_host | $connection_info | $status | $response_time | $download_status | $download_speed | $endpoints_result | $os"
    
    # Write to log file
    echo "$log_entry" >> "$LOG_FILE"
    
    # Optional: also output to stdout for debugging
    # echo "$log_entry"
}

# Run main function
main