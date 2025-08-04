#!/usr/bin/env python3
"""
Internet Connectivity Monitor
A comprehensive Python script to monitor internet connectivity and generate ISP-ready reports.
"""

import argparse
import csv
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    import requests
except ImportError:
    requests = None

try:
    import psutil
except ImportError:
    psutil = None


class ConnectivityMonitor:
    def __init__(self, log_dir: str = "logs", debug: bool = False):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # JSON logging removed - using CSV only
        self.csv_log_file = self.log_dir / "connectivity_summary.csv"
        self.debug_log_file = self.log_dir / "wifi_monitor_debug.log"
        
        # Setup debug logging
        self.debug = debug
        if debug:
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(self.debug_log_file),
                    logging.StreamHandler()
                ]
            )
            self.logger = logging.getLogger(__name__)
        else:
            # Setup basic logging for errors
            logging.basicConfig(
                level=logging.ERROR,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(self.debug_log_file)
                ]
            )
            self.logger = logging.getLogger(__name__)
        
        # Test endpoints
        self.dns_servers = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]
        self.http_endpoints = [
            "http://www.google.com",
            "http://www.github.com",
            "http://www.cloudflare.com",
            "http://www.yuvilabs.com"
        ]
        self.https_endpoints = [
            "https://www.google.com",
            "https://www.github.com",
            "https://www.cloudflare.com",
            "https://www.yuvilabs.com"
        ]
        
        # Test configuration
        self.ping_timeout = 3
        self.http_timeout = 5
        self.max_workers = 10
        
    def get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()
    
    def get_local_timestamp(self) -> str:
        """Get current timestamp in local timezone."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def get_system_info(self) -> Dict[str, str]:
        """Get system information."""
        try:
            hostname = socket.gethostname()
            username = os.getenv('USER', 'unknown')
            system = platform.system()
            return {
                "hostname": hostname,
                "username": username,
                "user_host": f"{username}@{hostname}",
                "system": system
            }
        except Exception as e:
            return {
                "hostname": "unknown",
                "username": "unknown", 
                "user_host": "unknown@unknown",
                "system": platform.system()
            }
    
    def _find_ping_command(self) -> str:
        """Find the ping command on the system."""
        # Common ping locations on different systems
        ping_locations = [
            "/sbin/ping",    # macOS and many Linux systems
            "/bin/ping",     # Some Linux systems
            "ping"           # If it's in PATH
        ]
        
        for ping_cmd in ping_locations:
            try:
                # Test if the command exists and works
                result = subprocess.run(
                    [ping_cmd, "-c", "1", "-W", "1", "127.0.0.1"] if platform.system().lower() != "windows" 
                    else [ping_cmd, "-n", "1", "-w", "1000", "127.0.0.1"],
                    capture_output=True, timeout=2
                )
                if result.returncode in [0, 1, 2]:  # 0=success, 1=no reply, 2=name resolution failed (all are valid ping responses)
                    return ping_cmd
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        
        return None

    def ping_host(self, host: str, timeout: int = None) -> Dict[str, Union[bool, float, str]]:
        """Ping a host and return connection status and latency."""
        if timeout is None:
            timeout = self.ping_timeout
            
        # Find ping command if not cached
        if not hasattr(self, '_ping_cmd'):
            self._ping_cmd = self._find_ping_command()
            
        if self._ping_cmd is None:
            return {
                "success": False,
                "latency_ms": None,
                "error": "Ping command not found in system PATH or standard locations"
            }
            
        try:
            # Use ping command appropriate for the OS
            if platform.system().lower() == "windows":
                cmd = [self._ping_cmd, "-n", "1", "-w", str(timeout * 1000), host]
            else:
                cmd = [self._ping_cmd, "-c", "1", "-W", str(timeout), host]
            
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1)
            end_time = time.time()
            
            if result.returncode == 0:
                # Extract latency from ping output
                output = result.stdout.lower()
                latency = None
                
                # Parse different ping output formats
                if "time=" in output:
                    try:
                        latency_str = output.split("time=")[1].split()[0]
                        latency = float(latency_str.replace("ms", ""))
                    except (IndexError, ValueError):
                        latency = (end_time - start_time) * 1000
                else:
                    latency = (end_time - start_time) * 1000
                
                return {
                    "success": True,
                    "latency_ms": round(latency, 2) if latency else None,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "latency_ms": None,
                    "error": result.stderr.strip() or "Ping failed"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "latency_ms": None,
                "error": f"Ping timeout after {timeout}s"
            }
        except FileNotFoundError:
            return {
                "success": False,
                "latency_ms": None,
                "error": f"Ping command not found: {self._ping_cmd if hasattr(self, '_ping_cmd') else 'ping'}"
            }
        except Exception as e:
            error_msg = f"Ping error: {str(e)}"
            if "No such file or directory" in str(e):
                error_msg = "Ping command not found - check PATH environment variable"
            elif "Permission denied" in str(e):
                error_msg = "Permission denied - check cron permissions for network commands"
            self.logger.error(error_msg)
            return {
                "success": False,
                "latency_ms": None,
                "error": error_msg
            }
    
    def test_http_connectivity(self, url: str, timeout: int = None) -> Dict[str, Union[bool, float, str]]:
        """Test HTTP/HTTPS connectivity to a URL."""
        if timeout is None:
            timeout = self.http_timeout
            
        try:
            if requests:
                start_time = time.time()
                response = requests.get(url, timeout=timeout, allow_redirects=True)
                end_time = time.time()
                
                return {
                    "success": response.status_code == 200,
                    "response_time_ms": round((end_time - start_time) * 1000, 2),
                    "status_code": response.status_code,
                    "error": None if response.status_code == 200 else f"HTTP {response.status_code}"
                }
            else:
                # Fallback using urllib if requests is not available
                import urllib.request
                import urllib.error
                
                start_time = time.time()
                try:
                    with urllib.request.urlopen(url, timeout=timeout) as response:
                        end_time = time.time()
                        return {
                            "success": True,
                            "response_time_ms": round((end_time - start_time) * 1000, 2),
                            "status_code": response.getcode(),
                            "error": None
                        }
                except urllib.error.HTTPError as e:
                    end_time = time.time()
                    return {
                        "success": False,
                        "response_time_ms": round((end_time - start_time) * 1000, 2),
                        "status_code": e.code,
                        "error": f"HTTP {e.code}"
                    }
                    
        except Exception as e:
            error_msg = str(e)
            # Provide more specific error messages
            if "Connection refused" in error_msg:
                error_msg = "Connection refused - service may be down"
            elif "Name or service not known" in error_msg or "nodename nor servname provided" in error_msg:
                error_msg = "DNS resolution failed"
            elif "timeout" in error_msg.lower():
                error_msg = f"Request timeout after {timeout}s"
            elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                error_msg = "SSL/TLS certificate error"
            elif "Permission denied" in error_msg:
                error_msg = "Permission denied - check network access permissions"
            
            self.logger.error(f"HTTP connectivity error for {url}: {error_msg}")
            
            return {
                "success": False,
                "response_time_ms": None,
                "status_code": None,
                "error": error_msg
            }
    
    def test_dns_resolution(self, hostname: str, timeout: int = 3) -> Dict[str, Union[bool, float, str, List[str]]]:
        """Test DNS resolution for a hostname."""
        try:
            start_time = time.time()
            socket.setdefaulttimeout(timeout)
            
            # Get IP addresses
            addr_info = socket.getaddrinfo(hostname, None)
            ips = list(set([info[4][0] for info in addr_info]))
            
            end_time = time.time()
            
            return {
                "success": True,
                "resolution_time_ms": round((end_time - start_time) * 1000, 2),
                "ips": ips,
                "error": None
            }
            
        except socket.gaierror as e:
            error_code = e.errno if hasattr(e, 'errno') else None
            if error_code == -2:
                error_msg = "Name resolution failed - hostname not found"
            elif error_code == -3:
                error_msg = "Temporary DNS failure - try again later"
            else:
                error_msg = f"DNS resolution failed: {str(e)}"
            
            return {
                "success": False,
                "resolution_time_ms": None,
                "ips": [],
                "error": error_msg
            }
        except socket.timeout:
            return {
                "success": False,
                "resolution_time_ms": None,
                "ips": [],
                "error": f"DNS resolution timeout after {timeout}s"
            }
        except Exception as e:
            return {
                "success": False,
                "resolution_time_ms": None,
                "ips": [],
                "error": f"DNS error: {str(e)}"
            }
        finally:
            socket.setdefaulttimeout(None)
    
    def get_network_interface_info(self) -> Dict[str, Union[str, None]]:
        """Get network interface information including WiFi SSID."""
        self.logger.debug("Starting network interface detection")
        try:
            if platform.system().lower() == "darwin":
                # macOS
                self.logger.debug("Using macOS network detection methods")
                return self._get_macos_network_info()
            elif platform.system().lower() == "linux":
                # Linux
                self.logger.debug("Using Linux network detection methods")
                return self._get_linux_network_info()
            else:
                self.logger.debug(f"Unsupported platform: {platform.system()}")
                return {"connection_type": "Unknown", "ssid": None}
        except Exception as e:
            self.logger.error(f"Error in get_network_interface_info: {str(e)}")
            return {"connection_type": "Error", "ssid": None, "error": str(e)}
    
    def _get_macos_network_info(self) -> Dict[str, Union[str, None]]:
        """Get network info on macOS with multiple robust detection methods."""
        self.logger.debug("Environment variables: PATH={}, HOME={}, USER={}".format(
            os.environ.get('PATH', 'NOT_SET'),
            os.environ.get('HOME', 'NOT_SET'), 
            os.environ.get('USER', 'NOT_SET')
        ))
        
        try:
            # Method 1: Try networksetup to get current WiFi network (most reliable)
            self.logger.debug("Method 1: Trying networksetup command on en0")
            try:
                cmd = ["/usr/sbin/networksetup", "-getairportnetwork", "en0"]
                self.logger.debug(f"Running command: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5
                )
                self.logger.debug(f"Command exit code: {result.returncode}")
                self.logger.debug(f"Command stdout: {result.stdout}")
                self.logger.debug(f"Command stderr: {result.stderr}")
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    if "Current Wi-Fi Network:" in output:
                        ssid = output.split("Current Wi-Fi Network:")[1].strip()
                        if ssid and ssid != "You are not associated with an AirPort network.":
                            self.logger.debug(f"Method 1 success: Found WiFi SSID: {ssid}")
                            return {"connection_type": "WiFi", "ssid": ssid}
                    elif "You are not associated with an AirPort network." not in output:
                        # Might be connected but different format
                        if output and output != "You are not associated with an AirPort network.":
                            self.logger.debug(f"Method 1 success (alt format): Found WiFi SSID: {output}")
                            return {"connection_type": "WiFi", "ssid": output}
                self.logger.debug("Method 1 failed: No WiFi network found on en0")
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                self.logger.debug(f"Method 1 exception: {type(e).__name__}: {str(e)}")
                if isinstance(e, FileNotFoundError):
                    self.logger.error("networksetup command not found - ensure it's in /usr/sbin/")
                elif isinstance(e, subprocess.TimeoutExpired):
                    self.logger.error("networksetup command timed out - possible permission or system issue")
                pass
            
            # Try en1 interface as well  
            self.logger.debug("Method 1b: Trying networksetup command on en1")
            try:
                cmd = ["/usr/sbin/networksetup", "-getairportnetwork", "en1"]
                self.logger.debug(f"Running command: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5
                )
                self.logger.debug(f"Command exit code: {result.returncode}")
                self.logger.debug(f"Command stdout: {result.stdout}")
                self.logger.debug(f"Command stderr: {result.stderr}")
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    if "Current Wi-Fi Network:" in output:
                        ssid = output.split("Current Wi-Fi Network:")[1].strip()
                        if ssid and ssid != "You are not associated with an AirPort network.":
                            self.logger.debug(f"Method 1b success: Found WiFi SSID: {ssid}")
                            return {"connection_type": "WiFi", "ssid": ssid}
                    elif "You are not associated with an AirPort network." not in output:
                        if output and output != "You are not associated with an AirPort network.":
                            self.logger.debug(f"Method 1b success (alt format): Found WiFi SSID: {output}")
                            return {"connection_type": "WiFi", "ssid": output}
                self.logger.debug("Method 1b failed: No WiFi network found on en1")
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                self.logger.debug(f"Method 1b exception: {type(e).__name__}: {str(e)}")
                pass
            
            # Method 2: Try system_profiler with improved parsing
            self.logger.debug("Method 2: Trying system_profiler command")
            try:
                cmd = ["/usr/sbin/system_profiler", "SPAirPortDataType"]
                self.logger.debug(f"Running command: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=10
                )
                self.logger.debug(f"Command exit code: {result.returncode}")
                self.logger.debug(f"Command stdout length: {len(result.stdout)} chars")
                self.logger.debug(f"Command stderr: {result.stderr}")
                
                if result.returncode == 0:
                    output = result.stdout
                    
                    # Look for Status: Connected first
                    if "Status: Connected" in output:
                        # Find current network information section
                        current_network_start = output.find("Current Network Information:")
                        if current_network_start != -1:
                            # Extract the network section
                            network_section = output[current_network_start:]
                            lines = network_section.split('\n')
                            
                            # Look for the SSID in the next few lines
                            for i, line in enumerate(lines):
                                if i == 0:  # Skip the header line
                                    continue
                                if i > 10:  # Don't search too far
                                    break
                                    
                                line = line.strip()
                                if line and ':' in line:
                                    # Skip known non-SSID fields
                                    if any(field in line.lower() for field in [
                                        'phy mode', 'channel', 'country code', 'network type', 
                                        'security', 'signal', 'noise', 'tx rate', 'mcs index'
                                    ]):
                                        continue
                                    
                                    # This should be the SSID line
                                    ssid = line.split(':')[0].strip()
                                    if ssid and len(ssid) > 0:
                                        self.logger.debug(f"Method 2 success: Found WiFi SSID: {ssid}")
                                        return {"connection_type": "WiFi", "ssid": ssid}
                self.logger.debug("Method 2 failed: No WiFi connection found in system_profiler")
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                self.logger.debug(f"Method 2 exception: {type(e).__name__}: {str(e)}")
                pass
            
            # Method 3: Check active interface and determine connection type
            self.logger.debug("Method 3: Trying to determine active network interface")
            active_interface = None
            try:
                cmd = ["route", "-n", "get", "default"]
                self.logger.debug(f"Running command: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5
                )
                self.logger.debug(f"Command exit code: {result.returncode}")
                self.logger.debug(f"Command stdout: {result.stdout}")
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'interface:' in line:
                            active_interface = line.split(':')[1].strip()
                            self.logger.debug(f"Found active interface: {active_interface}")
                            break
                if not active_interface:
                    self.logger.debug("No active interface found in route output")
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                self.logger.debug(f"Method 3 exception: {type(e).__name__}: {str(e)}")
                pass
            
            # Method 4: Use ifconfig to check interface type
            if active_interface:
                try:
                    result = subprocess.run(
                        ["ifconfig", active_interface],
                        capture_output=True, text=True, timeout=3
                    )
                    if result.returncode == 0:
                        ifconfig_output = result.stdout
                        if "inet " in ifconfig_output:
                            # Check if it's a WiFi interface
                            if active_interface.startswith('en'):
                                # Check hardware type in ifconfig output
                                if "media:" in ifconfig_output.lower() and "wireless" in ifconfig_output.lower():
                                    return {"connection_type": "WiFi", "ssid": "Connected (SSID detection failed)"}
                                elif active_interface == "en0":
                                    # en0 is typically WiFi on MacBooks
                                    return {"connection_type": "WiFi", "ssid": "Connected (SSID detection failed)"}
                                else:
                                    # Likely Ethernet
                                    return {"connection_type": "Ethernet", "ssid": None}
                            else:
                                return {"connection_type": "Other", "ssid": None}
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
            
            # Method 5: Check network services
            try:
                result = subprocess.run(
                    ["/usr/sbin/networksetup", "-listallhardwareports"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    output = result.stdout
                    lines = output.split('\n')
                    current_service = None
                    
                    for line in lines:
                        if line.startswith('Hardware Port:'):
                            current_service = line.split(':', 1)[1].strip()
                        elif line.startswith('Device:') and active_interface:
                            device = line.split(':', 1)[1].strip()
                            if device == active_interface:
                                if current_service and 'wi-fi' in current_service.lower():
                                    return {"connection_type": "WiFi", "ssid": "Connected (SSID detection failed)"}
                                elif current_service and 'ethernet' in current_service.lower():
                                    return {"connection_type": "Ethernet", "ssid": None}
                                else:
                                    return {"connection_type": "Other", "ssid": None}
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
            
            # Default fallback
            self.logger.debug("All methods failed, using fallback")
            if active_interface:
                self.logger.debug(f"Fallback: Detected interface {active_interface} as 'Other'")
                return {"connection_type": "Other", "ssid": None}
            else:
                self.logger.debug("Fallback: No interface detected, marking as 'Unknown'")
                return {"connection_type": "Unknown", "ssid": None}
                
        except Exception as e:
            self.logger.error(f"Unexpected error in _get_macos_network_info: {str(e)}")
            return {"connection_type": "Error", "ssid": None, "error": str(e)}
    
    def _get_linux_network_info(self) -> Dict[str, Union[str, None]]:
        """Get network info on Linux."""
        try:
            # Try iwgetid for WiFi SSID
            try:
                result = subprocess.run(
                    ["iwgetid", "-r"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return {"connection_type": "WiFi", "ssid": result.stdout.strip()}
            except:
                pass
            
            # Try nmcli as alternative
            try:
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith('yes:'):
                            ssid = line.split(':', 1)[1]
                            return {"connection_type": "WiFi", "ssid": ssid}
            except:
                pass
            
            # Check for ethernet
            try:
                result = subprocess.run(
                    ["ip", "link", "show"], capture_output=True, text=True, timeout=5
                )
                if "state UP" in result.stdout and ("eth" in result.stdout or "enp" in result.stdout):
                    return {"connection_type": "Ethernet", "ssid": None}
            except:
                pass
                
            return {"connection_type": "Unknown", "ssid": None}
            
        except Exception as e:
            return {"connection_type": "Error", "ssid": None, "error": str(e)}
    
    def get_gateway_ip(self) -> Optional[str]:
        """Get the default gateway IP address with multiple fallback methods."""
        try:
            if platform.system().lower() == "darwin":
                # Method 1: route command
                try:
                    result = subprocess.run(
                        ["route", "-n", "get", "default"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if 'gateway:' in line:
                                gateway = line.split(':')[1].strip()
                                if gateway:
                                    return gateway
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
                
                # Method 2: netstat command
                try:
                    result = subprocess.run(
                        ["netstat", "-rn", "-f", "inet"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if line.startswith('default') or line.startswith('0.0.0.0'):
                                parts = line.split()
                                if len(parts) >= 2:
                                    gateway = parts[1]
                                    # Validate it's an IP address
                                    if gateway.count('.') == 3:
                                        return gateway
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
                
                # Method 3: networksetup command
                try:
                    # Get active network service
                    result = subprocess.run(
                        ["/usr/sbin/networksetup", "-listnetworkserviceorder"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        # Look for Wi-Fi or Ethernet services
                        services = []
                        for line in result.stdout.split('\n'):
                            if 'Wi-Fi' in line or 'Ethernet' in line:
                                # Extract service name
                                if '"' in line:
                                    service = line.split('"')[1]
                                    services.append(service)
                        
                        # Try to get router info from active services
                        for service in services:
                            try:
                                result = subprocess.run(
                                    ["/usr/sbin/networksetup", "-getinfo", service],
                                    capture_output=True, text=True, timeout=3
                                )
                                if result.returncode == 0:
                                    for line in result.stdout.split('\n'):
                                        if 'Router:' in line:
                                            gateway = line.split(':')[1].strip()
                                            if gateway and gateway != 'none':
                                                return gateway
                            except:
                                continue
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
            
            elif platform.system().lower() == "linux":
                # Method 1: ip route command
                try:
                    result = subprocess.run(
                        ["ip", "route", "show", "default"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if 'via' in line:
                                parts = line.split()
                                via_idx = parts.index('via')
                                if via_idx + 1 < len(parts):
                                    return parts[via_idx + 1]
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
                
                # Method 2: route command
                try:
                    result = subprocess.run(
                        ["route", "-n"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if line.startswith('0.0.0.0'):
                                parts = line.split()
                                if len(parts) >= 2:
                                    return parts[1]
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
            
            return None
            
        except Exception:
            return None
    
    def run_connectivity_tests(self) -> Dict:
        """Run all connectivity tests in parallel."""
        results = {
            "timestamp": self.get_timestamp(),
            "local_timestamp": self.get_local_timestamp(),
            "system_info": self.get_system_info(),
            "network_info": self.get_network_interface_info(),
            "tests": {
                "ping": {},
                "http": {},
                "https": {},
                "dns": {}
            },
            "summary": {}
        }
        
        # Add gateway to ping tests
        gateway_ip = self.get_gateway_ip()
        ping_targets = self.dns_servers.copy()
        if gateway_ip:
            ping_targets.append(gateway_ip)
            results["gateway_ip"] = gateway_ip
        
        # Run tests in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit ping tests
            ping_futures = {
                executor.submit(self.ping_host, host): host 
                for host in ping_targets
            }
            
            # Submit HTTP tests
            http_futures = {
                executor.submit(self.test_http_connectivity, url): url 
                for url in self.http_endpoints
            }
            
            # Submit HTTPS tests  
            https_futures = {
                executor.submit(self.test_http_connectivity, url): url 
                for url in self.https_endpoints
            }
            
            # Submit DNS tests
            dns_test_hosts = ["google.com", "github.com", "cloudflare.com"]
            dns_futures = {
                executor.submit(self.test_dns_resolution, host): host 
                for host in dns_test_hosts
            }
            
            # Collect ping results
            for future in as_completed(ping_futures):
                host = ping_futures[future]
                try:
                    result = future.result()
                    results["tests"]["ping"][host] = result
                except Exception as e:
                    results["tests"]["ping"][host] = {
                        "success": False, "latency_ms": None, "error": str(e)
                    }
            
            # Collect HTTP results
            for future in as_completed(http_futures):
                url = http_futures[future]
                try:
                    result = future.result()
                    results["tests"]["http"][url] = result
                except Exception as e:
                    results["tests"]["http"][url] = {
                        "success": False, "response_time_ms": None, "error": str(e)
                    }
            
            # Collect HTTPS results
            for future in as_completed(https_futures):
                url = https_futures[future] 
                try:
                    result = future.result()
                    results["tests"]["https"][url] = result
                except Exception as e:
                    results["tests"]["https"][url] = {
                        "success": False, "response_time_ms": None, "error": str(e)
                    }
            
            # Collect DNS results
            for future in as_completed(dns_futures):
                host = dns_futures[future]
                try:
                    result = future.result()
                    results["tests"]["dns"][host] = result
                except Exception as e:
                    results["tests"]["dns"][host] = {
                        "success": False, "resolution_time_ms": None, "error": str(e)
                    }
        
        # Calculate summary statistics
        results["summary"] = self._calculate_summary(results["tests"])
        
        return results
    
    def _calculate_summary(self, tests: Dict) -> Dict:
        """Calculate summary statistics from test results."""
        summary = {
            "overall_score": 0,
            "connectivity_status": "Unknown",
            "ping_success_rate": 0,
            "http_success_rate": 0,
            "https_success_rate": 0,
            "dns_success_rate": 0,
            "average_ping_latency": None,
            "average_http_response_time": None,
            "issues_detected": []
        }
        
        # Calculate ping statistics
        ping_results = list(tests["ping"].values())
        if ping_results:
            ping_successes = sum(1 for r in ping_results if r["success"])
            summary["ping_success_rate"] = (ping_successes / len(ping_results)) * 100
            
            successful_pings = [r["latency_ms"] for r in ping_results if r["success"] and r["latency_ms"]]
            if successful_pings:
                summary["average_ping_latency"] = round(sum(successful_pings) / len(successful_pings), 2)
        
        # Calculate HTTP statistics
        http_results = list(tests["http"].values())
        if http_results:
            http_successes = sum(1 for r in http_results if r["success"])
            summary["http_success_rate"] = (http_successes / len(http_results)) * 100
            
            successful_http = [r["response_time_ms"] for r in http_results if r["success"] and r["response_time_ms"]]
            if successful_http:
                summary["average_http_response_time"] = round(sum(successful_http) / len(successful_http), 2)
        
        # Calculate HTTPS statistics
        https_results = list(tests["https"].values())
        if https_results:
            https_successes = sum(1 for r in https_results if r["success"])
            summary["https_success_rate"] = (https_successes / len(https_results)) * 100
        
        # Calculate DNS statistics
        dns_results = list(tests["dns"].values())
        if dns_results:
            dns_successes = sum(1 for r in dns_results if r["success"])
            summary["dns_success_rate"] = (dns_successes / len(dns_results)) * 100
        
        # Overall connectivity status and score
        success_rates = [
            summary["ping_success_rate"],
            summary["http_success_rate"],
            summary["https_success_rate"], 
            summary["dns_success_rate"]
        ]
        
        overall_success_rate = sum(success_rates) / len(success_rates)
        summary["overall_score"] = round(overall_success_rate, 1)
        
        if overall_success_rate >= 90:
            summary["connectivity_status"] = "Excellent"
        elif overall_success_rate >= 75:
            summary["connectivity_status"] = "Good"
        elif overall_success_rate >= 50:
            summary["connectivity_status"] = "Poor"
        else:
            summary["connectivity_status"] = "Failed"
        
        # Detect specific issues with better error classification
        ping_results = list(tests["ping"].values())
        ping_command_errors = sum(1 for r in ping_results 
                                if not r["success"] and r["error"] and 
                                ("No such file or directory" in r["error"] or 
                                 "command not found" in r["error"] or
                                 "Ping command not found" in r["error"]))
        
        # Only report packet loss if ping commands are working but failing
        if summary["ping_success_rate"] < 50:
            if ping_command_errors == len(ping_results):
                summary["issues_detected"].append("Ping command unavailable - unable to test packet loss")
            else:
                summary["issues_detected"].append("High packet loss detected")
        
        if summary["dns_success_rate"] < 75:
            summary["issues_detected"].append("DNS resolution issues")
        if summary["http_success_rate"] < 75:
            summary["issues_detected"].append("HTTP connectivity problems")
        if summary["average_ping_latency"] and summary["average_ping_latency"] > 500:
            summary["issues_detected"].append("High latency detected")
        
        return summary
    
    def log_results(self, results: Dict) -> None:
        """Log results to CSV file."""
        # Log to CSV file only
        self._log_to_csv(results)
    
    def _log_to_csv(self, results: Dict) -> None:
        """Log summary results to CSV file with newest entries at the top."""
        csv_row = {
            'timestamp': results['local_timestamp'],
            'user_host': results['system_info']['user_host'],
            'connection_type': results['network_info'].get('connection_type', 'Unknown'),
            'ssid': results['network_info'].get('ssid', ''),
            'overall_score': results['summary']['overall_score'],
            'connectivity_status': results['summary']['connectivity_status'],
            'ping_success_rate': results['summary']['ping_success_rate'],
            'avg_ping_latency': results['summary']['average_ping_latency'] or '',
            'http_success_rate': results['summary']['http_success_rate'],
            'https_success_rate': results['summary']['https_success_rate'],
            'dns_success_rate': results['summary']['dns_success_rate'],
            'issues': '; '.join(results['summary']['issues_detected']),
            'system': results['system_info']['system']
        }
        
        fieldnames = csv_row.keys()
        existing_rows = []
        
        # Read existing data if file exists
        if self.csv_log_file.exists():
            try:
                with open(self.csv_log_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    existing_rows = list(reader)
            except (IOError, csv.Error) as e:
                self.logger.error(f"Error reading existing CSV file: {e}")
                existing_rows = []
        
        # Write the file with new row at the top
        try:
            with open(self.csv_log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(csv_row)  # New row goes first
                
                # Write existing rows (this reverses the order on first run)
                for row in existing_rows:
                    writer.writerow(row)
        except IOError as e:
            self.logger.error(f"Error writing to CSV file: {e}")
            # Fallback to append mode if write fails
            try:
                with open(self.csv_log_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if not existing_rows:  # File was empty/new
                        writer.writeheader()
                    writer.writerow(csv_row)
            except IOError as fallback_error:
                self.logger.error(f"Fallback CSV write also failed: {fallback_error}")
    
    def monitor_once(self) -> Dict:
        """Run monitoring once and log results."""
        results = self.run_connectivity_tests()
        self.log_results(results)
        return results
    
    def analyze_logs(self, days: int = 7) -> Dict:
        """Analyze recent logs and generate ISP report."""
        try:
            # Read CSV logs
            if not self.csv_log_file.exists():
                return {"error": "No log data found"}
            
            logs = []
            with open(self.csv_log_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                logs = list(reader)
            
            if not logs:
                return {"error": "No log data found"}
            
            # Filter recent logs (if days specified)
            if days > 0:
                cutoff_date = datetime.now() - timedelta(days=days)
                filtered_logs = []
                for log in logs:
                    try:
                        log_date = datetime.strptime(log['timestamp'], '%Y-%m-%d %H:%M:%S')
                        if log_date >= cutoff_date:
                            filtered_logs.append(log)
                    except:
                        filtered_logs.append(log)  # Include if we can't parse date
                logs = filtered_logs
            
            return self._generate_analysis_report(logs)
            
        except Exception as e:
            return {"error": f"Failed to analyze logs: {str(e)}"}
    
    def _generate_analysis_report(self, logs: List[Dict]) -> Dict:
        """Generate comprehensive analysis report from logs."""
        if not logs:
            return {"error": "No log data to analyze"}
        
        total_tests = len(logs)
        
        # Calculate statistics
        scores = [float(log.get('overall_score', 0)) for log in logs if log.get('overall_score')]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        connectivity_issues = sum(1 for log in logs if float(log.get('overall_score', 100)) < 75)
        uptime_percentage = ((total_tests - connectivity_issues) / total_tests) * 100 if total_tests > 0 else 0
        
        # Analyze ping statistics
        ping_rates = [float(log.get('ping_success_rate', 0)) for log in logs if log.get('ping_success_rate')]
        avg_ping_rate = sum(ping_rates) / len(ping_rates) if ping_rates else 0
        
        latencies = []
        for log in logs:
            if log.get('avg_ping_latency') and log['avg_ping_latency'] != '':
                try:
                    latencies.append(float(log['avg_ping_latency']))
                except ValueError:
                    continue
        
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        max_latency = max(latencies) if latencies else None
        
        # Count outages (consecutive failed tests)
        outages = []
        current_outage_start = None
        for i, log in enumerate(logs):
            score = float(log.get('overall_score', 100))
            if score < 50:  # Consider < 50% as outage
                if current_outage_start is None:
                    current_outage_start = i
            else:
                if current_outage_start is not None:
                    outages.append((current_outage_start, i - 1))
                    current_outage_start = None
        
        # Don't forget ongoing outage
        if current_outage_start is not None:
            outages.append((current_outage_start, len(logs) - 1))
        
        # Common issues
        issue_counts = {}
        for log in logs:
            issues = log.get('issues', '')
            if issues:
                for issue in issues.split('; '):
                    issue = issue.strip()
                    if issue:
                        issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        # Generate report
        report = {
            "analysis_period": {
                "start_time": logs[0]['timestamp'] if logs else None,
                "end_time": logs[-1]['timestamp'] if logs else None,
                "total_tests": total_tests
            },
            "connectivity_summary": {
                "average_score": round(avg_score, 1),
                "uptime_percentage": round(uptime_percentage, 2),
                "connectivity_issues": connectivity_issues,
                "total_outages": len(outages)
            },
            "performance_metrics": {
                "average_ping_success_rate": round(avg_ping_rate, 1),
                "average_latency_ms": round(avg_latency, 2) if avg_latency else None,
                "max_latency_ms": round(max_latency, 2) if max_latency else None
            },
            "outage_details": [
                {
                    "start": logs[start]['timestamp'],
                    "end": logs[end]['timestamp'],
                    "duration_minutes": end - start + 1  # Rough estimate
                }
                for start, end in outages
            ],
            "common_issues": issue_counts,
            "recommendations": self._generate_recommendations(avg_score, uptime_percentage, issue_counts)
        }
        
        return report
    
    def _generate_recommendations(self, avg_score: float, uptime: float, issues: Dict) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []
        
        if uptime < 95:
            recommendations.append("Internet connectivity is below acceptable standards (95% uptime)")
        
        if avg_score < 75:
            recommendations.append("Overall connection quality is poor - contact ISP for service review")
        
        if "High packet loss detected" in issues:
            recommendations.append("High packet loss indicates network infrastructure problems")
        
        if "DNS resolution issues" in issues:
            recommendations.append("DNS problems detected - may need DNS server configuration review")
        
        if "High latency detected" in issues:
            recommendations.append("Consistent high latency suggests routing or congestion issues")
        
        if not recommendations:
            recommendations.append("Connection quality appears acceptable")
        
        return recommendations


def main():
    parser = argparse.ArgumentParser(
        description="Internet Connectivity Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python wifi_monitor.py --monitor          # Run single connectivity test
  python wifi_monitor.py --analyze          # Analyze recent logs  
  python wifi_monitor.py --analyze --days 1 # Analyze last 24 hours
        """
    )
    
    parser.add_argument('--monitor', action='store_true', 
                       help='Run connectivity monitoring (for cron jobs)')
    parser.add_argument('--analyze', action='store_true',
                       help='Analyze logs and generate ISP report')
    parser.add_argument('--days', type=int, default=7,
                       help='Number of days to analyze (default: 7, 0 for all)')
    parser.add_argument('--log-dir', default='logs',
                       help='Directory for log files (default: logs)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging (useful for troubleshooting cron issues)')
    
    args = parser.parse_args()
    
    if not args.monitor and not args.analyze:
        parser.print_help()
        sys.exit(1)
    
    monitor = ConnectivityMonitor(log_dir=args.log_dir, debug=args.debug)
    
    if args.monitor:
        # Run monitoring
        try:
            results = monitor.monitor_once()
            # Print brief status for cron logs
            summary = results['summary']
            print(f"Status: {summary['connectivity_status']} "
                  f"(Score: {summary['overall_score']}%)")
        except Exception as e:
            print(f"Monitor error: {str(e)}", file=sys.stderr)
            sys.exit(1)
    
    if args.analyze:
        # Run analysis
        try:
            report = monitor.analyze_logs(days=args.days)
            
            if "error" in report:
                print(f"Analysis error: {report['error']}", file=sys.stderr)
                sys.exit(1)
            
            # Print formatted report
            print("=" * 60)
            print("INTERNET CONNECTIVITY ANALYSIS REPORT")
            print("=" * 60)
            
            period = report['analysis_period']
            print(f"Analysis Period: {period['start_time']} to {period['end_time']}")
            print(f"Total Tests: {period['total_tests']}")
            print()
            
            summary = report['connectivity_summary']
            print("CONNECTIVITY SUMMARY:")
            print(f"  Average Score: {summary['average_score']}%")
            print(f"  Uptime: {summary['uptime_percentage']}%")
            print(f"  Connectivity Issues: {summary['connectivity_issues']}")
            print(f"  Total Outages: {summary['total_outages']}")
            print()
            
            metrics = report['performance_metrics']
            print("PERFORMANCE METRICS:")
            print(f"  Avg Ping Success Rate: {metrics['average_ping_success_rate']}%")
            if metrics['average_latency_ms']:
                print(f"  Average Latency: {metrics['average_latency_ms']}ms")
            if metrics['max_latency_ms']:
                print(f"  Maximum Latency: {metrics['max_latency_ms']}ms")
            print()
            
            if report['outage_details']:
                print("OUTAGE DETAILS:")
                for i, outage in enumerate(report['outage_details'], 1):
                    print(f"  {i}. {outage['start']} to {outage['end']} "
                          f"(~{outage['duration_minutes']} minutes)")
                print()
            
            if report['common_issues']:
                print("COMMON ISSUES:")
                for issue, count in sorted(report['common_issues'].items(), 
                                         key=lambda x: x[1], reverse=True):
                    print(f"  {issue}: {count} occurrences")
                print()
            
            print("RECOMMENDATIONS:")
            for rec in report['recommendations']:
                print(f"  • {rec}")
            
            print("\n" + "=" * 60)
            print("This report can be provided to your ISP as evidence of connectivity issues.")
            
        except Exception as e:
            print(f"Analysis error: {str(e)}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()