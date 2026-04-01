"""
Coordination Module - Coordenação entre múltiplos scouts.

Módulos:
- scout_coordinator: Coordena distribuição de tarefas
- redis_state_store: Compartilhamento de estado via Redis
"""
from .redis_state_store import RedisStateStore
from .scout_coordinator import ScoutCoordinator, Task

__all__ = ["ScoutCoordinator", "Task", "RedisStateStore"]
