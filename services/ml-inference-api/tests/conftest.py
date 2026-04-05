"""
Configuração pytest para testes do ML Inference API.
"""
import os
import sys
from pathlib import Path

# Adicionar src ao path ANTES de pytest coletar os testes
service_dir = Path(__file__).resolve().parents[1]
src_path = str(service_dir / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Adicionar ml_pipelines ao path para importar ApprovalPredictor
ml_pipelines_path = str(service_dir.parent / "ml_pipelines")
if ml_pipelines_path not in sys.path:
    sys.path.insert(0, ml_pipelines_path)


# Configurar variáveis de ambiente para testes
# Isso evita erros de validação do Pydantic Settings
os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")
os.environ.setdefault("MODEL_NAME", "approval_model")
os.environ.setdefault("MODEL_VERSION", "Production")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "0")
os.environ.setdefault("PROMETHEUS_PORT", "9090")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SERVICE_NAME", "ml-inference-api")
os.environ.setdefault("MAX_BATCH_SIZE", "100")
os.environ.setdefault("DEFAULT_TIMEOUT_MS", "5000")
os.environ.setdefault("CIRCUIT_BREAKER_THRESHOLD", "5")
os.environ.setdefault("CIRCUIT_BREAKER_TIMEOUT_MS", "60000")
os.environ.setdefault("ENABLE_GPU", "false")
