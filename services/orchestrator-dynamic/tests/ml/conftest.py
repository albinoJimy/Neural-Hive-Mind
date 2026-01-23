"""
Conftest para testes ML.

Configura sys.path para permitir imports do src.
"""

import sys
from pathlib import Path

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
