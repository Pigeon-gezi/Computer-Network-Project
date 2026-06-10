"""Dataset construction: feature DataFrame -> train/test splits."""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, StratifiedKFold
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

        # Drop identifier/non-numeric columns
        id_cols = ['sa', 'da', 'sa_oui', 'source_file', 'dominant_sa',
                   self.label_col]
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
