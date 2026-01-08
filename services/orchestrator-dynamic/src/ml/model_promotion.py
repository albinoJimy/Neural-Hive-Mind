"""
Sistema de Promoção de Modelos com Canary Deployment.

Implementa promoção segura de modelos ML com:
- Validação pré-promoção
- Canary deployment com traffic splitting
- Rollback automático baseado em métricas
- Auditoria de promoções
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


class PromotionStage(str, Enum):
    """Estágios de promoção."""
    PENDING = "pending"
    VALIDATING = "validating"
    CANARY = "canary"
    ROLLING_OUT = "rolling_out"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class PromotionResult(str, Enum):
    """Resultados possíveis de promoção."""
    SUCCESS = "success"
    FAILED_VALIDATION = "failed_validation"
    FAILED_CANARY = "failed_canary"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


@dataclass
class PromotionConfig:
    """Configuração de promoção."""
    canary_enabled: bool = True
    canary_traffic_pct: float = 10.0
    canary_duration_minutes: int = 30
    mae_threshold_pct: float = 15.0
    precision_threshold: float = 0.75
    auto_rollback_enabled: bool = True
    rollback_mae_increase_pct: float = 20.0


@dataclass
class PromotionRequest:
    """Representa uma solicitação de promoção."""
    request_id: str
    model_name: str
    source_version: str
    target_stage: str = "Production"
    initiated_by: str = "system"
    config: PromotionConfig = field(default_factory=PromotionConfig)
    created_at: datetime = field(default_factory=datetime.utcnow)
    stage: PromotionStage = PromotionStage.PENDING
    result: Optional[PromotionResult] = None
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'request_id': self.request_id,
            'model_name': self.model_name,
            'source_version': self.source_version,
            'target_stage': self.target_stage,
            'initiated_by': self.initiated_by,
            'created_at': self.created_at.isoformat(),
            'stage': self.stage.value,
            'result': self.result.value if self.result else None,
            'error_message': self.error_message,
            'metrics': self.metrics
        }


class ModelPromotionManager:
    """
    Gerenciador de promoção de modelos.

    Funcionalidades:
    - Validação pré-promoção (métricas, estatísticas, business rules)
    - Canary deployment com split de tráfego
    - Monitoramento durante canary
    - Rollback automático se métricas degradarem
    - Auditoria completa de promoções
    """

    def __init__(
        self,
        config,
        model_registry,
        model_validator,
        continuous_validator=None,
        mongodb_client=None,
        metrics=None
    ):
        """
        Args:
            config: Configuração do orchestrator
            model_registry: ModelRegistry instance
            model_validator: ModelValidator instance
            continuous_validator: ContinuousValidator instance (opcional)
            mongodb_client: Cliente MongoDB (opcional)
            metrics: OrchestratorMetrics (opcional)
        """
        self.config = config
        self.model_registry = model_registry
        self.model_validator = model_validator
        self.continuous_validator = continuous_validator
        self.mongodb_client = mongodb_client
        self.metrics = metrics
        self.logger = logger.bind(component="model_promotion")

        # Configuração de promoção
        self.default_config = PromotionConfig(
            canary_enabled=getattr(config, 'ml_canary_enabled', True),
            canary_traffic_pct=getattr(config, 'ml_canary_traffic_percentage', 10.0),
            canary_duration_minutes=getattr(config, 'ml_canary_duration_minutes', 30),
            mae_threshold_pct=getattr(config, 'ml_validation_mae_threshold', 0.15) * 100,
            precision_threshold=getattr(config, 'ml_validation_precision_threshold', 0.75),
            auto_rollback_enabled=getattr(config, 'ml_auto_rollback_enabled', True),
            rollback_mae_increase_pct=getattr(config, 'ml_rollback_mae_increase_pct', 20.0)
        )

        # Promoções ativas
        self._active_promotions: Dict[str, PromotionRequest] = {}

        # Histórico de promoções
        self._promotion_history: List[PromotionRequest] = []

        # Canary state
        self._canary_traffic_split: Dict[str, float] = {}

    async def promote_model(
        self,
        model_name: str,
        version: str,
        target_stage: str = "Production",
        initiated_by: str = "system",
        skip_canary: bool = False,
        config_overrides: Optional[Dict[str, Any]] = None
    ) -> PromotionRequest:
        """
        Inicia processo de promoção de modelo.

        Args:
            model_name: Nome do modelo
            version: Versão a promover
            target_stage: Stage de destino (default: Production)
            initiated_by: Quem iniciou a promoção
            skip_canary: Se True, pula fase canary
            config_overrides: Overrides de configuração

        Returns:
            PromotionRequest com status
        """
        # Criar request
        request_id = f"promo_{model_name}_{version}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        config = self.default_config
        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        if skip_canary:
            config.canary_enabled = False

        request = PromotionRequest(
            request_id=request_id,
            model_name=model_name,
            source_version=version,
            target_stage=target_stage,
            initiated_by=initiated_by,
            config=config
        )

        self._active_promotions[request_id] = request

        self.logger.info(
            "promotion_initiated",
            request_id=request_id,
            model_name=model_name,
            version=version,
            target_stage=target_stage
        )

        # Executar promoção em background
        asyncio.create_task(self._execute_promotion(request))

        return request

    async def _execute_promotion(self, request: PromotionRequest) -> None:
        """Executa o pipeline de promoção."""
        try:
            # 1. Validação pré-promoção
            request.stage = PromotionStage.VALIDATING
            validation_passed = await self._run_pre_promotion_validation(request)

            if not validation_passed:
                request.stage = PromotionStage.FAILED
                request.result = PromotionResult.FAILED_VALIDATION
                await self._finalize_promotion(request)
                return

            # 2. Canary deployment (se habilitado)
            if request.config.canary_enabled:
                request.stage = PromotionStage.CANARY
                canary_passed = await self._run_canary_deployment(request)

                if not canary_passed:
                    request.stage = PromotionStage.ROLLED_BACK
                    request.result = PromotionResult.FAILED_CANARY
                    await self._finalize_promotion(request)
                    return

            # 3. Rollout completo
            request.stage = PromotionStage.ROLLING_OUT
            await self._execute_full_rollout(request)

            # 4. Sucesso
            request.stage = PromotionStage.COMPLETED
            request.result = PromotionResult.SUCCESS

            await self._finalize_promotion(request)

        except Exception as e:
            self.logger.error(
                "promotion_failed",
                request_id=request.request_id,
                error=str(e)
            )
            request.stage = PromotionStage.FAILED
            request.error_message = str(e)
            await self._finalize_promotion(request)

    async def _run_pre_promotion_validation(
        self,
        request: PromotionRequest
    ) -> bool:
        """Executa validação pré-promoção."""
        self.logger.info(
            "running_pre_promotion_validation",
            request_id=request.request_id
        )

        try:
            # Carregar modelo candidato
            model = await self.model_registry.load_model(
                model_name=request.model_name,
                version=request.source_version
            )

            if model is None:
                request.error_message = "Modelo não encontrado"
                return False

            # Buscar metadados
            metadata = await self.model_registry.get_model_metadata(
                request.model_name
            )
            metrics = metadata.get('metrics', {})

            # Validar baseado no tipo de modelo
            if 'duration' in request.model_name.lower():
                mae_pct = metrics.get('mae_percentage', 100.0)
                if mae_pct > request.config.mae_threshold_pct:
                    request.error_message = (
                        f"MAE ({mae_pct:.2f}%) excede threshold "
                        f"({request.config.mae_threshold_pct:.2f}%)"
                    )
                    return False

            elif 'anomaly' in request.model_name.lower():
                precision = metrics.get('precision', 0.0)
                if precision < request.config.precision_threshold:
                    request.error_message = (
                        f"Precision ({precision:.2f}) abaixo do threshold "
                        f"({request.config.precision_threshold:.2f})"
                    )
                    return False

            request.metrics['pre_validation'] = metrics

            self.logger.info(
                "pre_promotion_validation_passed",
                request_id=request.request_id,
                metrics=metrics
            )

            return True

        except Exception as e:
            request.error_message = f"Erro na validação: {str(e)}"
            return False

    async def _run_canary_deployment(
        self,
        request: PromotionRequest
    ) -> bool:
        """Executa canary deployment."""
        self.logger.info(
            "starting_canary_deployment",
            request_id=request.request_id,
            traffic_pct=request.config.canary_traffic_pct,
            duration_minutes=request.config.canary_duration_minutes
        )

        try:
            # Configurar split de tráfego
            self._canary_traffic_split[request.model_name] = (
                request.config.canary_traffic_pct / 100.0
            )

            # Coletar baseline de métricas
            baseline_metrics = await self._collect_current_metrics(
                request.model_name
            )
            request.metrics['canary_baseline'] = baseline_metrics

            # Aguardar período canary
            await asyncio.sleep(request.config.canary_duration_minutes * 60)

            # Coletar métricas pós-canary
            canary_metrics = await self._collect_current_metrics(
                request.model_name
            )
            request.metrics['canary_result'] = canary_metrics

            # Verificar degradação
            if baseline_metrics and canary_metrics:
                baseline_mae = baseline_metrics.get('mae_pct', 0)
                canary_mae = canary_metrics.get('mae_pct', 0)

                if baseline_mae > 0:
                    mae_increase = ((canary_mae - baseline_mae) / baseline_mae) * 100

                    if mae_increase > request.config.rollback_mae_increase_pct:
                        self.logger.warning(
                            "canary_failed_mae_increase",
                            request_id=request.request_id,
                            baseline_mae=baseline_mae,
                            canary_mae=canary_mae,
                            increase_pct=mae_increase
                        )

                        # Rollback automático
                        if request.config.auto_rollback_enabled:
                            await self._execute_rollback(request)

                        return False

            # Limpar split de tráfego
            self._canary_traffic_split.pop(request.model_name, None)

            self.logger.info(
                "canary_deployment_passed",
                request_id=request.request_id
            )

            return True

        except Exception as e:
            self.logger.error(
                "canary_deployment_error",
                request_id=request.request_id,
                error=str(e)
            )
            self._canary_traffic_split.pop(request.model_name, None)
            return False

    async def _collect_current_metrics(
        self,
        model_name: str
    ) -> Dict[str, float]:
        """Coleta métricas atuais do validador contínuo."""
        if not self.continuous_validator:
            return {}

        try:
            current_metrics = self.continuous_validator.get_current_metrics()
            window_24h = current_metrics.get('24h', {})

            return {
                'mae': window_24h.get('mae'),
                'mae_pct': window_24h.get('mae_pct'),
                'sample_count': window_24h.get('sample_count', 0)
            }

        except Exception as e:
            self.logger.warning(
                "collect_metrics_failed",
                model_name=model_name,
                error=str(e)
            )
            return {}

    async def _execute_full_rollout(self, request: PromotionRequest) -> None:
        """Executa promoção completa do modelo."""
        self.logger.info(
            "executing_full_rollout",
            request_id=request.request_id
        )

        # Promover no MLflow
        await self.model_registry.promote_model(
            model_name=request.model_name,
            version=request.source_version,
            stage=request.target_stage
        )

        # Enriquecer metadados com informações de promoção
        await self.model_registry.enrich_model_metadata(
            model_name=request.model_name,
            version=request.source_version,
            metadata={
                'promotion_id': request.request_id,
                'promoted_at': datetime.utcnow().isoformat(),
                'promoted_by': request.initiated_by,
                'canary_enabled': request.config.canary_enabled
            }
        )

        self.logger.info(
            "full_rollout_completed",
            request_id=request.request_id
        )

    async def _execute_rollback(self, request: PromotionRequest) -> None:
        """Executa rollback de promoção."""
        self.logger.warning(
            "executing_promotion_rollback",
            request_id=request.request_id
        )

        try:
            result = await self.model_registry.rollback_model(
                model_name=request.model_name,
                reason=f"canary_failed_promotion_{request.request_id}"
            )

            request.metrics['rollback_result'] = result

        except Exception as e:
            self.logger.error(
                "rollback_failed",
                request_id=request.request_id,
                error=str(e)
            )

    async def _finalize_promotion(self, request: PromotionRequest) -> None:
        """Finaliza processo de promoção."""
        # Mover para histórico
        self._active_promotions.pop(request.request_id, None)
        self._promotion_history.append(request)

        # Limpar canary traffic split
        self._canary_traffic_split.pop(request.model_name, None)

        # Armazenar no MongoDB
        if self.mongodb_client:
            try:
                await self.mongodb_client.db['ml_promotions'].insert_one(
                    request.to_dict()
                )
            except Exception as e:
                self.logger.warning("store_promotion_failed", error=str(e))

        # Registrar métricas
        if self.metrics:
            try:
                self.metrics.record_promotion(
                    model_name=request.model_name,
                    result=request.result.value if request.result else 'unknown'
                )
            except Exception:
                pass

        self.logger.info(
            "promotion_finalized",
            request_id=request.request_id,
            stage=request.stage.value,
            result=request.result.value if request.result else None
        )

    def get_canary_traffic_split(self, model_name: str) -> float:
        """
        Retorna a fração de tráfego para canary.

        Args:
            model_name: Nome do modelo

        Returns:
            Fração de tráfego (0.0 a 1.0), 0.0 se não em canary
        """
        return self._canary_traffic_split.get(model_name, 0.0)

    def is_canary_active(self, model_name: str) -> bool:
        """Verifica se há canary ativo para o modelo."""
        return model_name in self._canary_traffic_split

    def get_promotion_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Retorna status de uma promoção."""
        # Verificar ativos
        if request_id in self._active_promotions:
            return self._active_promotions[request_id].to_dict()

        # Verificar histórico
        for req in self._promotion_history:
            if req.request_id == request_id:
                return req.to_dict()

        return None

    async def get_promotion_history(
        self,
        model_name: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Recupera histórico de promoções.

        Args:
            model_name: Filtrar por modelo (opcional)
            limit: Limite de resultados

        Returns:
            Lista de promoções
        """
        # Do MongoDB se disponível
        if self.mongodb_client:
            try:
                query = {}
                if model_name:
                    query['model_name'] = model_name

                results = await self.mongodb_client.db['ml_promotions'].find(
                    query
                ).sort('created_at', -1).limit(limit).to_list(limit)

                return results

            except Exception as e:
                self.logger.warning(
                    "get_promotion_history_failed",
                    error=str(e)
                )

        # Do cache local
        history = self._promotion_history
        if model_name:
            history = [r for r in history if r.model_name == model_name]

        return [r.to_dict() for r in history[-limit:]]

    async def cancel_promotion(self, request_id: str) -> bool:
        """
        Cancela uma promoção em andamento.

        Args:
            request_id: ID da promoção

        Returns:
            True se cancelada, False caso contrário
        """
        if request_id not in self._active_promotions:
            return False

        request = self._active_promotions[request_id]

        if request.stage in [PromotionStage.COMPLETED, PromotionStage.FAILED]:
            return False

        request.stage = PromotionStage.FAILED
        request.result = PromotionResult.CANCELLED
        request.error_message = "Cancelado manualmente"

        await self._finalize_promotion(request)

        self.logger.info(
            "promotion_cancelled",
            request_id=request_id
        )

        return True
