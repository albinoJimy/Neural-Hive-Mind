"""
Pipeline de Online Learning para Neural Hive Mind.

Este módulo implementa aprendizado incremental contínuo com:
- IncrementalLearner: Atualizações incrementais via partial_fit
- ShadowValidator: Validação paralela de modelos
- ModelEnsemble: Combinação de modelos batch + online
- RollbackManager: Gestão de versões e rollback automático
- OnlinePerformanceMonitor: Monitoramento específico de online learning
- OnlineDeploymentOrchestrator: Orquestração de deployment
"""

from .config import OnlineLearningConfig
from .incremental_learner import IncrementalLearner
from .shadow_validator import ShadowValidator
from .model_ensemble import ModelEnsemble
from .rollback_manager import RollbackManager
from .online_monitor import OnlinePerformanceMonitor
from .deployment_orchestrator import OnlineDeploymentOrchestrator

__all__ = [
    'OnlineLearningConfig',
    'IncrementalLearner',
    'ShadowValidator',
    'ModelEnsemble',
    'RollbackManager',
    'OnlinePerformanceMonitor',
    'OnlineDeploymentOrchestrator',
]

__version__ = '1.0.0'
