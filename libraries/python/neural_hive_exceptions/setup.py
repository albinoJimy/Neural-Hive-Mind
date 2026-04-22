"""
Setup configuration for neural_hive_exceptions.
"""

from setuptools import find_packages, setup

setup(
    name="neural-hive-exceptions",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "grpcio>=1.68.0",
    ],
    python_requires=">=3.12",
    description="Centralized exception library for Neural Hive-Mind platform",
    author="Neural Hive-Mind Team",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.12",
    ],
)
