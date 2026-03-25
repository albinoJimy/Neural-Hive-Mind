"""
Configuração pytest para testes do Execution Ticket Service.
"""
import sys
from pathlib import Path

# Adicionar src ao path ANTES de pytest coletar os testes
service_dir = Path(__file__).resolve().parents[1]
src_path = str(service_dir / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
