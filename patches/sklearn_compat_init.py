#!/usr/bin/env python3
"""
Init script to apply sklearn compatibility patch before model loading.

This script must be imported before any sklearn models are loaded to ensure
compatibility between different sklearn versions.
"""

import sys

# Apply sklearn compatibility patch early
try:
    from sklearn_compat import apply_sklearn_compatibility_patch
    apply_sklearn_compatibility_patch()
except ImportError:
    # Patch module not available, skip
    pass

# Patch must be applied before importing mlflow
import mlflow
from mlflow.pyfunc import load_model

# Monkey patch load_model to apply patch before loading
_original_load_model = load_model

def patched_load_model(model_uri, **kwargs):
    """Load model with sklearn compatibility patch applied."""
    # Apply patch before loading
    try:
        from sklearn_compat import patch_model_after_loading
        model = _original_load_model(model_uri, **kwargs)
        return patch_model_after_loading(model)
    except ImportError:
        return _original_load_model(model_uri, **kwargs)

# Replace mlflow.pyfunc.load_model
mlflow.pyfunc.load_model = patched_load_model

print("✓ Sklearn compatibility initialization complete")
