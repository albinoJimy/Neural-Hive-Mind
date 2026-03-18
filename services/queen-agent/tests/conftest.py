"""
Configuração pytest para testes do Queen Agent
"""
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Adicionar src ao path para imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Mock de dependências externas ANTES de qualquer import
sys.modules["neural_hive_domain"] = Mock()
sys.modules["neural_hive_specialists"] = Mock()
sys.modules["neural_hive_agent_sdk"] = Mock()
sys.modules["neural_hive_observability"] = Mock()
sys.modules["neural_hive_observability"].get_logger = Mock(return_value=MagicMock())
