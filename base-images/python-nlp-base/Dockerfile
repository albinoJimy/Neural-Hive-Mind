# Neural Hive-Mind Python NLP Base Image
# Base image with spaCy and pre-installed language models (pt, en)

FROM neural-hive-mind/python-grpc-base:1.0.0

# Build arguments for versioning
ARG VERSION=1.0.0
ARG BUILD_DATE

# Install spaCy
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir spacy>=3.7.0

# Download and install spaCy models
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.8.0/pt_core_news_sm-3.8.0-py3-none-any.whl \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Verify spaCy and models installation
RUN python -c "import spacy; import pt_core_news_sm; import en_core_web_sm; print('✓ spaCy', spacy.__version__, 'models: pt_core_news_sm, en_core_web_sm')"

# OCI metadata labels
LABEL org.opencontainers.image.title="Neural Hive-Mind Python NLP Base"
LABEL org.opencontainers.image.description="Base image with spaCy and pre-installed language models (pt, en)"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL neural-hive-mind.org/component="python-nlp-base"
