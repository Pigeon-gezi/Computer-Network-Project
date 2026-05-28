#!/usr/bin/env python3
"""Run device detection on pcap files or live capture.

Usage:
    python run_detector.py --pcap data/raw/test.pcap --model data/models/
    python run_detector.py --pcap data/raw/test.pcap --binary-detection
    python run_detector.py --features data/processed/features.csv --model data/models/
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd

from src.features.feature_extractor import FeatureExtractor
from src.ml.model_persistence import load_model, export_predictions_csv


def main():
    parser = argparse.ArgumentParser(description='Run device type detection')
    parser.add_argument('--pcap', '-p', help='Input pcap file')
    parser.add_argument('--features', '-f', help='Pre-extracted features CSV')
    parser.add_argument('--model', '-m', default='data/models/',
                        help='Model directory or path')
    parser.add_argument('--output', '-o', default='data/processed/detection_results.csv',
                        help='Output CSV path for results')
    parser.add_argument('--binary-detection', action='store_true',
                        help='Use camera detector (binary) model')
    parser.add_argument('--min-confidence', type=float, default=0.5,
                        help='Minimum confidence threshold')
    parser.add_argument('--max-frames', type=int, help='Max frames to process')
    args = parser.parse_args()

    # Load model
    model_name = 'camera_detector' if args.binary_detection else 'device_classifier'
    model_path = args.model
    if os.path.isdir(model_path):
        model, scaler, metadata = load_model(model_path, model_name)
    else:
        model, scaler, metadata = load_model(
            os.path.dirname(model_path),
            os.path.splitext(os.path.basename(model_path))[0])

    feature_names = metadata['feature_names']
    label_names = metadata['label_names']
    print(f"[*] Loaded model: {metadata.get('model_type', 'unknown')}")
    print(f"    Classes: {label_names}")
    print(f"    Features: {len(feature_names)}")

    # Get features
    if args.features:
        print(f"[*] Loading pre-extracted features from {args.features}")
        df = pd.read_csv(args.features)
    elif args.pcap:
        print(f"[*] Extracting features from {args.pcap}")
        extractor = FeatureExtractor()
        df = extractor.extract_from_pcap(args.pcap, max_frames=args.max_frames)
        if df.empty:
            print("ERROR: No features extracted. Check pcap content.")
            sys.exit(1)
    else:
        print("ERROR: --pcap or --features required.")
        sys.exit(1)

    if df.empty:
        print("No data to classify.")
        return

    # Prepare feature matrix
    X_df = df[[c for c in feature_names if c in df.columns]]
    missing = set(feature_names) - set(X_df.columns)
    for col in missing:
        X_df[col] = 0
    X_df = X_df[feature_names]  # Reorder to match model
    X_df = X_df.fillna(0).replace([np.inf, -np.inf], 0)

    X = X_df.values
    X_scaled = scaler.transform(X)

    # Predict
    predictions = model.predict(X_scaled)
    try:
        probabilities = model.predict_proba(X_scaled)
        confidence = probabilities.max(axis=1)
        pred_labels = [label_names[p] for p in predictions]

        # Add results
        result_cols = ['sa', 'da']
        result_cols = [c for c in result_cols if c in df.columns]

        results = df[result_cols].copy() if result_cols else pd.DataFrame(index=df.index)
        results['predicted_type'] = pred_labels
        results['confidence'] = confidence

        # Add per-class probabilities
        for i, name in enumerate(label_names):
            results[f'prob_{name}'] = probabilities[:, i]

        # Filter low confidence
        confident = results[results['confidence'] >= args.min_confidence]

    except (AttributeError, Exception):
        pred_labels = [label_names[p] for p in predictions]
        results = df[['sa', 'da']].copy() if 'sa' in df.columns else pd.DataFrame()
        results['predicted_type'] = pred_labels
        confident = results

    # Summary
    print(f"\n[*] Detection Results ({len(results)} devices/flows):")
    print(f"    High confidence (>{args.min_confidence}): {len(confident)}")

    if not results.empty:
        counts = results['predicted_type'].value_counts()
        for label, count in counts.items():
            print(f"    {label:<20s}: {count}")

    # Camera alerts
    camera_labels = [l for l in label_names if 'camera' in l.lower()]
    for cam_label in camera_labels:
        cameras = results[results['predicted_type'] == cam_label]
        if len(cameras) > 0:
            print(f"\n[!] POTENTIAL CAMERAS DETECTED ({cam_label}): {len(cameras)}")
            for _, row in cameras.iterrows():
                sa = row.get('sa', 'unknown')
                conf = row.get('confidence', 0)
                print(f"    MAC={sa}, confidence={conf:.3f}")

    # Export
    export_predictions_csv(results, args.output)
    print(f"\n[*] Results saved to {args.output}")


if __name__ == '__main__':
    main()
