"""Dataset construction: feature DataFrame -> train/test splits."""

import numpy as np
import pandas as pd
from sklearn.model_selection import (
    train_test_split, StratifiedKFold, GroupShuffleSplit,
    StratifiedGroupKFold,
)
from sklearn.preprocessing import StandardScaler, LabelEncoder


class Dataset:
    """Handles feature matrix construction, scaling, and splitting."""

    def __init__(self, feature_df, label_col='device_type'):
        self.feature_df = feature_df
        self.label_col = label_col
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.feature_names = None
        self.X_raw = None
        self.X_scaled = None
        self.y_encoded = None

    def prepare(self, exclude_cols=None):
        """Prepare feature matrix X and labels y.

        exclude_cols: additional non-feature columns to drop
        """
        if exclude_cols is None:
            exclude_cols = []

        # Drop identifiers and fields that can leak capture/device identity.
        id_cols = [
            'sa', 'da', 'sa_oui', 'source_file', 'session_id', 'dominant_sa',
            'device_mac', 'device_oui', 'window_idx', 'window_start',
            'time_start', 'is_known_camera_oui', 'camera_heuristic_score',
            self.label_col,
        ]
        drop_cols = [c for c in id_cols + exclude_cols if c in self.feature_df.columns]

        X_df = self.feature_df.drop(columns=drop_cols, errors='ignore')
        # Keep only numeric
        X_df = X_df.select_dtypes(include=[np.number])

        # Fill NaN/inf
        X_df = X_df.fillna(X_df.median())
        X_df = X_df.fillna(0)
        X_df = X_df.replace([np.inf, -np.inf], 0)

        self.feature_names = X_df.columns.tolist()
        X = X_df.values
        self.X_raw = X

        # Scale
        self.X_scaled = self.scaler.fit_transform(X)

        # Encode labels
        y = self.feature_df[self.label_col].values
        self.y_encoded = self.label_encoder.fit_transform(y)

        return self.X_scaled, self.y_encoded

    def split(self, test_size=0.3, random_state=42, stratify=True,
              fit_scaler_on_train=False):
        """Split into train/test sets. Returns X_train, X_test, y_train, y_test."""
        if self.X_scaled is None:
            self.prepare()

        stratify_labels = self.y_encoded if stratify else None
        if fit_scaler_on_train:
            X_train_raw, X_test_raw, y_train, y_test = train_test_split(
                self.X_raw, self.y_encoded,
                test_size=test_size,
                random_state=random_state,
                stratify=stratify_labels
            )
            self.scaler.fit(X_train_raw)
            self.X_scaled = self.scaler.transform(self.X_raw)
            return (
                self.scaler.transform(X_train_raw),
                self.scaler.transform(X_test_raw),
                y_train,
                y_test,
            )

        return train_test_split(
            self.X_scaled, self.y_encoded,
            test_size=test_size,
            random_state=random_state,
            stratify=stratify_labels
        )

    def split_by_group(self, group_col, test_size=0.3, random_state=42,
                       fit_scaler_on_train=False, stratify=True):
        """Split train/test by group so one capture/session cannot cross sets."""
        if self.X_scaled is None:
            self.prepare()
        if group_col not in self.feature_df.columns:
            raise ValueError(f"group column '{group_col}' not found")

        groups = self.feature_df[group_col].astype(str).values
        if stratify and len(set(self.y_encoded)) > 1:
            train_idx, test_idx = self._stratified_group_split(
                groups=groups,
                test_size=test_size,
                random_state=random_state,
            )
        else:
            splitter = GroupShuffleSplit(
                n_splits=1,
                test_size=test_size,
                random_state=random_state,
            )
            train_idx, test_idx = next(
                splitter.split(self.X_raw, self.y_encoded, groups)
            )

        X_train_raw = self.X_raw[train_idx]
        X_test_raw = self.X_raw[test_idx]
        y_train = self.y_encoded[train_idx]
        y_test = self.y_encoded[test_idx]

        if fit_scaler_on_train:
            self.scaler.fit(X_train_raw)
            self.X_scaled = self.scaler.transform(self.X_raw)
            X_train = self.scaler.transform(X_train_raw)
            X_test = self.scaler.transform(X_test_raw)
        else:
            X_train = self.X_scaled[train_idx]
            X_test = self.X_scaled[test_idx]

        return X_train, X_test, y_train, y_test, train_idx, test_idx

    def _stratified_group_split(self, groups, test_size, random_state):
        """Approximate a stratified grouped holdout split.

        StratifiedGroupKFold cannot target an exact test_size, so try several
        fold counts and choose the split with the best class balance/size match.
        """
        unique_groups = np.unique(groups)
        if len(unique_groups) < 2:
            raise ValueError("grouped split requires at least two groups")

        target_test = len(self.y_encoded) * test_size
        total_counts = np.bincount(self.y_encoded)
        total_ratio = total_counts / max(total_counts.sum(), 1)

        candidate_splits = []
        max_splits = min(len(unique_groups), 10)
        for n_splits in range(2, max_splits + 1):
            splitter = StratifiedGroupKFold(
                n_splits=n_splits,
                shuffle=True,
                random_state=random_state,
            )
            try:
                split_iter = splitter.split(
                    self.X_raw, self.y_encoded, groups
                )
                candidate_splits.extend(split_iter)
            except ValueError:
                continue

        if not candidate_splits:
            splitter = GroupShuffleSplit(
                n_splits=1,
                test_size=test_size,
                random_state=random_state,
            )
            return next(splitter.split(self.X_raw, self.y_encoded, groups))

        def score_split(split):
            train_idx, test_idx = split
            y_test = self.y_encoded[test_idx]
            test_counts = np.bincount(
                y_test, minlength=len(total_counts)
            )
            test_ratio = test_counts / max(test_counts.sum(), 1)
            balance_error = np.abs(test_ratio - total_ratio).sum()
            size_error = abs(len(test_idx) - target_test) / max(len(self.y_encoded), 1)
            missing_penalty = 0.0
            if np.any(test_counts == 0):
                missing_penalty += 2.0
            y_train = self.y_encoded[train_idx]
            train_counts = np.bincount(
                y_train, minlength=len(total_counts)
            )
            if np.any(train_counts == 0):
                missing_penalty += 2.0
            return missing_penalty + balance_error + size_error

        return min(candidate_splits, key=score_split)

    def get_kfold(self, n_splits=5, shuffle=True, random_state=42):
        """Return a StratifiedKFold splitter."""
        return StratifiedKFold(n_splits=n_splits, shuffle=True,
                               random_state=random_state)

    def get_class_names(self):
        """Return list of class name strings."""
        return self.label_encoder.classes_.tolist()

    def get_label_name(self, encoded):
        """Decode a single label."""
        return self.label_encoder.inverse_transform([encoded])[0]

    def inverse_transform_labels(self, y_encoded):
        """Decode array of labels."""
        return self.label_encoder.inverse_transform(y_encoded)

    def get_feature_stats(self):
        """Return DataFrame with per-feature mean, std, min, max."""
        if self.X_scaled is None:
            self.prepare()
        means = self.scaler.mean_
        stds = self.scaler.scale_
        return pd.DataFrame({
            'feature': self.feature_names,
            'mean': means,
            'std': stds,
        }).sort_values('std', ascending=False)
