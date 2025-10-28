"""
Configuração pytest para testes do Queen Agent
"""
import sys
from pathlib import Path

# Adicionar src ao path para imports
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))
