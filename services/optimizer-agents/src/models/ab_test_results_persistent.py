"""
Modelo de persistência para resultados de A/B Testing.

Define a estrutura para persistir ABTestResults no MongoDB,
incluindo conversão de/para dicionário e serialização.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
UTC = timezone.utc  # type: ignore
from typing import Any


@dataclass
class ABTestResultsPersistent:
    """
    Modelo de persistência para resultados de A/B Testing.

    Este modelo representa o documento MongoDB na coleção `ab_test_results`,
    com todos os campos necessários para reconstruir ABTestResults.
    """

    # Identificação
    experiment_id: str
    experiment_name: str

    # Timestamps
    created_at: datetime
    completed_at: datetime | None = None
    analysis_timestamp: datetime | None = None

    # Status
    status: str = "running"  # "running", "completed", "aborted"

    # Tamanhos de amostra
    control_size: int = 0
    treatment_size: int = 0

    # Análises de métricas
    primary_metrics_analysis: list[dict] = field(default_factory=list)
    secondary_metrics_analysis: list[dict] = field(default_factory=list)
    bayesian_analysis: list[dict] | None = None

    # Guardrails
    guardrails_status: dict = field(default_factory=dict)

    # Decisão estatística
    statistical_recommendation: str = "INCONCLUSIVE"  # "APPLY", "REJECT", "INCONCLUSIVE"
    confidence_level: float = 0.0

    # Early stopping
    early_stopped: bool = False
    early_stop_reason: str | None = None

    # Metadados adicionais
    metadata: dict = field(default_factory=dict)

    def to_mongo_dict(self) -> dict[str, Any]:
        """
        Converter para dicionário pronto para inserção no MongoDB.

        Returns:
            Dicionário com campos serializáveis para MongoDB
        """
        doc = asdict(self)

        # Converter datetime para ISO format string se necessário
        if isinstance(self.created_at, datetime):
            doc["created_at"] = self.created_at.isoformat()
        if self.completed_at and isinstance(self.completed_at, datetime):
            doc["completed_at"] = self.completed_at.isoformat()
        if self.analysis_timestamp and isinstance(self.analysis_timestamp, datetime):
            doc["analysis_timestamp"] = self.analysis_timestamp.isoformat()

        return doc

    @classmethod
    def from_ab_test_results(
        cls,
        experiment_name: str,
        results: "ABTestResults",
        completed_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> "ABTestResultsPersistent":
        """
        Criar instância de persistência a partir de ABTestResults.

        Args:
            experiment_name: Nome do experimento
            results: Resultados do A/B test (ABTestResults do engine)
            completed_at: Timestamp de conclusão (opcional)
            metadata: Metadados adicionais

        Returns:
            Instância de ABTestResultsPersistent
        """
        return cls(
            experiment_id=results.experiment_id,
            experiment_name=experiment_name,
            created_at=results.analysis_timestamp,
            completed_at=completed_at or datetime.now(UTC),
            analysis_timestamp=results.analysis_timestamp,
            status=results.status,
            control_size=results.control_size,
            treatment_size=results.treatment_size,
            primary_metrics_analysis=results.primary_metrics_analysis,
            secondary_metrics_analysis=results.secondary_metrics_analysis,
            bayesian_analysis=results.bayesian_analysis,
            guardrails_status=results.guardrails_status,
            statistical_recommendation=results.statistical_recommendation,
            confidence_level=results.confidence_level,
            early_stopped=results.early_stopped,
            early_stop_reason=results.early_stop_reason,
            metadata=metadata or {},
        )

    @classmethod
    def from_mongo_dict(cls, doc: dict[str, Any]) -> "ABTestResultsPersistent":
        """
        Criar instância a partir de documento MongoDB.

        Args:
            doc: Documento recuperado do MongoDB

        Returns:
            Instância de ABTestResultsPersistent
        """
        # Converter ISO strings para datetime
        created_at = doc.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        completed_at = doc.get("completed_at")
        if completed_at and isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)

        analysis_timestamp = doc.get("analysis_timestamp")
        if analysis_timestamp and isinstance(analysis_timestamp, str):
            analysis_timestamp = datetime.fromisoformat(analysis_timestamp)

        return cls(
            experiment_id=doc["experiment_id"],
            experiment_name=doc["experiment_name"],
            created_at=created_at,
            completed_at=completed_at,
            analysis_timestamp=analysis_timestamp,
            status=doc.get("status", "running"),
            control_size=doc.get("control_size", 0),
            treatment_size=doc.get("treatment_size", 0),
            primary_metrics_analysis=doc.get("primary_metrics_analysis", []),
            secondary_metrics_analysis=doc.get("secondary_metrics_analysis", []),
            bayesian_analysis=doc.get("bayesian_analysis"),
            guardrails_status=doc.get("guardrails_status", {}),
            statistical_recommendation=doc.get("statistical_recommendation", "INCONCLUSIVE"),
            confidence_level=doc.get("confidence_level", 0.0),
            early_stopped=doc.get("early_stopped", False),
            early_stop_reason=doc.get("early_stop_reason"),
            metadata=doc.get("metadata", {}),
        )

    def to_summary_dict(self) -> dict[str, Any]:
        """
        Retornar resumo dos resultados para exibição em listagens.

        Returns:
            Dicionário com campos principais
        """
        return {
            "experiment_id": self.experiment_id,
            "experiment_name": self.experiment_name,
            "status": self.status,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            "recommendation": self.statistical_recommendation,
            "confidence": self.confidence_level,
            "control_size": self.control_size,
            "treatment_size": self.treatment_size,
            "total_sample_size": self.control_size + self.treatment_size,
            "early_stopped": self.early_stopped,
        }
