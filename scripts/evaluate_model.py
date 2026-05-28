#!/usr/bin/env python3
"""Evaluate trained models and generate full evaluation report with figures.

Usage:
    python evaluate_model.py --features data/processed/features.csv --model data/models/
    python evaluate_model.py --features data/processed/features.csv --model data/models/ --report
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.ml.dataset import Dataset
from src.ml.model_persistence import load_model, save_results
from src.ml.model_evaluator import (
    evaluate_model, evaluate_binary_detection, cross_validate_model, print_evaluation
)
from src.features.feature_selector import rank_features_by_importance
from src.visualization.result_plots import (
    plot_confusion_matrix, plot_roc_curves, plot_pr_curve,
    plot_model_comparison, plot_camera_detection_summary
)
from src.visualization.feature_plots import (
    plot_correlation_heatmap, plot_pca_scatter, plot_feature_importance
)


def main():
    parser = argparse.ArgumentParser(description='Evaluate model and generate report')
    parser.add_argument('--features', '-f', required=True, help='Feature CSV')
    parser.add_argument('--model', '-m', default='data/models/',
                        help='Model directory')
    parser.add_argument('--output', '-o', default='report/figures/',
                        help='Output directory for figures')
    parser.add_argument('--label-col', default='device_type',
                        help='Label column name')
    parser.add_argument('--cv', type=int, default=5, help='CV folds')
    parser.add_argument('--binary', action='store_true',
                        help='Evaluate as binary camera detector')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # Load data
    print(f"[*] Loading {args.features}")
    df = pd.read_csv(args.features)
    dataset = Dataset(df, label_col=args.label_col)
    X, y = dataset.prepare()
    class_names = dataset.get_class_names()
    _, X_test, _, y_test = dataset.split(test_size=0.3)

    print(f"    Samples: {len(df)}, Features: {X.shape[1]}")
    print(f"    Classes: {class_names}")

    # Load model
    model, scaler, metadata = load_model(args.model)
    print(f"[*] Model: {metadata.get('model_type', 'unknown')}")

    X_test_scaled = scaler.transform(X_test)

    # Evaluate
    results = evaluate_model(model, X_test_scaled, y_test, class_names)
    print_evaluation(results, class_names)

    # Cross-validation
    print("\n[*] Cross-validation...")
    cv_scores = cross_validate_model(model, X, y, cv=args.cv)
    for metric in ['test_accuracy', 'test_f1_macro', 'test_f1_weighted']:
        if metric in cv_scores:
            vals = cv_scores[metric]
            print(f"    {metric}: {vals.mean():.4f} (+/- {vals.std():.4f})")

    # Generate figures
    print("\n[*] Generating figures...")

    # Confusion matrix
    fig = plot_confusion_matrix(
        results['confusion_matrix'], class_names,
        save_path=os.path.join(args.output, 'confusion_matrix.png'))
    plt.close(fig)
    print("    confusion_matrix.png")

    # Normalized confusion matrix
    fig = plot_confusion_matrix(
        results['confusion_matrix'], class_names, normalize=True,
        save_path=os.path.join(args.output, 'confusion_matrix_norm.png'))
    plt.close(fig)
    print("    confusion_matrix_norm.png")

    # ROC curves
    if results.get('roc_auc'):
        fig = plot_roc_curves(
            results['roc_auc'],
            save_path=os.path.join(args.output, 'roc_curves.png'))
        plt.close(fig)
        print("    roc_curves.png")

    # Feature importance
    imp_df = rank_features_by_importance(X, y, dataset.feature_names)
    fig = plot_feature_importance(
        imp_df, top_n=20,
        save_path=os.path.join(args.output, 'feature_importance.png'))
    plt.close(fig)
    print("    feature_importance.png")

    # Correlation heatmap
    top_features = imp_df.head(15)['feature'].tolist()
    fig = plot_correlation_heatmap(
        df[top_features + [args.label_col] if args.label_col in df.columns else top_features],
        top_n=15,
        save_path=os.path.join(args.output, 'correlation_heatmap.png'))
    plt.close(fig)
    print("    correlation_heatmap.png")

    # PCA
    from src.features.feature_selector import apply_pca
    X_pca, pca_model, evr = apply_pca(X, n_components=2)
    fig = plot_pca_scatter(
        X_pca, y, class_names,
        save_path=os.path.join(args.output, 'pca_scatter.png'))
    plt.close(fig)
    print(f"    pca_scatter.png (explained variance: {evr[0]:.2%}, {evr[1]:.2%})")

    # Binary detection
    if args.binary or len(class_names) == 2:
        camera_idx = 0
        for i, name in enumerate(class_names):
            if 'camera' in name.lower():
                camera_idx = i
                break
        det_results = evaluate_binary_detection(
            model, X_test_scaled, y_test, positive_label=camera_idx)
        fig = plot_camera_detection_summary(
            det_results,
            save_path=os.path.join(args.output, 'camera_detection.png'))
        plt.close(fig)
        print("    camera_detection.png")

        if 'pr_curve' in det_results:
            fig = plot_pr_curve(
                det_results['pr_curve'],
                save_path=os.path.join(args.output, 'pr_curve.png'))
            plt.close(fig)
            print("    pr_curve.png")

    # Save evaluation JSON
    save_results(results)

    print(f"\n[*] Report generated in {args.output}")
    print(f"[*] Top 5 features for camera detection:")
    camera_features = ['large_frame_ratio', 'mean_frame_size', 'uplink_ratio',
                       'qos_data_ratio', 'burst_density', 'cv_iat',
                       'burst_regularity', 'mean_data_rate', 'protected_ratio']
    for feat in camera_features:
        if feat in imp_df['feature'].values:
            rank = imp_df[imp_df['feature'] == feat]['rank'].values[0]
            imp = imp_df[imp_df['feature'] == feat]['importance'].values[0]
            print(f"    {feat:<30s} rank={rank:3d}  importance={imp:.4f}")


if __name__ == '__main__':
    main()
