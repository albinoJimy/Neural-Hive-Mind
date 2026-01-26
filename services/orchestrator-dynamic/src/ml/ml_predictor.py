"""
ML Predictor facade para coordenação de predições.

Coordena DurationPredictor e AnomalyDetector, combinando resultados
e estimando recursos necessários para execução de tickets.
"""

from typing import Dict, Any
import asyncio
import structlog

from .duration_predictor import DurationPredictor
from .anomaly_detector import AnomalyDetector

logger = structlog.get_logger(__name__)


class MLPredictor:
    """
    Facade para predições ML de tickets.

    Coordena:
    - Predição de duração (DurationPredictor)
    - Detecção de anomalias (AnomalyDetector)
    - Estimativa de recursos (CPU/Memory)

    Executa predições em paralelo para minimizar latência.
    """

    # Base values para estimativa de recursos por task_type
    RESOURCE_BASELINE = {
        'BUILD': {'cpu_m': 500, 'memory_mb': 512},
        'DEPLOY': {'cpu_m': 200, 'memory_mb': 1024},
        'TEST': {'cpu_m': 300, 'memory_mb': 256},
        'VALIDATE': {'cpu_m': 200, 'memory_mb': 256},
        'EXECUTE': {'cpu_m': 300, 'memory_mb': 512},
        'PLAN': {'cpu_m': 400, 'memory_mb': 512},
        'CONSOLIDATE': {'cpu_m': 200, 'memory_mb': 256}
    }

    # Multiplicadores por risk_band
    RISK_MULTIPLIERS = {
        'critical': 1.5,
        'high': 1.3,
        'medium': 1.0,
        'low': 0.8
    }

    def __init__(self, config, mongodb_client, model_registry, metrics):
        """
        Inicializa MLPredictor.

        Args:
            config: Configuração do orchestrator
            mongodb_client: Cliente MongoDB
            model_registry: ModelRegistry para modelos
            metrics: OrchestratorMetrics para observabilidade
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.model_registry = model_registry
        self.metrics = metrics
        self.logger = logger.bind(component="ml_predictor")

        # Predictors
        self.duration_predictor = DurationPredictor(
            config=config,
            mongodb_client=mongodb_client,
            model_registry=model_registry,
            metrics=metrics
        )

        self.anomaly_detector = AnomalyDetector(
            config=config,
            mongodb_client=mongodb_client,
            model_registry=model_registry,
            metrics=metrics
        )

    async def initialize(self):
        """
        Inicializa ambos os predictors.

        Assume que o ModelRegistry já foi inicializado por quem o criou.
        """
        try:
            # Inicializa predictors em paralelo
            await asyncio.gather(
                self.duration_predictor.initialize(),
                self.anomaly_detector.initialize()
            )

            self.logger.info("ml_predictor_initialized")

        except Exception as e:
            self.logger.error("ml_predictor_init_failed", error=str(e))
            raise

    async def ensure_models_trained(self) -> Dict[str, bool]:
        """
        Garante que modelos estão treinados, executando treinamento inicial se necessário.

        Chamado durante startup para validar estado dos modelos.

        Returns:
            Dict com status de cada modelo: {'duration': bool, 'anomaly': bool}
        """
        try:
            self.logger.info("checking_models_training_status")

            # Verificar e treinar modelos em paralelo
            results = await asyncio.gather(
                self.duration_predictor._ensure_model_trained(),
                self.anomaly_detector._ensure_model_trained(),
                return_exceptions=True
            )

            duration_ready = results[0]
            anomaly_ready = results[1]

            # Handle exceptions
            if isinstance(duration_ready, Exception):
                self.logger.error("duration_model_check_failed", error=str(duration_ready))
                duration_ready = False

            if isinstance(anomaly_ready, Exception):
                self.logger.error("anomaly_model_check_failed", error=str(anomaly_ready))
                anomaly_ready = False

            status = {
                'duration': duration_ready,
                'anomaly': anomaly_ready
            }

            self.logger.info(
                "models_training_status_checked",
                duration_ready=duration_ready,
                anomaly_ready=anomaly_ready
            )

            return status

        except Exception as e:
            self.logger.error("ensure_models_trained_failed", error=str(e))
            return {'duration': False, 'anomaly': False}

    async def predict_and_enrich(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executa todas as predições e enriquece ticket com metadata.

        Adiciona campo 'predictions' ao ticket com:
        - duration_ms: Duração prevista
        - duration_confidence: Confiança da predição (0-1)
        - resource_estimate: {cpu_m, memory_mb}
        - anomaly: {is_anomaly, score, type, explanation}

        Args:
            ticket: Dict com dados do ticket

        Returns:
            Ticket enriquecido com campo 'predictions'
        """
        try:
            ticket_id = ticket.get('ticket_id', 'unknown')

            # Executa predições em paralelo
            duration_result, anomaly_result = await asyncio.gather(
                self.duration_predictor.predict_duration(ticket),
                self.anomaly_detector.detect_anomaly(ticket),
                return_exceptions=True
            )

            # Handle exceptions
            if isinstance(duration_result, Exception):
                self.logger.warning("duration_prediction_failed", error=str(duration_result))
                duration_result = {
                    'duration_ms': float(ticket.get('estimated_duration_ms', 60000.0)),
                    'confidence': 0.3
                }

            if isinstance(anomaly_result, Exception):
                self.logger.warning("anomaly_detection_failed", error=str(anomaly_result))
                anomaly_result = {
                    'is_anomaly': False,
                    'anomaly_score': 0.0,
                    'anomaly_type': None,
                    'explanation': 'Detecção falhou'
                }

            # Estima recursos baseado na duração prevista
            predicted_duration = duration_result.get('duration_ms', 60000.0)
            task_type = ticket.get('task_type', 'EXECUTE')
            risk_band = ticket.get('risk_band', 'medium')

            resource_estimate = self._estimate_resources(
                duration_ms=predicted_duration,
                task_type=task_type,
                risk_band=risk_band
            )

            # Enriquece ticket com predictions
            ticket['predictions'] = {
                'duration_ms': duration_result.get('duration_ms'),
                'duration_confidence': duration_result.get('confidence'),
                'resource_estimate': resource_estimate,
                'anomaly': {
                    'is_anomaly': anomaly_result.get('is_anomaly'),
                    'anomaly_score': anomaly_result.get('anomaly_score'),
                    'anomaly_type': anomaly_result.get('anomaly_type'),
                    'explanation': anomaly_result.get('explanation')
                }
            }

            self.logger.info(
                "ticket_enriched_with_predictions",
                ticket_id=ticket_id,
                predicted_duration_ms=predicted_duration,
                confidence=duration_result.get('confidence'),
                is_anomaly=anomaly_result.get('is_anomaly'),
                resource_cpu_m=resource_estimate['cpu_m'],
                resource_memory_mb=resource_estimate['memory_mb']
            )

            return ticket

        except Exception as e:
            self.logger.error("predict_and_enrich_failed", error=str(e), ticket_id=ticket.get('ticket_id'))
            # Retorna ticket sem modificação em caso de erro
            return ticket

    def _estimate_resources(
        self,
        duration_ms: float,
        task_type: str,
        risk_band: str
    ) -> Dict[str, int]:
        """
        Estima recursos necessários (CPU e memória).

        Fórmulas:
        - cpu_m = base_cpu[task_type] * (duration_ms / 60000) * risk_multiplier
        - memory_mb = base_memory[task_type] * risk_multiplier

        Args:
            duration_ms: Duração prevista em milissegundos
            task_type: Tipo da tarefa
            risk_band: Banda de risco

        Returns:
            Dict com cpu_m (millicores) e memory_mb
        """
        try:
            # Base resources
            baseline = self.RESOURCE_BASELINE.get(
                task_type.upper(),
                {'cpu_m': 300, 'memory_mb': 512}
            )

            # Risk multiplier
            risk_multiplier = self.RISK_MULTIPLIERS.get(
                risk_band.lower(),
                1.0
            )

            # Duration factor (normalizado para 1 minuto)
            duration_factor = max(0.5, min(3.0, duration_ms / 60000.0))

            # Calcula recursos
            cpu_m = int(baseline['cpu_m'] * duration_factor * risk_multiplier)
            memory_mb = int(baseline['memory_mb'] * risk_multiplier)

            # Limita valores
            cpu_m = max(100, min(cpu_m, 4000))  # 100m - 4000m
            memory_mb = max(128, min(memory_mb, 4096))  # 128MB - 4GB

            return {
                'cpu_m': cpu_m,
                'memory_mb': memory_mb
            }

        except Exception as e:
            self.logger.warning("resource_estimation_failed", error=str(e))
            return {
                'cpu_m': 300,
                'memory_mb': 512
            }

    async def close(self):
        """
        Limpa recursos do MLPredictor.
        """
        try:
            await self.model_registry.close()
            self.logger.info("ml_predictor_closed")
        except Exception as e:
            self.logger.error("ml_predictor_close_failed", error=str(e))
