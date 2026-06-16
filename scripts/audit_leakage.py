#!/usr/bin/env python3
"""Audit feature CSVs for obvious leakage and suspicious split behavior."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from src.ml.dataset import Dataset


RISK_COLUMNS = {
    'device_mac': 'device identity',
    'device_oui': 'vendor identity',
    'sa': 'source identity',
    'da': 'destination identity',
    'sa_oui': 'vendor identity',
    'source_file': 'capture/session identity',
    'session_id': 'capture/session identity',
    'window_idx': 'position inside one capture',
    'window_start': 'absolute/relative capture time',
    'time_start': 'absolute/relative capture time',
    'is_known_camera_oui': 'uses known camera vendor list',
    'camera_heuristic_score': 'hand-coded camera score derived before training',
}


def main():
    parser = argparse.ArgumentParser(
        description='Check a feature CSV for leakage-prone columns and split overlap.'
    )
    parser.add_argument('--features', '-f', required=True, help='Feature CSV')
    parser.add_argument('--label-col', default='device_type',
                        help='Label column name')
    parser.add_argument('--test-size', type=float, default=0.3,
                        help='Test set fraction used by train_model.py')
    parser.add_argument('--random-state', type=int, default=42,
                        help='Random seed used by train_model.py')
    parser.add_argument('--positive-label', default='wireless_camera',
                        help='Positive label for binary AUC checks')
    parser.add_argument('--group-col', default=None,
                        help='Optional group column for grouped split audit')
    parser.add_argument('--top', type=int, default=20,
                        help='Number of strongest single-feature AUCs to print')
    args = parser.parse_args()

    df = pd.read_csv(args.features)
    if args.label_col not in df.columns:
        raise SystemExit(f"label column not found: {args.label_col}")

    print(f"[*] Loaded {args.features}")
    print(f"    Rows: {len(df)}, Columns: {len(df.columns)}")
    print("\n[*] Label counts")
    print(df[args.label_col].value_counts(dropna=False).to_string())

    dataset = Dataset(df, label_col=args.label_col)
    dataset.prepare()
    feature_names = dataset.feature_names
    print(f"\n[*] Columns used as model features: {len(feature_names)}")

    risk_in_csv = [c for c in RISK_COLUMNS if c in df.columns]
    risk_in_model = [c for c in risk_in_csv if c in feature_names]
    print("\n[*] Leakage-prone columns present in CSV")
    if risk_in_csv:
        for col in risk_in_csv:
            marker = "USED" if col in feature_names else "not used"
            print(f"    {col:<24s} {marker:<8s} {RISK_COLUMNS[col]}")
    else:
        print("    none")

    if risk_in_model:
        print("\n[!] High-risk columns are currently entering the model:")
        for col in risk_in_model:
            print(f"    {col}: {RISK_COLUMNS[col]}")
    else:
        print("\n[*] No listed identity columns enter the numeric feature matrix.")

    _audit_categorical_identity(df, args.label_col)
    _audit_random_split_overlap(
        df, args.label_col, args.test_size, args.random_state
    )
    if args.group_col:
        _audit_group_split_overlap(
            df, args.label_col, args.group_col, args.test_size, args.random_state
        )
    _audit_single_feature_auc(
        df, feature_names, args.label_col, args.positive_label, args.top
    )


def _audit_categorical_identity(df, label_col):
    print("\n[*] Categorical identity checks")
    checked = False
    for col in ['device_mac', 'device_oui', 'source_file', 'session_id']:
        if col not in df.columns:
            continue
        checked = True
        table = df.groupby(col)[label_col].nunique(dropna=False)
        pure = int((table == 1).sum())
        print(f"    {col:<12s}: {pure}/{len(table)} values map to one label")
        preview = (
            df.groupby([col, label_col]).size()
            .sort_values(ascending=False)
            .head(8)
        )
        print(preview.to_string())
    if not checked:
        print("    no common identity columns found")


def _audit_random_split_overlap(df, label_col, test_size, random_state):
    print("\n[*] Reproduced row-level random split overlap")
    labels = LabelEncoder().fit_transform(df[label_col].values)
    indices = np.arange(len(df))
    train_idx, test_idx = train_test_split(
        indices,
        test_size=test_size,
        random_state=random_state,
        stratify=labels if len(set(labels)) > 1 else None,
    )
    train_df = df.iloc[train_idx]
    test_df = df.iloc[test_idx]
    print(f"    Train rows: {len(train_df)}, Test rows: {len(test_df)}")

    for col in ['source_file', 'session_id', 'device_mac']:
        if col not in df.columns:
            continue
        train_values = set(train_df[col].astype(str))
        test_values = set(test_df[col].astype(str))
        overlap = sorted(train_values & test_values)
        print(f"    {col:<12s}: {len(overlap)} values appear in both train and test")
        if overlap:
            print(f"        examples: {', '.join(overlap[:8])}")


def _audit_group_split_overlap(df, label_col, group_col, test_size, random_state):
    print(f"\n[*] Grouped split overlap by '{group_col}'")
    if group_col not in df.columns:
        print(f"    skipped: group column not found: {group_col}")
        return

    dataset = Dataset(df, label_col=label_col)
    dataset.prepare()
    _, _, _, _, train_idx, test_idx = dataset.split_by_group(
        group_col=group_col,
        test_size=test_size,
        random_state=random_state,
        fit_scaler_on_train=False,
        stratify=True,
    )
    train_df = df.iloc[train_idx]
    test_df = df.iloc[test_idx]

    train_groups = set(train_df[group_col].astype(str))
    test_groups = set(test_df[group_col].astype(str))
    overlap = sorted(train_groups & test_groups)
    print(f"    Train rows: {len(train_df)}, Test rows: {len(test_df)}")
    print(f"    Train groups: {len(train_groups)}, Test groups: {len(test_groups)}")
    print(f"    {group_col:<12s}: {len(overlap)} values appear in both train and test")
    if overlap:
        print(f"        examples: {', '.join(overlap[:8])}")

    print("    Test label counts:")
    print(test_df[label_col].value_counts(dropna=False).to_string())


def _audit_single_feature_auc(df, feature_names, label_col, positive_label, top):
    print(f"\n[*] Single-feature AUC vs '{positive_label}'")
    y = (df[label_col].astype(str).values == positive_label).astype(int)
    if len(set(y)) < 2:
        print("    skipped: positive and negative labels are both required")
        return

    rows = []
    for col in feature_names:
        x = pd.to_numeric(df[col], errors='coerce')
        x = x.replace([np.inf, -np.inf], np.nan)
        x = x.fillna(x.median())
        x = x.fillna(0)
        if x.nunique(dropna=False) <= 1:
            continue
        try:
            auc = roc_auc_score(y, x.values)
        except ValueError:
            continue
        strength = max(auc, 1.0 - auc)
        rows.append((strength, auc, col))

    if not rows:
        print("    no usable numeric features")
        return

    rows.sort(reverse=True)
    print("    Features near 1.0 or 0.0 can separate labels by themselves.")
    for strength, auc, col in rows[:top]:
        flag = "  <-- suspicious" if strength >= 0.98 else ""
        print(f"    {col:<32s} AUC={auc:.4f} strength={strength:.4f}{flag}")


if __name__ == '__main__':
    main()
