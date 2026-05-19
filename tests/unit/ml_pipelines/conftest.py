"""
Local conftest para garantir sys.path inclui raiz do repo.
Necessário porque o pytest collection do test_model_promotion.py importa
ml_pipelines.deployment.model_promotion antes do pythonpath ini option
ter efeito.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # 3 levels up: ml_pipelines/unit/tests/<root>
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
