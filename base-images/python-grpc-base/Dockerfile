# Neural Hive-Mind Python gRPC Base Image
# Base image with gRPC and protobuf for service communication

FROM neural-hive-mind/python-ml-base:1.0.0

# Build arguments for versioning
ARG VERSION=1.0.0
ARG BUILD_DATE

# Install gRPC dependencies
# protobuf >=6.31.1 required by grpcio-tools 1.75.1
RUN pip install --no-cache-dir \
    grpcio==1.75.1 \
    grpcio-tools==1.75.1 \
    grpcio-health-checking==1.75.1 \
    protobuf>=6.31.1

# Verify gRPC and protobuf installation
RUN python -c "import grpc; import google.protobuf; print('✓ gRPC', grpc.__version__, 'protobuf', google.protobuf.__version__)"

# OCI metadata labels
LABEL org.opencontainers.image.title="Neural Hive-Mind Python gRPC Base"
LABEL org.opencontainers.image.description="Base image with gRPC and protobuf for service communication"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL neural-hive-mind.org/component="python-grpc-base"
