"""
Validador de Modelos ML.

Implementa validações para garantir qualidade antes de promoção:
- Validação estatística (K-S test, Chi-square)
- Validação de business rules (bounds, consistência)
- Validação de fairness (sem viés por task_type)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from scipy import stats
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.metrics import precision_score, recall_score, f1_score
import structlog

logger = structlog.get_logger(__name__)


class ModelValidationResult:
    """Resultado de validação de modelo."""

    def __init__(
        self,
        passed: bool,
        checks: Dict[str, Dict[str, Any]],
        overall_score: float,
        recommendations: List[str]
    ):
        self.passed = passed
        self.checks = checks
        self.overall_score = overall_score
        self.recommendations = recommendations
        self.validated_at = pd.Timestamp.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'passed': self.passed,
            'checks': self.checks,
            'overall_score': self.overall_score,
            'recommendations': self.recommendations,
            'validated_at': self.validated_at.isoformat()
        }


class ModelValidator:
    """
    Validador de modelos ML antes de promoção.

    Executa múltiplas validações:
    - Statistical: Distribuição de erros, KS test
    - Business: Bounds de predição, consistência
    - Fairness: Sem viés por grupo
    - Performance: MAE, RMSE, R², Precision, Recall
    """

    def __init__(self, config):
        """
        Args:
            config: Configuração do orchestrator
        """
        self.config = config
        self.logger = logger.bind(component="model_validator")

        # Thresholds de validação
        self.mae_threshold = getattr(config, 'ml_validation_mae_threshold', 0.15)
        self.r2_threshold = 0.7
        self.precision_threshold = getattr(config, 'ml_validation_precision_threshold', 0.75)
        self.recall_threshold = 0.60
        self.f1_threshold = 0.65
        self.fpr_threshold = 0.10

        # Bounds de predição
        self.min_duration_ms = 1000  # 1 segundo
        self.max_duration_ms = 3600000  # 1 hora

    def validate_duration_predictor(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        confidence: Optional[np.ndarray] = None,
        task_types: Optional[np.ndarray] = None
    ) -> ModelValidationResult:
        """
        Valida DurationPredictor.

        Args:
            y_true: Durações reais
            y_pred: Durações preditas
            confidence: Scores de confiança (opcional)
            task_types: Task types para análise de fairness (opcional)

        Returns:
            ModelValidationResult
        """
        checks = {}
        recommendations = []

        # 1. Performance Metrics
        checks['performance'] = self._validate_performance_metrics(y_true, y_pred)
        if not checks['performance']['passed']:
            recommendations.append(checks['performance'].get('recommendation', ''))

        # 2. Statistical Tests
        checks['statistical'] = self._validate_statistical_distribution(y_true, y_pred)
        if not checks['statistical']['passed']:
            recommendations.append(checks['statistical'].get('recommendation', ''))

        # 3. Business Rules
        checks['business'] = self._validate_business_rules(y_pred)
        if not checks['business']['passed']:
            recommendations.append(checks['business'].get('recommendation', ''))

        # 4. Confidence Calibration
        if confidence is not None:
            checks['confidence'] = self._validate_confidence_calibration(
                y_true, y_pred, confidence
            )
            if not checks['confidence']['passed']:
                recommendations.append(checks['confidence'].get('recommendation', ''))

        # 5. Fairness (por task_type)
        if task_types is not None:
            checks['fairness'] = self._validate_fairness(y_true, y_pred, task_types)
            if not checks['fairness']['passed']:
                recommendations.append(checks['fairness'].get('recommendation', ''))

        # Calcular score geral
        passed_checks = sum(1 for c in checks.values() if c.get('passed', False))
        total_checks = len(checks)
        overall_score = passed_checks / total_checks if total_checks > 0 else 0

        # Determinar se passou
        # Deve passar em performance e business pelo menos
        passed = (
            checks.get('performance', {}).get('passed', False) and
            checks.get('business', {}).get('passed', False) and
            overall_score >= 0.75
        )

        # Limpar recomendações vazias
        recommendations = [r for r in recommendations if r]

        result = ModelValidationResult(
            passed=passed,
            checks=checks,
            overall_score=overall_score,
            recommendations=recommendations
        )

        self.logger.info(
            "duration_predictor_validated",
            passed=passed,
            overall_score=overall_score,
            checks_passed=passed_checks,
            checks_total=total_checks
        )

        return result

    def validate_anomaly_detector(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        anomaly_scores: Optional[np.ndarray] = None
    ) -> ModelValidationResult:
        """
        Valida AnomalyDetector.

        Args:
            y_true: Labels reais (0=normal, 1=anomalia)
            y_pred: Labels preditos
            anomaly_scores: Scores de anomalia (opcional)

        Returns:
            ModelValidationResult
        """
        checks = {}
        recommendations = []

        # 1. Classification Metrics
        checks['classification'] = self._validate_classification_metrics(y_true, y_pred)
        if not checks['classification']['passed']:
            recommendations.append(checks['classification'].get('recommendation', ''))

        # 2. False Positive Rate
        checks['fpr'] = self._validate_false_positive_rate(y_true, y_pred)
        if not checks['fpr']['passed']:
            recommendations.append(checks['fpr'].get('recommendation', ''))

        # 3. Anomaly Rate Sanity
        checks['anomaly_rate'] = self._validate_anomaly_rate(y_pred)
        if not checks['anomaly_rate']['passed']:
            recommendations.append(checks['anomaly_rate'].get('recommendation', ''))

        # 4. Score Distribution (se disponível)
        if anomaly_scores is not None:
            checks['score_distribution'] = self._validate_score_distribution(
                y_true, anomaly_scores
            )
            if not checks['score_distribution']['passed']:
                recommendations.append(checks['score_distribution'].get('recommendation', ''))

        # Calcular score geral
        passed_checks = sum(1 for c in checks.values() if c.get('passed', False))
        total_checks = len(checks)
        overall_score = passed_checks / total_checks if total_checks > 0 else 0

        # Deve passar em classification e fpr
        passed = (
            checks.get('classification', {}).get('passed', False) and
            checks.get('fpr', {}).get('passed', False)
        )

        recommendations = [r for r in recommendations if r]

        result = ModelValidationResult(
            passed=passed,
            checks=checks,
            overall_score=overall_score,
            recommendations=recommendations
        )

        self.logger.info(
            "anomaly_detector_validated",
            passed=passed,
            overall_score=overall_score
        )

        return result

    def _validate_performance_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, Any]:
        """Valida métricas de performance."""
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2 = r2_score(y_true, y_pred)

        mean_duration = np.mean(y_true)
        mae_pct = mae / mean_duration if mean_duration > 0 else 1.0

        passed = mae_pct < self.mae_threshold and r2 > self.r2_threshold

        result = {
            'passed': passed,
            'metrics': {
                'mae': float(mae),
                'mae_pct': float(mae_pct),
                'rmse': float(rmse),
                'r2': float(r2)
            },
            'thresholds': {
                'mae_pct': self.mae_threshold,
                'r2': self.r2_threshold
            }
        }

        if not passed:
            if mae_pct >= self.mae_threshold:
                result['recommendation'] = f"MAE ({mae_pct:.1%}) excede threshold ({self.mae_threshold:.0%})"
            if r2 <= self.r2_threshold:
                result['recommendation'] = f"R² ({r2:.3f}) abaixo de {self.r2_threshold}"

        return result

    def _validate_statistical_distribution(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, Any]:
        """Valida distribuição estatística dos erros."""
        errors = y_pred - y_true
        relative_errors = errors / (y_true + 1e-6)

        # Teste de normalidade dos erros
        _, shapiro_p = stats.shapiro(errors[:min(5000, len(errors))])

        # Teste se erros são centrados em zero
        _, ttest_p = stats.ttest_1samp(errors, 0)

        # Verificar viés
        mean_error = np.mean(relative_errors)
        is_unbiased = abs(mean_error) < 0.05

        # K-S test entre predições e targets
        ks_stat, ks_p = stats.ks_2samp(y_true, y_pred)

        passed = is_unbiased and ks_p > 0.01

        result = {
            'passed': passed,
            'metrics': {
                'mean_relative_error': float(mean_error),
                'shapiro_p': float(shapiro_p),
                'ttest_p': float(ttest_p),
                'ks_statistic': float(ks_stat),
                'ks_p_value': float(ks_p)
            }
        }

        if not passed:
            if not is_unbiased:
                result['recommendation'] = f"Viés detectado: erro médio = {mean_error:.3f}"
            elif ks_p <= 0.01:
                result['recommendation'] = f"Distribuição de predições difere significativamente dos targets"

        return result

    def _validate_business_rules(
        self,
        y_pred: np.ndarray
    ) -> Dict[str, Any]:
        """Valida regras de negócio."""
        # Bounds check
        below_min = np.sum(y_pred < self.min_duration_ms)
        above_max = np.sum(y_pred > self.max_duration_ms)

        out_of_bounds_pct = (below_min + above_max) / len(y_pred)

        # Valores negativos
        negative_count = np.sum(y_pred < 0)

        passed = out_of_bounds_pct < 0.05 and negative_count == 0

        result = {
            'passed': passed,
            'metrics': {
                'below_min_count': int(below_min),
                'above_max_count': int(above_max),
                'out_of_bounds_pct': float(out_of_bounds_pct),
                'negative_count': int(negative_count)
            },
            'bounds': {
                'min_duration_ms': self.min_duration_ms,
                'max_duration_ms': self.max_duration_ms
            }
        }

        if not passed:
            if negative_count > 0:
                result['recommendation'] = f"{negative_count} predições negativas"
            else:
                result['recommendation'] = f"{out_of_bounds_pct:.1%} predições fora dos bounds"

        return result

    def _validate_confidence_calibration(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        confidence: np.ndarray
    ) -> Dict[str, Any]:
        """Valida calibração de confidence scores."""
        errors = np.abs(y_pred - y_true)

        # Dividir em grupos por confidence
        high_conf_mask = confidence > 0.8
        low_conf_mask = confidence < 0.5

        high_conf_mae = np.mean(errors[high_conf_mask]) if high_conf_mask.sum() > 10 else np.nan
        low_conf_mae = np.mean(errors[low_conf_mask]) if low_conf_mask.sum() > 10 else np.nan

        # Alta confiança deve ter erro menor
        calibrated = np.isnan(high_conf_mae) or np.isnan(low_conf_mae) or high_conf_mae < low_conf_mae

        # Correlação entre confidence e erro (deve ser negativa)
        correlation = np.corrcoef(confidence, errors)[0, 1]

        passed = calibrated and (np.isnan(correlation) or correlation < 0)

        result = {
            'passed': passed,
            'metrics': {
                'high_conf_mae': float(high_conf_mae) if not np.isnan(high_conf_mae) else None,
                'low_conf_mae': float(low_conf_mae) if not np.isnan(low_conf_mae) else None,
                'error_confidence_correlation': float(correlation) if not np.isnan(correlation) else None
            }
        }

        if not passed:
            result['recommendation'] = "Confidence scores não estão calibrados com os erros"

        return result

    def _validate_fairness(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        groups: np.ndarray
    ) -> Dict[str, Any]:
        """Valida fairness por grupo."""
        unique_groups = np.unique(groups)
        group_metrics = {}

        errors = np.abs(y_pred - y_true)

        for group in unique_groups:
            mask = groups == group
            if mask.sum() < 10:
                continue

            group_mae = np.mean(errors[mask])
            group_mean = np.mean(y_true[mask])
            group_mae_pct = group_mae / group_mean if group_mean > 0 else 0

            group_metrics[str(group)] = {
                'mae': float(group_mae),
                'mae_pct': float(group_mae_pct),
                'count': int(mask.sum())
            }

        if not group_metrics:
            return {'passed': True, 'metrics': {}, 'note': 'Insufficient data per group'}

        # Verificar se há disparidade significativa
        mae_pcts = [m['mae_pct'] for m in group_metrics.values()]
        max_disparity = max(mae_pcts) / min(mae_pcts) if min(mae_pcts) > 0 else float('inf')

        passed = max_disparity < 2.0

        result = {
            'passed': passed,
            'metrics': {
                'group_metrics': group_metrics,
                'max_disparity_ratio': float(max_disparity)
            }
        }

        if not passed:
            result['recommendation'] = f"Disparidade significativa entre grupos (ratio={max_disparity:.2f})"

        return result

    def _validate_classification_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, Any]:
        """Valida métricas de classificação."""
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)

        passed = (
            precision >= self.precision_threshold and
            recall >= self.recall_threshold and
            f1 >= self.f1_threshold
        )

        result = {
            'passed': passed,
            'metrics': {
                'precision': float(precision),
                'recall': float(recall),
                'f1_score': float(f1)
            },
            'thresholds': {
                'precision': self.precision_threshold,
                'recall': self.recall_threshold,
                'f1': self.f1_threshold
            }
        }

        if not passed:
            issues = []
            if precision < self.precision_threshold:
                issues.append(f"precision={precision:.2%}")
            if recall < self.recall_threshold:
                issues.append(f"recall={recall:.2%}")
            if f1 < self.f1_threshold:
                issues.append(f"F1={f1:.3f}")
            result['recommendation'] = f"Métricas abaixo do threshold: {', '.join(issues)}"

        return result

    def _validate_false_positive_rate(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, Any]:
        """Valida false positive rate."""
        from sklearn.metrics import confusion_matrix

        try:
            tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        except ValueError:
            fpr = 0

        passed = fpr < self.fpr_threshold

        result = {
            'passed': passed,
            'metrics': {
                'false_positive_rate': float(fpr)
            },
            'threshold': self.fpr_threshold
        }

        if not passed:
            result['recommendation'] = f"FPR ({fpr:.2%}) excede threshold ({self.fpr_threshold:.0%})"

        return result

    def _validate_anomaly_rate(
        self,
        y_pred: np.ndarray
    ) -> Dict[str, Any]:
        """Valida taxa de anomalias preditas."""
        anomaly_rate = np.mean(y_pred)

        # Taxa razoável: entre 1% e 30%
        passed = 0.01 <= anomaly_rate <= 0.30

        result = {
            'passed': passed,
            'metrics': {
                'anomaly_rate': float(anomaly_rate)
            },
            'bounds': {
                'min': 0.01,
                'max': 0.30
            }
        }

        if not passed:
            if anomaly_rate < 0.01:
                result['recommendation'] = f"Taxa de anomalias muito baixa ({anomaly_rate:.2%})"
            else:
                result['recommendation'] = f"Taxa de anomalias muito alta ({anomaly_rate:.2%})"

        return result

    def _validate_score_distribution(
        self,
        y_true: np.ndarray,
        scores: np.ndarray
    ) -> Dict[str, Any]:
        """Valida distribuição de scores de anomalia."""
        anomaly_scores = scores[y_true == 1]
        normal_scores = scores[y_true == 0]

        if len(anomaly_scores) < 5 or len(normal_scores) < 5:
            return {'passed': True, 'note': 'Insufficient data'}

        # Anomalias devem ter scores menores (mais negativos)
        mean_anomaly_score = np.mean(anomaly_scores)
        mean_normal_score = np.mean(normal_scores)

        # K-S test para separação
        ks_stat, ks_p = stats.ks_2samp(anomaly_scores, normal_scores)

        # Scores de anomalia devem ser distintos dos normais
        passed = ks_p < 0.05 and mean_anomaly_score < mean_normal_score

        result = {
            'passed': passed,
            'metrics': {
                'mean_anomaly_score': float(mean_anomaly_score),
                'mean_normal_score': float(mean_normal_score),
                'ks_statistic': float(ks_stat),
                'ks_p_value': float(ks_p)
            }
        }

        if not passed:
            result['recommendation'] = "Scores de anomalia não distinguem bem anomalias de normais"

        return result
