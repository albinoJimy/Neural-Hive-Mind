"""
Setup configuration for neural_hive_infrastructure.
"""

from setuptools import find_packages, setup

setup(
    name="neural-hive-infrastructure",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
    ],
    python_requires=">=3.12",
    description="Centralized infrastructure settings for Neural Hive-Mind platform",
    author="Neural Hive-Mind Team",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.12",
    ],
)
