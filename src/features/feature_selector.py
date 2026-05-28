"""Feature importance ranking and dimensionality reduction utilities.

Used to identify which 802.11 MAC-layer features are most discriminative
for device classification, and to reduce feature space for visualization.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA


def rank_features_by_importance(X, y, feature_names=None):
    """Rank features by Random Forest Gini importance.

    Args:
        X: feature matrix (n_samples, n_features)
        y: labels
        feature_names: optional list of feature names

    Returns:
        DataFrame with columns: feature, importance, rank
    """
    rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X, y)

    if feature_names is None:
        feature_names = [f'feature_{i}' for i in range(X.shape[1])]

    importances = pd.DataFrame({
        'feature': feature_names[:X.shape[1]],
        'importance': rf.feature_importances_,
    })
    importances = importances.sort_values('importance', ascending=False)
    importances['rank'] = range(1, len(importances) + 1)
    importances['cumulative'] = importances['importance'].cumsum()
    return importances.reset_index(drop=True)


def select_top_features(X, y=None, feature_names=None, top_k=20,
                        importance_threshold=0.01):
    """Select top-k features by RF importance, or all above threshold.

    Returns: X_reduced, selected_indices, importance_df
    """
    if y is None:
        raise ValueError("y must be provided for supervised feature selection")

    imp_df = rank_features_by_importance(X, y, feature_names)

    # Select by top_k or threshold
    if top_k is not None:
        selected = imp_df.head(top_k)
    else:
        selected = imp_df[imp_df['importance'] >= importance_threshold]

    indices = selected.index.tolist()
    X_reduced = X[:, indices] if hasattr(X, 'shape') else X.iloc[:, indices]
    return X_reduced, indices, imp_df


def apply_pca(X, n_components=2, scale=True):
    """Apply PCA for dimensionality reduction (mainly for visualization).

    Returns: X_pca, pca_model, explained_variance_ratio
    """
    if scale:
        scaler = StandardScaler()
        X = scaler.fit_transform(X)

    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X)
    return X_pca, pca, pca.explained_variance_ratio_


def get_camera_signature_features():
    """Return the list of features most discriminative for camera detection.

    Based on domain knowledge from Liu et al. (2018) and Zhang et al. (2025).
    """
    return [
        'large_frame_ratio',
        'mean_frame_size',
        'uplink_ratio',
        'qos_data_ratio',
        'mean_iat',
        'cv_iat',
        'burst_count',
        'burst_regularity',
        'burst_density',
        'mean_burst_packets',
        'mean_burst_bytes',
        'mean_data_rate',
        'protected_ratio',
        'mean_rssi',
        'rssi_variance',
        'rssi_range',
        'is_5ghz',
        'throughput_bps',
    ]


def get_feature_groups():
    """Return feature groups for grouped analysis.

    Each group is a dict: name -> list of feature name prefixes.
    """
    return {
        'frame_size': ['mean_frame_size', 'std_frame_size', 'large_frame_ratio',
                       'small_frame_ratio'],
        'inter_arrival_time': ['mean_iat', 'std_iat', 'cv_iat', 'median_iat'],
        'direction': ['uplink_ratio'],
        'signal_strength': ['mean_rssi', 'std_rssi', 'rssi_range', 'rssi_trend'],
        'frame_type': ['data_frame_ratio', 'mgmt_frame_ratio', 'qos_data_ratio'],
        'burst': ['burst_count', 'mean_burst_packets', 'mean_burst_bytes',
                  'burst_regularity', 'burst_density'],
        'data_rate': ['mean_data_rate', 'max_data_rate'],
        'qos_encryption': ['protected_ratio', 'retry_ratio'],
        'throughput': ['throughput_bps', 'packet_count', 'total_bytes'],
    }
