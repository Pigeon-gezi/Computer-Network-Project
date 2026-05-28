"""Model evaluation: cross-validation, metrics, confusion matrix, ROC."""

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    classification_report, confusion_matrix, roc_curve, auc,
    precision_recall_curve
)
from sklearn.model_selection import cross_val_score, cross_validate


def evaluate_model(model, X_test, y_test, class_names=None):
    """Comprehensive evaluation of a trained model.

    Returns dict with all metrics.
    """
    y_pred = model.predict(X_test)

    results = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision_macro': precision_score(y_test, y_pred, average='macro',
                                            zero_division=0),
        'recall_macro': recall_score(y_test, y_pred, average='macro',
                                      zero_division=0),
        'f1_macro': f1_score(y_test, y_pred, average='macro', zero_division=0),
        'precision_weighted': precision_score(y_test, y_pred, average='weighted',
                                               zero_division=0),
        'recall_weighted': recall_score(y_test, y_pred, average='weighted',
                                         zero_division=0),
        'f1_weighted': f1_score(y_test, y_pred, average='weighted',
                                 zero_division=0),
        'predictions': y_pred,
    }

    # Per-class metrics
    if class_names:
        results['classification_report'] = classification_report(
            y_test, y_pred, target_names=class_names, zero_division=0)
        results['per_class'] = {}
        for i, name in enumerate(class_names):
            y_true_bin = (y_test == i).astype(int)
            y_pred_bin = (y_pred == i).astype(int)
            results['per_class'][name] = {
                'precision': precision_score(y_true_bin, y_pred_bin, zero_division=0),
                'recall': recall_score(y_true_bin, y_pred_bin, zero_division=0),
                'f1': f1_score(y_true_bin, y_pred_bin, zero_division=0),
                'support': int(np.sum(y_true_bin)),
            }

    # Confusion matrix
    results['confusion_matrix'] = confusion_matrix(y_test, y_pred)

    # ROC AUC (one-vs-rest, if probability available)
    try:
        y_prob = model.predict_proba(X_test)
        n_classes = y_prob.shape[1]

        results['roc_auc'] = {}
        for i in range(n_classes):
            y_true_bin = (y_test == i).astype(int)
            if len(np.unique(y_true_bin)) > 1:
                fpr, tpr, _ = roc_curve(y_true_bin, y_prob[:, i])
                results['roc_auc'][class_names[i] if class_names else i] = {
                    'auc': auc(fpr, tpr),
                    'fpr': fpr.tolist(),
                    'tpr': tpr.tolist(),
                }
    except (AttributeError, Exception):
        results['roc_auc'] = None

    return results


def cross_validate_model(model, X, y, cv=5, scoring=None):
    """Run cross-validation and return scores.

    Returns dict with train/test scores for each fold.
    """
    if scoring is None:
        scoring = ['accuracy', 'f1_macro', 'f1_weighted']

    scores = cross_validate(
        model, X, y, cv=cv,
        scoring=scoring,
        return_train_score=True,
        n_jobs=-1
    )
    return scores


def evaluate_binary_detection(model, X_test, y_test, positive_label=0):
    """Evaluate for binary 'camera detection' scenario.

    Reports detection-specific metrics useful for the camera detection use case.
    """
    y_pred = model.predict(X_test)

    # Treat positive_label as 'camera' class
    y_true_bin = (y_test == positive_label).astype(int)
    y_pred_bin = (y_pred == positive_label).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true_bin, y_pred_bin).ravel()

    results = {
        'true_positive': int(tp),
        'false_positive': int(fp),
        'true_negative': int(tn),
        'false_negative': int(fn),
        'detection_rate': tp / max(tp + fn, 1),  # recall for camera class
        'false_alarm_rate': fp / max(fp + tn, 1),  # false positive rate
        'precision': tp / max(tp + fp, 1),
        'f1': 2 * tp / max(2 * tp + fp + fn, 1),
    }

    # PR curve
    try:
        y_prob = model.predict_proba(X_test)[:, positive_label]
        precision_curve, recall_curve, _ = precision_recall_curve(
            y_true_bin, y_prob)
        results['pr_curve'] = {
            'precision': precision_curve.tolist(),
            'recall': recall_curve.tolist(),
        }
    except (AttributeError, Exception):
        pass

    return results


def print_evaluation(results, class_names=None):
    """Pretty-print evaluation results."""
    print("=" * 60)
    print("Model Evaluation Results")
    print("=" * 60)
    print(f"Accuracy:            {results['accuracy']:.4f}")
    print(f"F1 (macro):          {results['f1_macro']:.4f}")
    print(f"F1 (weighted):       {results['f1_weighted']:.4f}")
    print(f"Precision (macro):   {results['precision_macro']:.4f}")
    print(f"Recall (macro):      {results['recall_macro']:.4f}")

    if results.get('classification_report'):
        print("\n" + results['classification_report'])

    print("Confusion Matrix:")
    cm = results['confusion_matrix']
    if class_names:
        header = " " * 12 + "".join(f"{n:>10s}" for n in class_names)
        print(header)
        for i, row in enumerate(cm):
            print(f"{class_names[i]:>10s}  " + "".join(f"{v:10d}" for v in row))
    else:
        print(cm)

    if results.get('roc_auc'):
        print("\nROC AUC (One-vs-Rest):")
        for cls, data in results['roc_auc'].items():
            print(f"  {cls}: {data['auc']:.4f}")
