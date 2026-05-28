#!/usr/bin/env python3
"""Train SVM + Random Forest device classifier from extracted features.

Usage:
    python train_model.py --features data/processed/features.csv --output data/models/
    python train_model.py --features data/processed/features.csv --binary-camera
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd

from src.ml.dataset import Dataset
from src.ml.svm_classifier import train_svm, train_svm_binary
from src.ml.rf_classifier import train_random_forest, train_rf_binary
from src.ml.model_evaluator import evaluate_model, evaluate_binary_detection, print_evaluation
from src.ml.model_persistence import save_model
from src.ml.ensemble import build_ensemble, compare_models


def main():
    parser = argparse.ArgumentParser(description='Train device classifier')
    parser.add_argument('--features', '-f', required=True,
                        help='Feature CSV from extract_features.py')
    parser.add_argument('--output', '-o', default='data/models/',
                        help='Output directory for trained models')
    parser.add_argument('--label-col', default='device_type',
                        help='Column name for device labels')
    parser.add_argument('--binary-camera', action='store_true',
                        help='Train binary camera-vs-all classifier')
    parser.add_argument('--test-size', type=float, default=0.3,
                        help='Test set fraction')
    parser.add_argument('--cv', type=int, default=5,
                        help='Cross-validation folds')
    args = parser.parse_args()

    # Load data
    print(f"[*] Loading features from {args.features}")
    df = pd.read_csv(args.features)
    print(f"    {len(df)} samples, {len(df.columns)} columns")

    if args.label_col not in df.columns:
        print(f"ERROR: label column '{args.label_col}' not found.")
        print(f"Available columns: {list(df.columns)}")
        sys.exit(1)

    # Prepare dataset
    dataset = Dataset(df, label_col=args.label_col)
    X, y = dataset.prepare()
    X_train, X_test, y_train, y_test = dataset.split(
        test_size=args.test_size, stratify=(len(set(y)) > 1))

    class_names = dataset.get_class_names()
    print(f"\nClasses: {class_names}")
    print(f"Train: {X_train.shape[0]} samples, Test: {X_test.shape[0]} samples")
    print(f"Features: {X_train.shape[1]}")

    # Train models
    os.makedirs(args.output, exist_ok=True)

    if args.binary_camera:
        _train_binary_mode(X_train, y_train, X_test, y_test,
                           dataset, class_names, args)
    else:
        _train_multiclass_mode(X_train, y_train, X_test, y_test,
                               dataset, class_names, args)


def _train_multiclass_mode(X_train, y_train, X_test, y_test,
                           dataset, class_names, args):
    """Train multiclass SVM + RF + Ensemble."""
    print("\n" + "=" * 60)
    print("Training SVM...")
    svm_model, svm_grid, svm_params = train_svm(
        X_train, y_train, cv=args.cv)
    print(f"Best SVM params: {svm_params}")

    print("\nTraining Random Forest...")
    rf_model, rf_grid, rf_params, rf_importances = train_random_forest(
        X_train, y_train, cv=args.cv)
    print(f"Best RF params: {rf_params}")

    print("\nBuilding Ensemble...")
    ensemble, components = build_ensemble(
        svm_model=svm_model, rf_model=rf_model,
        X_train=X_train, y_train=y_train)

    # Evaluate
    print("\n" + "=" * 60)
    print("EVALUATION")
    print("=" * 60)

    svm_results = evaluate_model(svm_model, X_test, y_test, class_names)
    rf_results = evaluate_model(rf_model, X_test, y_test, class_names)
    ens_results = evaluate_model(ensemble, X_test, y_test, class_names)

    print("\n--- SVM ---")
    print_evaluation(svm_results, class_names)
    print("\n--- Random Forest ---")
    print_evaluation(rf_results, class_names)
    print("\n--- Ensemble ---")
    print_evaluation(ens_results, class_names)

    # Save best model
    best_model = ensemble
    best_name = 'ensemble'
    if ens_results['f1_weighted'] < svm_results['f1_weighted']:
        best_model = svm_model
        best_name = 'svm'
    if svm_results['f1_weighted'] < rf_results['f1_weighted']:
        if rf_results['f1_weighted'] > ens_results.get('f1_weighted', 0):
            best_model = rf_model
            best_name = 'rf'

    print(f"\n[*] Best model: {best_name}")

    save_model(best_model, dataset.scaler,
               feature_names=dataset.feature_names,
               label_names=class_names,
               output_dir=args.output,
               model_name='device_classifier')

    # Also save all component models
    save_model(svm_model, dataset.scaler, dataset.feature_names, class_names,
               args.output, 'svm_model')
    save_model(rf_model, dataset.scaler, dataset.feature_names, class_names,
               args.output, 'rf_model')

    print(f"[*] Models saved to {args.output}")

    # Feature importance
    print("\n[*] Top 10 RF Feature Importances:")
    imp_df = pd.DataFrame({
        'feature': dataset.feature_names,
        'importance': rf_importances,
    }).sort_values('importance', ascending=False)
    for _, row in imp_df.head(10).iterrows():
        print(f"    {row['feature']:<35s} {row['importance']:.4f}")


def _train_binary_mode(X_train, y_train, X_test, y_test,
                       dataset, class_names, args):
    """Train binary camera-vs-all classifier."""
    # Convert to binary: first class (assumed 'camera' or similar) = 1, rest = 0
    # Or check if a 'wireless_camera' class exists
    camera_idx = None
    for i, name in enumerate(class_names):
        if 'camera' in name.lower():
            camera_idx = i
            break

    if camera_idx is None:
        # Use first class as positive
        camera_idx = 0
        print(f"WARNING: No 'camera' class found. Using '{class_names[0]}' as positive.")

    y_train_bin = (y_train == camera_idx).astype(int)
    y_test_bin = (y_test == camera_idx).astype(int)

    print(f"\nBinary classification: '{class_names[camera_idx]}' vs all")
    print(f"Train positive: {y_train_bin.sum()}/{len(y_train_bin)}")
    print(f"Test positive:  {y_test_bin.sum()}/{len(y_test_bin)}")

    print("\nTraining Binary SVM...")
    svm_model, svm_grid, svm_params = train_svm_binary(
        X_train, y_train_bin, cv=args.cv)
    print(f"Best SVM params: {svm_params}")

    print("\nTraining Binary Random Forest...")
    rf_model, rf_grid, rf_params, rf_importances = train_rf_binary(
        X_train, y_train_bin, cv=args.cv)
    print(f"Best RF params: {rf_params}")

    # Ensemble
    from src.ml.ensemble import build_ensemble
    ensemble, _ = build_ensemble(
        svm_model=svm_model, rf_model=rf_model,
        X_train=X_train, y_train=y_train_bin)

    # Evaluate detection
    print("\n" + "=" * 60)
    print("CAMERA DETECTION RESULTS")
    print("=" * 60)

    svm_det = evaluate_binary_detection(svm_model, X_test, y_test_bin)
    rf_det = evaluate_binary_detection(rf_model, X_test, y_test_bin)
    ens_det = evaluate_binary_detection(ensemble, X_test, y_test_bin)

    for name, det in [('SVM', svm_det), ('RF', rf_det), ('Ensemble', ens_det)]:
        print(f"\n{name}:")
        print(f"  Detection Rate:    {det['detection_rate']:.3f}")
        print(f"  False Alarm Rate:  {det['false_alarm_rate']:.3f}")
        print(f"  Precision:         {det['precision']:.3f}")
        print(f"  F1 Score:          {det['f1']:.3f}")
        print(f"  TP={det['true_positive']}, FP={det['false_positive']}, "
              f"TN={det['true_negative']}, FN={det['false_negative']}")

    # Save best
    best = ensemble
    best_name = 'ensemble'
    if ens_det['f1'] < svm_det['f1']:
        best, best_name = svm_model, 'svm'
    if svm_det['f1'] < rf_det['f1'] and rf_det['f1'] > ens_det.get('f1', 0):
        best, best_name = rf_model, 'rf'

    print(f"\n[*] Best detection model: {best_name}")
    binary_names = [f'non_{class_names[camera_idx]}', class_names[camera_idx]]
    save_model(best, dataset.scaler, dataset.feature_names, binary_names,
               args.output, 'camera_detector')


if __name__ == '__main__':
    main()
