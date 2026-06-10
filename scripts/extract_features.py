#!/usr/bin/env python3
"""Extract features from pcap files and save as CSV.

Usage:
    python extract_features.py --input data/raw/capture.pcap --output data/processed/features.csv
    python extract_features.py --input-dir data/raw/ --output data/processed/all_features.csv
    python extract_features.py --input data/raw/ --labels data/labels.csv --output data/processed/
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from src.features.feature_extractor import FeatureExtractor


def main():
    parser = argparse.ArgumentParser(
        description='Extract 802.11 MAC features from pcap files')
    parser.add_argument('--input', '-i', help='Single pcap file')
    parser.add_argument('--input-dir', '-d', help='Directory of pcap files')
    parser.add_argument('--output', '-o', required=True,
                        help='Output CSV path (or directory for batch)')
    parser.add_argument('--labels', '-l', help='labels.csv file for supervised data')
    parser.add_argument('--max-frames', type=int, help='Max frames per file')
    parser.add_argument('--window', type=float, default=10.0,
                        help='Window duration for window features (seconds)')
    parser.add_argument('--flow-timeout', type=float, default=5.0,
                        help='Flow timeout (seconds)')
    parser.add_argument('--burst-threshold', type=float, default=1.0,
                        help='Burst IAT threshold (ms)')
    parser.add_argument('--extract-windows', action='store_true',
                        help='Also extract window-level features')
    parser.add_argument('--no-progress', action='store_true',
                        help='Disable progress bars')
    args = parser.parse_args()

    extractor = FeatureExtractor(
        window_duration_sec=args.window,
        flow_timeout_sec=args.flow_timeout,
        burst_iat_threshold_ms=args.burst_threshold,
        show_progress=not args.no_progress,
    )

    if args.input_dir:
        # Batch mode
        label_map = _load_labels(args.labels) if args.labels else None
        df = extractor.extract_from_pcap_batch(
            args.input_dir, label_map, max_frames=args.max_frames)
        if df.empty:
            print("No features extracted. Check pcap files and monitor mode.")
            sys.exit(1)
        df.to_csv(args.output, index=False)
        print(f"[*] Extracted {len(df)} flow records from {args.input_dir} -> {args.output}")
        print(f"    Columns: {list(df.columns)}")

    elif args.input:
        # Single file
        df = extractor.extract_from_pcap(args.input, max_frames=args.max_frames)
        if df.empty:
            print(f"No frames found in {args.input}. Is it a valid 802.11 pcap?")
            sys.exit(1)
        df.to_csv(args.output, index=False)
        print(f"[*] Extracted {len(df)} flow records -> {args.output}")
        print(f"    Features: {extractor.feature_cols}")

        # Optionally extract window features
        if args.extract_windows:
            win_df = extractor.extract_window_features(args.input)
            win_path = args.output.replace('.csv', '_windows.csv')
            win_df.to_csv(win_path, index=False)
            print(f"[*] Window features: {len(win_df)} windows -> {win_path}")

    else:
        print("ERROR: --input or --input-dir required.")
        sys.exit(1)


def _load_labels(labels_path):
    """Parse labels.csv into {session_prefix: device_type} mapping."""
    if not os.path.exists(labels_path):
        print(f"WARNING: labels file not found: {labels_path}")
        return None

    labels_df = pd.read_csv(labels_path)
    label_map = {}
    for _, row in labels_df.iterrows():
        session = row.get('session_id', '')
        device = row.get('device_type', 'unknown')
        if session:
            label_map[session] = device
    return label_map


if __name__ == '__main__':
    main()
