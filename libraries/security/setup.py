"""
Setup configuration for neural-hive-security library
"""

from setuptools import setup, find_packages

setup(
    name="neural-hive-security",
    version="1.0.0",
    description="Vault and SPIFFE integration for Neural Hive-Mind",
    author="Neural Hive-Mind Team",
    python_requires=">=3.11",
    packages=find_packages(),
    install_requires=[
        "hvac>=1.2.0",
        "grpcio>=1.54.0",
        "httpx>=0.24.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "tenacity>=8.2.0",
        "structlog>=23.1.0",
        "prometheus-client>=0.17.0",
        "cryptography>=41.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-mock>=3.11.0",
            "pytest-cov>=4.1.0",
            "black>=23.7.0",
            "mypy>=1.4.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.11",
        "Topic :: Security",
    ],
)
