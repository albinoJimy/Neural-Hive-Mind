FROM 37.60.241.150:30500/neural-hive-mind/python-grpc-base:1.0.7

ARG VERSION=1.0.0
ARG BUILD_DATE

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    "pandas==2.2.3" \
    "numpy==1.26.4" \
    "scipy==1.14.1" \
    "scikit-learn==1.5.2" \
    "mlflow==2.19.0"

RUN python -c "import pandas; import numpy; import scipy; import sklearn; import mlflow; print('✓ MLOps deps installed')"

LABEL org.opencontainers.image.title="Neural Hive-Mind Python MLOps Base" \
      org.opencontainers.image.description="Base image with MLOps dependencies (pandas, numpy, scikit-learn, mlflow)" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      neural-hive-mind.org/component="python-mlops-base"
