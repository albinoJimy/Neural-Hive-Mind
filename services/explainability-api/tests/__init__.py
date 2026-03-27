# Configuração de path para testes do explainability-api
import sys
from pathlib import Path

# Adicionar diretório do serviço (pai de tests) ao path antes de qualquer import
# Isso permite imports como "from src.repositories.xxx import YYY"
service_dir = Path(__file__).resolve().parents[1]
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))
