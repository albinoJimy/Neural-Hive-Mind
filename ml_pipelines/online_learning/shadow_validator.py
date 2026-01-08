"""
Shadow Validator para Online Learning.

Implementa validação paralela de modelos online comparando com modelo batch
(baseline) para garantir qualidade antes do deployment.
"""

import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import structlog
import numpy as np
from scipy import stats
from prometheus_client import Counter, Histogram, Gauge
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from .config import OnlineLearningConfig
from .incremental_learner import IncrementalLearner

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Métricas Prometheus
shadow_validations_total = Counter(
    'neural_hive_shadow_validations_total',
    'Total de validações shadow',
    ['specialist_type', 'result']
)
shadow_validation_duration = Histogram(
    'neural_hive_shadow_validation_duration_seconds',
    'Duração de validações shadow',
    ['specialist_type']
)
shadow_accuracy_ratio = Gauge(
    'neural_hive_shadow_accuracy_ratio',
    'Razão de accuracy online/batch',
    ['specialist_type']
)
shadow_latency_ratio = Gauge(
    'neural_hive_shadow_latency_ratio',
    'Razão de latência online/batch',
    ['specialist_type']
)
shadow_kl_divergence = Gauge(
    'neural_hive_shadow_kl_divergence',
    'KL divergence entre distribuições',
    ['specialist_type']
)


class ShadowValidationResult:
    """Resultado de uma validação shadow."""

    def __init__(
        self,
        passed: bool,
        validation_id: str,
        specialist_type: str,
        metrics: Dict[str, Any],
        failures: List[str],
        timestamp: datetime
    ):
        self.passed = passed
        self.validation_id = validation_id
        self.specialist_type = specialist_type
        self.metrics = metrics
        self.failures = failures
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            'passed': self.passed,
            'validation_id': self.validation_id,
            'specialist_type': self.specialist_type,
            'metrics': self.metrics,
            'failures': self.failures,
            'timestamp': self.timestamp.isoformat()
        }


class ShadowValidator:
    """
    Executa validação paralela de modelos online vs batch.

    Compara predições e métricas entre modelo online (challenger) e
    modelo batch (baseline) para garantir qualidade antes do deployment.

    Critérios de validação:
    - Accuracy >= threshold relativo ao baseline
    - Latência <= threshold relativo ao baseline
    - KL divergence <= threshold máximo
    - Predições consistentes (concordância mínima)
    """

    def __init__(
        self,
        config: OnlineLearningConfig,
        specialist_type: str,
        batch_model: Any,
        online_learner: IncrementalLearner
    ):
        """
        Inicializa ShadowValidator.

        Args:
            config: Configuração de online learning
            specialist_type: Tipo do especialista
            batch_model: Modelo batch (baseline)
            online_learner: Learner incremental (challenger)
        """
        self.config = config
        self.specialist_type = specialist_type
        self.batch_model = batch_model
        self.online_learner = online_learner

        # Histórico de validações
        self._validation_history: List[ShadowValidationResult] = []

        logger.info(
            "shadow_validator_initialized",
            specialist_type=specialist_type,
            accuracy_threshold=config.shadow_accuracy_threshold,
            latency_threshold=config.shadow_latency_threshold,
            kl_threshold=config.shadow_kl_divergence_threshold
        )

    def _compute_kl_divergence(
        self,
        p: np.ndarray,
        q: np.ndarray,
        epsilon: float = 1e-10
    ) -> float:
        """
        Calcula KL divergence entre duas distribuições de probabilidade.

        Args:
            p: Distribuição de referência (batch)
            q: Distribuição de comparação (online)
            epsilon: Valor mínimo para evitar log(0)

        Returns:
            KL divergence
        """
        p = np.clip(p, epsilon, 1.0)
        q = np.clip(q, epsilon, 1.0)

        # Normalizar para garantir que são distribuições válidas
        p = p / p.sum(axis=1, keepdims=True)
        q = q / q.sum(axis=1, keepdims=True)

        # KL divergence média sobre todas as amostras
        kl = np.sum(p * np.log(p / q), axis=1)
        return float(np.mean(kl))

    def _measure_latency(
        self,
        model: Any,
        X: np.ndarray,
        is_online: bool = False
    ) -> Tuple[np.ndarray, float]:
        """
        Mede latência de predição.

        Args:
            model: Modelo para predição
            X: Features de entrada
            is_online: Se é modelo online (usa predict_proba diferente)

        Returns:
            Tuple (predições, latência em ms)
        """
        start_time = time.perf_counter()

        if is_online:
            predictions = self.online_learner.predict_proba(X)
        else:
            predictions = model.predict_proba(X)

        latency_ms = (time.perf_counter() - start_time) * 1000

        return predictions, latency_ms

    def validate(
        self,
        X: np.ndarray,
        y: Optional[np.ndarray] = None
    ) -> ShadowValidationResult:
        """
        Executa validação shadow completa.

        Args:
            X: Features para validação
            y: Labels verdadeiros (opcional, para accuracy)

        Returns:
            ShadowValidationResult com resultado da validação
        """
        validation_id = f"shadow-{uuid.uuid4().hex[:12]}"
        start_time = time.time()
        failures = []
        metrics = {}

        with tracer.start_as_current_span(
            "shadow_validation",
            kind=SpanKind.INTERNAL,
            attributes={
                "specialist_type": self.specialist_type,
                "validation_id": validation_id,
                "sample_size": len(X)
            }
        ) as span:
            try:
                X = np.asarray(X)

                # Limitar amostra se necessário
                if len(X) > self.config.shadow_sample_size:
                    indices = np.random.choice(
                        len(X),
                        size=self.config.shadow_sample_size,
                        replace=False
                    )
                    X = X[indices]
                    if y is not None:
                        y = np.asarray(y)[indices]

                # Executar predições com medição de latência
                batch_probas, batch_latency = self._measure_latency(
                    self.batch_model, X, is_online=False
                )
                online_probas, online_latency = self._measure_latency(
                    None, X, is_online=True
                )

                # Calcular métricas
                metrics['batch_latency_ms'] = batch_latency
                metrics['online_latency_ms'] = online_latency
                metrics['latency_ratio'] = online_latency / batch_latency if batch_latency > 0 else float('inf')
                metrics['sample_size'] = len(X)

                # Validar latência
                if metrics['latency_ratio'] > self.config.shadow_latency_threshold:
                    failures.append(
                        f"Latência muito alta: ratio={metrics['latency_ratio']:.2f} "
                        f"(threshold={self.config.shadow_latency_threshold})"
                    )

                # Calcular KL divergence
                kl_div = self._compute_kl_divergence(batch_probas, online_probas)
                metrics['kl_divergence'] = kl_div

                if kl_div > self.config.shadow_kl_divergence_threshold:
                    failures.append(
                        f"KL divergence muito alta: {kl_div:.4f} "
                        f"(threshold={self.config.shadow_kl_divergence_threshold})"
                    )

                # Calcular concordância de predições
                batch_preds = np.argmax(batch_probas, axis=1)
                online_preds = np.argmax(online_probas, axis=1)
                agreement_rate = np.mean(batch_preds == online_preds)
                metrics['prediction_agreement'] = float(agreement_rate)

                # Calcular accuracy se labels disponíveis
                if y is not None:
                    y = np.asarray(y)

                    # Mapear labels para índices
                    classes = self.online_learner.classes
                    y_indices = np.array([
                        list(classes).index(label) if label in classes else -1
                        for label in y
                    ])
                    valid_mask = y_indices >= 0

                    if valid_mask.sum() > 0:
                        batch_accuracy = np.mean(
                            batch_preds[valid_mask] == y_indices[valid_mask]
                        )
                        online_accuracy = np.mean(
                            online_preds[valid_mask] == y_indices[valid_mask]
                        )

                        metrics['batch_accuracy'] = float(batch_accuracy)
                        metrics['online_accuracy'] = float(online_accuracy)
                        metrics['accuracy_ratio'] = (
                            online_accuracy / batch_accuracy
                            if batch_accuracy > 0 else 0.0
                        )

                        if metrics['accuracy_ratio'] < self.config.shadow_accuracy_threshold:
                            failures.append(
                                f"Accuracy muito baixa: ratio={metrics['accuracy_ratio']:.3f} "
                                f"(threshold={self.config.shadow_accuracy_threshold})"
                            )

                # Calcular estatísticas de confiança
                batch_confidence = np.max(batch_probas, axis=1)
                online_confidence = np.max(online_probas, axis=1)
                metrics['batch_avg_confidence'] = float(np.mean(batch_confidence))
                metrics['online_avg_confidence'] = float(np.mean(online_confidence))
                metrics['confidence_correlation'] = float(
                    np.corrcoef(batch_confidence, online_confidence)[0, 1]
                )

                # Teste estatístico de equivalência
                _, p_value = stats.ks_2samp(
                    batch_confidence, online_confidence
                )
                metrics['ks_test_p_value'] = float(p_value)

                # Determinar resultado
                passed = len(failures) == 0
                duration_seconds = time.time() - start_time
                metrics['validation_duration_seconds'] = duration_seconds

                # Emitir métricas Prometheus
                shadow_validations_total.labels(
                    specialist_type=self.specialist_type,
                    result='passed' if passed else 'failed'
                ).inc()
                shadow_validation_duration.labels(
                    specialist_type=self.specialist_type
                ).observe(duration_seconds)

                if 'accuracy_ratio' in metrics:
                    shadow_accuracy_ratio.labels(
                        specialist_type=self.specialist_type
                    ).set(metrics['accuracy_ratio'])

                shadow_latency_ratio.labels(
                    specialist_type=self.specialist_type
                ).set(metrics['latency_ratio'])
                shadow_kl_divergence.labels(
                    specialist_type=self.specialist_type
                ).set(kl_div)

                # Criar resultado
                result = ShadowValidationResult(
                    passed=passed,
                    validation_id=validation_id,
                    specialist_type=self.specialist_type,
                    metrics=metrics,
                    failures=failures,
                    timestamp=datetime.utcnow()
                )

                # Adicionar ao histórico
                self._validation_history.append(result)
                if len(self._validation_history) > 100:
                    self._validation_history = self._validation_history[-100:]

                # Log resultado
                log_level = logger.info if passed else logger.warning
                log_level(
                    "shadow_validation_completed",
                    validation_id=validation_id,
                    specialist_type=self.specialist_type,
                    passed=passed,
                    failures=failures,
                    kl_divergence=kl_div,
                    latency_ratio=metrics['latency_ratio'],
                    accuracy_ratio=metrics.get('accuracy_ratio'),
                    prediction_agreement=metrics['prediction_agreement']
                )

                # Adicionar atributos ao span
                span.set_attribute("validation.passed", passed)
                span.set_attribute("validation.kl_divergence", kl_div)
                span.set_attribute("validation.latency_ratio", metrics['latency_ratio'])
                span.set_attribute("validation.failures_count", len(failures))

                return result

            except Exception as e:
                span.record_exception(e)
                span.set_attribute("validation.error", str(e))

                logger.error(
                    "shadow_validation_failed",
                    validation_id=validation_id,
                    specialist_type=self.specialist_type,
                    error=str(e)
                )

                shadow_validations_total.labels(
                    specialist_type=self.specialist_type,
                    result='error'
                ).inc()

                return ShadowValidationResult(
                    passed=False,
                    validation_id=validation_id,
                    specialist_type=self.specialist_type,
                    metrics={'error': str(e)},
                    failures=[f"Erro durante validação: {str(e)}"],
                    timestamp=datetime.utcnow()
                )

    def get_validation_summary(self, window_size: int = 10) -> Dict[str, Any]:
        """
        Retorna resumo das últimas validações.

        Args:
            window_size: Número de validações a considerar

        Returns:
            Dict com resumo de validações
        """
        recent = self._validation_history[-window_size:]

        if not recent:
            return {
                'total_validations': 0,
                'pass_rate': 0.0,
                'avg_kl_divergence': 0.0,
                'avg_latency_ratio': 0.0,
                'common_failures': []
            }

        passed_count = sum(1 for r in recent if r.passed)
        kl_values = [r.metrics.get('kl_divergence', 0) for r in recent]
        latency_ratios = [r.metrics.get('latency_ratio', 1) for r in recent]

        # Contar falhas comuns
        all_failures = []
        for r in recent:
            all_failures.extend(r.failures)

        failure_counts = {}
        for f in all_failures:
            # Extrair tipo de falha
            failure_type = f.split(':')[0] if ':' in f else f[:50]
            failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1

        common_failures = sorted(
            failure_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return {
            'total_validations': len(recent),
            'pass_rate': passed_count / len(recent),
            'avg_kl_divergence': float(np.mean(kl_values)),
            'avg_latency_ratio': float(np.mean(latency_ratios)),
            'avg_accuracy_ratio': float(np.mean([
                r.metrics.get('accuracy_ratio', 1.0)
                for r in recent
                if 'accuracy_ratio' in r.metrics
            ])) if any('accuracy_ratio' in r.metrics for r in recent) else None,
            'common_failures': [
                {'type': f[0], 'count': f[1]}
                for f in common_failures
            ],
            'last_validation': recent[-1].to_dict() if recent else None
        }

    def should_approve_deployment(self) -> Tuple[bool, str]:
        """
        Determina se deployment deve ser aprovado baseado em histórico.

        Returns:
            Tuple (approved, reason)
        """
        if not self._validation_history:
            return False, "Nenhuma validação executada ainda"

        # Verificar última validação
        last_result = self._validation_history[-1]
        if not last_result.passed:
            return False, f"Última validação falhou: {', '.join(last_result.failures)}"

        # Verificar taxa de sucesso recente
        summary = self.get_validation_summary(window_size=5)
        if summary['pass_rate'] < 0.8:
            return False, f"Taxa de sucesso baixa: {summary['pass_rate']:.1%}"

        # Verificar tendência de KL divergence
        recent_kl = [
            r.metrics.get('kl_divergence', 0)
            for r in self._validation_history[-5:]
        ]
        if len(recent_kl) >= 3:
            if recent_kl[-1] > recent_kl[-3] * 1.2:  # KL aumentando
                return False, f"KL divergence aumentando: {recent_kl[-1]:.4f}"

        return True, "Todas as validações passaram"
