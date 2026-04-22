"""
Neural Hive-Mind Infrastructure Library

Biblioteca central com configurações base partilhadas por todos os serviços.
Elimina duplicação de código e garante consistência em toda a plataforma.
"""

from .settings import (
    BaseInfrastructureSettings,
    GRPCSettings,
    KafkaSettings,
    MongoDBSettings,
    ObservabilitySettings,
    OpenTelemetrySettings,
    RedisSettings,
    SPIFFESettings,
    VaultSettings,
    get_settings,
)

__all__ = [
    "BaseInfrastructureSettings",
    "KafkaSettings",
    "MongoDBSettings",
    "RedisSettings",
    "OpenTelemetrySettings",
    "GRPCSettings",
    "SPIFFESettings",
    "VaultSettings",
    "ObservabilitySettings",
    "get_settings",
]

__version__ = "1.0.0"
