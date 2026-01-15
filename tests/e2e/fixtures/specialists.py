"""
Fixtures para Specialists gRPC em testes E2E.

Fornece canais e stubs gRPC para os 5 specialists do Consensus Engine.
"""

from typing import Dict

import grpc
import pytest


# Namespace Kubernetes dos specialists
SPECIALISTS_NAMESPACE = "neural-hive-specialists"

# Configuração dos 5 specialists
SPECIALIST_CONFIGS = {
    "technical": {
        "host": f"specialist-technical.{SPECIALISTS_NAMESPACE}.svc.cluster.local",
        "port": 50051,
    },
    "business": {
        "host": f"specialist-business.{SPECIALISTS_NAMESPACE}.svc.cluster.local",
        "port": 50051,
    },
    "architecture": {
        "host": f"specialist-architecture.{SPECIALISTS_NAMESPACE}.svc.cluster.local",
        "port": 50051,
    },
    "behavior": {
        "host": f"specialist-behavior.{SPECIALISTS_NAMESPACE}.svc.cluster.local",
        "port": 50051,
    },
    "evolution": {
        "host": f"specialist-evolution.{SPECIALISTS_NAMESPACE}.svc.cluster.local",
        "port": 50051,
    },
}


@pytest.fixture(scope="session")
async def specialist_grpc_channels() -> Dict[str, grpc.aio.Channel]:
    """
    Canais gRPC para os 5 specialists.

    Retorna dict com canais conectados a cada specialist.
    """
    channels: Dict[str, grpc.aio.Channel] = {}

    for specialist_type, config in SPECIALIST_CONFIGS.items():
        target = f"{config['host']}:{config['port']}"
        channels[specialist_type] = grpc.aio.insecure_channel(
            target,
            options=[
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.keepalive_permit_without_calls", True),
            ],
        )

    yield channels

    # Cleanup: fecha todos os canais
    for channel in channels.values():
        await channel.close()


@pytest.fixture(scope="session")
async def specialist_stubs(specialist_grpc_channels: Dict[str, grpc.aio.Channel]):
    """
    Stubs gRPC para os 5 specialists.

    Retorna dict com stubs para invocar métodos dos specialists.
    Tenta importar stubs gerados, usa placeholder se não disponível.
    """
    stubs: Dict[str, object] = {}

    try:
        # Tenta importar stubs gerados do protobuf
        from libs.proto import specialist_pb2_grpc

        for specialist_type, channel in specialist_grpc_channels.items():
            stubs[specialist_type] = specialist_pb2_grpc.SpecialistServiceStub(channel)
    except ImportError:
        # Placeholder se stubs não estiverem disponíveis
        # Retorna os canais diretamente para testes que não precisam de stubs
        for specialist_type, channel in specialist_grpc_channels.items():
            stubs[specialist_type] = channel

    return stubs


@pytest.fixture(scope="function")
def specialist_endpoints() -> Dict[str, str]:
    """
    Endpoints dos specialists como strings.

    Útil para configurações que precisam apenas das URLs.
    """
    return {
        specialist_type: f"{config['host']}:{config['port']}"
        for specialist_type, config in SPECIALIST_CONFIGS.items()
    }


@pytest.fixture(scope="function")
def all_specialist_types() -> list:
    """Lista de todos os tipos de specialists."""
    return ["technical", "business", "architecture", "behavior", "evolution"]
