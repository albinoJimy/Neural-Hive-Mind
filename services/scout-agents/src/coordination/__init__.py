"""
Coordination Module - Coordenação entre múltiplos scouts.

Módulos:
- scout_coordinator: Coordena distribuição de tarefas
- redis_state_store: Compartilhamento de estado via Redis
"""
from .scout_coordinator import ScoutCoordinator, Task
from .redis_state_store import RedisStateStore

__all__ = ['ScoutCoordinator', 'Task', 'RedisStateStore']
