"""
Setup configuration for neural_hive_integration library.

This library provides integrated clients and orchestration for Phase 2 Flow C.
"""

from setuptools import setup, find_packages

setup(
    name="neural_hive_integration",
    version="1.1.5",  # Fix 2a, 2b, 2c, 3: cognitive_plan aninhado
    description="Neural Hive Mind Phase 2 Integration Library",
    author="Neural Hive Team",
    packages=find_packages(),
    package_data={
        "neural_hive_integration.proto_stubs": ["*.py"],
    },
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.25.2",
        "grpcio>=1.71.2",  # Aligned with requirements-base.txt
        "protobuf>=5.27.0",  # Required for proto_stubs
        "structlog>=23.1.0",
        # OpenTelemetry - updated to 0.62b1 stack (2026-04-29)
        "opentelemetry-api==1.41.1",
        "opentelemetry-sdk==1.41.1",
        "opentelemetry-semantic-conventions==0.62b1",
        "opentelemetry-instrumentation==0.62b1",
        "opentelemetry-instrumentation-httpx==0.62b1",
        "pydantic>=2.0.0",
        "tenacity>=8.2.0",
        "prometheus-client>=0.17.0",
        "aiokafka>=0.8.0",
        "redis>=5.0.0",
        "avro-python3>=1.10.0",
        # "neural_hive_resilience>=0.1.0",  # Temporarily disabled - not available
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-mock>=3.11.0",
            "pytest-cov>=4.1.0",
            "black>=23.7.0",
            "mypy>=1.4.0",
        ]
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
