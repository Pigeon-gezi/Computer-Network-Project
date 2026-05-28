#!/usr/bin/env python3
"""Guided data collection: capture labeled training data for each device type.

Usage:
    python collect_training_data.py --interface wlan0mon --device camera --duration 300
    python collect_training_data.py --interface wlan0mon --device smartphone --duration 300
    python collect_training_data.py --interface wlan0mon --list       # show collected
"""

import argparse
import os
import sys
import json
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.capture.monitor_setup import detect_wireless_interfaces, verify_monitor_mode
from src.capture.capture_session import CaptureSession


LABELS_FILE = 'data/labels.csv'
DEVICE_TYPES = ['wireless_camera', 'smartphone', 'laptop', 'iot_sensor',
                'access_point', 'smart_speaker', 'unknown']


def main():
    parser = argparse.ArgumentParser(description='Collect labeled 802.11 training data')
    parser.add_argument('--interface', '-i', help='Monitor mode interface')
    parser.add_argument('--device', '-d', choices=DEVICE_TYPES,
                        help='Device type label for this capture')
    parser.add_argument('--duration', '-t', type=int, default=300,
                        help='Capture duration in seconds (default: 300)')
    parser.add_argument('--channel', '-c', type=int, help='WiFi channel to lock')
    parser.add_argument('--mac', '-m', help='Target device MAC address (filter)')
    parser.add_argument('--notes', '-n', help='Session notes')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List collected sessions')
    parser.add_argument('--detect', action='store_true',
                        help='Detect wireless interfaces and exit')
    args = parser.parse_args()

    if args.detect:
        ifaces = detect_wireless_interfaces()
        print("Detected wireless interfaces:")
        for iface in ifaces:
            print(f"  {iface}")
        return

    if args.list:
        list_sessions()
        return

    # Validate
    if not args.interface:
        print("ERROR: --interface required. Use --detect to find interfaces.")
        sys.exit(1)
    if not args.device:
        print("ERROR: --device required. Choose from:", ", ".join(DEVICE_TYPES))
        sys.exit(1)

    if not verify_monitor_mode(args.interface):
        print(f"WARNING: {args.interface} does not appear to be in monitor mode.")
        print("Run capture_setup.sh first or use --detect to check interfaces.")
        resp = input("Continue anyway? [y/N] ")
        if resp.lower() != 'y':
            sys.exit(1)

    # Build filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    session_name = f"{args.device}_{timestamp}"
    output_name = f"{session_name}"

    # Create capture session
    cap = CaptureSession(args.interface)

    display_filter = None
    if args.mac:
        display_filter = f'wlan.addr == {args.mac}'
        print(f"Filtering for MAC: {args.mac}")

    print(f"[*] Capturing '{args.device}' traffic for {args.duration}s...")
    print(f"    Output: data/raw/{output_name}.pcap")

    path = cap.capture_duration(args.duration, output_name,
                                 channel=args.channel,
                                 display_filter=display_filter)

    # Record session in labels.csv
    record_session(args.device, args.mac or 'unknown', session_name, args.notes)
    print(f"[*] Done. Session recorded.")


def record_session(device_type, mac, session_name, notes=''):
    """Append session record to data/labels.csv."""
    os.makedirs('data', exist_ok=True)

    # Create header if file doesn't exist
    if not os.path.exists(LABELS_FILE):
        with open(LABELS_FILE, 'w') as f:
            f.write('device_mac,device_type,session_id,notes,timestamp\n')

    with open(LABELS_FILE, 'a') as f:
        f.write(f'{mac},{device_type},{session_name},{notes or ""},{datetime.now().isoformat()}\n')


def list_sessions():
    """List all collected sessions from labels.csv."""
    if not os.path.exists(LABELS_FILE):
        print("No sessions recorded yet.")
        return

    print(f"{'Session':<40s} {'Device':<18s} {'MAC':<20s} {'Notes'}")
    print("-" * 100)
    with open(LABELS_FILE) as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 5:
                session, device, mac, notes = parts[2], parts[1], parts[0], parts[3]
                print(f"{session:<40s} {device:<18s} {mac:<20s} {notes}")


if __name__ == '__main__':
    main()
