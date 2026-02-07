"""
Sklearn compatibility patch for cross-version model loading.

This module provides monkey patching to handle sklearn version incompatibilities.
"""

import sys
import structlog

logger = structlog.get_logger()

_PATCH_APPLIED = False


def _monkey_patch_sklearn_trees():
    """Monkey patch sklearn tree classes for monotonic_cst compatibility."""
    global _PATCH_APPLIED

    if _PATCH_APPLIED:
        return

    try:
        from sklearn.tree import (
            DecisionTreeClassifier,
            DecisionTreeRegressor,
            ExtraTreeClassifier,
            ExtraTreeRegressor,
        )
        from sklearn.ensemble._forest import BaseForest

        # Store original __getattribute__
        original_classes = {}

        # Create a closure factory to avoid late binding issues
        def create_patched_getattribute(original_getattribute):
            """Factory to create patched __getattribute__ for each class separately."""
            def patched_getattribute(self, name):
                """Handle missing monotonic_cst attribute gracefully."""
                if name == 'monotonic_cst' and not hasattr(self, '_monotonic_cst_patched'):
                    # Return None for missing monotonic_cst attribute
                    return None
                return original_getattribute(self, name)
            return patched_getattribute

        for cls in [DecisionTreeClassifier, DecisionTreeRegressor, ExtraTreeClassifier, ExtraTreeRegressor]:
            original_classes[cls] = cls.__getattribute__
            cls.__getattribute__ = create_patched_getattribute(cls.__getattribute__)
            # Mark that we've patched this class
            object.__setattr__(cls, '_monotonic_cst_patched', True)

        # Patch BaseForest validation
        original_validate = BaseForest._validate_X_predict

        def patched_validate(self, X, *args, **kwargs):
            for estimator in self.estimators_:
                if hasattr(estimator, 'tree_') and not hasattr(estimator, 'monotonic_cst'):
                    object.__setattr__(estimator, 'monotonic_cst', None)
            return original_validate(self, X, *args, **kwargs)

        BaseForest._validate_X_predict = patched_validate
        _PATCH_APPLIED = True

        logger.info(
            "Sklearn compatibility patch applied",
            sklearn_version=sys.modules.get('sklearn').__version__ if 'sklearn' in sys.modules else 'unknown'
        )

    except Exception as e:
        logger.error(
            "Failed to apply sklearn compatibility patch",
            error=str(e),
            error_type=type(e).__name__
        )


def apply_sklearn_compatibility_patch():
    """Apply sklearn compatibility patches for cross-version model loading."""
    _monkey_patch_sklearn_trees()


def patch_model_after_loading(model):
    """Patch a loaded sklearn model for compatibility."""
    try:
        sklearn_model = None
        if hasattr(model, '_model_impl'):
            sklearn_model = getattr(model._model_impl, 'sklearn_model', None)
        elif hasattr(model, 'predict'):
            sklearn_model = model

        if sklearn_model is None:
            return model

        patched_count = 0

        if hasattr(sklearn_model, 'estimators_'):
            for estimator in sklearn_model.estimators_:
                if hasattr(estimator, 'tree_') and not hasattr(estimator, 'monotonic_cst'):
                    object.__setattr__(estimator, 'monotonic_cst', None)
                    patched_count += 1
                if hasattr(estimator, 'estimators_'):
                    for nested in estimator.estimators_:
                        if hasattr(nested, 'tree_') and not hasattr(nested, 'monotonic_cst'):
                            object.__setattr__(nested, 'monotonic_cst', None)
                            patched_count += 1
        elif hasattr(sklearn_model, 'tree_') and not hasattr(sklearn_model, 'monotonic_cst'):
            object.__setattr__(sklearn_model, 'monotonic_cst', None)
            patched_count += 1

        if patched_count > 0:
            logger.debug(
                "Model patched for sklearn compatibility",
                patched_estimators=patched_count,
                model_type=type(sklearn_model).__name__
            )

    except Exception as e:
        logger.warning(
            "Failed to patch model after loading",
            error=str(e),
            error_type=type(e).__name__
        )

    return model


# Auto-apply patch on module import
apply_sklearn_compatibility_patch()
