"""Setup configuration for neural-hive-approval-common library."""

from setuptools import setup

setup(
    name="neural-hive-approval-common",
    version="1.0.0",
    description="Unified approval models and decision logic for Neural Hive Mind",
    author="Neural Hive Mind Team",
    packages=["neural_hive_approval_common"],
    package_dir={"neural_hive_approval_common": "."},
    install_requires=[
        "pydantic>=2.5.2",
        "structlog>=23.2.0",
        "confluent-kafka>=2.3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.12.0",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
