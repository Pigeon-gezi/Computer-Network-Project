"""Random Forest classifier with GridSearchCV tuning."""

from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV


def build_rf_pipeline():
    """Build Random Forest pipeline."""
    return Pipeline([
        ('rf', RandomForestClassifier(random_state=42, n_jobs=-1,
                                       class_weight='balanced')),
    ])


def get_rf_param_grid():
    """Return hyperparameter grid for Random Forest."""
    return {
        'rf__n_estimators': [100, 200, 300],
        'rf__max_depth': [10, 20, None],
        'rf__min_samples_split': [2, 5, 10],
        'rf__min_samples_leaf': [1, 2, 4],
    }


def train_random_forest(X_train, y_train, cv=5, scoring='f1_weighted', n_jobs=-1):
    """Train Random Forest with grid search.

    Returns: best_model, grid_search object, best_params dict
    """
    pipeline = build_rf_pipeline()
    param_grid = get_rf_param_grid()

    grid = GridSearchCV(
        pipeline, param_grid,
        cv=cv, scoring=scoring,
        n_jobs=n_jobs, verbose=1
    )
    grid.fit(X_train, y_train)

    # Extract feature importances
    best_rf = grid.best_estimator_.named_steps['rf']
    importances = best_rf.feature_importances_

    return grid.best_estimator_, grid, grid.best_params_, importances


def train_rf_binary(X_train, y_train, cv=5, n_jobs=-1):
    """Train RF optimized for binary detection with focus on recall."""
    pipeline = Pipeline([
        ('rf', RandomForestClassifier(random_state=42, n_jobs=-1,
                                       class_weight='balanced_subsample')),
    ])
    param_grid = {
        'rf__n_estimators': [150, 250, 350],
        'rf__max_depth': [15, 25, None],
        'rf__min_samples_split': [2, 5],
        'rf__min_samples_leaf': [1, 2],
    }
    grid = GridSearchCV(
        pipeline, param_grid,
        cv=cv, scoring='f1',
        n_jobs=n_jobs, verbose=1
    )
    grid.fit(X_train, y_train)
    best_rf = grid.best_estimator_.named_steps['rf']
    return grid.best_estimator_, grid, grid.best_params_, best_rf.feature_importances_
