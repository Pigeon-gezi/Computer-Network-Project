"""Feature analysis: correlation heatmap, PCA scatter, importance bar chart."""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')


def plot_correlation_heatmap(feature_df, top_n=20, save_path=None):
    """Correlation heatmap of top features."""
    # Select numeric columns
    numeric_df = feature_df.select_dtypes(include=[np.number])

    # Keep only top-N by variance
    variances = numeric_df.var().sort_values(ascending=False)
    top_cols = variances.head(top_n).index.tolist()
    corr = numeric_df[top_cols].corr()

    fig, ax = plt.subplots(figsize=(12, 10))
    im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
    ax.set_xticks(range(len(top_cols)))
    ax.set_yticks(range(len(top_cols)))
    ax.set_xticklabels(top_cols, rotation=45, ha='right', fontsize=8)
    ax.set_yticklabels(top_cols, fontsize=8)
    ax.set_title('Feature Correlation Heatmap')

    plt.colorbar(im, ax=ax, shrink=0.8)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_pca_scatter(X_pca, labels=None, label_names=None, save_path=None):
    """2D PCA scatter plot with class coloring."""
    fig, ax = plt.subplots(figsize=(10, 8))

    if labels is not None:
        unique_labels = sorted(set(labels))
        cmap = plt.cm.tab10
        for i, label in enumerate(unique_labels):
            mask = np.array(labels) == label
            name = label_names[i] if label_names else str(label)
            ax.scatter(X_pca[mask, 0], X_pca[mask, 1],
                       c=[cmap(i % 10)], label=name, alpha=0.6, s=30)
        ax.legend()
    else:
        ax.scatter(X_pca[:, 0], X_pca[:, 1], alpha=0.5, s=20)

    ax.set_xlabel('Principal Component 1')
    ax.set_ylabel('Principal Component 2')
    ax.set_title('PCA: Feature Space Projection')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_feature_importance(importances_df, top_n=20, save_path=None):
    """Horizontal bar chart of feature importances."""
    df = importances_df.head(top_n).sort_values('importance')

    fig, ax = plt.subplots(figsize=(10, 8))
    bars = ax.barh(range(len(df)), df['importance'], color='steelblue')
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df['feature'])
    ax.set_xlabel('Importance (Gini)')
    ax.set_title(f'Top {top_n} Feature Importances')

    # Add value labels
    for i, (bar, val) in enumerate(zip(bars, df['importance'])):
        ax.text(val + 0.002, i, f'{val:.4f}', va='center', fontsize=8)

    ax.invert_yaxis()
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_feature_boxplot(feature_df, feature_names, by_label=None, save_path=None):
    """Side-by-side boxplots of key features grouped by device type."""
    n = len(feature_names)
    ncols = min(3, n)
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows))
    if n == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for i, feat_name in enumerate(feature_names):
        ax = axes[i]
        if feat_name not in feature_df.columns:
            ax.set_visible(False)
            continue

        if by_label is not None and by_label in feature_df.columns:
            for label in feature_df[by_label].unique():
                subset = feature_df[feature_df[by_label] == label][feat_name].dropna()
                ax.boxplot(subset.values, positions=[list(feature_df[by_label].unique()).index(label) + 1],
                           widths=0.5)
            ax.set_xticks(range(1, len(feature_df[by_label].unique()) + 1))
            ax.set_xticklabels(feature_df[by_label].unique(), rotation=45, fontsize=8)
        else:
            ax.boxplot(feature_df[feat_name].dropna().values)
            ax.set_xticklabels([])

        ax.set_title(feat_name, fontsize=9)
        ax.grid(True, alpha=0.3, axis='y')

    # Hide unused subplots
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    plt.suptitle('Feature Distributions by Device Type', fontsize=14)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig
