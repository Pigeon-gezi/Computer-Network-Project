"""Ensemble classifier: SVM + Random Forest soft voting."""

import numpy as np
from sklearn.ensemble import VotingClassifier

from .svm_classifier import train_svm
from .rf_classifier import train_random_forest


class WeightedSoftVotingClassifier:
    """Soft-voting wrapper for already-fitted estimators."""

    def __init__(self, estimators, weights):
        self.estimators = estimators
        self.weights = np.asarray(weights, dtype=float)
        self.classes_ = estimators[0][1].classes_

    def predict_proba(self, X):
        weighted_probs = None
        for weight, (_, model) in zip(self.weights, self.estimators):
            if not np.array_equal(model.classes_, self.classes_):
                raise ValueError("All estimators must use the same class order")
            probs = model.predict_proba(X) * weight
            weighted_probs = probs if weighted_probs is None else weighted_probs + probs
        return weighted_probs / self.weights.sum()

    def predict(self, X):
        probabilities = self.predict_proba(X)
        return self.classes_[np.argmax(probabilities, axis=1)]


def build_ensemble(svm_model=None, rf_model=None, X_train=None, y_train=None,
                   cv=5, n_jobs=-1):
    """Build a VotingClassifier ensemble of SVM + Random Forest.

    If svm_model/rf_model are None, trains new models on X_train, y_train.

    Returns: ensemble model, dict of component models
    """
    if svm_model is None and X_train is not None:
        svm_model, _, svm_params = train_svm(X_train, y_train, cv=cv,
                                              n_jobs=n_jobs)
    if rf_model is None and X_train is not None:
        rf_model, _, rf_params, _ = train_random_forest(
            X_train, y_train, cv=cv, n_jobs=n_jobs)

    ensemble = VotingClassifier(
        estimators=[
            ('svm', svm_model),
            ('rf', rf_model),
        ],
        voting='soft',
        weights=[1, 1],
    )

    if X_train is not None:
        ensemble.fit(X_train, y_train)

    components = {'svm': svm_model, 'rf': rf_model}
    return ensemble, components


def build_weighted_ensemble(svm_model, rf_model, X_val, y_val,
                            metric_fn=None):
    """Build ensemble with weights optimized on validation set.

    Tries different weight combinations and picks the best.
    """
    if metric_fn is None:
        from sklearn.metrics import f1_score
        metric_fn = lambda y_true, y_pred: f1_score(y_true, y_pred, average='weighted')

    best_score = 0
    best_weights = (1, 1)
    best_ensemble = None

    for w_svm in range(1, 6):
        for w_rf in range(1, 6):
            ensemble = WeightedSoftVotingClassifier(
                estimators=[('svm', svm_model), ('rf', rf_model)],
                weights=[w_svm, w_rf],
            )
            y_pred = ensemble.predict(X_val)
            score = metric_fn(y_val, y_pred)
            if score > best_score:
                best_score = score
                best_weights = (w_svm, w_rf)
                best_ensemble = ensemble

    return best_ensemble, best_weights, best_score


def ensemble_predict_with_confidence(ensemble, X):
    """Predict with confidence scores from the ensemble.

    Returns: predictions array, confidence array, per-class probabilities
    """
    predictions = ensemble.predict(X)
    probabilities = ensemble.predict_proba(X)
    confidence = probabilities.max(axis=1)
    return predictions, confidence, probabilities


def compare_models(svm_model, rf_model, ensemble_model, X_test, y_test,
                   class_names=None):
    """Compare SVM, RF, and Ensemble on test data.

    Returns dict of per-model metrics.
    """
    from .model_evaluator import evaluate_model

    results = {
        'svm': evaluate_model(svm_model, X_test, y_test, class_names),
        'rf': evaluate_model(rf_model, X_test, y_test, class_names),
        'ensemble': evaluate_model(ensemble_model, X_test, y_test, class_names),
    }

    # Summary
    print("Model Comparison:")
    print(f"{'Model':<12s} {'Accuracy':>10s} {'F1 Macro':>10s} {'F1 Weighted':>12s}")
    print("-" * 46)
    for name, res in results.items():
        print(f"{name:<12s} {res['accuracy']:10.4f} {res['f1_macro']:10.4f} "
              f"{res['f1_weighted']:12.4f}")

    return results
