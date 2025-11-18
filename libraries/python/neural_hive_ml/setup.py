"""Setup configuration for neural-hive-ml package."""

from setuptools import setup, find_packages

setup(
    name="neural-hive-ml",
    version="1.0.0",
    description="Biblioteca centralizada de modelos preditivos para Neural Hive-Mind",
    author="Neural Hive Mind Team",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "xgboost>=2.0.0",
        "lightgbm>=4.0.0",
        "prophet>=1.1.0",
        "statsmodels>=0.14.0",
        "scikit-learn>=1.3.0",
        "tensorflow>=2.13.0",
        "mlflow>=2.8.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "optuna>=3.0.0",
        "redis>=5.0.0",
        "motor>=3.3.0",
        "pmdarima>=2.0.0",
        "prometheus-client>=0.19.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
        ]
    },
)
