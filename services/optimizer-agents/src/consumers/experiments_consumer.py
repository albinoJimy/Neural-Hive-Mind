import asyncio
import json
from typing import Optional

import structlog
from confluent_kafka import Consumer, KafkaError, KafkaException

from src.config.settings import get_settings

logger = structlog.get_logger()


class ExperimentsConsumer:
    """
    Kafka consumer para tópico experiments.results (publicado por sistema de experimentos).

    Consome resultados de experimentos e atualiza Q-table com base no sucesso/falha.
    """

    def __init__(self, settings=None, optimization_engine=None, experiment_manager=None, metrics=None):
        self.settings = settings or get_settings()
        self.optimization_engine = optimization_engine
        self.experiment_manager = experiment_manager
        self.metrics = metrics
        self.consumer: Optional[Consumer] = None
        self.running = False

    def start(self):
        """Iniciar consumer Kafka."""
        try:
            conf = {
                "bootstrap.servers": self.settings.kafka_bootstrap_servers,
                "group.id": self.settings.kafka_consumer_group_id,
                "auto.offset.reset": "latest",
                "enable.auto.commit": False,
                "max.poll.interval.ms": 300000,
            }

            self.consumer = Consumer(conf)
            self.consumer.subscribe([self.settings.kafka_experiments_topic])

            self.running = True

            logger.info("experiments_consumer_started", topic=self.settings.kafka_experiments_topic)

            asyncio.create_task(self._consume_loop())

        except Exception as e:
            logger.error("experiments_consumer_start_failed", error=str(e))
            raise

    async def _consume_loop(self):
        """Loop de consumo de mensagens."""
        try:
            while self.running:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("reached_end_of_partition", partition=msg.partition())
                    else:
                        logger.error("kafka_error", error=msg.error())
                    continue

                await self._process_message(msg)
                self.consumer.commit(asynchronous=False)

                if self.metrics:
                    self.metrics.increment_counter("experiment_results_consumed_total")

        except KafkaException as e:
            logger.error("kafka_consume_loop_error", error=str(e))
        except Exception as e:
            logger.error("consume_loop_error", error=str(e))

    async def _process_message(self, msg):
        """Processar mensagem de resultado de experimento."""
        try:
            experiment_result = json.loads(msg.value().decode("utf-8"))

            experiment_id = experiment_result.get("experiment_id", "unknown")
            status = experiment_result.get("status", "unknown")
            final_metrics = experiment_result.get("metrics", {})

            logger.info(
                "experiment_result_received",
                experiment_id=experiment_id,
                status=status,
            )

            # Atualizar ExperimentManager
            if self.experiment_manager:
                await self.experiment_manager.update_experiment_status(
                    experiment_id=experiment_id,
                    status=status,
                    final_metrics=final_metrics,
                )

            # Analisar resultados e atualizar Q-table
            if status == "COMPLETED":
                await self._process_completed_experiment(experiment_id, experiment_result)
            elif status == "FAILED" or status == "ABORTED":
                await self._process_failed_experiment(experiment_id, experiment_result)

        except json.JSONDecodeError as e:
            logger.error("experiment_result_deserialization_failed", error=str(e))
        except Exception as e:
            logger.error("experiment_result_processing_failed", error=str(e))

    async def _process_completed_experiment(self, experiment_id: str, result: dict):
        """
        Processar experimento completado com sucesso.

        Args:
            experiment_id: ID do experimento
            result: Resultado do experimento
        """
        try:
            # Obter detalhes do experimento
            experiment = await self.experiment_manager.get_experiment(experiment_id)

            if not experiment:
                logger.warning("experiment_not_found", experiment_id=experiment_id)
                return

            # Extrair métricas
            baseline_metrics = experiment.get("baseline_metrics", {})
            final_metrics = result.get("metrics", {})
            hypothesis = experiment.get("hypothesis", {})

            # Calcular reward baseado em melhoria
            improvement = self._calculate_improvement(baseline_metrics, final_metrics)

            # Determinar se atingiu critério de sucesso
            success_criteria = experiment.get("success_criteria", {})
            met_criteria = self._check_success_criteria(improvement, success_criteria)

            if met_criteria:
                reward = improvement
                logger.info(
                    "experiment_succeeded",
                    experiment_id=experiment_id,
                    improvement=improvement,
                    reward=reward,
                )

                if self.metrics:
                    self.metrics.increment_counter("experiments_succeeded_total")
            else:
                # Não atingiu critério, reward negativo
                reward = -0.1
                logger.warning(
                    "experiment_below_criteria",
                    experiment_id=experiment_id,
                    improvement=improvement,
                )

                if self.metrics:
                    self.metrics.increment_counter("experiments_below_criteria_total")

            # Atualizar Q-table
            if self.optimization_engine:
                state = hypothesis.get("state", {})
                action = hypothesis.get("action")
                next_state = self._extract_state(final_metrics)

                self.optimization_engine.update_q_table(
                    state=state,
                    action=action,
                    reward=reward,
                    next_state=next_state,
                )

                logger.info(
                    "q_table_updated",
                    experiment_id=experiment_id,
                    reward=reward,
                )

        except Exception as e:
            logger.error("process_completed_experiment_failed", experiment_id=experiment_id, error=str(e))

    async def _process_failed_experiment(self, experiment_id: str, result: dict):
        """
        Processar experimento falhado ou abortado.

        Args:
            experiment_id: ID do experimento
            result: Resultado do experimento
        """
        try:
            # Obter detalhes do experimento
            experiment = await self.experiment_manager.get_experiment(experiment_id)

            if not experiment:
                logger.warning("experiment_not_found", experiment_id=experiment_id)
                return

            hypothesis = experiment.get("hypothesis", {})

            # Reward negativo por falha
            reward = -0.5

            logger.warning(
                "experiment_failed",
                experiment_id=experiment_id,
                reason=result.get("failure_reason", "unknown"),
            )

            if self.metrics:
                self.metrics.increment_counter("experiments_failed_total")

            # Atualizar Q-table com reward negativo
            if self.optimization_engine:
                state = hypothesis.get("state", {})
                action = hypothesis.get("action")
                next_state = state  # Estado não mudou

                self.optimization_engine.update_q_table(
                    state=state,
                    action=action,
                    reward=reward,
                    next_state=next_state,
                )

                logger.info(
                    "q_table_updated_negative",
                    experiment_id=experiment_id,
                    reward=reward,
                )

        except Exception as e:
            logger.error("process_failed_experiment_failed", experiment_id=experiment_id, error=str(e))

    def _calculate_improvement(self, baseline: dict, final: dict) -> float:
        """
        Calcular melhoria entre baseline e final.

        Args:
            baseline: Métricas baseline
            final: Métricas finais

        Returns:
            Percentual de melhoria (0.0 - 1.0+)
        """
        # Exemplo simplificado - assumir métrica principal é latency_p95
        baseline_latency = baseline.get("latency_p95", 1000)
        final_latency = final.get("latency_p95", 1000)

        if baseline_latency == 0:
            return 0.0

        improvement = (baseline_latency - final_latency) / baseline_latency

        return max(0.0, improvement)  # Clamp mínimo em 0

    def _check_success_criteria(self, improvement: float, criteria: dict) -> bool:
        """
        Verificar se critério de sucesso foi atingido.

        Args:
            improvement: Melhoria alcançada
            criteria: Critérios de sucesso

        Returns:
            True se critérios atingidos
        """
        min_improvement = criteria.get("min_improvement", 0.05)
        return improvement >= min_improvement

    def _extract_state(self, metrics: dict) -> dict:
        """
        Extrair estado das métricas.

        Args:
            metrics: Métricas atuais

        Returns:
            Estado discretizado
        """
        # Discretizar métricas em buckets
        latency = metrics.get("latency_p95", 1000)
        error_rate = metrics.get("error_rate", 0.0)
        slo_compliance = metrics.get("slo_compliance", 1.0)

        latency_bucket = "low" if latency < 500 else "medium" if latency < 1000 else "high"
        error_bucket = "low" if error_rate < 0.01 else "medium" if error_rate < 0.05 else "high"
        slo_bucket = "compliant" if slo_compliance >= 0.99 else "degraded"

        return {
            "latency": latency_bucket,
            "error_rate": error_bucket,
            "slo_compliance": slo_bucket,
        }

    def stop(self):
        """Parar consumer."""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("experiments_consumer_stopped")
