"""
Configuração pytest para testes do Queen Agent
"""

import sys
import pytest
import pytest_asyncio
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, MagicMock
from httpx import AsyncClient, ASGITransport

# Adicionar src ao path para imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# NOTA: Os mocks de dependências externas já estão configurados no conftest.py raiz
# usando ModuleType para compatibilidade com Pydantic.
# Aqui apenas garantimos que o src_path está no PYTHONPATH.


@pytest_asyncio.fixture
async def async_client(app):
    """Cliente HTTP assíncrono para testar APIs"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
