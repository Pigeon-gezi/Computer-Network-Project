"""Result visualization: confusion matrix, ROC curve, PR curve, model comparison."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')


def plot_confusion_matrix(cm, class_names=None, normalize=False, save_path=None):
    """Plot confusion matrix as a heatmap."""
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1, keepdims=True)
        cm = np.nan_to_num(cm)

    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(cm, cmap='Blues', aspect='auto')

    n = cm.shape[0]
    for i in range(n):
        for j in range(n):
            text = f'{cm[i, j]:.2f}' if normalize else f'{cm[i, j]}'
            color = 'white' if cm[i, j] > cm.max() / 2 else 'black'
            ax.text(j, i, text, ha='center', va='center', color=color, fontsize=10)

    if class_names:
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(class_names, rotation=45, ha='right')
        ax.set_yticklabels(class_names)

    ax.set_xlabel('Predicted')
    ax.set_ylabel('True')
    ax.set_title('Confusion Matrix' + (' (Normalized)' if normalize else ''))

    plt.colorbar(im, ax=ax, shrink=0.8)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_roc_curves(roc_data, save_path=None):
    """Plot ROC curves (one-vs-rest) from evaluate_model results."""
    fig, ax = plt.subplots(figsize=(8, 7))

    colors = plt.cm.tab10.colors
    for i, (cls_name, data) in enumerate(roc_data.items()):
        if isinstance(data, dict) and 'auc' in data:
            ax.plot(data['fpr'], data['tpr'],
                    label=f'{cls_name} (AUC={data["auc"]:.3f})',
                    color=colors[i % len(colors)], linewidth=2)

    ax.plot([0, 1], [0, 1], 'k--', alpha=0.3, label='Random')
    ax.set_xlabel('False Positive Rate')
    ax.set_ylabel('True Positive Rate')
    ax.set_title('ROC Curves (One-vs-Rest)')
    ax.legend(loc='lower right')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_pr_curve(pr_data, save_path=None):
    """Plot Precision-Recall curve for binary camera detection."""
    fig, ax = plt.subplots(figsize=(8, 7))

    precision = pr_data.get('precision', [])
    recall = pr_data.get('recall', [])

    if len(precision) > 0 and len(recall) > 0:
        ax.plot(recall, precision, 'b-', linewidth=2)
        ax.fill_between(recall, precision, alpha=0.2, color='blue')

    ax.set_xlabel('Recall')
    ax.set_ylabel('Precision')
    ax.set_title('Precision-Recall Curve (Camera Detection)')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_model_comparison(results_dict, metric='f1_weighted', save_path=None):
    """Bar chart comparing SVM, RF, and Ensemble on a specific metric."""
    fig, ax = plt.subplots(figsize=(8, 5))

    models = list(results_dict.keys())
    values = [results_dict[m].get(metric, 0) for m in models]
    colors = ['#ff9999', '#66b3ff', '#99ff99'][:len(models)]

    bars = ax.bar(models, values, color=colors)
    ax.set_ylabel(metric.replace('_', ' ').title())
    ax.set_title(f'Model Comparison: {metric.replace("_", " ").title()}')
    ax.set_ylim(0, max(values) * 1.15)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f'{val:.4f}', ha='center', fontsize=11)

    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_camera_detection_summary(detection_results, save_path=None):
    """Visual summary for camera detection: TP/FP/TN/FN as stacked bar."""
    fig, ax = plt.subplots(figsize=(6, 5))

    metrics = ['True Positive', 'False Positive', 'True Negative', 'False Negative']
    values = [
        detection_results.get('true_positive', 0),
        detection_results.get('false_positive', 0),
        detection_results.get('true_negative', 0),
        detection_results.get('false_negative', 0),
    ]
    colors = ['#2ca02c', '#d62728', '#1f77b4', '#ff7f0e']

    ax.bar(metrics, values, color=colors)
    ax.set_ylabel('Count')
    ax.set_title('Camera Detection Results')

    # Add value labels
    for i, (metric, val) in enumerate(zip(metrics, values)):
        ax.text(i, val + max(values) * 0.01, str(val), ha='center')

    # Add summary stats as text
    dr = detection_results.get('detection_rate', 0)
    far = detection_results.get('false_alarm_rate', 0)
    ax.text(0.5, -0.2, f'Detection Rate: {dr:.2%}  |  False Alarm Rate: {far:.2%}',
            transform=ax.transAxes, ha='center', fontsize=11,
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig
