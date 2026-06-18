#!/usr/bin/env python3
"""Detect suspicious camera MACs from an unlabeled pcap.

This is an inference/demo entry point. It does not require labels.csv.
It ranks MAC addresses observed in one pcap, extracts MAC-level window
features for each candidate, and aggregates rule and/or model predictions
per MAC.
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from src.features.feature_extractor import FeatureExtractor
from src.ml.model_persistence import load_model, export_predictions_csv
from src.ml.rule_baseline import DEFAULT_RULE_THRESHOLD, predict_dataframe

MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
HIGH_RISK_MODEL_FEATURES = {
    "device_mac",
    "device_oui",
    "source_file",
    "session_id",
    "window_idx",
    "window_start",
    "time_start",
    "is_known_camera_oui",
    "camera_heuristic_score",
}


def main():
    parser = argparse.ArgumentParser(
        description="Detect suspicious camera MACs from an unlabeled pcap"
    )
    parser.add_argument("--pcap", "-p", required=True, help="Input pcap file")
    parser.add_argument(
        "--method",
        choices=["ml", "rule", "both"],
        default="ml",
        help="Detection method: trained ML model, rule baseline, or both",
    )
    parser.add_argument("--model", "-m", default="data/models/", help="Model directory")
    parser.add_argument(
        "--model-name",
        default="camera_detector",
        help="Model name prefix in model directory",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data/processed/unknown_detection_results.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--window", type=float, default=10.0, help="Device-window duration in seconds"
    )
    parser.add_argument(
        "--top-macs",
        type=int,
        default=20,
        help="Number of top MACs to inspect; use 0 for all",
    )
    parser.add_argument(
        "--min-frames",
        type=int,
        default=100,
        help="Minimum total observed frames for a candidate MAC",
    )
    parser.add_argument(
        "--min-source-frames",
        type=int,
        default=10,
        help="Minimum source frames for a candidate MAC",
    )
    parser.add_argument(
        "--camera-threshold",
        type=float,
        default=0.6,
        help="ML mode: mean camera probability threshold",
    )
    parser.add_argument(
        "--window-ratio-threshold",
        type=float,
        default=0.5,
        help="ML mode: camera-window ratio threshold",
    )
    parser.add_argument(
        "--rule-threshold",
        type=float,
        default=DEFAULT_RULE_THRESHOLD,
        help="Rule mode: minimum rule score for camera prediction",
    )
    parser.add_argument(
        "--rule-window-ratio-threshold",
        type=float,
        default=0.5,
        help="Rule mode: suspicious if this fraction of windows pass rules",
    )
    parser.add_argument(
        "--max-frames", type=int, help="Max frames per MAC during feature extraction"
    )
    parser.add_argument(
        "--no-progress", action="store_true", help="Disable progress bars"
    )
    args = parser.parse_args()

    if not os.path.exists(args.pcap):
        print(f"ERROR: pcap not found: {args.pcap}")
        sys.exit(1)

    use_ml = args.method in ("ml", "both")
    use_rule = args.method in ("rule", "both")
    model = scaler = metadata = None
    feature_names = label_names = None
    camera_label_idx = camera_prob_col = None

    print(f"[*] Detection method: {args.method}")
    if use_ml:
        model, scaler, metadata = load_model(args.model, args.model_name)
        feature_names = metadata["feature_names"]
        label_names = metadata["label_names"]

        print(f"[*] Loaded model: {metadata.get('model_type', 'unknown')}")
        print(f"    Model name: {args.model_name}")
        print(f"    Classes: {label_names}")
        print(f"    Features: {len(feature_names)}")
        _warn_if_risky_features(feature_names)

        camera_label_idx = find_camera_label_index(label_names)
        camera_prob_col = find_probability_column(model, camera_label_idx)
    else:
        print("[*] Rule-only mode: model loading skipped")

    print(f"\n[*] Enumerating MACs in {args.pcap}")
    candidates = enumerate_macs(args.pcap)
    if not candidates:
        print("ERROR: no 802.11 MAC addresses found in pcap.")
        sys.exit(1)

    candidates = [
        row
        for row in candidates
        if row["total_frames"] >= args.min_frames
        and row["source_frames"] >= args.min_source_frames
    ]
    if args.top_macs > 0:
        candidates = candidates[: args.top_macs]

    if not candidates:
        print("No candidates passed the frame thresholds.")
        print("Try lowering --min-frames or --min-source-frames.")
        sys.exit(1)

    print(f"    Candidates selected: {len(candidates)}")
    for i, row in enumerate(candidates[:10], start=1):
        print(
            f"    {i:2d}. {row['mac']}  total={row['total_frames']}  "
            f"source={row['source_frames']}  data_source={row['data_source_frames']}"
        )

    extractor = FeatureExtractor(
        window_duration_sec=args.window,
        show_progress=not args.no_progress,
    )

    results = []
    for i, candidate in enumerate(candidates, start=1):
        mac = candidate["mac"]
        print(f"\n[*] [{i}/{len(candidates)}] Extracting device windows for {mac}")
        df = extractor.extract_device_windows_from_pcap(
            args.pcap,
            target_mac=mac,
            window_sec=args.window,
            max_frames=args.max_frames,
            show_progress=not args.no_progress,
        )
        summary = dict(candidate)
        if df.empty:
            summary.update(
                {
                    "status": "no_features",
                    "window_count": 0,
                    "ml_predicted_type": "unknown",
                    "ml_camera_prob_mean": 0.0,
                    "ml_camera_prob_max": 0.0,
                    "ml_camera_window_ratio": 0.0,
                    "ml_suspicious_camera": False,
                    "rule_score_mean": 0.0,
                    "rule_score_max": 0.0,
                    "rule_camera_window_ratio": 0.0,
                    "rule_camera_pred_windows": 0,
                    "rule_suspicious_camera": False,
                    "suspicious_camera": False,
                }
            )
            results.append(summary)
            print("    no device-window features")
            continue

        mac_summary = {"status": "ok", "window_count": len(df)}
        if use_ml:
            mac_summary.update(
                predict_ml_and_aggregate(
                    df=df,
                    model=model,
                    scaler=scaler,
                    feature_names=feature_names,
                    label_names=label_names,
                    camera_label_idx=camera_label_idx,
                    camera_prob_col=camera_prob_col,
                    camera_threshold=args.camera_threshold,
                    window_ratio_threshold=args.window_ratio_threshold,
                )
            )
        if use_rule:
            mac_summary.update(
                predict_rule_and_aggregate(
                    df=df,
                    rule_threshold=args.rule_threshold,
                    rule_window_ratio_threshold=args.rule_window_ratio_threshold,
                )
            )
        mac_summary["suspicious_camera"] = _combined_suspicious(
            mac_summary, use_ml=use_ml, use_rule=use_rule
        )
        mac_summary.update(key_feature_means(df))
        summary.update(mac_summary)
        results.append(summary)

        flag = "YES" if summary["suspicious_camera"] else "no"
        print_candidate_result(summary, use_ml=use_ml, use_rule=use_rule, flag=flag)

    result_df = pd.DataFrame(results)
    result_df = sort_results(result_df, method=args.method)

    print_summary(result_df, method=args.method)
    export_predictions_csv(result_df, args.output)
    print(f"\n[*] Results saved to {args.output}")


def enumerate_macs(pcap_path):
    """Return MAC candidates ranked by data-source and total frame counts."""
    fields = [
        "wlan.sa",
        "wlan.da",
        "wlan.ta",
        "wlan.ra",
        "wlan.bssid",
        "wlan.fc.type",
    ]
    cmd = [
        "tshark",
        "-r",
        pcap_path,
        "-T",
        "fields",
        "-E",
        "separator=/t",
        "-E",
        "occurrence=f",
    ]
    for field in fields:
        cmd.extend(["-e", field])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print("ERROR: tshark not found. Install tshark or run inside the Ubuntu VM.")
        sys.exit(1)

    if proc.returncode != 0:
        print(f"ERROR: tshark failed while enumerating MACs:\n{proc.stderr}")
        sys.exit(1)

    stats = defaultdict(
        lambda: {
            "mac": "",
            "total_frames": 0,
            "source_frames": 0,
            "dest_frames": 0,
            "transmitter_frames": 0,
            "receiver_frames": 0,
            "bssid_frames": 0,
            "data_frames": 0,
            "data_source_frames": 0,
        }
    )

    for line in proc.stdout.splitlines():
        parts = line.rstrip("\n").split("\t")
        if len(parts) < len(fields):
            parts.extend([""] * (len(fields) - len(parts)))
        sa, da, ta, ra, bssid, frame_type = parts[: len(fields)]
        frame_type_i = parse_int(frame_type, default=-1)
        is_data = frame_type_i == 2

        addresses = [
            ("source_frames", sa),
            ("dest_frames", da),
            ("transmitter_frames", ta),
            ("receiver_frames", ra),
            ("bssid_frames", bssid),
        ]
        seen_in_frame = set()
        for key, raw_mac in addresses:
            mac = normalize_mac(raw_mac)
            if not is_candidate_mac(mac):
                continue
            stats[mac]["mac"] = mac
            stats[mac][key] += 1
            seen_in_frame.add(mac)
            if is_data and key == "source_frames":
                stats[mac]["data_source_frames"] += 1

        for mac in seen_in_frame:
            stats[mac]["total_frames"] += 1
            if is_data:
                stats[mac]["data_frames"] += 1

    rows = list(stats.values())
    rows.sort(
        key=lambda row: (
            row["data_source_frames"],
            row["source_frames"],
            row["total_frames"],
        ),
        reverse=True,
    )
    return rows


def predict_ml_and_aggregate(
    df,
    model,
    scaler,
    feature_names,
    label_names,
    camera_label_idx,
    camera_prob_col,
    camera_threshold,
    window_ratio_threshold,
):
    X_df = df[[c for c in feature_names if c in df.columns]].copy()
    missing = set(feature_names) - set(X_df.columns)
    for col in missing:
        X_df[col] = 0
    X_df = X_df[feature_names]
    X_df = X_df.fillna(X_df.median(numeric_only=True))
    X_df = X_df.fillna(0)
    X_df = X_df.replace([np.inf, -np.inf], 0)

    X_scaled = scaler.transform(X_df.values)
    predictions = model.predict(X_scaled)
    pred_labels = [label_for_prediction(p, label_names) for p in predictions]

    camera_window_mask = np.array(
        [
            label_index_for_prediction(p, label_names) == camera_label_idx
            for p in predictions
        ]
    )
    camera_probs = None
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X_scaled)
        if probs.ndim == 2 and probs.shape[1] > camera_prob_col:
            camera_probs = probs[:, camera_prob_col]

    if camera_probs is None:
        camera_probs = camera_window_mask.astype(float)

    camera_window_ratio = float(camera_window_mask.mean())
    camera_prob_mean = float(np.mean(camera_probs))
    camera_prob_max = float(np.max(camera_probs))
    suspicious = (
        camera_prob_mean >= camera_threshold
        or camera_window_ratio >= window_ratio_threshold
    )

    summary = {
        "ml_predicted_type": most_common(pred_labels),
        "ml_camera_prob_mean": camera_prob_mean,
        "ml_camera_prob_max": camera_prob_max,
        "ml_camera_window_ratio": camera_window_ratio,
        "ml_camera_pred_windows": int(camera_window_mask.sum()),
        "ml_suspicious_camera": suspicious,
    }
    return summary


def predict_rule_and_aggregate(df, rule_threshold, rule_window_ratio_threshold):
    predictions, scored = predict_dataframe(df, threshold=rule_threshold)
    rule_window_ratio = float(predictions.mean()) if len(predictions) else 0.0
    rule_score_mean = float(scored["rule_score"].mean()) if not scored.empty else 0.0
    rule_score_max = float(scored["rule_score"].max()) if not scored.empty else 0.0

    triggered = []
    for item in scored.get("triggered_rules", []):
        if not item:
            continue
        triggered.extend(str(item).split(";"))
    common_rules = most_common_list(triggered, top_n=5)
    suspicious = rule_window_ratio >= rule_window_ratio_threshold

    return {
        "rule_score_mean": rule_score_mean,
        "rule_score_max": rule_score_max,
        "rule_camera_window_ratio": rule_window_ratio,
        "rule_camera_pred_windows": int(predictions.sum()),
        "rule_suspicious_camera": suspicious,
        "rule_common_triggers": ";".join(common_rules),
    }


def _combined_suspicious(summary, use_ml, use_rule):
    flags = []
    if use_ml:
        flags.append(bool(summary.get("ml_suspicious_camera", False)))
    if use_rule:
        flags.append(bool(summary.get("rule_suspicious_camera", False)))
    return any(flags)


def print_candidate_result(summary, use_ml, use_rule, flag):
    parts = [f"windows={summary['window_count']}"]
    if use_ml:
        parts.extend([
            f"ml_prob_mean={summary['ml_camera_prob_mean']:.3f}",
            f"ml_window_ratio={summary['ml_camera_window_ratio']:.3f}",
        ])
    if use_rule:
        parts.extend([
            f"rule_score_mean={summary['rule_score_mean']:.2f}",
            f"rule_window_ratio={summary['rule_camera_window_ratio']:.3f}",
        ])
    parts.append(f"suspicious={flag}")
    print("    " + "  ".join(parts))


def sort_results(result_df, method):
    columns = ["suspicious_camera"]
    if method in ("ml", "both"):
        columns.extend(["ml_camera_prob_mean", "ml_camera_window_ratio"])
    if method in ("rule", "both"):
        columns.extend(["rule_camera_window_ratio", "rule_score_mean"])
    columns.extend(["data_source_frames", "total_frames"])
    columns = [col for col in columns if col in result_df.columns]
    return result_df.sort_values(columns, ascending=[False] * len(columns))


def key_feature_means(df):
    selected = [
        "packet_count",
        "total_bytes",
        "throughput_bps",
        "mean_frame_size",
        "large_frame_ratio",
        "uplink_packet_ratio",
        "uplink_bytes_ratio",
        "downlink_packet_ratio",
        "qos_data_ratio",
        "mean_data_rate",
        "mean_rssi",
        "burst_count",
        "burst_density",
    ]
    output = {}
    for col in selected:
        if col in df.columns:
            output[f"mean_{col}"] = float(
                pd.to_numeric(df[col], errors="coerce").fillna(0).mean()
            )
    return output


def print_summary(result_df, method):
    print("\n" + "=" * 72)
    print("UNKNOWN PCAP DETECTION SUMMARY")
    print("=" * 72)

    cols = [
        "mac",
        "total_frames",
        "source_frames",
        "data_source_frames",
        "window_count",
    ]
    if method in ("ml", "both"):
        cols.extend([
            "ml_camera_prob_mean",
            "ml_camera_prob_max",
            "ml_camera_window_ratio",
            "ml_suspicious_camera",
        ])
    if method in ("rule", "both"):
        cols.extend([
            "rule_score_mean",
            "rule_score_max",
            "rule_camera_window_ratio",
            "rule_suspicious_camera",
            "rule_common_triggers",
        ])
    cols.append("suspicious_camera")
    cols = [col for col in cols if col in result_df.columns]
    print(result_df[cols].to_string(index=False))

    suspicious = result_df[result_df["suspicious_camera"] == True]
    if suspicious.empty:
        print("\n[ ] No suspicious camera MACs above threshold.")
        return

    print("\n[!] Suspicious camera MACs:")
    for _, row in suspicious.iterrows():
        parts = [f"    {row['mac']}"]
        if method in ("ml", "both") and "ml_camera_prob_mean" in row:
            parts.append(f"ml_prob_mean={row['ml_camera_prob_mean']:.3f}")
        if method in ("rule", "both") and "rule_score_mean" in row:
            parts.append(f"rule_score_mean={row['rule_score_mean']:.2f}")
        parts.append(f"windows={int(row['window_count'])}")
        print("  ".join(parts))


def find_camera_label_index(label_names):
    for i, name in enumerate(label_names):
        lower = str(name).lower()
        if "camera" in lower and not lower.startswith("non_"):
            return i
    for i, name in enumerate(label_names):
        if "camera" in str(name).lower():
            return i
    return 0


def find_probability_column(model, label_idx):
    classes = getattr(model, "classes_", None)
    if classes is None and hasattr(model, "named_steps"):
        final_step = list(model.named_steps.values())[-1]
        classes = getattr(final_step, "classes_", None)
    if classes is None:
        return label_idx
    for i, cls in enumerate(classes):
        try:
            if int(cls) == label_idx:
                return i
        except (TypeError, ValueError):
            if str(cls) == str(label_idx):
                return i
    return min(label_idx, len(classes) - 1)


def label_index_for_prediction(prediction, label_names):
    try:
        idx = int(prediction)
    except (TypeError, ValueError):
        return -1
    if 0 <= idx < len(label_names):
        return idx
    return -1


def label_for_prediction(prediction, label_names):
    idx = label_index_for_prediction(prediction, label_names)
    if idx >= 0:
        return label_names[idx]
    return str(prediction)


def most_common(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return "unknown"
    return max(counts.items(), key=lambda item: item[1])[0]


def most_common_list(values, top_n=5):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [
        value for value, _ in sorted(
            counts.items(), key=lambda item: item[1], reverse=True
        )[:top_n]
    ]


def _warn_if_risky_features(feature_names):
    risky = [name for name in feature_names if name in HIGH_RISK_MODEL_FEATURES]
    if not risky:
        return
    print("\nWARNING: model metadata contains high-risk features:")
    for name in risky:
        print(f"    {name}")
    print("Use a model retrained after excluding identity/time/heuristic features.")


def normalize_mac(value):
    return str(value or "").strip().lower().replace("-", ":")


def is_candidate_mac(mac):
    if not MAC_RE.match(mac):
        return False
    if mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
        return False
    first_octet = int(mac.split(":")[0], 16)
    return (first_octet & 1) == 0


def parse_int(value, default=0):
    value = str(value).strip()
    if not value:
        return default
    try:
        return int(value, 0)
    except ValueError:
        try:
            return int(float(value))
        except ValueError:
            return default


if __name__ == "__main__":
    main()
