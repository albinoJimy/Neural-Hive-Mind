"""
Configuração pytest para testes de integração
"""

import sys
from pathlib import Path

# Adicionar src ao path para imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

# NOTA: Os mocks de dependências externas já estão configurados no conftest.py raiz
# usando ModuleType para compatibilidade com Pydantic.
# Aqui apenas garantimos que o src_path está no PYTHONPATH.
