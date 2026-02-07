"""
Sklearn compatibility patch for cross-version model loading.

This module provides monkey patching to handle sklearn version incompatibilities,
particularly the monotonic_cst attribute added in sklearn 1.4+.

When models trained with sklearn 1.3.x are loaded in sklearn 1.4+ environments,
the tree-based models expect the monotonic_cst attribute which doesn't exist in older models.
This patch intercepts attribute access to gracefully handle missing attributes.
"""

import sys
import warnings
import structlog

logger = structlog.get_logger()

# Track if patch has been applied
_PATCH_APPLIED = False


def _monkey_patch_sklearn_trees():
    """
    Monkey patch sklearn tree classes to handle missing monotonic_cst attribute.

    This patch modifies the __getattribute__ method of tree classes to return None
    for monotonic_cst when it doesn't exist, preventing AttributeError during predict().
    """
    global _PATCH_APPLIED

    if _PATCH_APPLIED:
        return

    try:
        from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor, ExtraTreeClassifier, ExtraTreeRegressor
        from sklearn.ensemble._forest import BaseForest

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

        # Apply patch to all tree classes
        tree_classes = [
            DecisionTreeClassifier,
            DecisionTreeRegressor,
            ExtraTreeClassifier,
            ExtraTreeRegressor,
        ]

        for cls in tree_classes:
            cls.__getattribute__ = create_patched_getattribute(cls.__getattribute__)
            # Mark that we've patched this class
            object.__setattr__(cls, '_monotonic_cst_patched', True)

        # Also patch BaseForest's validation method
        if hasattr(BaseForest, '_validate_X_predict'):
            original_validate = BaseForest._validate_X_predict

            def patched_validate(self, X, *args, **kwargs):
                """Patch _validate_X_predict to handle monotonic_cst access."""
                # Add monotonic_cst to all estimators before validation
                if hasattr(self, 'estimators_'):
                    for estimator in self.estimators_:
                        if hasattr(estimator, 'tree_') and not hasattr(estimator, 'monotonic_cst'):
                            object.__setattr__(estimator, 'monotonic_cst', None)
                return original_validate(self, X, *args, **kwargs)

            BaseForest._validate_X_predict = patched_validate

        _PATCH_APPLIED = True

        logger.info(
            "Sklearn compatibility patch applied",
            patched_classes=len(tree_classes),
            sklearn_version=sys.modules.get('sklearn').__version__ if 'sklearn' in sys.modules else 'unknown'
        )

    except ImportError as e:
        logger.warning(
            "Failed to import sklearn for patching",
            error=str(e)
        )
    except Exception as e:
        logger.error(
            "Failed to apply sklearn compatibility patch",
            error=str(e),
            error_type=type(e).__name__
        )


def apply_sklearn_compatibility_patch():
    """
    Apply sklearn compatibility patches for cross-version model loading.

    This function should be called before loading any sklearn models from MLflow
    to ensure compatibility between different sklearn versions.
    """
    _monkey_patch_sklearn_trees()


def patch_model_after_loading(model):
    """
    Patch a loaded sklearn model for compatibility.

    This function manually adds the missing monotonic_cst attribute to all
    tree estimators in an ensemble model.

    Args:
        model: Loaded sklearn model or MLflow pyfunc wrapper

    Returns:
        The patched model
    """
    try:
        # Get underlying sklearn model
        sklearn_model = None
        if hasattr(model, '_model_impl'):
            sklearn_model = getattr(model._model_impl, 'sklearn_model', None)
        elif hasattr(model, 'predict'):
            sklearn_model = model

        if sklearn_model is None:
            return model

        patched_count = 0

        # Patch ensemble estimators
        if hasattr(sklearn_model, 'estimators_'):
            for estimator in sklearn_model.estimators_:
                if hasattr(estimator, 'tree_') and not hasattr(estimator, 'monotonic_cst'):
                    object.__setattr__(estimator, 'monotonic_cst', None)
                    patched_count += 1

                # Handle nested estimators (e.g., in BaggingClassifier)
                if hasattr(estimator, 'estimators_'):
                    for nested in estimator.estimators_:
                        if hasattr(nested, 'tree_') and not hasattr(nested, 'monotonic_cst'):
                            object.__setattr__(nested, 'monotonic_cst', None)
                            patched_count += 1

        # Patch single tree models
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
