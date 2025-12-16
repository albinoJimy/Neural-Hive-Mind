FROM neural-hive-mind/python-grpc-base:1.0.0

ARG VERSION=1.0.0
ARG BUILD_DATE

RUN pip install --no-cache-dir \
    "pandas>=2.1.3" \
    "numpy>=1.26.2" \
    "scipy>=1.11.0" \
    "scikit-learn>=1.4.0,<1.6.0" \
    "mlflow>=2.9.0"

RUN python -c "import pandas; import numpy; import scipy; import sklearn; import mlflow; print('✓ MLOps deps installed')"

LABEL org.opencontainers.image.title="Neural Hive-Mind Python MLOps Base" \
      org.opencontainers.image.description="Base image with MLOps dependencies (pandas, numpy, scikit-learn, mlflow)" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      neural-hive-mind.org/component="python-mlops-base"
