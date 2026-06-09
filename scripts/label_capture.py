#!/usr/bin/env python3
"""Suggest source MACs from a pcap and append a row to data/labels.csv."""

import argparse
import csv
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime


DEVICE_TYPES = [
    'wireless_camera',
    'smartphone',
    'laptop',
    'tablet',
    'iot_sensor',
    'access_point',
    'smart_speaker',
    'unknown',
]


def main():
    parser = argparse.ArgumentParser(
        description='Inspect a pcap, choose a likely device MAC, and update labels.csv')
    parser.add_argument('--pcap', '-p', required=True, help='Input pcap file')
    parser.add_argument('--device', '-d', required=True, choices=DEVICE_TYPES,
                        help='Device type label')
    parser.add_argument('--session-id', '-s',
                        help='Session id. Defaults to pcap basename without extension')
    parser.add_argument('--labels', '-l', default='data/labels.csv',
                        help='labels.csv path')
    parser.add_argument('--notes', '-n', default='', help='Notes for this capture')
    parser.add_argument('--mac', '-m',
                        help='Known target MAC. If omitted, choose from detected candidates')
    parser.add_argument('--top', type=int, default=10,
                        help='Number of candidate MACs to show')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Non-interactive: select the top candidate')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print the row but do not write labels.csv')
    args = parser.parse_args()

    if not os.path.exists(args.pcap):
        print(f"ERROR: pcap not found: {args.pcap}", file=sys.stderr)
        sys.exit(1)

    session_id = args.session_id or os.path.splitext(os.path.basename(args.pcap))[0]
    candidates = get_source_mac_counts(args.pcap)

    selected_mac = args.mac
    if selected_mac is None:
        selected_mac = choose_mac(candidates, args.top, args.yes)
    selected_mac = normalize_mac(selected_mac)

    row = {
        'device_mac': selected_mac,
        'device_type': args.device,
        'session_id': session_id,
        'notes': args.notes,
        'timestamp': datetime.now().isoformat(timespec='seconds'),
    }

    print("\nLabel row:")
    print(','.join(row.values()))

    if args.dry_run:
        print("[*] Dry run: labels.csv not modified.")
        return

    append_label(args.labels, row)
    print(f"[*] Appended label to {args.labels}")


def get_source_mac_counts(pcap_path):
    """Return Counter({source_mac: packet_count}) for data frames in pcap."""
    cmd = [
        'tshark',
        '-r', pcap_path,
        '-Y', 'wlan.fc.type == 2 && wlan.sa',
        '-T', 'fields',
        '-e', 'wlan.sa',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print("ERROR: tshark not found. Install Wireshark/tshark first.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or "ERROR: tshark failed to read pcap", file=sys.stderr)
        sys.exit(exc.returncode)

    counts = Counter()
    for line in result.stdout.splitlines():
        mac = normalize_mac(line.strip())
        if mac:
            counts[mac] += 1
    return counts


def choose_mac(candidates, top_n, assume_yes):
    if not candidates:
        print("ERROR: no data-frame source MACs found in pcap.", file=sys.stderr)
        sys.exit(1)

    ranked = candidates.most_common(top_n)
    print("Candidate source MACs from data frames:")
    for idx, (mac, count) in enumerate(ranked, 1):
        print(f"  {idx:>2}. {mac:<17s} {count:>8d} frames")

    if assume_yes:
        mac = ranked[0][0]
        print(f"[*] Selected top candidate: {mac}")
        return mac

    choice = input("Select MAC by number, or paste MAC address [1]: ").strip()
    if not choice:
        return ranked[0][0]

    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(ranked):
            return ranked[idx - 1][0]
        print(f"ERROR: choice out of range: {choice}", file=sys.stderr)
        sys.exit(1)

    return choice


def append_label(labels_path, row):
    os.makedirs(os.path.dirname(labels_path) or '.', exist_ok=True)
    exists = os.path.exists(labels_path)
    fieldnames = ['device_mac', 'device_type', 'session_id', 'notes', 'timestamp']
    with open(labels_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists or os.path.getsize(labels_path) == 0:
            writer.writeheader()
        writer.writerow(row)


def normalize_mac(value):
    return value.strip().lower()


if __name__ == '__main__':
    main()
