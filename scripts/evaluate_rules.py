#!/usr/bin/env python3
"""Evaluate a rule-based camera detector on extracted device-window features."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from src.ml.rule_baseline import (
    DEFAULT_RULE_THRESHOLD,
    describe_rules,
    predict_dataframe,
)
from src.visualization.result_plots import plot_confusion_matrix


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate rule-based camera detection baseline')
    parser.add_argument('--features', '-f', required=True,
                        help='Device-window feature CSV')
    parser.add_argument('--output', '-o', default='report/rule_baseline',
                        help='Output report directory')
    parser.add_argument('--label-col', default='device_type',
                        help='Ground-truth label column')
    parser.add_argument('--positive-label', default='wireless_camera',
                        help='Label treated as camera/positive class')
    parser.add_argument('--threshold', type=float,
                        default=DEFAULT_RULE_THRESHOLD,
                        help='Rule score threshold for camera prediction')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    df = pd.read_csv(args.features)
    if args.label_col not in df.columns:
        print(f"ERROR: label column not found: {args.label_col}")
        sys.exit(1)

    y_true = (df[args.label_col].astype(str) == args.positive_label).astype(int)
    if y_true.nunique() < 2:
        print("ERROR: rule evaluation requires both positive and negative samples.")
        sys.exit(1)

    y_pred, scored = predict_dataframe(df, threshold=args.threshold)
    results = evaluate_binary(y_true, y_pred)

    print(f"[*] Rule baseline on {args.features}")
    print(f"    Samples: {len(df)}")
    print(f"    Positive label: {args.positive_label}")
    print(f"    Rule threshold: {args.threshold}")
    print("\nRules:")
    rule_table = describe_rules()
    print(rule_table[['name', 'feature', 'op', 'threshold', 'weight']].to_string(index=False))

    print("\n" + "=" * 60)
    print("RULE-BASED CAMERA DETECTION RESULTS")
    print("=" * 60)
    print(f"Accuracy:          {results['accuracy']:.4f}")
    print(f"Precision:         {results['precision']:.4f}")
    print(f"Recall:            {results['recall']:.4f}")
    print(f"F1 Score:          {results['f1']:.4f}")
    print(f"Detection Rate:    {results['detection_rate']:.4f}")
    print(f"False Alarm Rate:  {results['false_alarm_rate']:.4f}")
    print(f"Miss Rate:         {results['miss_rate']:.4f}")
    print(f"TP={results['true_positive']}, FP={results['false_positive']}, "
          f"TN={results['true_negative']}, FN={results['false_negative']}")

    print("\nClassification Report:")
    print(classification_report(
        y_true, y_pred,
        target_names=['non_wireless_camera', args.positive_label],
        zero_division=0,
    ))

    print("Confusion Matrix:")
    print(results['confusion_matrix'])

    output_df = build_prediction_output(df, scored, y_true, y_pred, args)
    prediction_path = os.path.join(args.output, 'rule_predictions.csv')
    output_df.to_csv(prediction_path, index=False)

    rule_path = os.path.join(args.output, 'rules.csv')
    rule_table.to_csv(rule_path, index=False)

    metrics_path = os.path.join(args.output, 'rule_metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(_jsonable(results), f, indent=2)

    class_names = ['non_wireless_camera', args.positive_label]
    fig = plot_confusion_matrix(
        results['confusion_matrix'],
        class_names,
        save_path=os.path.join(args.output, 'rule_confusion_matrix.png'),
    )
    plt.close(fig)

    fig = plot_confusion_matrix(
        results['confusion_matrix'],
        class_names,
        normalize=True,
        save_path=os.path.join(args.output, 'rule_confusion_matrix_norm.png'),
    )
    plt.close(fig)

    print(f"\n[*] Report generated in {args.output}")
    print("    rule_predictions.csv")
    print("    rules.csv")
    print("    rule_metrics.json")
    print("    rule_confusion_matrix.png")
    print("    rule_confusion_matrix_norm.png")


def evaluate_binary(y_true, y_pred):
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    return {
        'accuracy': accuracy_score(y_true, y_pred),
        'precision': precision_score(y_true, y_pred, zero_division=0),
        'recall': recall_score(y_true, y_pred, zero_division=0),
        'f1': f1_score(y_true, y_pred, zero_division=0),
        'true_positive': int(tp),
        'false_positive': int(fp),
        'true_negative': int(tn),
        'false_negative': int(fn),
        'detection_rate': tp / max(tp + fn, 1),
        'false_alarm_rate': fp / max(fp + tn, 1),
        'miss_rate': fn / max(tp + fn, 1),
        'confusion_matrix': cm,
    }


def build_prediction_output(df, scored, y_true, y_pred, args):
    id_cols = [
        'source_file',
        'device_mac',
        'device_type',
        'window_idx',
        'packet_count',
        'total_bytes',
        'throughput_bps',
        'mean_frame_size',
        'large_frame_ratio',
        'uplink_packet_ratio',
        'qos_data_ratio',
    ]
    cols = [col for col in id_cols if col in df.columns]
    out = df[cols].copy()
    out['true_binary'] = y_true.values
    out['pred_binary'] = y_pred.values
    out['true_label'] = [
        args.positive_label if value == 1 else f'non_{args.positive_label}'
        for value in y_true.values
    ]
    out['pred_label'] = [
        args.positive_label if value == 1 else f'non_{args.positive_label}'
        for value in y_pred.values
    ]
    out['rule_score'] = scored['rule_score'].values
    out['triggered_rules'] = scored['triggered_rules'].values
    out['correct'] = out['true_binary'] == out['pred_binary']
    return out


def _jsonable(results):
    output = {}
    for key, value in results.items():
        if hasattr(value, 'tolist'):
            output[key] = value.tolist()
        else:
            output[key] = value
    return output


if __name__ == '__main__':
    main()
