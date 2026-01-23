"""
Comparador de Modelos ML para análise detalhada pré-promoção.

Executa comparações estatísticas e visuais entre modelo candidato e modelo atual,
gerando relatórios HTML interativos para suportar decisões de promoção.
"""

import asyncio
import base64
import io
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import numpy as np
import structlog
from scipy import stats as scipy_stats

if TYPE_CHECKING:
    from .model_registry import ModelRegistry

logger = structlog.get_logger(__name__)


@dataclass
class ComparisonResult:
    """Resultado da comparação entre modelos."""

    model_name: str
    current_version: str
    candidate_version: str

    # Métricas
    metrics_comparison: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Testes estatísticos
    statistical_tests: Dict[str, Any] = field(default_factory=dict)

    # Fairness
    fairness_analysis: Dict[str, Any] = field(default_factory=dict)

    # Visualizações (base64)
    visualizations: Dict[str, str] = field(default_factory=dict)

    # Recomendação
    recommendation: str = 'manual_review'  # 'promote', 'reject', 'manual_review'
    recommendation_reason: str = ''
    confidence_score: float = 0.5

    # Metadados
    compared_at: datetime = field(default_factory=datetime.utcnow)
    test_samples_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        result = asdict(self)
        result['compared_at'] = self.compared_at.isoformat()
        return result


class ModelComparator:
    """
    Compara modelos ML candidato vs atual com análises estatísticas e visuais.

    Funcionalidades:
    - Comparação de métricas (F1, precision, recall, MAE, latency)
    - Testes estatísticos (McNemar, paired t-test)
    - Análise de fairness por task_type, domain, security_level
    - Geração de visualizações (confusion matrix, error distribution, feature importance)
    - Relatório HTML interativo
    - Salvamento como artifact MLflow
    """

    def __init__(
        self,
        config,
        model_registry: 'ModelRegistry',
        mongodb_client=None,
        metrics=None,
        logger=None
    ):
        """
        Inicializa o comparador.

        Args:
            config: Configuração do orchestrator
            model_registry: ModelRegistry instance
            mongodb_client: Cliente MongoDB (opcional)
            metrics: OrchestratorMetrics (opcional)
            logger: Logger estruturado (opcional)
        """
        self.config = config
        self.model_registry = model_registry
        self.mongodb_client = mongodb_client
        self.metrics = metrics
        self.logger = logger or structlog.get_logger(__name__).bind(
            component='model_comparator'
        )

        # Thresholds de comparação
        self.mae_threshold = getattr(config, 'ml_validation_mae_threshold', 0.15)
        self.improvement_threshold = 0.02  # 2% melhoria mínima para recomendar promoção
        self.degradation_threshold = 0.05  # 5% piora para recomendar rejeição
        self.confidence_threshold = getattr(
            config, 'ml_comparison_confidence_threshold', 0.7
        )

    async def compare_models(
        self,
        model_name: str,
        current_version: str,
        candidate_version: str,
        test_data: Dict[str, Any],
        confidence_threshold: Optional[float] = None
    ) -> ComparisonResult:
        """
        Executa comparação completa entre modelos.

        Args:
            model_name: Nome do modelo
            current_version: Versão atual em produção
            candidate_version: Versão candidata
            test_data: Dados de teste com X_test, y_test, metadata
            confidence_threshold: Threshold de confiança para recomendação (override)

        Returns:
            ComparisonResult com análise completa
        """
        # Usar threshold injetado ou default
        effective_confidence_threshold = (
            confidence_threshold if confidence_threshold is not None
            else self.confidence_threshold
        )
        start_time = time.time()

        self.logger.info(
            'starting_model_comparison',
            model_name=model_name,
            current_version=current_version,
            candidate_version=candidate_version,
            test_samples=len(test_data.get('y_test', []))
        )

        result = ComparisonResult(
            model_name=model_name,
            current_version=current_version,
            candidate_version=candidate_version,
            test_samples_count=len(test_data.get('y_test', []))
        )

        try:
            # Carregar modelos
            current_model = await self.model_registry.load_model(
                model_name=model_name,
                version=current_version
            )
            candidate_model = await self.model_registry.load_model(
                model_name=model_name,
                version=candidate_version
            )

            if not current_model or not candidate_model:
                result.recommendation = 'reject'
                result.recommendation_reason = 'Falha ao carregar modelos'
                result.confidence_score = 0.0
                return result

            # Extrair dados de teste
            X_test = np.array(test_data['X_test'])
            y_test = np.array(test_data['y_test'])
            metadata = test_data.get('metadata', {})

            # Executar predições com coleta de latências
            current_preds, current_latencies = await self._predict(
                current_model, X_test, collect_latencies=True
            )
            candidate_preds, candidate_latencies = await self._predict(
                candidate_model, X_test, collect_latencies=True
            )

            if current_preds is None or candidate_preds is None:
                result.recommendation = 'reject'
                result.recommendation_reason = 'Falha ao executar predições'
                result.confidence_score = 0.0
                return result

            # Determinar tipo de modelo
            model_type = self._determine_model_type(model_name, y_test)

            # Comparar métricas
            result.metrics_comparison = self._compare_metrics(
                y_test, current_preds, candidate_preds, model_type
            )

            # Adicionar métricas de latência
            if current_latencies and candidate_latencies:
                latency_metrics = self._compare_latency_metrics(
                    current_latencies, candidate_latencies
                )
                result.metrics_comparison.update(latency_metrics)

            # Testes estatísticos
            result.statistical_tests = self._statistical_tests(
                y_test, current_preds, candidate_preds, model_type
            )

            # Análise de fairness
            result.fairness_analysis = self._fairness_analysis(
                y_test, current_preds, candidate_preds, metadata, model_type
            )

            # Gerar visualizações
            result.visualizations = self._generate_visualizations(
                y_test, current_preds, candidate_preds, model_type,
                current_model, candidate_model
            )

            # Determinar recomendação
            self._determine_recommendation(result, effective_confidence_threshold)

            duration = time.time() - start_time

            # Registrar métricas Prometheus
            if self.metrics:
                try:
                    self.metrics.ml_model_comparison_total.labels(
                        model_name=model_name,
                        recommendation=result.recommendation
                    ).inc()
                    self.metrics.ml_model_comparison_duration_seconds.labels(
                        model_name=model_name
                    ).observe(duration)
                    self.metrics.ml_model_comparison_confidence.labels(
                        model_name=model_name
                    ).set(result.confidence_score)
                except Exception as e:
                    self.logger.warning('metrics_recording_failed', error=str(e))

            self.logger.info(
                'model_comparison_completed',
                model_name=model_name,
                recommendation=result.recommendation,
                confidence=result.confidence_score,
                duration_seconds=duration
            )

            return result

        except Exception as e:
            self.logger.error(
                'model_comparison_failed',
                model_name=model_name,
                error=str(e)
            )
            result.recommendation = 'manual_review'
            result.recommendation_reason = f'Erro na comparação: {str(e)}'
            result.confidence_score = 0.0
            return result

    async def _predict(
        self,
        model,
        X: np.ndarray,
        collect_latencies: bool = False
    ) -> tuple[Optional[np.ndarray], Optional[List[float]]]:
        """
        Executa predição com modelo.

        Args:
            model: Modelo a usar para predição
            X: Dados de entrada
            collect_latencies: Se True, coleta latência por predição individual

        Returns:
            Tuple (predições, latências em ms) - latências é None se collect_latencies=False
        """
        try:
            if not hasattr(model, 'predict'):
                return None, None

            if collect_latencies:
                # Executar predições individuais para coletar latências
                latencies = []
                predictions = []
                for i in range(len(X)):
                    start_time = time.time()
                    pred = await asyncio.to_thread(model.predict, X[i:i+1])
                    latency_ms = (time.time() - start_time) * 1000
                    latencies.append(latency_ms)
                    predictions.append(pred[0])
                return np.array(predictions), latencies
            else:
                preds = await asyncio.to_thread(model.predict, X)
                return preds, None

        except Exception as e:
            self.logger.error('prediction_failed', error=str(e))
            return None, None

    def _determine_model_type(self, model_name: str, y: np.ndarray) -> str:
        """Determina tipo de modelo (classification ou regression)."""
        if 'anomaly' in model_name.lower() or 'classifier' in model_name.lower():
            return 'classification'
        if 'duration' in model_name.lower() or 'predictor' in model_name.lower():
            return 'regression'

        # Inferir pelo target
        unique_values = np.unique(y)
        if len(unique_values) <= 10 and all(isinstance(v, (int, np.integer, bool)) for v in unique_values):
            return 'classification'
        return 'regression'

    def _compare_metrics(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray,
        model_type: str
    ) -> Dict[str, Dict[str, float]]:
        """
        Compara métricas entre modelos.

        Returns:
            Dict com métricas e comparação
        """
        from sklearn.metrics import (
            mean_absolute_error, mean_squared_error, r2_score,
            precision_score, recall_score, f1_score, accuracy_score
        )

        metrics_comparison = {}

        if model_type == 'regression':
            # MAE
            current_mae = mean_absolute_error(y_true, current_preds)
            candidate_mae = mean_absolute_error(y_true, candidate_preds)
            diff_pct = ((candidate_mae - current_mae) / current_mae * 100) if current_mae > 0 else 0
            metrics_comparison['mae'] = {
                'current': float(current_mae),
                'candidate': float(candidate_mae),
                'diff_pct': float(diff_pct),
                'improved': candidate_mae < current_mae
            }

            # RMSE
            current_rmse = np.sqrt(mean_squared_error(y_true, current_preds))
            candidate_rmse = np.sqrt(mean_squared_error(y_true, candidate_preds))
            diff_pct = ((candidate_rmse - current_rmse) / current_rmse * 100) if current_rmse > 0 else 0
            metrics_comparison['rmse'] = {
                'current': float(current_rmse),
                'candidate': float(candidate_rmse),
                'diff_pct': float(diff_pct),
                'improved': candidate_rmse < current_rmse
            }

            # R²
            current_r2 = r2_score(y_true, current_preds)
            candidate_r2 = r2_score(y_true, candidate_preds)
            diff_pct = ((candidate_r2 - current_r2) / abs(current_r2) * 100) if current_r2 != 0 else 0
            metrics_comparison['r2'] = {
                'current': float(current_r2),
                'candidate': float(candidate_r2),
                'diff_pct': float(diff_pct),
                'improved': candidate_r2 > current_r2
            }

            # MAE Percentage (se valores são positivos)
            if np.mean(y_true) > 0:
                current_mae_pct = current_mae / np.mean(y_true) * 100
                candidate_mae_pct = candidate_mae / np.mean(y_true) * 100
                metrics_comparison['mae_pct'] = {
                    'current': float(current_mae_pct),
                    'candidate': float(candidate_mae_pct),
                    'diff_pct': float(candidate_mae_pct - current_mae_pct),
                    'improved': candidate_mae_pct < current_mae_pct
                }

        else:  # classification
            # Accuracy
            current_acc = accuracy_score(y_true, current_preds)
            candidate_acc = accuracy_score(y_true, candidate_preds)
            diff_pct = ((candidate_acc - current_acc) / current_acc * 100) if current_acc > 0 else 0
            metrics_comparison['accuracy'] = {
                'current': float(current_acc),
                'candidate': float(candidate_acc),
                'diff_pct': float(diff_pct),
                'improved': candidate_acc > current_acc
            }

            # Precision, Recall, F1 (para binário ou média macro)
            average = 'binary' if len(np.unique(y_true)) == 2 else 'macro'

            try:
                current_prec = precision_score(y_true, current_preds, average=average, zero_division=0)
                candidate_prec = precision_score(y_true, candidate_preds, average=average, zero_division=0)
                diff_pct = ((candidate_prec - current_prec) / current_prec * 100) if current_prec > 0 else 0
                metrics_comparison['precision'] = {
                    'current': float(current_prec),
                    'candidate': float(candidate_prec),
                    'diff_pct': float(diff_pct),
                    'improved': candidate_prec > current_prec
                }
            except Exception:
                pass

            try:
                current_rec = recall_score(y_true, current_preds, average=average, zero_division=0)
                candidate_rec = recall_score(y_true, candidate_preds, average=average, zero_division=0)
                diff_pct = ((candidate_rec - current_rec) / current_rec * 100) if current_rec > 0 else 0
                metrics_comparison['recall'] = {
                    'current': float(current_rec),
                    'candidate': float(candidate_rec),
                    'diff_pct': float(diff_pct),
                    'improved': candidate_rec > current_rec
                }
            except Exception:
                pass

            try:
                current_f1 = f1_score(y_true, current_preds, average=average, zero_division=0)
                candidate_f1 = f1_score(y_true, candidate_preds, average=average, zero_division=0)
                diff_pct = ((candidate_f1 - current_f1) / current_f1 * 100) if current_f1 > 0 else 0
                metrics_comparison['f1_score'] = {
                    'current': float(current_f1),
                    'candidate': float(candidate_f1),
                    'diff_pct': float(diff_pct),
                    'improved': candidate_f1 > current_f1
                }
            except Exception:
                pass

        return metrics_comparison

    def _compare_latency_metrics(
        self,
        current_latencies: List[float],
        candidate_latencies: List[float]
    ) -> Dict[str, Dict[str, float]]:
        """
        Compara métricas de latência entre modelos.

        Args:
            current_latencies: Latências do modelo atual (ms)
            candidate_latencies: Latências do modelo candidato (ms)

        Returns:
            Dict com métricas p50, p95, p99 e comparações
        """
        latency_metrics = {}

        current_arr = np.array(current_latencies)
        candidate_arr = np.array(candidate_latencies)

        # P50 (mediana)
        current_p50 = float(np.percentile(current_arr, 50))
        candidate_p50 = float(np.percentile(candidate_arr, 50))
        diff_pct = ((candidate_p50 - current_p50) / current_p50 * 100) if current_p50 > 0 else 0
        latency_metrics['latency_p50_ms'] = {
            'current': current_p50,
            'candidate': candidate_p50,
            'diff_pct': float(diff_pct),
            'improved': candidate_p50 < current_p50
        }

        # P95
        current_p95 = float(np.percentile(current_arr, 95))
        candidate_p95 = float(np.percentile(candidate_arr, 95))
        diff_pct = ((candidate_p95 - current_p95) / current_p95 * 100) if current_p95 > 0 else 0
        latency_metrics['latency_p95_ms'] = {
            'current': current_p95,
            'candidate': candidate_p95,
            'diff_pct': float(diff_pct),
            'improved': candidate_p95 < current_p95
        }

        # P99
        current_p99 = float(np.percentile(current_arr, 99))
        candidate_p99 = float(np.percentile(candidate_arr, 99))
        diff_pct = ((candidate_p99 - current_p99) / current_p99 * 100) if current_p99 > 0 else 0
        latency_metrics['latency_p99_ms'] = {
            'current': current_p99,
            'candidate': candidate_p99,
            'diff_pct': float(diff_pct),
            'improved': candidate_p99 < current_p99
        }

        return latency_metrics

    def _statistical_tests(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray,
        model_type: str
    ) -> Dict[str, Any]:
        """
        Executa testes estatísticos.

        Returns:
            Dict com resultados dos testes
        """
        results = {}

        if model_type == 'classification':
            results['mcnemar_test'] = self._mcnemar_test(y_true, current_preds, candidate_preds)
        else:
            results['paired_ttest'] = self._paired_ttest(y_true, current_preds, candidate_preds)

        return results

    def _mcnemar_test(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray
    ) -> Dict[str, Any]:
        """
        McNemar test para classificação.

        Testa se há diferença significativa entre os modelos.
        """
        from scipy.stats import chi2

        # Criar tabela de contingência
        current_correct = (current_preds == y_true)
        candidate_correct = (candidate_preds == y_true)

        b = np.sum(current_correct & ~candidate_correct)  # Current certo, Candidate errado
        c = np.sum(~current_correct & candidate_correct)  # Current errado, Candidate certo

        # McNemar statistic
        if b + c == 0:
            return {
                'statistic': 0.0,
                'p_value': 1.0,
                'significant': False,
                'interpretation': 'Modelos têm performance idêntica',
                'b': int(b),
                'c': int(c)
            }

        statistic = ((abs(b - c) - 1) ** 2) / (b + c)
        p_value = 1 - chi2.cdf(statistic, df=1)

        significant = p_value < 0.05

        if significant:
            if c > b:
                interpretation = 'Candidato é significativamente melhor'
            else:
                interpretation = 'Modelo atual é significativamente melhor'
        else:
            interpretation = 'Não há diferença significativa'

        return {
            'statistic': float(statistic),
            'p_value': float(p_value),
            'significant': significant,
            'interpretation': interpretation,
            'b': int(b),
            'c': int(c)
        }

    def _paired_ttest(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray
    ) -> Dict[str, Any]:
        """
        Paired t-test para regressão.

        Testa se há diferença significativa nos erros.
        """
        current_errors = np.abs(current_preds - y_true)
        candidate_errors = np.abs(candidate_preds - y_true)

        statistic, p_value = scipy_stats.ttest_rel(current_errors, candidate_errors)

        significant = p_value < 0.05

        mean_current = float(np.mean(current_errors))
        mean_candidate = float(np.mean(candidate_errors))

        if significant:
            if mean_candidate < mean_current:
                interpretation = 'Candidato tem erros significativamente menores'
            else:
                interpretation = 'Modelo atual tem erros significativamente menores'
        else:
            interpretation = 'Não há diferença significativa nos erros'

        return {
            'statistic': float(statistic),
            'p_value': float(p_value),
            'significant': significant,
            'interpretation': interpretation,
            'mean_current_error': mean_current,
            'mean_candidate_error': mean_candidate
        }

    def _fairness_analysis(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray,
        metadata: Dict[str, Any],
        model_type: str = 'regression'
    ) -> Dict[str, Any]:
        """
        Análise de fairness por grupos.

        Compara performance por task_type, domain, security_level.
        Usa métricas apropriadas baseadas no tipo de modelo:
        - Classificação: accuracy ou F1 score
        - Regressão: MAE

        Args:
            y_true: Valores reais
            current_preds: Predições do modelo atual
            candidate_preds: Predições do modelo candidato
            metadata: Metadados com campos de grupo
            model_type: 'classification' ou 'regression'
        """
        from sklearn.metrics import accuracy_score, f1_score

        fairness_results = {}

        group_fields = ['task_type', 'domain', 'security_level']

        # Determinar nome da métrica baseado no tipo de modelo
        if model_type == 'classification':
            metric_name = 'accuracy'
        else:
            metric_name = 'mae'

        for group_field in group_fields:
            if group_field not in metadata:
                continue

            groups = np.array(metadata[group_field])
            unique_groups = np.unique(groups)

            if len(unique_groups) <= 1:
                continue

            group_metrics = {}
            for group in unique_groups:
                mask = groups == group
                if np.sum(mask) < 10:  # Mínimo de amostras
                    continue

                if model_type == 'classification':
                    # Usar accuracy para classificação
                    current_metric = float(accuracy_score(y_true[mask], current_preds[mask]))
                    candidate_metric = float(accuracy_score(y_true[mask], candidate_preds[mask]))
                    # Para accuracy, melhoria = candidato > atual
                    improvement = ((candidate_metric - current_metric) / current_metric * 100) if current_metric > 0 else 0
                else:
                    # Usar MAE para regressão
                    current_metric = float(np.mean(np.abs(current_preds[mask] - y_true[mask])))
                    candidate_metric = float(np.mean(np.abs(candidate_preds[mask] - y_true[mask])))
                    # Para MAE, melhoria = atual > candidato (menor é melhor)
                    improvement = ((current_metric - candidate_metric) / current_metric * 100) if current_metric > 0 else 0

                group_metrics[str(group)] = {
                    f'current_{metric_name}': current_metric,
                    f'candidate_{metric_name}': candidate_metric,
                    'improvement_pct': float(improvement),
                    'sample_count': int(np.sum(mask))
                }

            if group_metrics:
                # Calcular disparity ratio
                metrics_values = [
                    m[f'candidate_{metric_name}'] for m in group_metrics.values()
                ]
                if len(metrics_values) > 1 and min(metrics_values) > 0:
                    disparity_ratio = max(metrics_values) / min(metrics_values)
                else:
                    disparity_ratio = 1.0

                fairness_results[group_field] = {
                    'groups': group_metrics,
                    'disparity_ratio': float(disparity_ratio),
                    'is_fair': disparity_ratio < 2.0,
                    'metric_type': metric_name
                }

        return fairness_results

    def _generate_visualizations(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray,
        model_type: str,
        current_model: Any = None,
        candidate_model: Any = None
    ) -> Dict[str, str]:
        """
        Gera visualizações como base64.

        Returns:
            Dict com nome da viz e imagem base64
        """
        visualizations = {}

        try:
            if model_type == 'classification':
                viz = self._generate_confusion_matrix(y_true, current_preds, candidate_preds)
                if viz:
                    visualizations['confusion_matrix'] = viz
            else:
                viz = self._generate_error_distribution(y_true, current_preds, candidate_preds)
                if viz:
                    visualizations['error_distribution'] = viz

            # Feature importance diff
            if current_model and candidate_model:
                feature_names = getattr(current_model, 'feature_names_in_', None)
                if feature_names is None:
                    # Gerar nomes genéricos
                    if hasattr(current_model, 'feature_importances_'):
                        n_features = len(current_model.feature_importances_)
                        feature_names = [f'feature_{i}' for i in range(n_features)]

                if feature_names is not None:
                    viz = self._generate_feature_importance_diff(
                        current_model, candidate_model, list(feature_names)
                    )
                    if viz:
                        visualizations['feature_importance_diff'] = viz

            # Prediction scatter
            viz = self._generate_prediction_scatter(y_true, current_preds, candidate_preds)
            if viz:
                visualizations['prediction_scatter'] = viz

        except Exception as e:
            self.logger.warning('visualization_generation_failed', error=str(e))

        return visualizations

    def _generate_confusion_matrix(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray
    ) -> Optional[str]:
        """Gera confusion matrix comparativa."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import seaborn as sns
            from sklearn.metrics import confusion_matrix

            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            # Current model
            cm_current = confusion_matrix(y_true, current_preds)
            sns.heatmap(cm_current, annot=True, fmt='d', ax=axes[0], cmap='Blues')
            axes[0].set_title('Modelo Atual')
            axes[0].set_ylabel('Label Real')
            axes[0].set_xlabel('Label Predito')

            # Candidate model
            cm_candidate = confusion_matrix(y_true, candidate_preds)
            sns.heatmap(cm_candidate, annot=True, fmt='d', ax=axes[1], cmap='Greens')
            axes[1].set_title('Modelo Candidato')
            axes[1].set_ylabel('Label Real')
            axes[1].set_xlabel('Label Predito')

            plt.tight_layout()

            # Convert to base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)

            return image_base64

        except Exception as e:
            self.logger.warning('confusion_matrix_generation_failed', error=str(e))
            return None

    def _generate_error_distribution(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray
    ) -> Optional[str]:
        """Gera histograma de distribuição de erros."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            current_errors = current_preds - y_true
            candidate_errors = candidate_preds - y_true

            fig, ax = plt.subplots(figsize=(10, 6))

            ax.hist(current_errors, bins=50, alpha=0.5, label='Modelo Atual', color='blue')
            ax.hist(candidate_errors, bins=50, alpha=0.5, label='Modelo Candidato', color='green')

            ax.axvline(
                np.mean(current_errors), color='blue', linestyle='--',
                label=f'Média Atual: {np.mean(current_errors):.2f}'
            )
            ax.axvline(
                np.mean(candidate_errors), color='green', linestyle='--',
                label=f'Média Candidato: {np.mean(candidate_errors):.2f}'
            )

            ax.set_xlabel('Erro de Predição')
            ax.set_ylabel('Frequência')
            ax.set_title('Distribuição de Erros')
            ax.legend()
            ax.grid(True, alpha=0.3)

            # Convert to base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)

            return image_base64

        except Exception as e:
            self.logger.warning('error_distribution_generation_failed', error=str(e))
            return None

    def _generate_feature_importance_diff(
        self,
        current_model: Any,
        candidate_model: Any,
        feature_names: List[str]
    ) -> Optional[str]:
        """Gera gráfico de diferença de feature importance."""
        if not (hasattr(current_model, 'feature_importances_') and
                hasattr(candidate_model, 'feature_importances_')):
            return None

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            current_imp = current_model.feature_importances_
            candidate_imp = candidate_model.feature_importances_

            # Calcular diferença
            diff = candidate_imp - current_imp

            # Ordenar por diferença absoluta
            indices = np.argsort(np.abs(diff))[-20:]  # Top 20

            fig, ax = plt.subplots(figsize=(10, 8))

            y_pos = np.arange(len(indices))
            colors = ['green' if d > 0 else 'red' for d in diff[indices]]

            ax.barh(y_pos, diff[indices], color=colors, alpha=0.7)
            ax.set_yticks(y_pos)
            ax.set_yticklabels([feature_names[i] for i in indices])
            ax.set_xlabel('Diferença de Importância (Candidato - Atual)')
            ax.set_title('Mudanças em Feature Importance (Top 20)')
            ax.axvline(0, color='black', linestyle='--', linewidth=0.8)
            ax.grid(True, alpha=0.3, axis='x')

            plt.tight_layout()

            # Convert to base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)

            return image_base64

        except Exception as e:
            self.logger.warning('feature_importance_diff_generation_failed', error=str(e))
            return None

    def _generate_prediction_scatter(
        self,
        y_true: np.ndarray,
        current_preds: np.ndarray,
        candidate_preds: np.ndarray
    ) -> Optional[str]:
        """Gera scatter plot de predições."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(12, 5))

            # Current model
            axes[0].scatter(y_true, current_preds, alpha=0.5, s=10)
            axes[0].plot([y_true.min(), y_true.max()], [y_true.min(), y_true.max()], 'r--', lw=2)
            axes[0].set_xlabel('Valor Real')
            axes[0].set_ylabel('Valor Predito')
            axes[0].set_title('Modelo Atual')
            axes[0].grid(True, alpha=0.3)

            # Candidate model
            axes[1].scatter(y_true, candidate_preds, alpha=0.5, s=10, color='green')
            axes[1].plot([y_true.min(), y_true.max()], [y_true.min(), y_true.max()], 'r--', lw=2)
            axes[1].set_xlabel('Valor Real')
            axes[1].set_ylabel('Valor Predito')
            axes[1].set_title('Modelo Candidato')
            axes[1].grid(True, alpha=0.3)

            plt.tight_layout()

            # Convert to base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)

            return image_base64

        except Exception as e:
            self.logger.warning('prediction_scatter_generation_failed', error=str(e))
            return None

    def _determine_recommendation(
        self,
        result: ComparisonResult,
        confidence_threshold: Optional[float] = None
    ) -> None:
        """
        Determina recomendação baseada em métricas e testes.

        Args:
            result: ComparisonResult a modificar in-place
            confidence_threshold: Threshold de confiança para recomendar promoção (override)

        Modifica result in-place.
        """
        # Usar threshold injetado ou default da instância
        effective_threshold = (
            confidence_threshold if confidence_threshold is not None
            else self.confidence_threshold
        )
        confidence_factors = []
        reasons = []

        # Avaliar métricas
        improved_metrics = 0
        degraded_metrics = 0
        total_metrics = len(result.metrics_comparison)

        for metric, values in result.metrics_comparison.items():
            if values.get('improved', False):
                improved_metrics += 1
                if abs(values.get('diff_pct', 0)) >= self.improvement_threshold * 100:
                    confidence_factors.append(0.2)
                    reasons.append(f'{metric} melhorou {abs(values["diff_pct"]):.1f}%')
            else:
                if abs(values.get('diff_pct', 0)) >= self.degradation_threshold * 100:
                    degraded_metrics += 1
                    confidence_factors.append(-0.3)
                    reasons.append(f'{metric} piorou {abs(values["diff_pct"]):.1f}%')

        # Avaliar testes estatísticos
        for test_name, test_result in result.statistical_tests.items():
            if test_result.get('significant', False):
                if 'melhor' in test_result.get('interpretation', '').lower():
                    if 'candidato' in test_result.get('interpretation', '').lower():
                        confidence_factors.append(0.3)
                        reasons.append(f'{test_name}: candidato significativamente melhor')
                    else:
                        confidence_factors.append(-0.3)
                        reasons.append(f'{test_name}: atual significativamente melhor')
            else:
                confidence_factors.append(0.0)

        # Avaliar fairness
        for group_field, analysis in result.fairness_analysis.items():
            if analysis.get('is_fair', True):
                confidence_factors.append(0.1)
            else:
                confidence_factors.append(-0.2)
                reasons.append(f'Disparidade de fairness em {group_field}')

        # Calcular confidence score
        base_confidence = 0.5
        if confidence_factors:
            confidence_adjustment = sum(confidence_factors) / len(confidence_factors)
            result.confidence_score = max(0.0, min(1.0, base_confidence + confidence_adjustment))
        else:
            result.confidence_score = base_confidence

        # Determinar recomendação
        if total_metrics > 0:
            improvement_ratio = improved_metrics / total_metrics
        else:
            improvement_ratio = 0.5

        if result.confidence_score >= effective_threshold and improvement_ratio >= 0.6:
            result.recommendation = 'promote'
            result.recommendation_reason = 'Candidato apresenta melhorias significativas. ' + '; '.join(reasons[:3])
        elif result.confidence_score < 0.3 or degraded_metrics >= total_metrics * 0.5:
            result.recommendation = 'reject'
            result.recommendation_reason = 'Candidato apresenta degradação significativa. ' + '; '.join(reasons[:3])
        else:
            result.recommendation = 'manual_review'
            result.recommendation_reason = 'Resultados inconclusivos, revisão manual recomendada. ' + '; '.join(reasons[:3])

    def _generate_html_report(self, result: ComparisonResult) -> str:
        """
        Gera relatório HTML.

        Args:
            result: ComparisonResult

        Returns:
            String HTML
        """
        from jinja2 import Template

        template_path = Path(__file__).parent / 'templates' / 'model_comparison_report.html'

        if template_path.exists():
            with open(template_path, 'r') as f:
                template_str = f.read()
        else:
            # Template inline como fallback
            template_str = self._get_inline_template()

        template = Template(template_str)

        # Determinar classe CSS da recomendação
        recommendation_class = {
            'promote': 'recommendation-promote',
            'reject': 'recommendation-reject',
            'manual_review': 'recommendation-review'
        }.get(result.recommendation, 'recommendation-review')

        html = template.render(
            model_name=result.model_name,
            current_version=result.current_version,
            candidate_version=result.candidate_version,
            recommendation=result.recommendation,
            recommendation_class=recommendation_class,
            recommendation_reason=result.recommendation_reason,
            confidence_score=round(result.confidence_score * 100, 1),
            metrics_comparison=result.metrics_comparison,
            statistical_tests=result.statistical_tests,
            fairness_analysis=result.fairness_analysis,
            visualizations=result.visualizations,
            compared_at=result.compared_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            test_samples_count=result.test_samples_count
        )

        return html

    def _get_inline_template(self) -> str:
        """Retorna template HTML inline como fallback."""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Relatório de Comparação: {{ model_name }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
        h2 { color: #555; margin-top: 30px; }
        h3 { color: #666; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 12px; text-align: left; border: 1px solid #ddd; }
        th { background: #f8f9fa; }
        .metric-improved { color: #28a745; font-weight: bold; }
        .metric-degraded { color: #dc3545; font-weight: bold; }
        .recommendation-promote { background: #d4edda; padding: 15px; border-radius: 5px; border-left: 4px solid #28a745; }
        .recommendation-reject { background: #f8d7da; padding: 15px; border-radius: 5px; border-left: 4px solid #dc3545; }
        .recommendation-review { background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107; }
        .visualization img { max-width: 100%; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }
        .summary { margin-bottom: 30px; }
        footer { margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Relatório de Comparação de Modelos</h1>
        <p><strong>Modelo:</strong> {{ model_name }}</p>
        <p><strong>Versão Atual:</strong> {{ current_version }} | <strong>Versão Candidata:</strong> {{ candidate_version }}</p>

        <section class="summary">
            <h2>Resumo Executivo</h2>
            <div class="{{ recommendation_class }}">
                <strong>Recomendação:</strong> {{ recommendation | upper }}
                <p>{{ recommendation_reason }}</p>
                <p><strong>Confiança:</strong> {{ confidence_score }}%</p>
            </div>
        </section>

        <section class="metrics">
            <h2>Comparação de Métricas de Performance</h2>
            <table>
                <thead>
                    <tr><th>Métrica</th><th>Atual</th><th>Candidato</th><th>Variação</th></tr>
                </thead>
                <tbody>
                    {% for metric, values in metrics_comparison.items() %}
                    {% if not metric.startswith('latency_') %}
                    <tr>
                        <td>{{ metric }}</td>
                        <td>{{ "%.4f"|format(values.current) }}</td>
                        <td>{{ "%.4f"|format(values.candidate) }}</td>
                        <td class="{{ 'metric-improved' if values.improved else 'metric-degraded' }}">
                            {{ "%.2f"|format(values.diff_pct) }}%
                        </td>
                    </tr>
                    {% endif %}
                    {% endfor %}
                </tbody>
            </table>
        </section>

        {% set has_latency = metrics_comparison.get('latency_p50_ms') %}
        {% if has_latency %}
        <section class="latency">
            <h2>Comparação de Latência</h2>
            <table>
                <thead>
                    <tr><th>Percentil</th><th>Atual (ms)</th><th>Candidato (ms)</th><th>Variação</th></tr>
                </thead>
                <tbody>
                    {% for metric, values in metrics_comparison.items() %}
                    {% if metric.startswith('latency_') %}
                    <tr>
                        <td>{{ metric | replace('latency_', '') | replace('_ms', '') | upper }}</td>
                        <td>{{ "%.2f"|format(values.current) }}</td>
                        <td>{{ "%.2f"|format(values.candidate) }}</td>
                        <td class="{{ 'metric-improved' if values.improved else 'metric-degraded' }}">
                            {{ "%.2f"|format(values.diff_pct) }}%
                        </td>
                    </tr>
                    {% endif %}
                    {% endfor %}
                </tbody>
            </table>
        </section>
        {% endif %}

        <section class="statistical-tests">
            <h2>Testes Estatísticos</h2>
            {% for test_name, result in statistical_tests.items() %}
            <div class="test-result">
                <h3>{{ test_name }}</h3>
                <p><strong>Estatística:</strong> {{ "%.4f"|format(result.statistic) }}</p>
                <p><strong>P-valor:</strong> {{ "%.4f"|format(result.p_value) }}</p>
                <p><strong>Significativo:</strong> {{ "Sim" if result.significant else "Não" }}</p>
                <p><strong>Interpretação:</strong> {{ result.interpretation }}</p>
            </div>
            {% endfor %}
        </section>

        {% if fairness_analysis %}
        <section class="fairness">
            <h2>Análise de Fairness</h2>
            {% for group_field, analysis in fairness_analysis.items() %}
            {% set metric_type = analysis.get('metric_type', 'mae') %}
            {% set metric_label = 'Accuracy' if metric_type == 'accuracy' else 'MAE' %}
            <h3>{{ group_field }}</h3>
            <p><strong>Ratio de Disparidade:</strong> {{ "%.2f"|format(analysis.disparity_ratio) }}
               ({{ "Justo" if analysis.is_fair else "Injusto" }}) - Métrica: {{ metric_label }}</p>
            <table>
                <thead>
                    <tr><th>Grupo</th><th>{{ metric_label }} Atual</th><th>{{ metric_label }} Candidato</th><th>Melhoria</th></tr>
                </thead>
                <tbody>
                    {% for group, metrics in analysis.groups.items() %}
                    {% set current_key = 'current_' ~ metric_type %}
                    {% set candidate_key = 'candidate_' ~ metric_type %}
                    <tr>
                        <td>{{ group }}</td>
                        <td>{{ "%.4f"|format(metrics.get(current_key, metrics.get('current_mae', 0))) }}</td>
                        <td>{{ "%.4f"|format(metrics.get(candidate_key, metrics.get('candidate_mae', 0))) }}</td>
                        <td>{{ "%.2f"|format(metrics.improvement_pct) }}%</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endfor %}
        </section>
        {% endif %}

        {% if visualizations %}
        <section class="visualizations">
            <h2>Visualizações</h2>
            {% for viz_name, base64_img in visualizations.items() %}
            <div class="visualization">
                <h3>{{ viz_name | replace("_", " ") | title }}</h3>
                <img src="data:image/png;base64,{{ base64_img }}" alt="{{ viz_name }}">
            </div>
            {% endfor %}
        </section>
        {% endif %}

        <footer>
            <p><strong>Gerado em:</strong> {{ compared_at }}</p>
            <p><strong>Amostras de teste:</strong> {{ test_samples_count }}</p>
        </footer>
    </div>
</body>
</html>'''

    async def save_report_to_mlflow(
        self,
        html_report: str,
        model_name: str,
        run_id: Optional[str] = None
    ) -> bool:
        """
        Salva relatório HTML como artifact MLflow.

        Args:
            html_report: String HTML do relatório
            model_name: Nome do modelo
            run_id: ID do run MLflow (opcional)

        Returns:
            True se salvo com sucesso
        """
        try:
            import mlflow
            import tempfile
            import os

            # Criar arquivo temporário
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.html',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(html_report)
                temp_path = f.name

            try:
                if run_id:
                    # Usar run existente
                    with mlflow.start_run(run_id=run_id):
                        mlflow.log_artifact(temp_path, 'model_comparison')
                        mlflow.set_tag('comparison.performed', 'true')
                        mlflow.set_tag('comparison.timestamp', datetime.utcnow().isoformat())
                else:
                    # Criar novo run
                    with mlflow.start_run(run_name=f'comparison_{model_name}'):
                        mlflow.log_artifact(temp_path, 'model_comparison')
                        mlflow.set_tag('comparison.performed', 'true')
                        mlflow.set_tag('comparison.timestamp', datetime.utcnow().isoformat())
                        mlflow.set_tag('model_name', model_name)

                self.logger.info(
                    'report_saved_to_mlflow',
                    model_name=model_name,
                    run_id=run_id
                )
                return True

            finally:
                # Limpar arquivo temporário
                os.unlink(temp_path)

        except Exception as e:
            self.logger.error(
                'save_report_to_mlflow_failed',
                model_name=model_name,
                error=str(e)
            )
            return False
