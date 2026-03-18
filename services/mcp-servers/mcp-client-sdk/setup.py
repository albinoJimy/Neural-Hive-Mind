# MCP Client SDK Setup

from setuptools import find_packages, setup

setup(
    name="mcp-client-sdk",
    version="1.0.0",
    description="SDK para conectar agentes ao MCP (Model Context Protocol)",
    author="Neural Hive Mind",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "httpx>=0.27.0",
        "pydantic-settings>=2.6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.3.0",
            "pytest-asyncio>=0.24.0",
            "pytest-mock>=3.14.0",
        ],
    },
    python_requires=">=3.10",
)
