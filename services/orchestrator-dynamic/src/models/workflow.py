"""
Modelos Pydantic para Cutover Workflow.

Define modelos para orquestração de cutover gradual (shadow mode → canary → full).
Implementa estratégia de migração segura com rollback automático.

NOTA: Este módulo usa Pydantic v2.
"""

import sys
from datetime import datetime
from enum import Enum
from typing import Any

# Python 3.10 compatibility
if sys.version_info >= (3, 11):
    from enum import _StrEnum as __StrEnum
else:

    class __StrEnum(str, Enum):
        """Polyfill para _StrEnum no Python 3.10"""


from pydantic import BaseModel, ConfigDict, Field, field_validator


class CutoverPhase(__StrEnum):
    """Fases do cutover."""

    SHADOW_MODE = "shadow_mode"
    CANARY_5 = "canary_5"
    CANARY_25 = "canary_25"
    CANARY_50 = "canary_50"
    FULL_CUTOVER = "full_cutover"
    ROLLED_BACK = "rolled_back"
    COMPLETED = "completed"
    PAUSED = "paused"


class RollbackReason(__StrEnum):
    """Motivos de rollback."""

    ERROR_RATE_EXCEEDED = "error_rate_exceeded"
    LATENCY_HIGH = "latency_high"
    SYSTEM_DOWN = "system_down"
    DATA_CORRUPTION = "data_corruption"
    MANUAL_REQUEST = "manual_request"
    BUSINESS_CRITICAL_BUG = "business_critical_bug"


class CutoverConfig(BaseModel):
    """Configuração do Cutover Workflow."""

    # URLs dos serviços
    legacy_service_url: str = Field(..., description="URL do serviço legado")
    target_service_url: str = Field(..., description="URL do serviço alvo (novo)")

    # Duração do Shadow Mode (horas)
    shadow_duration_hours: int = Field(
        default=168,
        description="Duração do shadow mode em horas (padrão: 7 dias)",
        ge=24,
        le=720,
    )

    # Estágios de Canary (% de tráfego)
    canary_stages: list[int] = Field(
        default_factory=lambda: [5, 25, 50, 100],
        description="Estágios de canary (percentual de tráfego)",
    )

    # Duração mínima de cada estágio canary (horas)
    canary_min_hours: int = Field(
        default=24,
        description="Duração mínima de cada estágio canary em horas",
        ge=1,
        le=168,
    )

    # Thresholds para rollback automático
    rollback_threshold_error_rate: float = Field(
        default=0.05,
        description="Taxa de erro para rollback automático (5%)",
        ge=0.01,
        le=0.5,
    )

    rollback_threshold_p95_latency_ms: int = Field(
        default=2000,
        description="Latência P95 para considerar rollback (ms)",
        ge=100,
        le=30000,
    )

    rollback_consecutive_minutes: int = Field(
        default=5,
        description="Minutos consecutivos acima do threshold para rollback",
        ge=1,
        le=60,
    )

    # Configurações avançadas
    enable_auto_rollback: bool = Field(default=True, description="Habilitar rollback automático")

    enable_auto_promote: bool = Field(
        default=True, description="Habilitar promoção automática de fase"
    )

    metrics_window_minutes: int = Field(
        default=15,
        description="Janela de minutos para cálculo de métricas",
        ge=5,
        le=60,
    )

    # Lista de usuários/segmentos para canary
    canary_user_segments: list[str] = Field(
        default_factory=list,
        description="Segmentos de usuários para canary (ex: beta_testers, region_us)",
    )

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("canary_stages")
    @classmethod
    def validate_canary_stages(cls, v: list[int]) -> list[int]:
        """Valida estágios de canary."""
        if not v:
            raise ValueError("canary_stages não pode ser vazio")
        if any(s < 1 or s > 100 for s in v):
            raise ValueError("Estágios devem estar entre 1 e 100")
        if v != sorted(v):
            raise ValueError("Estágios devem estar em ordem crescente")
        if 100 not in v:
            raise ValueError("Último estágio deve ser 100 (full cutover)")
        return v


class CutoverMetrics(BaseModel):
    """Métricas coletadas durante o cutover."""

    timestamp: datetime = Field(default_factory=datetime.now)
    phase: CutoverPhase

    # Métricas de erro
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Taxa de erro (0-1)")

    # Métricas de latência (ms)
    p50_latency_ms: int = Field(default=0, ge=0, description="Latência P50 em ms")
    p95_latency_ms: int = Field(default=0, ge=0, description="Latência P95 em ms")
    p99_latency_ms: int = Field(default=0, ge=0, description="Latência P99 em ms")

    # Métricas de volume
    requests_per_second: float = Field(default=0.0, ge=0.0, description="Requisições por segundo")

    # Métricas de negócio
    business_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Métricas específicas de negócio",
    )

    # Comparação legacy vs target
    legacy_p95_latency_ms: int | None = Field(
        default=None, description="Latência P95 do legado para comparação"
    )

    # Flag de anomalia detectada
    anomaly_detected: bool = Field(default=False, description="Anomalia detectada nas métricas")

    model_config = ConfigDict(use_enum_values=True)


class CutoverStatus(BaseModel):
    """Status atual do Cutover Workflow."""

    cutover_id: str = Field(..., description="ID único do cutover")
    phase: CutoverPhase = Field(default=CutoverPhase.SHADOW_MODE, description="Fase atual")

    # Tráfego
    traffic_percentage: int = Field(
        default=0, ge=0, le=100, description="Percentual de tráfego no target"
    )

    # Timestamps
    started_at: datetime = Field(default_factory=datetime.now)
    current_phase_start: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = Field(default=None, description="Data de conclusão")

    # Contadores
    phase_transitions: int = Field(default=0, description="Número de transições de fase")
    rollback_count: int = Field(default=0, description="Número de rollbacks executados")

    # Métricas atuais
    current_metrics: CutoverMetrics | None = Field(
        default=None, description="Métricas mais recentes"
    )

    # Histórico de métricas
    metrics_history: list[CutoverMetrics] = Field(
        default_factory=list, description="Histórico de métricas coletadas"
    )

    # Estado de rollback
    rollback_reason: RollbackReason | None = Field(
        default=None, description="Motivo do último rollback"
    )
    rollback_message: str | None = Field(default=None, description="Mensagem detalhada do rollback")

    # Configuração de referência
    config_snapshot: dict[str, Any] | None = Field(
        default=None, description="Snapshot da configuração usada"
    )

    # Metadados
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadados adicionais")

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("traffic_percentage")
    @classmethod
    def validate_traffic_percentage(cls, v: int, info) -> int:
        """Valida consistência entre fase e tráfego."""
        phase = info.data.get("phase")
        if phase == CutoverPhase.SHADOW_MODE and v != 0:
            raise ValueError("Shadow mode deve ter 0% de tráfego")
        if phase == CutoverPhase.FULL_CUTOVER and v != 100:
            raise ValueError("Full cutover deve ter 100% de tráfego")
        if phase == CutoverPhase.COMPLETED and v != 100:
            raise ValueError("Completed deve ter 100% de tráfego")
        if phase == CutoverPhase.ROLLED_BACK and v != 0:
            raise ValueError("Rolled back deve ter 0% de tráfego")
        return v

    def add_metrics(self, metrics: CutoverMetrics) -> None:
        """
        Adiciona métricas ao histórico e atualiza as correntes.

        Args:
            metrics: Métricas a adicionar
        """
        self.metrics_history.append(metrics)
        self.current_metrics = metrics

        # Manter histórico limitado (últimas 1000 métricas)
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]

    def get_metrics_summary(self) -> dict[str, Any]:
        """
        Retorna resumo das métricas coletadas.

        Returns:
            Dict com estatísticas agregadas
        """
        if not self.metrics_history:
            return {
                "total_samples": 0,
                "avg_error_rate": 0.0,
                "max_error_rate": 0.0,
                "avg_p95_latency_ms": 0,
            }

        error_rates = [m.error_rate for m in self.metrics_history]
        p95_latencies = [m.p95_latency_ms for m in self.metrics_history]

        return {
            "total_samples": len(self.metrics_history),
            "avg_error_rate": sum(error_rates) / len(error_rates),
            "max_error_rate": max(error_rates),
            "avg_p95_latency_ms": sum(p95_latencies) / len(p95_latencies),
            "max_p95_latency_ms": max(p95_latencies),
        }

    def should_trigger_rollback(self, config: CutoverConfig) -> tuple[bool, str | None]:
        """
        Verifica se deve ser acionado rollback baseado nas métricas.

        Args:
            config: Configuração do cutover com thresholds

        Returns:
            Tupla (should_rollback, reason)
        """
        if not self.current_metrics:
            return False, None

        metrics = self.current_metrics

        # Rollback imediato: error rate > threshold
        if metrics.error_rate > config.rollback_threshold_error_rate:
            return (
                True,
                f"Error rate {metrics.error_rate:.2%} excede threshold "
                f"{config.rollback_threshold_error_rate:.2%}",
            )

        # Rollback: latência P95 > 2x legacy (se disponível)
        if metrics.legacy_p95_latency_ms:
            latency_ratio = metrics.p95_latency_ms / metrics.legacy_p95_latency_ms
            if latency_ratio > 2.0:
                return (
                    True,
                    f"Latência P95 ({metrics.p95_latency_ms}ms) é {latency_ratio:.1f}x "
                    f"o legado ({metrics.legacy_p95_latency_ms}ms)",
                )

        # Rollback: latência P95 > threshold absoluto
        if metrics.p95_latency_ms > config.rollback_threshold_p95_latency_ms:
            return (
                True,
                f"Latência P95 ({metrics.p95_latency_ms}ms) excede threshold "
                f"({config.rollback_threshold_p95_latency_ms}ms)",
            )

        # Rollback: anomalia detectada
        if metrics.anomaly_detected:
            return True, "Anomalia detectada nas métricas"

        return False, None

    def can_promote_to_next_phase(self, config: CutoverConfig) -> tuple[bool, str | None]:
        """
        Verifica se pode promover para próxima fase.

        Args:
            config: Configuração do cutover

        Returns:
            Tupla (can_promote, reason)
        """
        import datetime as dt

        # Verificar tempo mínimo na fase atual
        time_in_phase = dt.datetime.now() - self.current_phase_start
        min_hours = (
            config.shadow_duration_hours
            if self.phase == CutoverPhase.SHADOW_MODE
            else config.canary_min_hours
        )

        if time_in_phase < dt.timedelta(hours=min_hours):
            remaining = dt.timedelta(hours=min_hours) - time_in_phase
            return False, f"Tempo mínimo não atingido. Restam {remaining}"

        # Verificar métricas se disponíveis
        if self.metrics_history:
            summary = self.get_metrics_summary()

            # Error rate deve ser menor que threshold
            if summary["avg_error_rate"] > config.rollback_threshold_error_rate / 2:
                return (
                    False,
                    f"Error rate médio {summary['avg_error_rate']:.2%} acima do aceitável",
                )

        return True, None


class CutoverEvent(BaseModel):
    """Evento emitido durante o cutover."""

    event_id: str = Field(..., description="ID único do evento")
    cutover_id: str = Field(..., description="ID do cutover")
    event_type: str = Field(..., description="Tipo do evento")
    timestamp: datetime = Field(default_factory=datetime.now)

    # Dados do evento
    phase: CutoverPhase
    previous_phase: CutoverPhase | None = None

    # Resultado
    success: bool = True
    message: str | None = None
    error_details: dict[str, Any] | None = None

    # Contexto
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)
