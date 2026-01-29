"""
Setup configuration for neural_hive_integration library.

This library provides integrated clients and orchestration for Phase 2 Flow C.
"""

from setuptools import setup, find_packages

setup(
    name="neural_hive_integration",
    version="1.1.4",  # Fix: added neural_hive_resilience dependency
    description="Neural Hive Mind Phase 2 Integration Library",
    author="Neural Hive Team",
    packages=find_packages(),
    package_data={
        "neural_hive_integration.proto_stubs": ["*.py"],
    },
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "httpx>=0.25.2",
        "grpcio>=1.68.1",  # Aligned with proto stubs GRPC_GENERATED_VERSION
        "protobuf>=5.27.0",  # Required for proto_stubs
        "structlog>=23.1.0",
        "opentelemetry-api>=1.21.0",
        "opentelemetry-sdk>=1.21.0",
        "opentelemetry-instrumentation-httpx>=0.42b0",
        "pydantic>=2.0.0",
        "tenacity>=8.2.0",
        "prometheus-client>=0.17.0",
        "aiokafka>=0.8.0",
        "redis>=5.0.0",
        "avro-python3>=1.10.0",
        "neural_hive_resilience>=0.1.0",  # Required for circuit breaker
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
