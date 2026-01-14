# Multi-stage Dockerfile for Code Forge - Neural Code Generation Pipeline
# Stage 1: Builder
FROM neural-hive-mind/python-observability-base:1.0.7 AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy local libraries first
COPY libraries/neural_hive_integration /tmp/neural_hive_integration

# Copy requirements and install dependencies
COPY services/code-forge/requirements.txt .
RUN pip install --no-cache-dir --user /tmp/neural_hive_integration || true && \
    pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime - use same base to get neural_hive_observability
FROM neural-hive-mind/python-observability-base:1.0.7

WORKDIR /app

# Install runtime dependencies (git for template cloning, docker-cli for builds, unzip for sonar-scanner)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    unzip \
    && curl -fsSL https://get.docker.com -o get-docker.sh \
    && sh get-docker.sh \
    && rm get-docker.sh \
    && rm -rf /var/lib/apt/lists/*

# Install Snyk CLI
RUN curl -o /usr/local/bin/snyk https://static.snyk.io/cli/latest/snyk-linux \
    && chmod +x /usr/local/bin/snyk

# Install Trivy
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin v0.45.0

# Install SonarQube Scanner
RUN curl -o /tmp/sonar-scanner.zip https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip \
    && unzip /tmp/sonar-scanner.zip -d /opt \
    && ln -s /opt/sonar-scanner-5.0.1.3006-linux/bin/sonar-scanner /usr/local/bin/sonar-scanner \
    && rm /tmp/sonar-scanner.zip

# Create non-root user first
RUN useradd -m -u 1000 codeforge

# Copy Python packages from builder
COPY --from=builder --chown=codeforge:codeforge /root/.local /home/codeforge/.local

# Set environment - user packages first, then system for neural_hive_observability
ENV PATH=/home/codeforge/.local/bin:$PATH
ENV PYTHONPATH=/home/codeforge/.local/lib/python3.11/site-packages:/usr/local/lib/python3.11/site-packages:/app

# Copy shared libraries
COPY --chown=codeforge:codeforge libraries/python/neural_hive_specialists /app/libraries/neural_hive_specialists

# Copy service code
COPY --chown=codeforge:codeforge services/code-forge/src /app/src

USER codeforge

# Expose ports
EXPOSE 8080 50051 9090

# Labels
LABEL service.name="code-forge" \
      service.version="1.0.0" \
      service.layer="execution" \
      service.component="neural-code-generation"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Entry point - usando asyncio.run(main())
CMD ["python", "-m", "src.main"]
