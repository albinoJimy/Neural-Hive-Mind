"""
Servidor gRPC para Orchestrator Dynamic.

Expõe serviço OrchestratorStrategic para receber comandos estratégicos
da Queen Agent, incluindo ajustes de prioridade, recursos, pausas e
acionamento de replanejamento.
"""

from .orchestrator_servicer import OrchestratorStrategicServicer
from .server import start_grpc_server, stop_grpc_server

__all__ = [
    'OrchestratorStrategicServicer',
    'start_grpc_server',
    'stop_grpc_server',
]
