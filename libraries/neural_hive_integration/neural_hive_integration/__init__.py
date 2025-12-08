"""
Neural Hive Integration Library

Provides unified clients and orchestration for Phase 2 Flow C integration.
"""

__version__ = "1.1.1"

from neural_hive_integration.clients.orchestrator_client import OrchestratorClient
from neural_hive_integration.clients.service_registry_client import ServiceRegistryClient
from neural_hive_integration.clients.execution_ticket_client import ExecutionTicketClient
from neural_hive_integration.clients.queen_agent_client import QueenAgentClient
from neural_hive_integration.clients.worker_agent_client import WorkerAgentClient
from neural_hive_integration.clients.code_forge_client import CodeForgeClient
from neural_hive_integration.clients.sla_management_client import SLAManagementClient
from neural_hive_integration.orchestration.flow_c_orchestrator import FlowCOrchestrator
from neural_hive_integration.models.flow_c_context import FlowCContext, FlowCStep, FlowCResult

__all__ = [
    "OrchestratorClient",
    "ServiceRegistryClient",
    "ExecutionTicketClient",
    "QueenAgentClient",
    "WorkerAgentClient",
    "CodeForgeClient",
    "SLAManagementClient",
    "FlowCOrchestrator",
    "FlowCContext",
    "FlowCStep",
    "FlowCResult",
]
