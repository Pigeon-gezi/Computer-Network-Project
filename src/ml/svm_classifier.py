"""SVM classifier with RBF/poly kernel and GridSearchCV tuning."""

from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV


def build_svm_pipeline():
    """Build SVM pipeline (assumes data is already scaled).
    Uses RBF kernel by default with class_weight='balanced'.
    """
    return Pipeline([
        ('svm', SVC(kernel='rbf', probability=True, class_weight='balanced',
                     random_state=42, cache_size=500)),
    ])


def get_svm_param_grid():
    """Return the hyperparameter search grid for SVM."""
    return {
        'svm__C': [0.1, 1, 10, 100],
        'svm__gamma': ['scale', 'auto', 0.01, 0.1],
        'svm__kernel': ['rbf', 'poly'],
    }


def train_svm(X_train, y_train, cv=5, scoring='f1_weighted', n_jobs=-1):
    """Train SVM with grid search cross-validation.

    Returns: best_model, grid_search object, best_params dict
    """
    pipeline = build_svm_pipeline()
    param_grid = get_svm_param_grid()

    grid = GridSearchCV(
        pipeline, param_grid,
        cv=cv, scoring=scoring,
        n_jobs=n_jobs, verbose=1
    )
    grid.fit(X_train, y_train)

    return grid.best_estimator_, grid, grid.best_params_


def train_svm_binary(X_train, y_train, cv=5, n_jobs=-1):
    """Train SVM optimized for binary classification (camera vs non-camera).
    Uses tighter C range and focuses on recall for the positive class.
    """
    pipeline = Pipeline([
        ('svm', SVC(kernel='rbf', probability=True, class_weight='balanced',
                     random_state=42)),
    ])
    param_grid = {
        'svm__C': [0.5, 1, 5, 10, 50],
        'svm__gamma': ['scale', 'auto', 0.05, 0.1],
    }
    grid = GridSearchCV(
        pipeline, param_grid,
        cv=cv, scoring='f1',
        n_jobs=n_jobs, verbose=1
    )
    grid.fit(X_train, y_train)
    return grid.best_estimator_, grid, grid.best_params_
