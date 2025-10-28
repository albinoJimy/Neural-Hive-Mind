"""
Setup script for Neural Hive-Mind Metrics Library
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_path.exists():
    with open(requirements_path, 'r', encoding='utf-8') as f:
        requirements = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith('#')
        ]

setup(
    name="neural-hive-metrics",
    version="1.0.0",
    author="Neural Hive-Mind Team",
    author_email="team@neural-hive.local",
    description="Biblioteca de métricas com suporte a exemplars e correlação distribuída para Neural Hive-Mind",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/neural-hive-mind/metrics",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: System :: Monitoring",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.7.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
        ],
        "fastapi": ["fastapi>=0.100.0"],
        "flask": ["flask>=2.3.0"],
        "django": ["django>=4.2.0"],
    },
    entry_points={
        "console_scripts": [
            "neural-hive-metrics=neural_hive_metrics.cli:main",
        ],
    },
    keywords="metrics monitoring observability neural-hive exemplars opentelemetry",
    project_urls={
        "Bug Reports": "https://github.com/neural-hive-mind/metrics/issues",
        "Source": "https://github.com/neural-hive-mind/metrics",
        "Documentation": "https://docs.neural-hive.local/metrics",
    },
)