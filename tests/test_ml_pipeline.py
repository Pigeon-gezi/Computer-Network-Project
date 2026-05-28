"""Tests for ML pipeline — trains on synthetic data to verify end-to-end flow."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pytest
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier

from src.ml.dataset import Dataset
from src.ml.svm_classifier import train_svm
from src.ml.rf_classifier import train_random_forest
from src.ml.ensemble import build_ensemble, ensemble_predict_with_confidence
from src.ml.model_evaluator import evaluate_model, evaluate_binary_detection
from src.ml.model_persistence import save_model, load_model


def make_synthetic_features(n_samples=200, n_features=20, n_classes=3,
                             random_state=42):
    """Generate synthetic 802.11-like features for testing the ML pipeline."""
    rng = np.random.RandomState(random_state)

    # Class centers (simulate different device types)
    centers = {
        0: {  # wireless_camera
            'mean_frame_size': (1300, 100),
            'large_frame_ratio': (0.8, 0.1),
            'uplink_ratio': (0.9, 0.05),
            'qos_data_ratio': (0.8, 0.1),
            'protected_ratio': (0.9, 0.05),
            'cv_iat': (0.2, 0.1),
            'burst_count': (30, 10),
            'burst_density': (150, 30),
            'mean_data_rate': (60, 10),
            'throughput_bps': (5e6, 1e6),
            'mean_rssi': (-45, 10),
            'rssi_range': (10, 5),
        },
        1: {  # smartphone
            'mean_frame_size': (400, 150),
            'large_frame_ratio': (0.2, 0.1),
            'uplink_ratio': (0.4, 0.15),
            'qos_data_ratio': (0.3, 0.1),
            'protected_ratio': (0.6, 0.2),
            'cv_iat': (0.8, 0.2),
            'burst_count': (10, 5),
            'burst_density': (30, 15),
            'mean_data_rate': (30, 15),
            'throughput_bps': (1e6, 5e5),
            'mean_rssi': (-55, 10),
            'rssi_range': (25, 10),
        },
        2: {  # laptop
            'mean_frame_size': (800, 200),
            'large_frame_ratio': (0.5, 0.15),
            'uplink_ratio': (0.5, 0.2),
            'qos_data_ratio': (0.5, 0.15),
            'protected_ratio': (0.7, 0.15),
            'cv_iat': (0.5, 0.2),
            'burst_count': (15, 8),
            'burst_density': (60, 20),
            'mean_data_rate': (40, 15),
            'throughput_bps': (3e6, 1.5e6),
            'mean_rssi': (-50, 10),
            'rssi_range': (15, 8),
        },
    }

    X = np.zeros((n_samples, n_features))
    y = np.zeros(n_samples, dtype=int)
    feature_names = list(centers[0].keys())

    # Fill remaining feature names if needed
    while len(feature_names) < n_features:
        feature_names.append(f'noise_feature_{len(feature_names)}')

    for i in range(n_samples):
        cls = rng.randint(0, n_classes)
        y[i] = cls
        for j, fname in enumerate(feature_names):
            if fname in centers[cls]:
                mean, std = centers[cls][fname]
                X[i, j] = rng.normal(mean, std)
            else:
                X[i, j] = rng.normal(0, 1)

    return X, y, feature_names


class TestDataset:
    """Test Dataset construction and splitting."""

    def test_prepare(self):
        X, y, feature_names = make_synthetic_features()
        import pandas as pd
        df = pd.DataFrame(X, columns=feature_names)
        df['device_type'] = [f'class_{int(i)}' for i in y]

        dataset = Dataset(df, label_col='device_type')
        X_scaled, y_encoded = dataset.prepare()
        assert X_scaled.shape == X.shape
        assert len(y_encoded) == len(y)
        assert dataset.feature_names is not None

    def test_split_stratified(self):
        X, y, feature_names = make_synthetic_features(n_samples=100, n_classes=2)
        import pandas as pd
        df = pd.DataFrame(X, columns=feature_names)
        df['device_type'] = [f'class_{int(i)}' for i in y]

        dataset = Dataset(df, label_col='device_type')
        X_train, X_test, y_train, y_test = dataset.split(test_size=0.3)
        assert len(X_train) + len(X_test) == len(df)
        # Should preserve class ratio roughly
        train_ratio = np.mean(y_train)
        test_ratio = np.mean(y_test)
        assert abs(train_ratio - test_ratio) < 0.3


class TestSVMTraining:
    """Test SVM training on synthetic data."""

    def test_train_svm(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=2)
        from sklearn.svm import SVC
        model = SVC(kernel='rbf', probability=True, random_state=42).fit(X, y)
        score = model.score(X, y)
        assert score > 0.5

    def test_predict(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=2)
        from sklearn.svm import SVC
        model = SVC(kernel='rbf', probability=True, random_state=42).fit(X, y)
        preds = model.predict(X[:10])
        assert len(preds) == 10


class TestRFTraining:
    """Test Random Forest training on synthetic data."""

    def test_train_rf(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=2)
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=50, random_state=42).fit(X, y)
        score = model.score(X, y)
        assert score > 0.5

    def test_feature_importances_sum(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=2)
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=50, random_state=42).fit(X, y)
        importances = model.feature_importances_
        assert len(importances) == X.shape[1]
        assert abs(sum(importances) - 1.0) < 0.01


class TestEnsemble:
    """Test ensemble construction and prediction."""

    def test_build_ensemble_fast(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=3)
        from sklearn.svm import SVC
        from sklearn.ensemble import RandomForestClassifier
        svm = SVC(kernel='rbf', probability=True, random_state=42).fit(X, y)
        rf = RandomForestClassifier(n_estimators=50, random_state=42).fit(X, y)
        ensemble, components = build_ensemble(svm_model=svm, rf_model=rf,
                                              X_train=X, y_train=y)
        assert 'svm' in components
        assert 'rf' in components

    def test_ensemble_predict(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=3)
        from sklearn.svm import SVC
        from sklearn.ensemble import RandomForestClassifier
        svm = SVC(kernel='rbf', probability=True, random_state=42).fit(X, y)
        rf = RandomForestClassifier(n_estimators=50, random_state=42).fit(X, y)
        ensemble, _ = build_ensemble(svm_model=svm, rf_model=rf,
                                     X_train=X, y_train=y)
        preds, confidence, probs = ensemble_predict_with_confidence(ensemble, X[:10])
        assert len(preds) == 10
        assert len(confidence) == 10
        assert confidence.min() >= 0 and confidence.max() <= 1


class TestModelEvaluator:
    """Test evaluation on synthetic data."""

    def test_evaluate_multiclass(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=3)
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=50, random_state=42).fit(X, y)
        X_test, y_test = X[:30], y[:30]
        results = evaluate_model(model, X_test, y_test,
                                 class_names=['camera', 'phone', 'laptop'])
        assert 0 <= results['accuracy'] <= 1
        assert results['confusion_matrix'].shape == (3, 3)

    def test_evaluate_binary_detection(self):
        X, y, _ = make_synthetic_features(n_samples=100, n_classes=2)
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        model.fit(X, y)
        results = evaluate_binary_detection(model, X[:30], y[:30], positive_label=0)
        assert 'detection_rate' in results
        assert 'false_alarm_rate' in results
        assert results['true_positive'] + results['false_negative'] > 0


class TestModelPersistence:
    """Test save/load round-trip."""

    def test_save_load_roundtrip(self, tmp_path):
        X, y, feature_names = make_synthetic_features(n_samples=50, n_classes=2)
        model = RandomForestClassifier(n_estimators=50, random_state=42)
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        scaler.fit(X)
        model.fit(scaler.transform(X), y)

        model_dir = str(tmp_path / 'models')
        save_model(model, scaler, feature_names, ['class_0', 'class_1'],
                   model_dir, 'test_model')

        loaded_model, loaded_scaler, metadata = load_model(model_dir, 'test_model')
        assert metadata['feature_names'] == feature_names
        assert metadata['label_names'] == ['class_0', 'class_1']

        # Should produce same predictions
        X_test = make_synthetic_features(n_samples=10)[0]
        preds_orig = model.predict(scaler.transform(X_test))
        preds_loaded = loaded_model.predict(loaded_scaler.transform(X_test))
        assert np.array_equal(preds_orig, preds_loaded)
