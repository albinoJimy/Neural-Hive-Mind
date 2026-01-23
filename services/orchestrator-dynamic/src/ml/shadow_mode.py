"""
Shadow Mode Runner para validação de modelos ML.

Executa modelo shadow (candidato) em paralelo com modelo de produção
sem afetar decisões reais. Permite validar comportamento do modelo novo
em condições reais antes de promovê-lo para canary/produção.

Características:
- Predição de produção: síncrona (bloqueia request)
- Predição shadow: assíncrona (fire-and-forget)
- Comparação de resultados e cálculo de agreement rate
- Circuit breaker para falhas do modelo shadow
- Persistência de comparações no MongoDB
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import structlog
import pybreaker

logger = structlog.get_logger(__name__)


class ShadowModeRunner:
    """
    Executa modelo shadow em paralelo com modelo de produção.

    O shadow mode é um estágio de validação onde o modelo candidato
    executa predições em paralelo com o modelo de produção. As predições
    shadow são assíncronas (fire-and-forget) para não impactar latência.

    Critérios de sucesso:
    - Agreement rate >= 90% (configurable)
    - Mínimo de 1000 predições (configurable)
    - Latência shadow não deve impactar produção

    Attributes:
        config: Configuração do orchestrator
        prod_model: Modelo de produção (servindo tráfego real)
        shadow_model: Modelo candidato (executando em shadow)
        model_registry: ModelRegistry para carregar modelos
        mongodb_client: Cliente MongoDB para persistência
        metrics: OrchestratorMetrics para observabilidade
        model_name: Nome do modelo sendo testado
        shadow_version: Versão do modelo shadow
    """

    def __init__(
        self,
        config,
        prod_model,
        shadow_model,
        model_registry,
        mongodb_client,
        metrics,
        model_name: str,
        shadow_version: str,
        audit_logger=None
    ):
        """
        Inicializa ShadowModeRunner.

        Args:
            config: Configuração do orchestrator
            prod_model: Modelo de produção carregado
            shadow_model: Modelo shadow (candidato) carregado
            model_registry: ModelRegistry instance
            mongodb_client: Cliente MongoDB
            metrics: OrchestratorMetrics instance
            model_name: Nome do modelo
            shadow_version: Versão do modelo shadow
            audit_logger: ModelAuditLogger instance (opcional)
        """
        self.config = config
        self.prod_model = prod_model
        self.shadow_model = shadow_model
        self.model_registry = model_registry
        self.mongodb_client = mongodb_client
        self.metrics = metrics
        self.model_name = model_name
        self.shadow_version = shadow_version
        self.audit_logger = audit_logger
        self._start_time = time.time()
        self.logger = logger.bind(
            component="shadow_mode_runner",
            model_name=model_name,
            shadow_version=shadow_version
        )

        # Configurações
        self.sample_rate = getattr(config, 'ml_shadow_mode_sample_rate', 1.0)
        self.persist_comparisons = getattr(config, 'ml_shadow_mode_persist_comparisons', True)
        self.circuit_breaker_enabled = getattr(config, 'ml_shadow_mode_circuit_breaker_enabled', True)

        # Estatísticas de agreement
        self.agreement_count = 0
        self.disagreement_count = 0
        self.total_count = 0
        self.total_latency_ms = 0.0

        # Versão de produção (para logging/métricas)
        self.prod_version = 'production'

        # Circuit breaker para shadow predictions
        if self.circuit_breaker_enabled:
            self.circuit_breaker = pybreaker.CircuitBreaker(
                fail_max=5,
                reset_timeout=60,
                listeners=[ShadowCircuitBreakerListener(self)]
            )
        else:
            self.circuit_breaker = None

        # Collection MongoDB para comparações
        self.collection_name = 'shadow_mode_comparisons'

        # Lock para estatísticas thread-safe
        self._stats_lock = asyncio.Lock()

        self.logger.info(
            "shadow_mode_runner_initialized",
            sample_rate=self.sample_rate,
            persist_comparisons=self.persist_comparisons,
            circuit_breaker_enabled=self.circuit_breaker_enabled
        )

        # Audit logging - shadow mode iniciado
        if self.audit_logger:
            asyncio.get_event_loop().create_task(self._log_shadow_mode_started())

    async def predict_with_shadow(
        self,
        features: Dict[str, Any],
        context: Dict[str, Any],
        prod_result: Optional[Dict[str, Any]] = None,
        normalized_features: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Dispara predição shadow em paralelo com predição de produção já calculada.

        Se prod_result for fornecido, usa o resultado já calculado e apenas
        dispara a predição shadow em background. Se não fornecido, executa
        a predição de produção internamente (comportamento legado).

        Args:
            features: Dict com features para predição (features_dict original)
            context: Dict com contexto (ticket_id, task_type, etc)
            prod_result: Resultado já calculado da predição de produção (opcional)
            normalized_features: Features normalizadas pelo caller (opcional, para garantir consistência)

        Returns:
            Dict com resultado da predição de produção:
            - duration_ms: Duração predita (para DurationPredictor)
            - confidence: Score de confiança
            - is_anomaly: Se é anomalia (para AnomalyDetector)
        """
        import random

        start_time = time.time()

        # Verificar se deve executar shadow (sampling)
        should_shadow = random.random() < self.sample_rate

        # Se prod_result não fornecido, calcula internamente (compatibilidade legada)
        if prod_result is None:
            try:
                prod_result = self._execute_production_prediction(features)
            except Exception as e:
                self.logger.error("production_prediction_failed", error=str(e))
                raise

        # Disparar predição shadow em background (fire-and-forget)
        if should_shadow and self._is_circuit_closed():
            asyncio.create_task(
                self._shadow_predict(
                    features, prod_result, context, start_time,
                    normalized_features=normalized_features
                )
            )

        return prod_result

    async def predict_shadow_only(
        self,
        features: Dict[str, Any],
        prod_result: Dict[str, Any],
        context: Dict[str, Any],
        normalized_features: Optional[Any] = None
    ) -> None:
        """
        Executa apenas a predição shadow em background (fire-and-forget).

        Usado quando o caller já calculou o prod_result usando a lógica
        normal do predictor e quer apenas disparar o shadow.

        Args:
            features: Dict com features originais (features_dict)
            prod_result: Resultado já calculado da predição de produção
            context: Dict com contexto (ticket_id, task_type, etc)
            normalized_features: Features normalizadas pelo caller (opcional)
        """
        import random

        start_time = time.time()

        # Verificar se deve executar shadow (sampling)
        should_shadow = random.random() < self.sample_rate

        # Disparar predição shadow em background (fire-and-forget)
        if should_shadow and self._is_circuit_closed():
            asyncio.create_task(
                self._shadow_predict(
                    features, prod_result, context, start_time,
                    normalized_features=normalized_features
                )
            )

    def _execute_production_prediction(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executa predição de produção.

        Args:
            features: Features para predição

        Returns:
            Dict com resultado da predição
        """
        import numpy as np

        # Converter features para array se necessário
        if isinstance(features, dict):
            feature_array = np.array([list(features.values())])
        else:
            feature_array = features

        # Determinar tipo de modelo baseado no nome
        if 'duration' in self.model_name.lower():
            # DurationPredictor
            predicted = float(self.prod_model.predict(feature_array)[0])
            return {
                'duration_ms': max(predicted, 1000.0),
                'confidence': 0.7  # Default confidence
            }
        elif 'anomaly' in self.model_name.lower():
            # AnomalyDetector
            prediction = self.prod_model.predict(feature_array)[0]
            score = float(self.prod_model.score_samples(feature_array)[0])
            return {
                'is_anomaly': prediction == -1,
                'anomaly_score': score,
                'confidence': abs(score)
            }
        else:
            # Modelo genérico
            predicted = self.prod_model.predict(feature_array)
            return {'prediction': predicted.tolist()}

    async def _shadow_predict(
        self,
        features: Dict[str, Any],
        prod_result: Dict[str, Any],
        context: Dict[str, Any],
        start_time: float,
        normalized_features: Optional[Any] = None
    ) -> None:
        """
        Executa predição shadow em background.

        Este método é executado de forma assíncrona (fire-and-forget).
        Compara resultado com produção, calcula agreement e persiste.

        Args:
            features: Features originais (features_dict) usadas na predição
            prod_result: Resultado da predição de produção
            context: Contexto (ticket_id, task_type, etc)
            start_time: Timestamp de início para cálculo de latência
            normalized_features: Features normalizadas pelo caller (opcional, garante consistência com produção)
        """
        import numpy as np

        shadow_start = time.time()

        try:
            # Verificar circuit breaker
            if self.circuit_breaker:
                state = self.circuit_breaker.current_state
                state_name = state.name if hasattr(state, 'name') else str(state)
                if state_name == 'open':
                    self.logger.debug("shadow_predict_skipped_circuit_open")
                    return

            # Usar features normalizadas se fornecidas, senão converter features dict
            if normalized_features is not None:
                feature_array = normalized_features
            elif isinstance(features, dict):
                feature_array = np.array([list(features.values())])
            else:
                feature_array = features

            # Executar predição shadow
            shadow_result = {}

            if 'duration' in self.model_name.lower():
                predicted = float(self.shadow_model.predict(feature_array)[0])
                shadow_result = {
                    'duration_ms': max(predicted, 1000.0),
                    'confidence': 0.7
                }
            elif 'anomaly' in self.model_name.lower():
                prediction = self.shadow_model.predict(feature_array)[0]
                score = float(self.shadow_model.score_samples(feature_array)[0])
                shadow_result = {
                    'is_anomaly': prediction == -1,
                    'anomaly_score': score,
                    'confidence': abs(score)
                }
            else:
                predicted = self.shadow_model.predict(feature_array)
                shadow_result = {'prediction': predicted.tolist()}

            shadow_latency_ms = (time.time() - shadow_start) * 1000
            prod_latency_ms = (shadow_start - start_time) * 1000

            # Calcular agreement
            agreement = self._calculate_agreement(prod_result, shadow_result)

            # Atualizar estatísticas
            await self._update_stats(agreement, shadow_latency_ms)

            # Registrar métricas
            if self.metrics:
                self.metrics.record_shadow_prediction(
                    model_name=self.model_name,
                    model_version=self.shadow_version,
                    status='success',
                    latency=shadow_latency_ms / 1000,
                    agreement=agreement
                )

            # Persistir comparação
            if self.persist_comparisons:
                comparison = {
                    'comparison_id': str(uuid.uuid4()),
                    'model_name': self.model_name,
                    'prod_version': self.prod_version,
                    'shadow_version': self.shadow_version,
                    'timestamp': datetime.utcnow(),
                    'features': features if isinstance(features, dict) else {},
                    'prod_result': prod_result,
                    'shadow_result': shadow_result,
                    'agreement': agreement,
                    'latency_ms': {
                        'prod': prod_latency_ms,
                        'shadow': shadow_latency_ms
                    },
                    'context': context
                }
                await self._persist_comparison(comparison)

            self.logger.debug(
                "shadow_prediction_completed",
                agreement_overall=agreement.get('overall'),
                shadow_latency_ms=round(shadow_latency_ms, 2)
            )

        except Exception as e:
            self.logger.warning("shadow_prediction_failed", error=str(e))

            # Registrar erro no circuit breaker
            if self.circuit_breaker:
                try:
                    self.circuit_breaker.call(lambda: self._raise_error(e))
                except pybreaker.CircuitBreakerError:
                    pass
                except:
                    pass

            # Registrar erro nas métricas
            if self.metrics:
                self.metrics.record_shadow_error(
                    model_name=self.model_name,
                    error_type=type(e).__name__
                )

    def _raise_error(self, error):
        """Helper para registrar erro no circuit breaker."""
        raise error

    def _calculate_agreement(
        self,
        prod_result: Dict[str, Any],
        shadow_result: Dict[str, Any]
    ) -> Dict[str, bool]:
        """
        Calcula agreement entre produção e shadow.

        Para DurationPredictor:
        - duration: Agreement se |prod - shadow| / prod < 15%

        Para AnomalyDetector:
        - anomaly: Agreement se prod_is_anomaly == shadow_is_anomaly

        Para ambos:
        - confidence: Agreement se |prod_conf - shadow_conf| < 0.2

        Args:
            prod_result: Resultado da predição de produção
            shadow_result: Resultado da predição shadow

        Returns:
            Dict com agreement por tipo:
            - overall: bool (agreement geral)
            - duration: bool (apenas para DurationPredictor)
            - anomaly: bool (apenas para AnomalyDetector)
            - confidence: bool
        """
        agreement = {}

        # Agreement para duration
        if 'duration_ms' in prod_result and 'duration_ms' in shadow_result:
            prod_duration = prod_result['duration_ms']
            shadow_duration = shadow_result['duration_ms']

            if prod_duration > 0:
                duration_diff_pct = abs(prod_duration - shadow_duration) / prod_duration
                agreement['duration'] = duration_diff_pct < 0.15  # 15% threshold
            else:
                agreement['duration'] = shadow_duration == 0

        # Agreement para anomaly
        if 'is_anomaly' in prod_result and 'is_anomaly' in shadow_result:
            agreement['anomaly'] = prod_result['is_anomaly'] == shadow_result['is_anomaly']

        # Agreement para confidence
        if 'confidence' in prod_result and 'confidence' in shadow_result:
            confidence_diff = abs(prod_result['confidence'] - shadow_result['confidence'])
            agreement['confidence'] = confidence_diff < 0.2

        # Calcular overall agreement
        # Overall é True se todos os agreements específicos são True
        specific_agreements = [v for k, v in agreement.items() if k != 'overall']
        agreement['overall'] = all(specific_agreements) if specific_agreements else True

        return agreement

    async def _update_stats(self, agreement: Dict[str, bool], latency_ms: float) -> None:
        """
        Atualiza estatísticas de agreement.

        Thread-safe usando asyncio.Lock.

        Args:
            agreement: Dict com agreement por tipo
            latency_ms: Latência da predição shadow em ms
        """
        async with self._stats_lock:
            self.total_count += 1
            self.total_latency_ms += latency_ms

            if agreement.get('overall', False):
                self.agreement_count += 1
            else:
                self.disagreement_count += 1

    async def _persist_comparison(self, comparison: Dict[str, Any]) -> None:
        """
        Persiste comparação no MongoDB.

        Args:
            comparison: Dict com dados da comparação
        """
        if not self.mongodb_client:
            return

        try:
            await self.mongodb_client.db[self.collection_name].insert_one(comparison)
        except Exception as e:
            self.logger.warning("persist_comparison_failed", error=str(e))

    def _is_circuit_closed(self) -> bool:
        """
        Verifica se circuit breaker está fechado (operação normal).

        Returns:
            True se fechado ou semi-aberto, False se aberto
        """
        if not self.circuit_breaker:
            return True
        # pybreaker.current_state pode ser objeto de estado ou string
        state = self.circuit_breaker.current_state
        state_name = state.name if hasattr(state, 'name') else str(state)
        return state_name != 'open'

    def get_agreement_stats(self) -> Dict[str, float]:
        """
        Retorna estatísticas agregadas de agreement.

        Returns:
            Dict com:
            - agreement_rate: Taxa de agreement (0-1)
            - prediction_count: Total de predições shadow
            - avg_latency_ms: Latência média em ms
            - disagreement_count: Contagem de disagreements
        """
        if self.total_count == 0:
            return {
                'agreement_rate': 0.0,
                'prediction_count': 0,
                'avg_latency_ms': 0.0,
                'disagreement_count': 0
            }

        return {
            'agreement_rate': self.agreement_count / self.total_count,
            'prediction_count': self.total_count,
            'avg_latency_ms': self.total_latency_ms / self.total_count,
            'disagreement_count': self.disagreement_count
        }

    async def _log_shadow_mode_started(self) -> None:
        """Registra início do shadow mode no audit log."""
        try:
            from .model_audit_logger import AuditEventContext
            context = AuditEventContext(
                user_id='system',
                reason='Shadow mode iniciado para validação de modelo',
                environment=getattr(self.config, 'environment', 'production'),
                triggered_by='automatic',
                metadata={
                    'prod_version': self.prod_version,
                    'sample_rate': self.sample_rate
                }
            )
            await self.audit_logger.log_shadow_mode_started(
                model_name=self.model_name,
                model_version=self.shadow_version,
                context=context,
                shadow_config={
                    'sample_rate': self.sample_rate,
                    'persist_comparisons': self.persist_comparisons,
                    'circuit_breaker_enabled': self.circuit_breaker_enabled
                }
            )
        except Exception as e:
            self.logger.warning('audit_logging_shadow_started_failed', error=str(e))

    async def close(self) -> None:
        """
        Limpa recursos do runner.

        Chamado quando shadow mode termina ou é cancelado.
        """
        stats = self.get_agreement_stats()

        self.logger.info(
            "shadow_mode_runner_closing",
            total_predictions=self.total_count,
            agreement_rate=stats.get('agreement_rate', 0)
        )

        # Audit logging - shadow mode concluído
        if self.audit_logger:
            try:
                from .model_audit_logger import AuditEventContext
                duration = time.time() - self._start_time
                context = AuditEventContext(
                    user_id='system',
                    reason='Shadow mode concluído',
                    duration_seconds=duration,
                    environment=getattr(self.config, 'environment', 'production'),
                    triggered_by='automatic',
                    metadata={'prod_version': self.prod_version}
                )
                await self.audit_logger.log_shadow_mode_completed(
                    model_name=self.model_name,
                    model_version=self.shadow_version,
                    context=context,
                    shadow_results={
                        'agreement_rate': stats.get('agreement_rate', 0),
                        'prediction_count': stats.get('prediction_count', 0),
                        'avg_latency_ms': stats.get('avg_latency_ms', 0),
                        'disagreement_count': stats.get('disagreement_count', 0)
                    }
                )
            except Exception as e:
                self.logger.warning('audit_logging_shadow_completed_failed', error=str(e))

        # Reset stats
        self.agreement_count = 0
        self.disagreement_count = 0
        self.total_count = 0
        self.total_latency_ms = 0.0


class ShadowCircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """
    Listener para eventos do circuit breaker shadow.

    Registra métricas Prometheus quando estado do circuit breaker muda.
    """

    def __init__(self, runner: ShadowModeRunner):
        """
        Args:
            runner: ShadowModeRunner instance
        """
        self.runner = runner

    def state_change(self, cb, old_state, new_state):
        """Callback quando estado do circuit breaker muda."""
        logger.info(
            "shadow_circuit_breaker_state_change",
            model_name=self.runner.model_name,
            old_state=old_state.name,
            new_state=new_state.name
        )

        if self.runner.metrics:
            state_name = new_state.name.lower()
            self.runner.metrics.set_shadow_circuit_breaker_state(
                model_name=self.runner.model_name,
                state=state_name
            )

    def failure(self, cb, exc):
        """Callback quando falha é registrada."""
        logger.debug(
            "shadow_circuit_breaker_failure",
            model_name=self.runner.model_name,
            failure_count=cb.fail_counter,
            error=str(exc)
        )

    def success(self, cb):
        """Callback quando operação tem sucesso."""
        pass
