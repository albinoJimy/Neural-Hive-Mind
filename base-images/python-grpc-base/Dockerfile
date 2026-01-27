# Neural Hive-Mind Python gRPC Base Image
# Base image with gRPC and protobuf for service communication

# Registry pode ser sobrescrito no build:
# --build-arg REGISTRY=37.60.241.150:30500 (interno)
# --build-arg REGISTRY=ghcr.io/albinojimy (GHCR)
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-ml-base:1.0.7

# Build arguments for versioning
ARG VERSION=1.0.7
ARG BUILD_DATE

# Install gRPC dependencies
# Versoes normalizadas: grpcio 1.68.1 + protobuf 5.29.2
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    grpcio==1.68.1 \
    grpcio-tools==1.68.1 \
    grpcio-health-checking==1.68.1 \
    protobuf==5.29.2

# Verify gRPC and protobuf installation
RUN python -c "import grpc; import google.protobuf; print('gRPC', grpc.__version__, 'protobuf', google.protobuf.__version__)"

# OCI metadata labels
LABEL org.opencontainers.image.title="Neural Hive-Mind Python gRPC Base"
LABEL org.opencontainers.image.description="Base image with gRPC and protobuf for service communication"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL neural-hive-mind.org/component="python-grpc-base"
