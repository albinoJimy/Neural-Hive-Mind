"""Setup configuration for neural-hive-approval-common library.

Layout standard: o package vive em ``./neural_hive_approval_common/`` e o
``setup.py`` está na raiz. ``find_packages`` faz o discovery — não definir
``package_dir`` evita o bug histórico em que o package era mapeado para a
raiz do repositório (instalações não-editable arrastavam ``setup.py``,
``pytest.ini`` e ``.coverage`` como módulos Python).
"""

from setuptools import find_packages, setup

setup(
    name="neural-hive-approval-common",
    version="1.1.0",
    description="Unified approval models and decision logic for Neural Hive Mind",
    author="Neural Hive Mind Team",
    packages=find_packages(exclude=("tests", "tests.*")),
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
