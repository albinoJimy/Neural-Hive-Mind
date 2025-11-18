"""
LoadPredictor Local - Preditor leve de carga e tempo de fila.

Implementa predições heurísticas usando dados históricos do MongoDB para estimar:
- Tempo de espera em fila (queue_time)
- Carga atual do worker (load_percentage)

Projetado para latência <50ms como fallback quando optimizer-agents indisponível.
"""

import time
import structlog
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics

logger = structlog.get_logger(__name__)


class LoadPredictor:
    """
    Preditor local de carga de workers usando heurísticas simples.

    Usa moving averages e exponential smoothing para estimar:
    - Queue time: tempo estimado de espera em fila
    - Worker load: percentual de carga atual do worker

    Cache em Redis para otimizar latência (<50ms).
    """

    def __init__(
        self,
        config: OrchestratorSettings,
        mongodb_client,
        redis_client,
        metrics: OrchestratorMetrics
    ):
        """
        Inicializa LoadPredictor.

        Args:
            config: Configurações do orchestrator
            mongodb_client: Cliente MongoDB para dados históricos
            redis_client: Cliente Redis para cache
            metrics: OrchestratorMetrics para observabilidade
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.metrics = metrics
        self.logger = logger.bind(component="load_predictor_local")

        # Parâmetros de predição
        self.window_minutes = config.ml_local_load_window_minutes
        self.cache_ttl_seconds = config.ml_local_load_cache_ttl_seconds

        # Smoothing parameters
        self.alpha = 0.3  # Exponential smoothing factor

    async def predict_queue_time(
        self,
        worker_id: str,
        ticket: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Prediz tempo de espera em fila para um worker.

        Args:
            worker_id: ID do worker
            ticket: Ticket opcional para contexto (estimativa de duração)

        Returns:
            Tempo estimado de fila em milissegundos
        """
        start_time = time.time()

        try:
            # Verificar cache primeiro
            cache_key = f"queue_pred:{worker_id}"
            cached = await self._get_from_cache(cache_key)

            if cached is not None:
                self.logger.debug(
                    "queue_prediction_cache_hit",
                    worker_id=worker_id,
                    predicted_ms=cached
                )
                return float(cached)

            # Buscar dados históricos recentes
            recent_completions = await self._fetch_recent_completions(
                worker_id,
                self.window_minutes
            )

            if not recent_completions:
                # Sem dados: retornar estimativa default
                default_queue_ms = 1000.0  # 1 segundo
                await self._save_to_cache(cache_key, default_queue_ms)

                self.logger.debug(
                    "queue_prediction_no_data",
                    worker_id=worker_id,
                    predicted_ms=default_queue_ms
                )

                return default_queue_ms

            # Estimar queue depth atual
            queue_depth = await self._estimate_queue_depth(worker_id)

            # Calcular moving average de durações
            avg_duration = self._calculate_moving_average(
                [c['actual_duration_ms'] for c in recent_completions],
                window=10
            )

            # Predição: queue_depth * avg_duration
            predicted_queue_ms = queue_depth * avg_duration

            # Aplicar exponential smoothing se houver predição anterior
            if cached is not None:
                predicted_queue_ms = (
                    self.alpha * predicted_queue_ms +
                    (1 - self.alpha) * cached
                )

            # Limitar entre 0 e 60 segundos
            predicted_queue_ms = max(0.0, min(predicted_queue_ms, 60000.0))

            # Salvar no cache
            await self._save_to_cache(cache_key, predicted_queue_ms)

            # Métricas
            duration_seconds = time.time() - start_time
            self.metrics.record_ml_prediction(
                model_type='queue_time_local',
                status='success',
                duration=duration_seconds
            )

            # Registrar predição de queue time
            self.metrics.record_predicted_queue_time(
                predicted_ms=predicted_queue_ms,
                source='local'
            )

            self.logger.debug(
                "queue_time_predicted",
                worker_id=worker_id,
                predicted_ms=predicted_queue_ms,
                queue_depth=queue_depth,
                avg_duration_ms=avg_duration,
                latency_ms=duration_seconds * 1000
            )

            return float(predicted_queue_ms)

        except Exception as e:
            self.logger.error(
                "queue_prediction_error",
                worker_id=worker_id,
                error=str(e)
            )
            self.metrics.record_ml_error('queue_prediction')

            # Fallback: retornar estimativa conservadora
            return 2000.0  # 2 segundos

    async def predict_worker_load(self, worker_id: str) -> float:
        """
        Prediz carga atual do worker como percentual.

        Args:
            worker_id: ID do worker

        Returns:
            Carga estimada como percentual (0.0-1.0)
        """
        start_time = time.time()

        try:
            # Verificar cache
            cache_key = f"load_pred:{worker_id}"
            cached = await self._get_from_cache(cache_key)

            if cached is not None:
                self.logger.debug(
                    "load_prediction_cache_hit",
                    worker_id=worker_id,
                    predicted_load=cached
                )
                return float(cached)

            # Estimar queue depth
            queue_depth = await self._estimate_queue_depth(worker_id)

            # Buscar capacidade máxima do worker (heurística: 10 tarefas)
            max_capacity = 10.0

            # Calcular carga como percentual
            load_pct = min(queue_depth / max_capacity, 1.0)

            # Salvar no cache
            await self._save_to_cache(cache_key, load_pct)

            # Métricas
            duration_seconds = time.time() - start_time
            self.metrics.record_ml_prediction(
                model_type='worker_load_local',
                status='success',
                duration=duration_seconds
            )

            # Registrar predição de worker load
            self.metrics.record_predicted_worker_load(
                predicted_pct=load_pct,
                source='local'
            )

            self.logger.debug(
                "worker_load_predicted",
                worker_id=worker_id,
                predicted_load_pct=load_pct,
                queue_depth=queue_depth,
                latency_ms=duration_seconds * 1000
            )

            return float(load_pct)

        except Exception as e:
            self.logger.error(
                "load_prediction_error",
                worker_id=worker_id,
                error=str(e)
            )
            self.metrics.record_ml_error('load_prediction')

            # Fallback: assumir carga média
            return 0.5

    async def _fetch_recent_completions(
        self,
        worker_id: str,
        window_minutes: int
    ) -> List[Dict]:
        """
        Busca tickets completados recentemente para um worker.

        Args:
            worker_id: ID do worker
            window_minutes: Janela de tempo em minutos

        Returns:
            Lista de tickets completados
        """
        # Verificar se MongoDB está disponível
        if not self.mongodb_client:
            self.logger.debug(
                "fetch_completions_skipped_no_mongodb",
                worker_id=worker_id
            )
            return []

        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)

            tickets = await self.mongodb_client.db[
                self.config.mongodb_collection_tickets
            ].find({
                'allocated_worker_id': worker_id,
                'status': 'COMPLETED',
                'completed_at': {'$gte': cutoff_time},
                'actual_duration_ms': {'$exists': True, '$ne': None}
            }).sort('completed_at', -1).limit(50).to_list(None)

            return tickets

        except Exception as e:
            self.logger.error(
                "fetch_completions_error",
                worker_id=worker_id,
                error=str(e)
            )
            return []

    async def _estimate_queue_depth(self, worker_id: str) -> int:
        """
        Estima profundidade da fila de um worker.

        Conta tickets ativos (PENDING, EXECUTING) alocados ao worker.

        Args:
            worker_id: ID do worker

        Returns:
            Número de tickets ativos
        """
        # Verificar se MongoDB está disponível
        if not self.mongodb_client:
            self.logger.debug(
                "queue_depth_estimation_skipped_no_mongodb",
                worker_id=worker_id
            )
            return 0

        try:
            count = await self.mongodb_client.db[
                self.config.mongodb_collection_tickets
            ].count_documents({
                'allocated_worker_id': worker_id,
                'status': {'$in': ['PENDING', 'EXECUTING']}
            })

            return count

        except Exception as e:
            self.logger.error(
                "queue_depth_estimation_error",
                worker_id=worker_id,
                error=str(e)
            )
            return 0

    def _calculate_moving_average(
        self,
        data: List[float],
        window: int
    ) -> float:
        """
        Calcula moving average simples.

        Args:
            data: Lista de valores
            window: Tamanho da janela

        Returns:
            Média móvel
        """
        if not data:
            return 5000.0  # Default: 5 segundos

        # Pegar últimos N valores
        recent_data = data[-window:] if len(data) > window else data

        if not recent_data:
            return 5000.0

        return sum(recent_data) / len(recent_data)

    async def _get_from_cache(self, key: str) -> Optional[float]:
        """
        Obtém valor do cache Redis.

        Args:
            key: Chave do cache

        Returns:
            Valor cached ou None
        """
        try:
            if not self.redis_client:
                return None

            value = await self.redis_client.get(key)

            if value is not None:
                return float(value)

            return None

        except Exception as e:
            self.logger.warning(
                "cache_get_error",
                key=key,
                error=str(e)
            )
            return None

    async def _save_to_cache(self, key: str, value: float):
        """
        Salva valor no cache Redis com TTL.

        Args:
            key: Chave do cache
            value: Valor a salvar
        """
        try:
            if not self.redis_client:
                return

            await self.redis_client.setex(
                key,
                self.cache_ttl_seconds,
                str(value)
            )

        except Exception as e:
            self.logger.warning(
                "cache_save_error",
                key=key,
                error=str(e)
            )
