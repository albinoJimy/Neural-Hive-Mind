"""Clientes de integração para Optimizer Agents."""

from src.clients.analyst_agents_grpc_client import AnalystAgentsGrpcClient
from src.clients.argo_workflows_client import ArgoWorkflowsClient
from src.clients.clickhouse_client import ClickHouseClient
from src.clients.consensus_engine_grpc_client import ConsensusEngineGrpcClient
from src.clients.mlflow_client import MLflowClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.orchestrator_grpc_client import OrchestratorGrpcClient
from src.clients.queen_agent_grpc_client import QueenAgentGrpcClient
from src.clients.redis_client import RedisClient
from src.clients.service_registry_client import ServiceRegistryClient

__all__ = [
    "AnalystAgentsGrpcClient",
    "ArgoWorkflowsClient",
    "ClickHouseClient",
    "ConsensusEngineGrpcClient",
    "MLflowClient",
    "MongoDBClient",
    "OrchestratorGrpcClient",
    "QueenAgentGrpcClient",
    "RedisClient",
    "ServiceRegistryClient",
]
