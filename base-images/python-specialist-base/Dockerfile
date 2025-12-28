FROM neural-hive-mind/python-nlp-base:1.0.0

ARG VERSION=1.0.0
ARG BUILD_DATE

WORKDIR /app

# Copy and install neural_hive_specialists library
COPY libraries/python/neural_hive_specialists /tmp/neural_hive_specialists
RUN pip install --no-cache-dir -r /tmp/neural_hive_specialists/requirements.txt && \
    pip install --no-cache-dir /tmp/neural_hive_specialists && \
    rm -rf /tmp/neural_hive_specialists

# Copy and install neural_hive_observability library for distributed tracing
COPY libraries/python/neural_hive_observability /tmp/neural_hive_observability
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir /tmp/neural_hive_observability && \
    rm -rf /tmp/neural_hive_observability

# Install additional specialist dependencies
# NOTA: scikit-learn>=1.5.0,<1.6.0 para compatibilidade com modelos retreinados em 2025-12-06
# NOTA: sentence-transformers é requerido pelo semantic_pipeline (import global em semantic_analyzer.py)

# First install torch separately (large download, using retries)
# Using CPU-only version to reduce download size
# torch 2.4.1 is compatible with transformers >= 4.32.0 (required by sentence-transformers)
RUN pip install --no-cache-dir --retries 5 --timeout 120 \
    torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu

# Then install sentence-transformers (depends on torch)
# Version 3.3.1 is stable and compatible with torch 2.4.x
RUN pip install --no-cache-dir --retries 5 --timeout 120 \
    "sentence-transformers==3.3.1"

# Install remaining dependencies (aligned with services requirements)
RUN pip install --no-cache-dir \
    "fastapi==0.115.6" \
    "uvicorn[standard]==0.34.0" \
    "requests>=2.31.0" \
    "pydantic==2.10.4" \
    "pydantic-settings==2.7.1" \
    "tenacity>=8.2.3" \
    "pybreaker>=1.0.1" \
    "pandas==2.2.3" \
    "numpy==1.26.4" \
    "scikit-learn==1.5.2" \
    "structlog==24.4.0"

# Verify installation including critical imports
RUN python -c "\
import fastapi; \
import pandas; \
from neural_hive_specialists import BaseSpecialist, SpecialistConfig, ProbabilisticModelWrapper; \
from neural_hive_specialists.semantic_pipeline import SemanticPipeline; \
from neural_hive_specialists.compliance import ComplianceLayer; \
from neural_hive_specialists.feedback import FeedbackCollector; \
from neural_hive_observability import init_tracing, get_tracer, init_metrics; \
import sys; \
assert 'probabilistic_wrapper' in sys.modules, 'probabilistic_wrapper not in sys.modules'; \
print('✓ Specialist base ready - all imports validated'); \
print('✓ neural_hive_observability available for distributed tracing')"

LABEL org.opencontainers.image.title="Neural Hive-Mind Python Specialist Base" \
      org.opencontainers.image.description="Base image with neural_hive_specialists library and common dependencies for specialist services" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      neural-hive-mind.org/component="python-specialist-base"
