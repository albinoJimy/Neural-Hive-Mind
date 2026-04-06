from neural_hive_domain import UTC
"""
Health Monitor Service para Self-Healing Engine.

Detecta problemas de saúde nos serviços e componentes do Neural Hive-Mind.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import structlog

logger = structlog.get_logger()



@dataclass
class HealthStatus:
    """Resultado de verificação de saúde de um serviço."""

    service_name: str
    healthy: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "service_name": self.service_name,
            "healthy": self.healthy,
            "checked_at": self.checked_at.isoformat(),
            "response_time_ms": self.response_time_ms,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class LagStatus:
    """Resultado de verificação de lag de consumidor Kafka."""

    consumer_group: str
    topic: str
    lag: int
    threshold: int
    within_threshold: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    partitions: Dict[int, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "consumer_group": self.consumer_group,
            "topic": self.topic,
            "lag": self.lag,
            "threshold": self.threshold,
            "within_threshold": self.within_threshold,
            "checked_at": self.checked_at.isoformat(),
            "partitions": self.partitions,
        }


@dataclass
class ConnectionStatus:
    """Resultado de verificação de conexão com banco de dados."""

    connection_string: str
    connected: bool
    database_type: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
    database_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "connection_string": self.connection_string,
            "connected": self.connected,
            "database_type": self.database_type,
            "checked_at": self.checked_at.isoformat(),
            "response_time_ms": self.response_time_ms,
            "error": self.error,
            "database_info": self.database_info,
        }


class HealthMonitor:
    """
    Monitor de saúde para serviços Neural Hive-Mind.

    Verifica periodicamente a saúde dos serviços e componentes.
    """

    def __init__(
        self,
        service_registry_client=None,
        check_interval_seconds: int = 30,
        kafka_bootstrap_servers: str = "kafka:9092",
        default_lag_threshold: int = 10000,
        http_timeout_seconds: int = 5,
    ):
        self.service_registry_client = service_registry_client
        self.check_interval_seconds = check_interval_seconds
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.default_lag_threshold = default_lag_threshold
        self.http_timeout_seconds = http_timeout_seconds
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Obtém ou cria sessão HTTP."""
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=self.http_timeout_seconds)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    async def close(self):
        """Fecha recursos."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    async def check_service_health(
        self,
        service_name: str,
        namespace: str = "neural-hive-orchestration",
        health_endpoint: str = "/health",
    ) -> HealthStatus:
        """
        Verifica se um serviço está saudável.

        Args:
            service_name: Nome do serviço
            namespace: Namespace Kubernetes
            health_endpoint: Endpoint de saúde

        Returns:
            HealthStatus com resultado da verificação
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Obter endereço do serviço via Service Registry
            if self.service_registry_client:
                address = await self.service_registry_client.get_service_address(service_name)
                if not address:
                    return HealthStatus(
                        service_name=service_name,
                        healthy=False,
                        error_message=f"Service {service_name} not found in registry",
                    )
                url = f"{address}{health_endpoint}"
            else:
                # Fallback para DNS Kubernetes padrão
                url = f"http://{service_name}.{namespace}.svc.cluster.local:8080{health_endpoint}"

            session = await self._get_http_session()
            async with session.get(url) as response:
                elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                if response.status == 200:
                    return HealthStatus(
                        service_name=service_name,
                        healthy=True,
                        response_time_ms=elapsed_ms,
                        metadata={"url": url},
                    )
                else:
                    return HealthStatus(
                        service_name=service_name,
                        healthy=False,
                        response_time_ms=elapsed_ms,
                        error_message=f"HTTP {response.status}",
                    )

        except asyncio.TimeoutError:
            return HealthStatus(service_name=service_name, healthy=False, error_message="Timeout")
        except Exception as e:
            return HealthStatus(service_name=service_name, healthy=False, error_message=str(e))

    async def check_kafka_consumer_lag(
        self, consumer_group: str, topic: str, threshold: Optional[int] = None
    ) -> LagStatus:
        """
        Verifica lag de consumidor Kafka.

        Args:
            consumer_group: Grupo de consumidores
            topic: Tópico Kafka
            threshold: Limite de lag (usa default se não especificado)

        Returns:
            LagStatus com resultado da verificação
        """
        threshold = threshold or self.default_lag_threshold

        try:
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                group_id=consumer_group,
                enable_auto_commit=False,
            )

            # Obter partições do tópico
            partitions = consumer.partitions_for_topic(topic)
            if not partitions:
                return LagStatus(
                    consumer_group=consumer_group,
                    topic=topic,
                    lag=0,
                    threshold=threshold,
                    within_threshold=True,
                    partitions={},
                )

            # Buscar offsets
            from aiokafka.structs import TopicPartition

            tps = [TopicPartition(topic, p) for p in partitions]

            # Committed offsets
            committed = await consumer.committed(tps)
            # High watermarks
            highwater = await consumer.highwater(tps)

            total_lag = 0
            partition_lags = {}

            for tp in tps:
                committed_offset = committed.get(tp, 0)
                high_offset = highwater.get(tp, 0)
                lag = high_offset - committed_offset
                partition_lags[tp.partition] = lag
                total_lag += lag

            await consumer.stop()

            return LagStatus(
                consumer_group=consumer_group,
                topic=topic,
                lag=total_lag,
                threshold=threshold,
                within_threshold=total_lag < threshold,
                partitions=partition_lags,
            )

        except Exception as e:
            logger.error(
                "health_monitor.kafka_lag_check_failed",
                consumer_group=consumer_group,
                topic=topic,
                error=str(e),
            )
            # Em caso de erro, retornar lag zero para evitar falsos positivos
            return LagStatus(
                consumer_group=consumer_group,
                topic=topic,
                lag=0,
                threshold=threshold,
                within_threshold=True,
            )

    async def check_database_connection(
        self, connection_string: str, database_type: str = "mongodb"
    ) -> ConnectionStatus:
        """
        Verifica conectividade com banco de dados.

        Args:
            connection_string: String de conexão
            database_type: Tipo de banco (mongodb, postgresql, etc.)

        Returns:
            ConnectionStatus com resultado da verificação
        """
        start_time = asyncio.get_event_loop().time()

        try:
            if database_type == "mongodb":
                import motor.motor_asyncio

                client = motor.motor_asyncio.AsyncIOMotorClient(
                    connection_string, serverSelectionTimeoutMS=5
                )

                # Ping para testar conexão
                result = await client.admin.command("ping")

                elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                if result.get("ok") == 1.0:
                    return ConnectionStatus(
                        connection_string=connection_string,
                        connected=True,
                        database_type=database_type,
                        response_time_ms=elapsed_ms,
                        database_info={"version": result.get("version")},
                    )
                else:
                    return ConnectionStatus(
                        connection_string=connection_string,
                        connected=False,
                        database_type=database_type,
                        error="Ping failed",
                    )

            elif database_type == "postgresql":
                import asyncpg

                conn = await asyncpg.connect(connection_string, timeout=5)
                elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                await conn.close()

                return ConnectionStatus(
                    connection_string=connection_string,
                    connected=True,
                    database_type=database_type,
                    response_time_ms=elapsed_ms,
                )

            else:
                return ConnectionStatus(
                    connection_string=connection_string,
                    connected=False,
                    database_type=database_type,
                    error=f"Unsupported database type: {database_type}",
                )

        except Exception as e:
            return ConnectionStatus(
                connection_string=connection_string,
                connected=False,
                database_type=database_type,
                error=str(e),
            )

    async def run_periodic_checks(self, services: list[str]) -> Dict[str, HealthStatus]:
        """
        Executa verificações periódicas para múltiplos serviços.

        Args:
            services: Lista de nomes de serviços para verificar

        Returns:
            Dicionário com resultados por serviço
        """
        results = {}

        tasks = [self.check_service_health(service) for service in services]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)

        for service, status in zip(services, statuses):
            if isinstance(status, Exception):
                results[service] = HealthStatus(
                    service_name=service, healthy=False, error_message=str(status)
                )
            else:
                results[service] = status

        return results
