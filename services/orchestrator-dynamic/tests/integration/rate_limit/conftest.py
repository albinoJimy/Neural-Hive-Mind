"""
Conftest isolado para testes de rate limiting.

Este conftest não depende de módulos externos problemáticos,
permitindo que os testes de rate limit sejam executados independentemente.
"""
import sys
from pathlib import Path

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
