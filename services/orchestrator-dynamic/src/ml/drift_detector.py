"""
Módulo de detecção de drift para monitorar mudanças na distribuição de dados
e degradação de performance dos modelos ML.

Implementa três tipos de drift:
1. Feature Drift: Mudanças na distribuição das features de entrada (PSI)
2. Prediction Drift: Degradação da acurácia das predições (MAE ratio)
3. Target Drift: Mudanças na distribuição da variável alvo (K-S test)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import numpy as np
from scipy import stats

from src.config.settings import OrchestratorSettings
from src.clients.mongodb_client import MongoDBClient
from src.observability.metrics import OrchestratorMetrics
from src.ml.feature_engineering import extract_ticket_features

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detector de drift para modelos ML."""

    def __init__(
        self,
        config: OrchestratorSettings,
        mongodb_client: MongoDBClient,
        metrics: Optional[OrchestratorMetrics] = None
    ):
        """
        Inicializa o detector de drift.

        Args:
            config: Configurações do orchestrator
            mongodb_client: Cliente MongoDB para consultas (async)
            metrics: Instância de métricas para registro
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.metrics = metrics or OrchestratorMetrics()

        # Thresholds de drift
        self.psi_threshold = getattr(config, 'ml_drift_psi_threshold', 0.25)
        self.mae_ratio_threshold = getattr(config, 'ml_drift_mae_ratio_threshold', 1.5)
        self.ks_pvalue_threshold = getattr(config, 'ml_drift_ks_pvalue_threshold', 0.05)

        logger.info(
            "DriftDetector initialized",
            extra={
                "psi_threshold": self.psi_threshold,
                "mae_ratio_threshold": self.mae_ratio_threshold,
                "ks_pvalue_threshold": self.ks_pvalue_threshold
            }
        )

    def _calculate_psi(
        self,
        expected: np.ndarray,
        actual: np.ndarray,
        bins: int = 10
    ) -> float:
        """
        Calcula Population Stability Index (PSI) entre duas distribuições.

        PSI = sum((actual_pct - expected_pct) * ln(actual_pct / expected_pct))

        Args:
            expected: Distribuição baseline (treino)
            actual: Distribuição atual (produção)
            bins: Número de bins para histograma

        Returns:
            Valor PSI (0-infinito)
        """
        # Criar bins baseados na distribuição esperada
        _, bin_edges = np.histogram(expected, bins=bins)

        # Calcular distribuições
        expected_counts, _ = np.histogram(expected, bins=bin_edges)
        actual_counts, _ = np.histogram(actual, bins=bin_edges)

        # Converter para percentuais
        expected_pct = expected_counts / len(expected)
        actual_pct = actual_counts / len(actual)

        # Evitar divisão por zero
        expected_pct = np.where(expected_pct == 0, 0.0001, expected_pct)
        actual_pct = np.where(actual_pct == 0, 0.0001, actual_pct)

        # Calcular PSI
        psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))

        return float(psi)

    async def detect_feature_drift(self, window_days: int = 7) -> Dict[str, float]:
        """
        Detecta drift nas features de entrada usando PSI.

        Args:
            window_days: Janela de análise em dias

        Returns:
            Dict com PSI score por feature
        """
        try:
            # Query tickets recentes via cliente async
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=window_days)

            recent_tickets = await self.mongodb_client.db['execution_tickets'].find({
                "created_at": {"$gte": start_date, "$lte": end_date},
                "status": "completed"
            }).limit(1000).to_list(length=1000)

            if len(recent_tickets) < 50:
                logger.warning(
                    f"Insufficient recent tickets for drift detection: {len(recent_tickets)}"
                )
                return {}

            # Extrair features dos tickets recentes
            recent_features = []
            for ticket in recent_tickets:
                features = extract_ticket_features(ticket)
                if features:
                    recent_features.append(features)

            if not recent_features:
                logger.warning("No features extracted from recent tickets")
                return {}

            # Carregar baseline de features do MongoDB (async)
            baseline_doc = await self.mongodb_client.db['ml_feature_baselines'].find_one(
                {},
                sort=[("timestamp", -1)]
            )

            if not baseline_doc:
                logger.warning("No feature baseline found in database")
                return {}

            baseline_features = baseline_doc.get('features', {})

            # Calcular PSI para cada feature
            psi_scores = {}

            for feature_name in recent_features[0].keys():
                try:
                    # Valores recentes
                    recent_values = np.array([
                        f[feature_name] for f in recent_features
                        if feature_name in f and f[feature_name] is not None
                    ])

                    # Valores baseline
                    baseline_data = baseline_features.get(feature_name, {})
                    if not baseline_data or 'values' not in baseline_data:
                        continue

                    baseline_values = np.array(baseline_data['values'])

                    # Calcular PSI
                    if len(recent_values) > 0 and len(baseline_values) > 0:
                        psi = self._calculate_psi(baseline_values, recent_values)
                        psi_scores[feature_name] = psi

                        # Registrar métrica
                        if self.metrics:
                            self.metrics.record_drift_score(
                                drift_type="feature",
                                score=psi,
                                feature=feature_name
                            )

                        # Log drift significativo
                        if psi > self.psi_threshold:
                            logger.warning(
                                f"Significant feature drift detected: {feature_name}",
                                extra={"psi_score": psi, "threshold": self.psi_threshold}
                            )

                except Exception as e:
                    logger.error(
                        f"Error calculating PSI for feature {feature_name}: {e}"
                    )

            return psi_scores

        except Exception as e:
            logger.error(f"Error detecting feature drift: {e}", exc_info=True)
            return {}

    async def detect_prediction_drift(self, window_days: int = 7) -> Dict[str, float]:
        """
        Detecta degradação na acurácia das predições comparando MAE atual vs treino.

        Args:
            window_days: Janela de análise em dias

        Returns:
            Dict com MAE por janela temporal e drift ratio
        """
        try:
            end_date = datetime.utcnow()

            # Calcular MAE para diferentes janelas
            mae_results = {}

            for days in [1, 3, 7]:
                if days > window_days:
                    continue

                start_date = end_date - timedelta(days=days)

                # Query tickets completos com predições (async)
                tickets = await self.mongodb_client.db['execution_tickets'].find({
                    "created_at": {"$gte": start_date, "$lte": end_date},
                    "status": "completed",
                    "actual_duration_ms": {"$exists": True, "$gt": 0},
                    "predictions.duration_ms": {"$exists": True, "$gt": 0}
                }).limit(500).to_list(length=500)

                if not tickets:
                    continue

                # Calcular MAE
                errors = []
                for ticket in tickets:
                    actual = ticket.get('actual_duration_ms', 0)
                    predicted = ticket.get('predictions', {}).get('duration_ms', 0)

                    if actual > 0 and predicted > 0:
                        error = abs(actual - predicted)
                        errors.append(error)

                if errors:
                    mae = np.mean(errors)
                    mae_results[f'mae_{days}d'] = float(mae)

            # Obter MAE de treino do MLflow (via baseline ou metadata)
            training_mae = await self._get_training_mae()
            if training_mae:
                mae_results['mae_training'] = training_mae

                # Calcular drift ratio (MAE atual / MAE treino)
                current_mae = mae_results.get('mae_7d') or mae_results.get('mae_3d') or mae_results.get('mae_1d')
                if current_mae:
                    drift_ratio = current_mae / training_mae
                    mae_results['drift_ratio'] = float(drift_ratio)

                    # Registrar métrica
                    if self.metrics:
                        self.metrics.record_drift_score(
                            drift_type="prediction",
                            score=drift_ratio,
                            model_name="duration-predictor"
                        )

                    # Log degradação crítica
                    if drift_ratio > self.mae_ratio_threshold:
                        logger.warning(
                            "Critical prediction drift detected",
                            extra={
                                "drift_ratio": drift_ratio,
                                "current_mae": current_mae,
                                "training_mae": training_mae,
                                "threshold": self.mae_ratio_threshold
                            }
                        )

            return mae_results

        except Exception as e:
            logger.error(f"Error detecting prediction drift: {e}", exc_info=True)
            return {}

    async def detect_target_drift(self, window_days: int = 7) -> Dict[str, Any]:
        """
        Detecta mudanças na distribuição da variável alvo (actual_duration_ms)
        usando Kolmogorov-Smirnov test.

        Args:
            window_days: Janela de análise em dias

        Returns:
            Dict com estatísticas de drift do target
        """
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=window_days)

            # Query tickets recentes (async)
            recent_tickets = await self.mongodb_client.db['execution_tickets'].find({
                "created_at": {"$gte": start_date, "$lte": end_date},
                "status": "completed",
                "actual_duration_ms": {"$exists": True, "$gt": 0}
            }).limit(1000).to_list(length=1000)

            if len(recent_tickets) < 50:
                logger.warning(f"Insufficient tickets for target drift: {len(recent_tickets)}")
                return {}

            recent_durations = np.array([
                t['actual_duration_ms'] for t in recent_tickets
                if 'actual_duration_ms' in t and t['actual_duration_ms'] > 0
            ])

            # Carregar distribuição baseline (async)
            baseline_doc = await self.mongodb_client.db['ml_feature_baselines'].find_one(
                {},
                sort=[("timestamp", -1)]
            )

            if not baseline_doc or 'target_distribution' not in baseline_doc:
                logger.warning("No target baseline found in database")
                return {}

            baseline_stats = baseline_doc['target_distribution']
            baseline_durations = np.array(baseline_stats.get('values', []))

            if len(baseline_durations) == 0:
                return {}

            # Realizar K-S test
            ks_statistic, p_value = stats.ks_2samp(baseline_durations, recent_durations)

            # Calcular shifts de estatísticas descritivas
            baseline_mean = baseline_stats.get('mean', np.mean(baseline_durations))
            baseline_std = baseline_stats.get('std', np.std(baseline_durations))

            recent_mean = float(np.mean(recent_durations))
            recent_std = float(np.std(recent_durations))

            # Handle division by zero for mean_shift_pct
            if baseline_mean == 0:
                logger.warning(
                    "baseline_mean is zero, cannot calculate mean_shift_pct normally",
                    extra={
                        "baseline_mean": baseline_mean,
                        "recent_mean": recent_mean
                    }
                )
                mean_shift_pct = 0.0
            else:
                mean_shift_pct = ((recent_mean - baseline_mean) / baseline_mean) * 100

            std_shift_pct = ((recent_std - baseline_std) / baseline_std) * 100 if baseline_std > 0 else 0

            result = {
                'ks_statistic': float(ks_statistic),
                'p_value': float(p_value),
                'mean_shift_pct': float(mean_shift_pct),
                'std_shift_pct': float(std_shift_pct),
                'baseline_mean': float(baseline_mean),
                'baseline_std': float(baseline_std),
                'recent_mean': recent_mean,
                'recent_std': recent_std
            }

            # Registrar métrica
            if self.metrics:
                self.metrics.record_drift_score(
                    drift_type="target",
                    score=ks_statistic,
                    model_name="duration-predictor"
                )

            # Log drift significativo
            if p_value < self.ks_pvalue_threshold:
                logger.warning(
                    "Significant target drift detected",
                    extra={
                        "ks_statistic": ks_statistic,
                        "p_value": p_value,
                        "mean_shift_pct": mean_shift_pct
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Error detecting target drift: {e}", exc_info=True)
            return {}

    async def run_drift_check(self) -> Dict[str, Any]:
        """
        Executa verificação completa de drift (features, predictions, target).

        Returns:
            Relatório consolidado de drift
        """
        window_days = getattr(self.config, 'ml_drift_check_window_days', 7)

        logger.info(f"Running drift check with {window_days} day window")

        # Executar detecções (async)
        feature_drift = await self.detect_feature_drift(window_days)
        prediction_drift = await self.detect_prediction_drift(window_days)
        target_drift = await self.detect_target_drift(window_days)

        # Determinar status geral
        overall_status = self._determine_overall_status(
            feature_drift,
            prediction_drift,
            target_drift
        )

        # Gerar recomendações
        recommendations = self._generate_recommendations(
            feature_drift,
            prediction_drift,
            target_drift
        )

        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'window_days': window_days,
            'feature_drift': feature_drift,
            'prediction_drift': prediction_drift,
            'target_drift': target_drift,
            'overall_status': overall_status,
            'recommendations': recommendations
        }

        # Atualizar status geral em métricas
        if self.metrics:
            status_value = {'ok': 0, 'warning': 1, 'critical': 2}.get(overall_status, 0)
            self.metrics.update_drift_status(
                model_name="duration-predictor",
                drift_type="overall",
                status=overall_status
            )

        logger.info(
            "Drift check completed",
            extra={
                "overall_status": overall_status,
                "features_drifted": len([s for s in feature_drift.values() if s > self.psi_threshold]),
                "prediction_drift_ratio": prediction_drift.get('drift_ratio'),
                "target_drift_pvalue": target_drift.get('p_value')
            }
        )

        return report

    def _determine_overall_status(
        self,
        feature_drift: Dict[str, float],
        prediction_drift: Dict[str, float],
        target_drift: Dict[str, Any]
    ) -> str:
        """Determina status geral baseado nos drifts detectados."""

        # Verificar drift crítico
        critical_conditions = [
            # Prediction drift crítico
            prediction_drift.get('drift_ratio', 0) > self.mae_ratio_threshold,
            # Feature drift crítico em múltiplas features
            len([s for s in feature_drift.values() if s > self.psi_threshold]) > 3,
            # Target drift muito significativo
            target_drift.get('p_value', 1.0) < 0.01
        ]

        if any(critical_conditions):
            return 'critical'

        # Verificar drift moderado
        warning_conditions = [
            # Prediction drift moderado
            prediction_drift.get('drift_ratio', 0) > 1.2,
            # Qualquer feature drift moderado
            len([s for s in feature_drift.values() if s > 0.1]) > 0,
            # Target drift significativo
            target_drift.get('p_value', 1.0) < self.ks_pvalue_threshold
        ]

        if any(warning_conditions):
            return 'warning'

        return 'ok'

    def _generate_recommendations(
        self,
        feature_drift: Dict[str, float],
        prediction_drift: Dict[str, float],
        target_drift: Dict[str, Any]
    ) -> List[str]:
        """Gera recomendações baseadas nos drifts detectados."""

        recommendations = []

        # Feature drift
        for feature, psi in feature_drift.items():
            if psi > self.psi_threshold:
                recommendations.append(
                    f"Feature drift detectado em {feature} (PSI={psi:.3f}). "
                    "Revisar distribuição de dados recentes."
                )

        # Prediction drift
        drift_ratio = prediction_drift.get('drift_ratio')
        if drift_ratio and drift_ratio > self.mae_ratio_threshold:
            recommendations.append(
                f"Acurácia degradou {(drift_ratio - 1) * 100:.1f}% comparado ao treino. "
                "Retreinamento urgente recomendado."
            )
        elif drift_ratio and drift_ratio > 1.2:
            recommendations.append(
                f"Acurácia degradou {(drift_ratio - 1) * 100:.1f}%. "
                "Monitorar e considerar retreinamento."
            )

        # Target drift
        p_value = target_drift.get('p_value')
        if p_value is not None and p_value < self.ks_pvalue_threshold:
            mean_shift = target_drift.get('mean_shift_pct', 0)
            recommendations.append(
                f"Distribuição do target mudou significativamente "
                f"(p-value={p_value:.4f}, mean shift={mean_shift:.1f}%). "
                "Verificar mudanças na carga de trabalho."
            )

        if not recommendations:
            recommendations.append("Nenhum drift significativo detectado. Modelos estáveis.")

        return recommendations

    async def _get_training_mae(self) -> Optional[float]:
        """Obtém MAE de treino do baseline mais recente."""
        try:
            baseline_doc = await self.mongodb_client.db['ml_feature_baselines'].find_one(
                {},
                sort=[("timestamp", -1)]
            )

            if baseline_doc and 'training_mae' in baseline_doc:
                return float(baseline_doc['training_mae'])

            return None

        except Exception as e:
            logger.error(f"Error getting training MAE: {e}")
            return None

    async def save_feature_baseline(
        self,
        features_data: List[Dict[str, Any]],
        target_values: List[float],
        training_mae: float,
        model_name: str = "duration-predictor",
        version: str = "latest"
    ) -> None:
        """
        Salva baseline de features para futuras comparações de drift.

        Args:
            features_data: Lista de dicts com features extraídas
            target_values: Lista de valores do target (actual_duration_ms)
            training_mae: MAE do modelo treinado
            model_name: Nome do modelo
            version: Versão do modelo
        """
        try:
            if not features_data:
                logger.warning("No features data to save baseline")
                return

            # Extrair valores por feature
            baseline_features = {}
            for feature_name in features_data[0].keys():
                values = [
                    f[feature_name] for f in features_data
                    if feature_name in f and f[feature_name] is not None
                ]
                if values:
                    baseline_features[feature_name] = {
                        'values': values,
                        'mean': float(np.mean(values)),
                        'std': float(np.std(values)),
                        'min': float(np.min(values)),
                        'max': float(np.max(values))
                    }

            # Salvar baseline no MongoDB (async)
            baseline_doc = {
                'model_name': model_name,
                'version': version,
                'timestamp': datetime.utcnow(),
                'features': baseline_features,
                'target_distribution': {
                    'values': target_values[:1000],  # Limitar para não crescer demais
                    'mean': float(np.mean(target_values)),
                    'std': float(np.std(target_values)),
                    'percentiles': {
                        'p50': float(np.percentile(target_values, 50)),
                        'p95': float(np.percentile(target_values, 95)),
                        'p99': float(np.percentile(target_values, 99))
                    }
                },
                'training_mae': training_mae,
                'sample_count': len(features_data)
            }

            await self.mongodb_client.db['ml_feature_baselines'].insert_one(baseline_doc)

            logger.info(
                "Feature baseline saved",
                extra={
                    "model_name": model_name,
                    "version": version,
                    "features_count": len(baseline_features),
                    "sample_count": len(features_data)
                }
            )

        except Exception as e:
            logger.error(f"Error saving feature baseline: {e}", exc_info=True)
