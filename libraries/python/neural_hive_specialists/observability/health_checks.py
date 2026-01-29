"""
SpecialistHealthChecker: Health checks avançados para especialistas e dependências.

Verifica saúde de MLflow, MongoDB, feature extraction, circuit breakers,
e exporta status detalhado para endpoints de health check.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import structlog
import asyncio
from enum import Enum
import mlflow
from mlflow.tracking import MlflowClient

logger = structlog.get_logger(__name__)


class HealthStatus(str, Enum):
    """Status de saúde de um componente."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentHealth:
    """Representa saúde de um componente individual."""

    def __init__(
        self,
        component_name: str,
        status: HealthStatus,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        latency_ms: Optional[float] = None,
    ):
        self.component_name = component_name
        self.status = status
        self.message = message or ""
        self.details = details or {}
        self.latency_ms = latency_ms
        self.checked_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "component": self.component_name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at.isoformat(),
        }


class SpecialistHealthChecker:
    """Verificador de saúde de especialistas e dependências."""

    def __init__(self, config: Dict[str, Any], specialist_type: str):
        """
        Inicializa health checker.

        Args:
            config: Configuração do especialista
            specialist_type: Tipo do especialista
        """
        self.config = config
        self.specialist_type = specialist_type

        # Cache de status (TTL: 30s)
        self._health_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 30

        logger.info(
            "SpecialistHealthChecker initialized", specialist_type=specialist_type
        )

    async def check_all_health(self) -> Dict[str, Any]:
        """
        Verifica saúde de todos os componentes.

        Returns:
            Dicionário com status de saúde agregado
        """
        # Verificar cache
        if self._is_cache_valid():
            logger.debug("Returning cached health status")
            return self._health_cache

        try:
            logger.info("Starting comprehensive health check")

            # Executar checks em paralelo
            results = await asyncio.gather(
                self._check_mongodb_health(),
                self._check_mlflow_health(),
                self._check_feature_extraction_health(),
                self._check_circuit_breakers_health(),
                self._check_ledger_health(),
                return_exceptions=True,
            )

            # Processar resultados
            components = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error("Health check failed", error=str(result))
                    components.append(
                        ComponentHealth(
                            component_name="unknown",
                            status=HealthStatus.UNHEALTHY,
                            message=str(result),
                        )
                    )
                elif isinstance(result, ComponentHealth):
                    components.append(result)

            # Determinar status geral
            overall_status = self._determine_overall_status(components)

            health_report = {
                "specialist_type": self.specialist_type,
                "overall_status": overall_status.value,
                "checked_at": datetime.utcnow().isoformat(),
                "components": [comp.to_dict() for comp in components],
                "summary": self._generate_summary(components),
            }

            # Atualizar cache
            self._health_cache = health_report
            self._cache_timestamp = datetime.utcnow()

            logger.info(
                "Health check completed",
                overall_status=overall_status.value,
                components_count=len(components),
            )

            return health_report

        except Exception as e:
            logger.error("Failed to check health", error=str(e), exc_info=True)
            return {
                "specialist_type": self.specialist_type,
                "overall_status": HealthStatus.UNHEALTHY.value,
                "checked_at": datetime.utcnow().isoformat(),
                "error": str(e),
            }

    async def _check_mongodb_health(self) -> ComponentHealth:
        """Verifica saúde do MongoDB."""
        start_time = datetime.utcnow()

        try:
            client = MongoClient(
                self.config.get("mongodb_uri"), serverSelectionTimeoutMS=5000
            )

            # Ping MongoDB
            client.admin.command("ping")

            # Verificar database
            db = client[self.config.get("mongodb_database", "neural_hive")]
            collections = db.list_collection_names()

            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Verificar tamanho do ledger
            ledger_size = db["cognitive_ledger"].count_documents({})

            status = HealthStatus.HEALTHY
            message = "MongoDB operational"

            # Degraded se latência alta
            if latency_ms > 1000:
                status = HealthStatus.DEGRADED
                message = "MongoDB slow response"

            return ComponentHealth(
                component_name="mongodb",
                status=status,
                message=message,
                details={
                    "collections_count": len(collections),
                    "ledger_documents": ledger_size,
                },
                latency_ms=latency_ms,
            )

        except PyMongoError as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="mongodb",
                status=HealthStatus.UNHEALTHY,
                message=f"MongoDB error: {str(e)}",
                latency_ms=latency_ms,
            )

    async def _check_mlflow_health(self) -> ComponentHealth:
        """Verifica saúde do MLflow."""
        start_time = datetime.utcnow()

        try:
            mlflow_uri = self.config.get("mlflow_tracking_uri")

            if not mlflow_uri:
                return ComponentHealth(
                    component_name="mlflow",
                    status=HealthStatus.UNKNOWN,
                    message="MLflow not configured",
                )

            # Configurar MLflow
            mlflow.set_tracking_uri(mlflow_uri)

            # Verificar conexão
            client = MlflowClient()
            experiments = client.search_experiments()

            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Verificar modelo registrado
            model_name = self.config.get("mlflow_model_name")
            model_status = "not_configured"

            if model_name:
                try:
                    registered_model = client.get_registered_model(model_name)
                    latest_versions = client.get_latest_versions(
                        model_name, stages=["Production"]
                    )

                    model_status = "registered"
                    if latest_versions:
                        model_status = "production_ready"

                except Exception:
                    model_status = "not_found"

            status = HealthStatus.HEALTHY
            message = "MLflow operational"

            if model_status == "not_found":
                status = HealthStatus.DEGRADED
                message = "MLflow operational but model not found"

            return ComponentHealth(
                component_name="mlflow",
                status=status,
                message=message,
                details={
                    "experiments_count": len(experiments),
                    "model_name": model_name,
                    "model_status": model_status,
                },
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="mlflow",
                status=HealthStatus.UNHEALTHY,
                message=f"MLflow error: {str(e)}",
                latency_ms=latency_ms,
            )

    async def _check_feature_extraction_health(self) -> ComponentHealth:
        """Verifica saúde do sistema de extração de features."""
        start_time = datetime.utcnow()

        try:
            # Verificar se feature extraction está habilitado
            enabled = self.config.get("enable_feature_extraction", True)

            if not enabled:
                return ComponentHealth(
                    component_name="feature_extraction",
                    status=HealthStatus.UNKNOWN,
                    message="Feature extraction disabled",
                )

            # Verificar ontologias carregadas
            ontology_path = self.config.get("ontology_path")

            status = HealthStatus.HEALTHY
            message = "Feature extraction operational"
            details = {}

            if ontology_path:
                import os

                if os.path.exists(ontology_path):
                    details["ontology_loaded"] = True
                else:
                    status = HealthStatus.DEGRADED
                    message = "Ontology file not found"
                    details["ontology_loaded"] = False

            # Verificar embeddings model
            embeddings_model = self.config.get(
                "embeddings_model", "paraphrase-multilingual-MiniLM-L12-v2"
            )
            details["embeddings_model"] = embeddings_model

            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="feature_extraction",
                status=status,
                message=message,
                details=details,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="feature_extraction",
                status=HealthStatus.UNHEALTHY,
                message=f"Feature extraction error: {str(e)}",
                latency_ms=latency_ms,
            )

    async def _check_circuit_breakers_health(self) -> ComponentHealth:
        """Verifica saúde dos circuit breakers."""
        start_time = datetime.utcnow()

        try:
            enabled = self.config.get("enable_circuit_breaker", True)

            if not enabled:
                return ComponentHealth(
                    component_name="circuit_breakers",
                    status=HealthStatus.UNKNOWN,
                    message="Circuit breakers disabled",
                )

            # Por enquanto, apenas verificar configuração
            # Em produção, verificaria o estado atual dos breakers
            failure_threshold = self.config.get("circuit_breaker_failure_threshold", 5)
            recovery_timeout = self.config.get("circuit_breaker_recovery_timeout", 60)

            status = HealthStatus.HEALTHY
            message = "Circuit breakers operational"

            details = {
                "failure_threshold": failure_threshold,
                "recovery_timeout_seconds": recovery_timeout,
            }

            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="circuit_breakers",
                status=status,
                message=message,
                details=details,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="circuit_breakers",
                status=HealthStatus.UNHEALTHY,
                message=f"Circuit breakers error: {str(e)}",
                latency_ms=latency_ms,
            )

    async def _check_ledger_health(self) -> ComponentHealth:
        """Verifica saúde do ledger cognitivo."""
        start_time = datetime.utcnow()

        try:
            client = MongoClient(
                self.config.get("mongodb_uri"), serverSelectionTimeoutMS=5000
            )

            db = client[self.config.get("mongodb_database", "neural_hive")]
            collection = db["cognitive_ledger"]

            # Verificar documentos recentes
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            recent_count = collection.count_documents(
                {
                    "evaluated_at": {"$gte": cutoff_time},
                    "specialist_type": self.specialist_type,
                }
            )

            # Verificar documentos bufferizados
            buffered_count = collection.count_documents(
                {
                    "evaluated_at": {"$gte": cutoff_time},
                    "specialist_type": self.specialist_type,
                    "buffered": True,
                }
            )

            buffered_rate = (
                (buffered_count / recent_count * 100) if recent_count > 0 else 0.0
            )

            status = HealthStatus.HEALTHY
            message = "Ledger operational"

            # Degraded se alta taxa de bufferização
            if buffered_rate > 20:
                status = HealthStatus.DEGRADED
                message = f"High buffer rate: {buffered_rate:.1f}%"

            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="ledger",
                status=status,
                message=message,
                details={
                    "recent_opinions_24h": recent_count,
                    "buffered_count": buffered_count,
                    "buffered_rate_pct": buffered_rate,
                },
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ComponentHealth(
                component_name="ledger",
                status=HealthStatus.UNHEALTHY,
                message=f"Ledger error: {str(e)}",
                latency_ms=latency_ms,
            )

    def _determine_overall_status(
        self, components: List[ComponentHealth]
    ) -> HealthStatus:
        """
        Determina status geral baseado nos componentes.

        Args:
            components: Lista de saúde dos componentes

        Returns:
            Status geral
        """
        if not components:
            return HealthStatus.UNKNOWN

        # Se algum componente crítico está UNHEALTHY, sistema é UNHEALTHY
        critical_components = {"mongodb", "ledger"}

        for comp in components:
            if comp.component_name in critical_components:
                if comp.status == HealthStatus.UNHEALTHY:
                    return HealthStatus.UNHEALTHY

        # Se algum componente está DEGRADED, sistema é DEGRADED
        for comp in components:
            if comp.status == HealthStatus.DEGRADED:
                return HealthStatus.DEGRADED

        # Se algum componente está UNHEALTHY (não crítico), sistema é DEGRADED
        for comp in components:
            if comp.status == HealthStatus.UNHEALTHY:
                return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    def _generate_summary(self, components: List[ComponentHealth]) -> Dict[str, Any]:
        """
        Gera resumo de saúde.

        Args:
            components: Lista de componentes

        Returns:
            Resumo estatístico
        """
        healthy_count = sum(1 for c in components if c.status == HealthStatus.HEALTHY)
        degraded_count = sum(1 for c in components if c.status == HealthStatus.DEGRADED)
        unhealthy_count = sum(
            1 for c in components if c.status == HealthStatus.UNHEALTHY
        )

        avg_latency = (
            sum(c.latency_ms for c in components if c.latency_ms) / len(components)
            if components
            else 0.0
        )

        return {
            "total_components": len(components),
            "healthy_components": healthy_count,
            "degraded_components": degraded_count,
            "unhealthy_components": unhealthy_count,
            "avg_latency_ms": avg_latency,
        }

    def _is_cache_valid(self) -> bool:
        """Verifica se cache de saúde ainda é válido."""
        if not self._health_cache or not self._cache_timestamp:
            return False

        age = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return age < self._cache_ttl_seconds
