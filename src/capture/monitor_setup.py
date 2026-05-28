"""WiFi interface detection and monitor mode management."""

import subprocess
import re
import time


def detect_wireless_interfaces():
    """Return list of WiFi interface names using iw/iwconfig."""
    interfaces = []
    # Try modern 'iw dev' first
    try:
        result = subprocess.run(['iw', 'dev'], capture_output=True, text=True)
        interfaces = re.findall(r'Interface\s+(\S+)', result.stdout)
    except FileNotFoundError:
        pass

    if not interfaces:
        # Fallback to iwconfig
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True)
            interfaces = re.findall(r'^(\S+)\s', result.stdout, re.MULTILINE)
        except FileNotFoundError:
            pass

    # Filter out lo and non-wireless
    interfaces = [i for i in interfaces if i != 'lo' and 'mon' not in i]
    return interfaces


def get_interface_info(interface):
    """Return dict with interface details (chipset, driver, supported modes)."""
    info = {'name': interface, 'monitor_capable': False}
    try:
        result = subprocess.run(['iw', 'list'], capture_output=True, text=True)
        info['iw_list'] = result.stdout
        info['monitor_capable'] = 'monitor' in result.stdout.lower()
    except FileNotFoundError:
        pass
    return info


def enable_monitor_mode(interface):
    """Put interface into monitor mode. Returns monitor interface name."""
    # Kill interfering processes
    try:
        subprocess.run(['sudo', 'airmon-ng', 'check', 'kill'],
                       capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try iw first (modern)
    try:
        subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'down'],
                       check=True, capture_output=True)
        subprocess.run(['sudo', 'iw', 'dev', interface, 'set', 'type', 'monitor'],
                       check=True, capture_output=True)
        subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'],
                       check=True, capture_output=True)
        time.sleep(1)
        if verify_monitor_mode(interface):
            return interface
    except subprocess.CalledProcessError:
        pass

    # Fallback to airmon-ng
    try:
        subprocess.run(['sudo', 'airmon-ng', 'start', interface],
                       check=True, capture_output=True, timeout=15)
        time.sleep(2)
        mon_iface = f"{interface}mon"
        if verify_monitor_mode(mon_iface):
            return mon_iface
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired):
        pass

    raise RuntimeError(f"Failed to enable monitor mode on {interface}")


def disable_monitor_mode(interface):
    """Restore interface to managed mode."""
    try:
        # Remove 'mon' suffix if present
        base_iface = interface.replace('mon', '')
        subprocess.run(['sudo', 'airmon-ng', 'stop', interface],
                       capture_output=True, timeout=15)
        subprocess.run(['sudo', 'ifconfig', base_iface, 'up'],
                       capture_output=True, timeout=10)
        subprocess.run(['sudo', 'systemctl', 'restart', 'NetworkManager'],
                       capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def verify_monitor_mode(interface):
    """Check if interface is in monitor mode."""
    try:
        result = subprocess.run(['iwconfig', interface], capture_output=True,
                                text=True, timeout=5)
        return 'Mode:Monitor' in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def set_channel(interface, channel):
    """Lock interface to a specific WiFi channel."""
    try:
        subprocess.run(['sudo', 'iw', 'dev', interface, 'set', 'channel',
                        str(channel)], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: iwconfig
        try:
            subprocess.run(['sudo', 'iwconfig', interface, 'channel',
                            str(channel)], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
