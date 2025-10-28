from setuptools import setup, find_packages

setup(
    name='neural-hive-agent-sdk',
    version='1.0.0',
    description='SDK para integração de agentes com Service Registry do Neural Hive-Mind',
    author='Neural Hive-Mind Team',
    packages=find_packages(),
    install_requires=[
        'grpcio>=1.59.0',
        'grpcio-tools>=1.59.0',
        'pydantic>=2.4.0',
        'pydantic-settings>=2.0.0',
        'structlog>=23.1.0',
        'protobuf>=4.24.0',
    ],
    python_requires='>=3.11',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.11',
    ],
)
