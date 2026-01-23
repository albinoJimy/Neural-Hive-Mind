"""Setup configuration for neural-hive-domain library."""

from setuptools import setup

setup(
    name='neural-hive-domain',
    version='1.0.0',
    description='Unified domain definitions for the Neural Hive Mind system',
    author='Neural Hive Mind Team',
    packages=['neural_hive_domain'],
    package_dir={'neural_hive_domain': '.'},
    install_requires=[
        'pydantic>=2.5.2',
        'structlog>=23.2.0',
    ],
    python_requires='>=3.11',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)
