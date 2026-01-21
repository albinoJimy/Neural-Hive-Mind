"""
Sistema de Promoção de Modelos com Shadow Mode e Canary Deployment.

Implementa promoção segura de modelos ML com:
- Validação pré-promoção
- Shadow mode para validação sem impacto em produção
- Canary deployment com traffic splitting
- Rollback automático baseado em métricas
- Auditoria de promoções
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from enum import Enum
from dataclasses import dataclass, field
import structlog

if TYPE_CHECKING:
    from .shadow_mode import ShadowModeRunner

logger = structlog.get_logger(__name__)


class PromotionStage(str, Enum):
    """Estágios de promoção."""
    PENDING = "pending"
    VALIDATING = "validating"
    SHADOW_MODE = "shadow_mode"
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
    # Shadow Mode Configuration
    shadow_mode_enabled: bool = True
    shadow_mode_duration_minutes: int = 10080  # 7 dias
    shadow_mode_min_predictions: int = 1000
    shadow_mode_agreement_threshold: float = 0.90
    # Canary Configuration
    canary_enabled: bool = True
    canary_traffic_pct: float = 10.0
    canary_duration_minutes: int = 30
    mae_threshold_pct: float = 15.0
    precision_threshold: float = 0.75
    auto_rollback_enabled: bool = True
    rollback_mae_increase_pct: float = 20.0
    # Gradual Rollout Configuration
    gradual_rollout_enabled: bool = True
    rollout_stages: List[float] = field(default_factory=lambda: [0.25, 0.50, 0.75, 1.0])
    checkpoint_duration_minutes: int = 30
    checkpoint_mae_threshold_pct: float = 20.0
    checkpoint_error_rate_threshold: float = 0.001  # 0.1%


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
    - Shadow mode para validação sem impacto em produção
    - Canary deployment com split de tráfego
    - Monitoramento durante canary
    - Rollback automático se métricas degradarem
    - Auditoria completa de promoções
    """

    def __init__(
        self,
        config,
        model_registry,
        model_validator=None,
        continuous_validator=None,
        mongodb_client=None,
        metrics=None
    ):
        """
        Args:
            config: Configuração do orchestrator
            model_registry: ModelRegistry instance
            model_validator: ModelValidator instance (opcional, usado para validação pré-promoção)
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
        self._initialized = False

        # Configuração de promoção
        self.default_config = PromotionConfig(
            # Shadow Mode
            shadow_mode_enabled=getattr(config, 'ml_shadow_mode_enabled', True),
            shadow_mode_duration_minutes=getattr(config, 'ml_shadow_mode_duration_minutes', 10080),
            shadow_mode_min_predictions=getattr(config, 'ml_shadow_mode_min_predictions', 1000),
            shadow_mode_agreement_threshold=getattr(config, 'ml_shadow_mode_agreement_threshold', 0.90),
            # Canary
            canary_enabled=getattr(config, 'ml_canary_enabled', True),
            canary_traffic_pct=getattr(config, 'ml_canary_traffic_percentage', 10.0),
            canary_duration_minutes=getattr(config, 'ml_canary_duration_minutes', 30),
            mae_threshold_pct=getattr(config, 'ml_validation_mae_threshold', 0.15) * 100,
            precision_threshold=getattr(config, 'ml_validation_precision_threshold', 0.75),
            auto_rollback_enabled=getattr(config, 'ml_auto_rollback_enabled', True),
            rollback_mae_increase_pct=getattr(config, 'ml_rollback_mae_increase_pct', 20.0),
            # Gradual Rollout
            gradual_rollout_enabled=getattr(config, 'ml_gradual_rollout_enabled', True),
            rollout_stages=getattr(config, 'ml_rollout_stages', [0.25, 0.50, 0.75, 1.0]),
            checkpoint_duration_minutes=getattr(config, 'ml_checkpoint_duration_minutes', 30),
            checkpoint_mae_threshold_pct=getattr(config, 'ml_checkpoint_mae_threshold_pct', 20.0),
            checkpoint_error_rate_threshold=getattr(config, 'ml_checkpoint_error_rate_threshold', 0.001)
        )

        # Promoções ativas
        self._active_promotions: Dict[str, PromotionRequest] = {}

        # Histórico de promoções
        self._promotion_history: List[PromotionRequest] = []

        # Shadow mode runners ativos
        self._shadow_mode_runners: Dict[str, 'ShadowModeRunner'] = {}

        # Canary state
        self._canary_traffic_split: Dict[str, float] = {}

        # Gradual rollout state
        self._rollout_current_stage: Dict[str, int] = {}  # model_name -> stage_index
        self._rollout_baseline_metrics: Dict[str, Dict[str, float]] = {}  # model_name -> metrics

    async def initialize(self) -> None:
        """
        Inicializa o ModelPromotionManager.

        Prepara recursos necessários e marca como inicializado.
        """
        if self._initialized:
            return

        self.logger.info("model_promotion_manager_initializing")

        # Inicialização de recursos se necessário
        # (atualmente não há recursos que precisem de inicialização async)

        self._initialized = True
        self.logger.info("model_promotion_manager_initialized")

    async def close(self) -> None:
        """
        Finaliza o ModelPromotionManager.

        Cancela promoções ativas e limpa recursos.
        """
        self.logger.info(
            "model_promotion_manager_closing",
            active_promotions=len(self._active_promotions),
            active_shadow_runners=len(self._shadow_mode_runners)
        )

        # Cancelar promoções ativas
        for request_id in list(self._active_promotions.keys()):
            try:
                await self.cancel_promotion(request_id)
            except Exception as e:
                self.logger.warning(
                    "cancel_promotion_on_close_failed",
                    request_id=request_id,
                    error=str(e)
                )

        # Fechar shadow mode runners ativos
        for model_name, runner in list(self._shadow_mode_runners.items()):
            try:
                await runner.close()
            except Exception as e:
                self.logger.warning(
                    "close_shadow_runner_failed",
                    model_name=model_name,
                    error=str(e)
                )

        self._shadow_mode_runners.clear()
        self._canary_traffic_split.clear()
        self._initialized = False

        self.logger.info("model_promotion_manager_closed")

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

            # 2. Shadow mode (se habilitado)
            if request.config.shadow_mode_enabled:
                request.stage = PromotionStage.SHADOW_MODE
                shadow_passed = await self._run_shadow_mode(request)

                if not shadow_passed:
                    request.stage = PromotionStage.FAILED
                    request.result = PromotionResult.FAILED_VALIDATION
                    request.error_message = f"Shadow mode falhou: {request.error_message}"
                    await self._finalize_promotion(request)
                    return

            # 3. Canary deployment (se habilitado)
            if request.config.canary_enabled:
                request.stage = PromotionStage.CANARY
                canary_passed = await self._run_canary_deployment(request)

                if not canary_passed:
                    request.stage = PromotionStage.ROLLED_BACK
                    request.result = PromotionResult.FAILED_CANARY
                    await self._finalize_promotion(request)
                    return

            # 4. Gradual rollout (se habilitado) ou rollout completo
            request.stage = PromotionStage.ROLLING_OUT

            if request.config.gradual_rollout_enabled:
                rollout_passed = await self._run_gradual_rollout(request)

                if not rollout_passed:
                    request.stage = PromotionStage.ROLLED_BACK
                    request.result = PromotionResult.ROLLED_BACK
                    await self._finalize_promotion(request)
                    return
            else:
                # Fallback para rollout direto (comportamento legado)
                self.logger.info(
                    "gradual_rollout_disabled_using_direct_promotion",
                    request_id=request.request_id
                )
                await self._execute_full_rollout(request)

            # 5. Sucesso
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

    async def _run_shadow_mode(
        self,
        request: PromotionRequest
    ) -> bool:
        """
        Executa shadow mode deployment.

        O modelo candidato executa predições em paralelo com o modelo de produção
        sem afetar decisões reais. Permite validar o comportamento antes de promover.

        Args:
            request: PromotionRequest

        Returns:
            True se passou, False caso contrário
        """
        from .shadow_mode import ShadowModeRunner

        self.logger.info(
            "starting_shadow_mode",
            request_id=request.request_id,
            duration_minutes=request.config.shadow_mode_duration_minutes,
            min_predictions=request.config.shadow_mode_min_predictions
        )

        try:
            # Carregar modelo de produção
            prod_model = await self.model_registry.load_model(
                model_name=request.model_name,
                stage='Production'
            )

            if not prod_model:
                request.error_message = "Modelo de produção não encontrado"
                return False

            # Determinar versão shadow a usar:
            # 1. Usar ml_shadow_model_version da config se configurada
            # 2. Senão, usar source_version do request
            shadow_version = getattr(self.config, 'ml_shadow_model_version', None)
            if not shadow_version:
                shadow_version = request.source_version

            # Carregar modelo shadow (candidato)
            shadow_model = await self.model_registry.load_model(
                model_name=request.model_name,
                version=shadow_version
            )

            if not shadow_model:
                request.error_message = f"Modelo shadow não encontrado (versão: {shadow_version})"
                return False

            # Criar shadow mode runner
            shadow_runner = ShadowModeRunner(
                config=self.config,
                prod_model=prod_model,
                shadow_model=shadow_model,
                model_registry=self.model_registry,
                mongodb_client=self.mongodb_client,
                metrics=self.metrics,
                model_name=request.model_name,
                shadow_version=shadow_version
            )

            # Registrar runner ativo
            self._shadow_mode_runners[request.model_name] = shadow_runner

            # Aguardar período shadow
            await asyncio.sleep(request.config.shadow_mode_duration_minutes * 60)

            # Coletar estatísticas
            stats = shadow_runner.get_agreement_stats()
            request.metrics['shadow_mode'] = stats

            # Validar critérios
            if stats['prediction_count'] < request.config.shadow_mode_min_predictions:
                self.logger.warning(
                    "shadow_mode_insufficient_predictions",
                    request_id=request.request_id,
                    predictions=stats['prediction_count'],
                    required=request.config.shadow_mode_min_predictions
                )
                request.error_message = (
                    f"Predições insuficientes: {stats['prediction_count']} < "
                    f"{request.config.shadow_mode_min_predictions}"
                )
                await shadow_runner.close()
                self._shadow_mode_runners.pop(request.model_name, None)
                return False

            if stats['agreement_rate'] < request.config.shadow_mode_agreement_threshold:
                self.logger.warning(
                    "shadow_mode_low_agreement",
                    request_id=request.request_id,
                    agreement_rate=stats['agreement_rate'],
                    threshold=request.config.shadow_mode_agreement_threshold
                )
                request.error_message = (
                    f"Agreement rate baixo: {stats['agreement_rate']:.2%} < "
                    f"{request.config.shadow_mode_agreement_threshold:.2%}"
                )
                await shadow_runner.close()
                self._shadow_mode_runners.pop(request.model_name, None)
                return False

            # Limpar runner
            await shadow_runner.close()
            self._shadow_mode_runners.pop(request.model_name, None)

            self.logger.info(
                "shadow_mode_passed",
                request_id=request.request_id,
                agreement_rate=stats['agreement_rate'],
                predictions=stats['prediction_count']
            )

            return True

        except Exception as e:
            self.logger.error(
                "shadow_mode_error",
                request_id=request.request_id,
                error=str(e)
            )
            # Limpar runner em caso de erro
            if request.model_name in self._shadow_mode_runners:
                try:
                    await self._shadow_mode_runners[request.model_name].close()
                except Exception:
                    pass
                self._shadow_mode_runners.pop(request.model_name, None)
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

    async def _run_gradual_rollout(
        self,
        request: PromotionRequest
    ) -> bool:
        """
        Executa rollout gradual com checkpoints de validação.

        Estágios progressivos (default):
        - 25% de tráfego por 30 minutos
        - 50% de tráfego por 30 minutos
        - 75% de tráfego por 30 minutos
        - 100% de tráfego (promoção completa)

        Em cada checkpoint:
        - Coleta métricas atuais
        - Compara com baseline (métricas pré-rollout)
        - Verifica degradação (MAE, error rate)
        - Rollback automático se degradação detectada

        Args:
            request: PromotionRequest

        Returns:
            True se rollout completado com sucesso, False se rollback executado
        """
        self.logger.info(
            "starting_gradual_rollout",
            request_id=request.request_id,
            stages=request.config.rollout_stages,
            checkpoint_duration_minutes=request.config.checkpoint_duration_minutes
        )

        try:
            # Coletar métricas baseline (antes do rollout)
            baseline_metrics = await self._collect_current_metrics(request.model_name)
            self._rollout_baseline_metrics[request.model_name] = baseline_metrics
            request.metrics['rollout_baseline'] = baseline_metrics

            self.logger.info(
                "rollout_baseline_collected",
                request_id=request.request_id,
                baseline_mae=baseline_metrics.get('mae_pct', 'N/A'),
                baseline_samples=baseline_metrics.get('sample_count', 0)
            )

            # Iterar pelos estágios de rollout
            for stage_index, traffic_pct in enumerate(request.config.rollout_stages):
                stage_name = f"stage_{stage_index + 1}"

                self.logger.info(
                    "rollout_stage_starting",
                    request_id=request.request_id,
                    stage=stage_name,
                    traffic_pct=traffic_pct * 100,
                    duration_minutes=request.config.checkpoint_duration_minutes
                )

                # Atualizar estado de rollout
                self._rollout_current_stage[request.model_name] = stage_index

                # Configurar split de tráfego
                self._canary_traffic_split[request.model_name] = traffic_pct

                # Emitir métricas Prometheus
                if self.metrics:
                    self.metrics.set_rollout_stage(
                        model_name=request.model_name,
                        stage=stage_index + 1
                    )
                    self.metrics.set_rollout_traffic_pct(
                        model_name=request.model_name,
                        traffic_pct=traffic_pct * 100
                    )

                # Se for o último estágio (100%), executar promoção completa
                if traffic_pct >= 1.0:
                    self.logger.info(
                        "rollout_final_stage_reached",
                        request_id=request.request_id
                    )
                    await self._execute_full_rollout(request)
                    break

                # Aguardar duração do checkpoint
                await asyncio.sleep(request.config.checkpoint_duration_minutes * 60)

                # Coletar métricas do checkpoint
                checkpoint_metrics = await self._collect_current_metrics(request.model_name)
                request.metrics[f'rollout_{stage_name}'] = checkpoint_metrics

                self.logger.info(
                    "rollout_checkpoint_metrics_collected",
                    request_id=request.request_id,
                    stage=stage_name,
                    checkpoint_mae=checkpoint_metrics.get('mae_pct', 'N/A'),
                    checkpoint_samples=checkpoint_metrics.get('sample_count', 0)
                )

                # Verificar degradação
                degradation_detected = await self._check_rollout_degradation(
                    request=request,
                    baseline_metrics=baseline_metrics,
                    checkpoint_metrics=checkpoint_metrics,
                    stage_name=stage_name
                )

                # Emitir métrica de checkpoint
                if self.metrics:
                    checkpoint_status = 'success' if not degradation_detected else 'degraded'
                    self.metrics.record_rollout_checkpoint(
                        model_name=request.model_name,
                        stage=stage_name,
                        status=checkpoint_status
                    )

                    if degradation_detected:
                        checkpoint_mae = checkpoint_metrics.get('mae_pct', 0)
                        baseline_mae = baseline_metrics.get('mae_pct', 0)
                        reason = 'mae_increase' if checkpoint_mae > baseline_mae else 'error_rate'
                        self.metrics.record_rollout_degradation(
                            model_name=request.model_name,
                            stage=stage_name,
                            reason=reason
                        )

                if degradation_detected:
                    self.logger.error(
                        "rollout_degradation_detected",
                        request_id=request.request_id,
                        stage=stage_name,
                        traffic_pct=traffic_pct * 100
                    )

                    # Executar rollback automático
                    if request.config.auto_rollback_enabled:
                        await self._execute_rollback(request)
                        request.error_message = f"Degradação detectada em {stage_name}"
                        # Limpar estado antes de retornar
                        self._rollout_current_stage.pop(request.model_name, None)
                        self._rollout_baseline_metrics.pop(request.model_name, None)
                        self._canary_traffic_split.pop(request.model_name, None)
                        return False
                    else:
                        self.logger.warning(
                            "rollout_degradation_auto_rollback_disabled",
                            request_id=request.request_id
                        )
                        # Continuar mesmo com degradação (não recomendado)

                self.logger.info(
                    "rollout_stage_completed",
                    request_id=request.request_id,
                    stage=stage_name,
                    traffic_pct=traffic_pct * 100
                )

            # Limpar estado de rollout
            self._rollout_current_stage.pop(request.model_name, None)
            self._rollout_baseline_metrics.pop(request.model_name, None)
            self._canary_traffic_split.pop(request.model_name, None)

            self.logger.info(
                "gradual_rollout_completed",
                request_id=request.request_id
            )

            return True

        except Exception as e:
            self.logger.error(
                "gradual_rollout_error",
                request_id=request.request_id,
                error=str(e)
            )

            # Limpar estado
            self._rollout_current_stage.pop(request.model_name, None)
            self._rollout_baseline_metrics.pop(request.model_name, None)
            self._canary_traffic_split.pop(request.model_name, None)

            return False

    async def _check_rollout_degradation(
        self,
        request: PromotionRequest,
        baseline_metrics: Dict[str, float],
        checkpoint_metrics: Dict[str, float],
        stage_name: str
    ) -> bool:
        """
        Verifica se houve degradação de métricas no checkpoint.

        Critérios de degradação:
        1. MAE aumentou mais que threshold (default: 20%)
        2. Error rate excedeu threshold (default: 0.1%)
        3. Sample count insuficiente para validação

        Args:
            request: PromotionRequest
            baseline_metrics: Métricas baseline (pré-rollout)
            checkpoint_metrics: Métricas do checkpoint atual
            stage_name: Nome do estágio (para logging)

        Returns:
            True se degradação detectada, False caso contrário
        """
        # Se não há métricas, não pode validar (assumir OK)
        if not baseline_metrics or not checkpoint_metrics:
            self.logger.warning(
                "rollout_checkpoint_no_metrics",
                request_id=request.request_id,
                stage=stage_name
            )
            return False

        # Verificar sample count mínimo
        checkpoint_samples = checkpoint_metrics.get('sample_count', 0)
        if checkpoint_samples < 10:
            self.logger.warning(
                "rollout_checkpoint_insufficient_samples",
                request_id=request.request_id,
                stage=stage_name,
                samples=checkpoint_samples
            )
            return False

        # Verificar degradação de MAE
        baseline_mae = baseline_metrics.get('mae_pct', 0)
        checkpoint_mae = checkpoint_metrics.get('mae_pct', 0)
        mae_increase_pct = 0.0

        if baseline_mae > 0:
            mae_increase_pct = ((checkpoint_mae - baseline_mae) / baseline_mae) * 100

            if mae_increase_pct > request.config.checkpoint_mae_threshold_pct:
                self.logger.warning(
                    "rollout_mae_degradation",
                    request_id=request.request_id,
                    stage=stage_name,
                    baseline_mae=baseline_mae,
                    checkpoint_mae=checkpoint_mae,
                    increase_pct=mae_increase_pct,
                    threshold_pct=request.config.checkpoint_mae_threshold_pct
                )
                return True

        # Verificar error rate (se disponível)
        checkpoint_error_rate = checkpoint_metrics.get('error_rate', 0)
        if checkpoint_error_rate > request.config.checkpoint_error_rate_threshold:
            self.logger.warning(
                "rollout_error_rate_exceeded",
                request_id=request.request_id,
                stage=stage_name,
                error_rate=checkpoint_error_rate,
                threshold=request.config.checkpoint_error_rate_threshold
            )
            return True

        # Nenhuma degradação detectada
        self.logger.info(
            "rollout_checkpoint_validation_passed",
            request_id=request.request_id,
            stage=stage_name,
            mae_increase_pct=mae_increase_pct if baseline_mae > 0 else 'N/A'
        )

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

            # Métricas de predição (janela 24h)
            prediction_metrics = current_metrics.get('prediction_metrics', {})
            window_24h = prediction_metrics.get('24h', {})

            # Métricas de latência (janela 24h)
            latency_metrics = current_metrics.get('latency_metrics', {})
            latency_24h = latency_metrics.get('24h', {})

            return {
                'mae': window_24h.get('mae'),
                'mae_pct': window_24h.get('mae_pct'),
                'r2': window_24h.get('r2'),
                'sample_count': window_24h.get('sample_count', 0),
                'latency_p50': latency_24h.get('p50'),
                'latency_p95': latency_24h.get('p95'),
                'latency_p99': latency_24h.get('p99'),
                'error_rate': latency_24h.get('error_rate')
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

    def get_shadow_runner(self, model_name: str) -> Optional['ShadowModeRunner']:
        """
        Retorna shadow runner ativo para o modelo.

        Usado pelos predictors para obter o runner durante predições
        e executar shadow predictions em paralelo.

        Args:
            model_name: Nome do modelo

        Returns:
            ShadowModeRunner ou None se não houver shadow mode ativo
        """
        return self._shadow_mode_runners.get(model_name)

    def is_shadow_mode_active(self, model_name: str) -> bool:
        """
        Verifica se há shadow mode ativo para o modelo.

        Args:
            model_name: Nome do modelo

        Returns:
            True se shadow mode está ativo, False caso contrário
        """
        return model_name in self._shadow_mode_runners
