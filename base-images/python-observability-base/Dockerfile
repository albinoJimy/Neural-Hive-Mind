# =============================================================================
# Neural Hive-Mind Python Observability Base Image
# =============================================================================
# Base image com neural_hive_observability pré-instalada
# Todos os serviços que precisam de observabilidade devem herdar desta imagem
# =============================================================================

FROM python:3.11-slim

# Build arguments
ARG VERSION=1.2.6
ARG BUILD_DATE

# Labels
LABEL org.opencontainers.image.title="Neural Hive-Mind Python Observability Base"
LABEL org.opencontainers.image.description="Base image with neural_hive_observability pre-installed"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL neural-hive-mind.org/component="python-observability-base"
LABEL neural-hive-mind.org/fix="opentelemetry-baggage-api-compatibility-get_all"

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install neural_hive_observability library from canonical location
COPY libraries/python/neural_hive_observability/ /tmp/neural_hive_observability/

# Install the library with all dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/neural_hive_observability/ && \
    rm -rf /tmp/neural_hive_observability

# Verify installation including critical functions
RUN python -c "from neural_hive_observability import init_observability, get_metrics, get_logger, instrument_grpc_channel, inject_context_to_metadata; from neural_hive_observability.context import extract_context_from_headers, set_baggage; print('✓ neural_hive_observability installed successfully with all required functions')"

# Print installed packages for debugging
RUN pip list | grep -E "opentelemetry|prometheus|grpcio|pydantic|structlog"
