from setuptools import setup, find_packages

setup(
    name="neural-hive-specialists",
    version="1.0.8",
    description="Biblioteca compartilhada para especialistas neurais do Neural Hive-Mind",
    author="Neural Hive-Mind Team",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.5.2",
        "grpcio>=1.60.0",
        "mlflow>=2.9.0",
        "pymongo>=4.6.0",
        "redis>=5.0.1",
        "neo4j>=5.15.0",
        "opentelemetry-api>=1.21.0",
        "prometheus-client>=0.19.0",
        "tenacity>=8.2.3",
        "circuitbreaker>=1.4.0",
    ],
    extras_require={
        "explainability": ["shap>=0.44.0", "lime>=0.2.0.1"],
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.12.0",
            "pytest-timeout>=2.2.0",
            "testcontainers>=3.7.1",
            "faker>=22.0.0",
            "grpcio-testing>=1.60.0",
        ],
    },
    python_requires=">=3.11",
)
