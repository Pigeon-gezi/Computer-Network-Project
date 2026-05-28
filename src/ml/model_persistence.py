"""Model persistence: save/load trained models, scalers, and metadata."""

import os
import json
import joblib
import numpy as np


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def save_model(model, scaler, feature_names, label_names, output_dir='data/models/',
               model_name='device_classifier'):
    """Save trained model, scaler, feature names, and label mapping."""
    os.makedirs(output_dir, exist_ok=True)

    joblib.dump(model, os.path.join(output_dir, f'{model_name}.joblib'))
    joblib.dump(scaler, os.path.join(output_dir, f'{model_name}_scaler.joblib'))

    metadata = {
        'feature_names': list(feature_names),
        'label_names': list(label_names),
        'model_type': type(model).__name__,
    }
    with open(os.path.join(output_dir, f'{model_name}_metadata.json'), 'w') as f:
        json.dump(metadata, f, indent=2, cls=NumpyEncoder)


def load_model(model_dir='data/models/', model_name='device_classifier'):
    """Load a trained model and associated objects.

    Returns: model, scaler, metadata dict
    """
    model = joblib.load(os.path.join(model_dir, f'{model_name}.joblib'))
    scaler = joblib.load(os.path.join(model_dir, f'{model_name}_scaler.joblib'))

    with open(os.path.join(model_dir, f'{model_name}_metadata.json')) as f:
        metadata = json.load(f)

    return model, scaler, metadata


def save_results(results, output_dir='data/processed/'):
    """Save evaluation results as JSON."""
    os.makedirs(output_dir, exist_ok=True)

    # Make results JSON-serializable
    serializable = {}
    for key, value in results.items():
        if isinstance(value, np.ndarray):
            serializable[key] = value.tolist()
        elif isinstance(value, dict):
            serializable[key] = {str(k): (v.tolist() if isinstance(v, np.ndarray) else v)
                                 for k, v in value.items()}
        else:
            try:
                json.dumps({key: value})
                serializable[key] = value
            except (TypeError, OverflowError):
                serializable[key] = str(value)

    with open(os.path.join(output_dir, 'evaluation_results.json'), 'w') as f:
        json.dump(serializable, f, indent=2, cls=NumpyEncoder)


def export_predictions_csv(predictions, output_path='data/processed/predictions.csv'):
    """Export device predictions to CSV."""
    import pandas as pd
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pd.DataFrame(predictions).to_csv(output_path, index=False)
