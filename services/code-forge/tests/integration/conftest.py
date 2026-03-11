"""
Conftest para testes de integração do Code Forge.

Importa fixtures do conftest unitário para reutilização.
"""

import sys
from pathlib import Path

# Adicionar caminho para fixtures do unit conftest
sys.path.insert(0, str(Path(__file__).parent.parent / 'unit'))

# Importar todas as fixtures do conftest unitário
from tests.unit.conftest import *
