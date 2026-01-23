from setuptools import setup, find_packages

setup(
    name="neural-hive-risk-scoring",
    version="1.0.0",
    description="Biblioteca de risk scoring multi-domínio para Neural Hive-Mind",
    author="Neural Hive-Mind Team",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.5.2",
        "structlog>=23.2.0",
        "prometheus-client>=0.19.0",
        "neural-hive-domain",
    ],
    python_requires=">=3.11",
)
