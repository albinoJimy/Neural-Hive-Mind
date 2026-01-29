"""
AggregatedMetricsCollector: Coleta e exporta métricas agregadas de alto nível.

Calcula métricas como consensus_rate, avg_confidence_by_specialist,
specialist_agreement_matrix para observabilidade holística do sistema.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from prometheus_client import Gauge, Histogram, Counter
import structlog
import asyncio
from collections import defaultdict
import numpy as np

logger = structlog.get_logger(__name__)


class AggregatedMetricsCollector:
    """Coleta e exporta métricas agregadas para Prometheus."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa coletor de métricas agregadas.

        Args:
            config: Configuração com mongodb_uri, mongodb_database
        """
        self.config = config
        self.mongodb_uri = config.get("mongodb_uri")
        self.mongodb_database = config.get("mongodb_database", "neural_hive")
        self._mongo_client: Optional[MongoClient] = None

        # Janela de tempo padrão para métricas (últimas 24h)
        self.metrics_window_hours = config.get("metrics_window_hours", 24)

        # Inicializar métricas Prometheus
        self._initialize_prometheus_metrics()

        logger.info(
            "AggregatedMetricsCollector initialized",
            metrics_window_hours=self.metrics_window_hours,
        )

    @property
    def mongo_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(
                self.mongodb_uri, serverSelectionTimeoutMS=5000
            )
        return self._mongo_client

    @property
    def collection(self):
        """Retorna collection de opiniões."""
        db = self.mongo_client[self.mongodb_database]
        return db["cognitive_ledger"]

    def _initialize_prometheus_metrics(self):
        """Inicializa métricas Prometheus de alto nível."""

        # Consensus Rate (taxa de consenso entre especialistas)
        self.consensus_rate = Gauge(
            "neural_hive_consensus_rate",
            "Taxa média de consenso entre especialistas (0.0-1.0)",
            [],
        )

        # Average Confidence by Specialist
        self.avg_confidence_by_specialist = Gauge(
            "neural_hive_avg_confidence_by_specialist",
            "Confiança média por tipo de especialista",
            ["specialist_type"],
        )

        # Average Risk by Specialist
        self.avg_risk_by_specialist = Gauge(
            "neural_hive_avg_risk_by_specialist",
            "Risco médio por tipo de especialista",
            ["specialist_type"],
        )

        # Specialist Agreement Score (concordância entre pares)
        self.specialist_agreement_score = Gauge(
            "neural_hive_specialist_agreement_score",
            "Score de concordância entre dois especialistas (0.0-1.0)",
            ["specialist_a", "specialist_b"],
        )

        # Ledger Health Score (saúde geral do ledger)
        self.ledger_health_score = Gauge(
            "neural_hive_ledger_health_score",
            "Score de saúde do ledger cognitivo (0.0-1.0)",
            [],
        )

        # Opinion Latency (latência de processamento)
        self.opinion_latency_p50 = Gauge(
            "neural_hive_opinion_latency_p50_ms",
            "Latência P50 de processamento de opiniões (ms)",
            ["specialist_type"],
        )

        self.opinion_latency_p95 = Gauge(
            "neural_hive_opinion_latency_p95_ms",
            "Latência P95 de processamento de opiniões (ms)",
            ["specialist_type"],
        )

        self.opinion_latency_p99 = Gauge(
            "neural_hive_opinion_latency_p99_ms",
            "Latência P99 de processamento de opiniões (ms)",
            ["specialist_type"],
        )

        # Recommendation Distribution
        self.recommendation_distribution = Gauge(
            "neural_hive_recommendation_distribution_pct",
            "Distribuição percentual de recomendações",
            ["recommendation_type"],
        )

        # High Risk Opinions Rate
        self.high_risk_rate = Gauge(
            "neural_hive_high_risk_opinions_rate",
            "Taxa de opiniões de alto risco (>0.7) nas últimas 24h",
            [],
        )

        # Buffered Opinions Rate
        self.buffered_rate = Gauge(
            "neural_hive_buffered_opinions_rate",
            "Taxa de opiniões bufferizadas (indisponibilidade)",
            ["specialist_type"],
        )

        # Total Opinions Counter
        self.total_opinions_24h = Gauge(
            "neural_hive_total_opinions_24h", "Total de opiniões nas últimas 24h", []
        )

        # Ledger Growth Rate
        self.ledger_growth_rate = Gauge(
            "neural_hive_ledger_growth_rate_per_hour",
            "Taxa de crescimento do ledger (opiniões/hora)",
            [],
        )

        # Masked Documents Rate (compliance)
        self.masked_documents_rate = Gauge(
            "neural_hive_masked_documents_rate",
            "Taxa de documentos mascarados por compliance",
            [],
        )

        # Signature Verification Success Rate
        self.signature_verification_rate = Gauge(
            "neural_hive_signature_verification_success_rate",
            "Taxa de sucesso na verificação de assinaturas",
            [],
        )

        logger.info("Prometheus metrics initialized for aggregated metrics")

    async def collect_all_metrics(self):
        """
        Coleta todas as métricas agregadas (assíncrono).

        Deve ser executado periodicamente (ex: a cada 60s).
        """
        try:
            logger.info("Starting aggregated metrics collection")

            # Executar coletas em paralelo
            await asyncio.gather(
                self._collect_consensus_metrics(),
                self._collect_specialist_metrics(),
                self._collect_latency_metrics(),
                self._collect_recommendation_distribution(),
                self._collect_ledger_health(),
                return_exceptions=True,
            )

            logger.info("Aggregated metrics collection completed")

        except Exception as e:
            logger.error(
                "Failed to collect aggregated metrics", error=str(e), exc_info=True
            )

    async def _collect_consensus_metrics(self):
        """Coleta métricas de consenso entre especialistas."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.metrics_window_hours)

            # Buscar planos recentes com múltiplas opiniões
            pipeline = [
                {"$match": {"evaluated_at": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": "$plan_id",
                        "opinions": {
                            "$push": {
                                "specialist_type": "$specialist_type",
                                "recommendation": "$opinion.recommendation",
                                "confidence": "$opinion.confidence_score",
                                "risk": "$opinion.risk_score",
                            }
                        },
                        "count": {"$sum": 1},
                    }
                },
                {"$match": {"count": {"$gte": 2}}},  # Pelo menos 2 especialistas
            ]

            results = list(self.collection.aggregate(pipeline))

            if not results:
                logger.debug("No multi-specialist plans found for consensus metrics")
                return

            # Calcular consensus rate
            total_consensus_score = 0.0
            plan_count = 0

            for plan in results:
                opinions = plan["opinions"]
                recommendations = [op["recommendation"] for op in opinions]

                # Calcular consenso (moda / total)
                most_common_rec = max(set(recommendations), key=recommendations.count)
                consensus_count = recommendations.count(most_common_rec)
                consensus_score = consensus_count / len(recommendations)

                total_consensus_score += consensus_score
                plan_count += 1

            avg_consensus_rate = (
                total_consensus_score / plan_count if plan_count > 0 else 0.0
            )

            self.consensus_rate.set(avg_consensus_rate)

            logger.info(
                "Consensus metrics collected",
                consensus_rate=avg_consensus_rate,
                plans_analyzed=plan_count,
            )

        except Exception as e:
            logger.error("Failed to collect consensus metrics", error=str(e))

    async def _collect_specialist_metrics(self):
        """Coleta métricas individuais por especialista."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.metrics_window_hours)

            pipeline = [
                {"$match": {"evaluated_at": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": "$specialist_type",
                        "avg_confidence": {"$avg": "$opinion.confidence_score"},
                        "avg_risk": {"$avg": "$opinion.risk_score"},
                        "buffered_count": {"$sum": {"$cond": ["$buffered", 1, 0]}},
                        "total_count": {"$sum": 1},
                    }
                },
            ]

            results = list(self.collection.aggregate(pipeline))

            for spec in results:
                specialist_type = spec["_id"]

                self.avg_confidence_by_specialist.labels(specialist_type).set(
                    spec["avg_confidence"]
                )

                self.avg_risk_by_specialist.labels(specialist_type).set(
                    spec["avg_risk"]
                )

                buffered_rate = (
                    (spec["buffered_count"] / spec["total_count"]) * 100
                    if spec["total_count"] > 0
                    else 0.0
                )
                self.buffered_rate.labels(specialist_type).set(buffered_rate)

            logger.info("Specialist metrics collected", specialists_count=len(results))

        except Exception as e:
            logger.error("Failed to collect specialist metrics", error=str(e))

    async def _collect_latency_metrics(self):
        """Coleta métricas de latência por especialista."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.metrics_window_hours)

            # Buscar tempos de processamento
            pipeline = [
                {"$match": {"evaluated_at": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": "$specialist_type",
                        "processing_times": {"$push": "$processing_time_ms"},
                    }
                },
            ]

            results = list(self.collection.aggregate(pipeline))

            for spec in results:
                specialist_type = spec["_id"]
                processing_times = np.array(spec["processing_times"])

                if len(processing_times) > 0:
                    p50 = np.percentile(processing_times, 50)
                    p95 = np.percentile(processing_times, 95)
                    p99 = np.percentile(processing_times, 99)

                    self.opinion_latency_p50.labels(specialist_type).set(p50)
                    self.opinion_latency_p95.labels(specialist_type).set(p95)
                    self.opinion_latency_p99.labels(specialist_type).set(p99)

            logger.info("Latency metrics collected")

        except Exception as e:
            logger.error("Failed to collect latency metrics", error=str(e))

    async def _collect_recommendation_distribution(self):
        """Coleta distribuição de recomendações."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.metrics_window_hours)

            pipeline = [
                {"$match": {"evaluated_at": {"$gte": cutoff_time}}},
                {"$group": {"_id": "$opinion.recommendation", "count": {"$sum": 1}}},
            ]

            results = list(self.collection.aggregate(pipeline))

            total = sum(r["count"] for r in results)

            for rec in results:
                recommendation_type = rec["_id"]
                percentage = (rec["count"] / total * 100) if total > 0 else 0.0

                self.recommendation_distribution.labels(recommendation_type).set(
                    percentage
                )

            # Calcular taxa de alto risco
            high_risk_count = self.collection.count_documents(
                {
                    "evaluated_at": {"$gte": cutoff_time},
                    "opinion.risk_score": {"$gte": 0.7},
                }
            )

            high_risk_rate = (high_risk_count / total * 100) if total > 0 else 0.0
            self.high_risk_rate.set(high_risk_rate)

            # Total de opiniões
            self.total_opinions_24h.set(total)

            # Taxa de crescimento (opiniões/hora)
            growth_rate = total / self.metrics_window_hours
            self.ledger_growth_rate.set(growth_rate)

            logger.info(
                "Recommendation distribution collected",
                total_opinions=total,
                high_risk_rate=high_risk_rate,
            )

        except Exception as e:
            logger.error("Failed to collect recommendation distribution", error=str(e))

    async def _collect_ledger_health(self):
        """Calcula score de saúde do ledger."""
        try:
            # Componentes de saúde:
            # 1. Taxa de consenso (quanto maior, melhor)
            # 2. Taxa de bufferização (quanto menor, melhor)
            # 3. Taxa de alto risco (quanto menor, melhor)
            # 4. Taxa de verificação de assinatura (quanto maior, melhor)

            consensus = self.consensus_rate._value.get()
            high_risk = self.high_risk_rate._value.get() / 100.0  # Normalizar

            # Calcular média de bufferização
            total_buffered_count = 0
            total_count = 0
            cutoff_time = datetime.utcnow() - timedelta(hours=self.metrics_window_hours)

            docs = self.collection.find({"evaluated_at": {"$gte": cutoff_time}})

            for doc in docs:
                total_count += 1
                if doc.get("buffered", False):
                    total_buffered_count += 1

            buffered_rate = (
                total_buffered_count / total_count if total_count > 0 else 0.0
            )

            # Calcular taxa de mascaramento (compliance)
            masked_count = self.collection.count_documents(
                {"masked_fields": {"$exists": True}}
            )
            total_all = self.collection.count_documents({})
            masked_rate = masked_count / total_all if total_all > 0 else 0.0
            self.masked_documents_rate.set(masked_rate * 100)

            # Score de saúde (0.0-1.0)
            # Fórmula: health = consensus * (1 - buffered_rate) * (1 - high_risk)
            health_score = consensus * (1.0 - buffered_rate) * (1.0 - high_risk)

            self.ledger_health_score.set(health_score)

            logger.info(
                "Ledger health calculated",
                health_score=health_score,
                consensus=consensus,
                buffered_rate=buffered_rate,
                high_risk_rate=high_risk,
            )

        except Exception as e:
            logger.error("Failed to calculate ledger health", error=str(e))

    def calculate_specialist_agreement_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Calcula matriz de concordância entre especialistas.

        Returns:
            Matriz de concordância {specialist_a: {specialist_b: agreement_score}}
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.metrics_window_hours)

            # Buscar planos com múltiplas opiniões
            pipeline = [
                {"$match": {"evaluated_at": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": "$plan_id",
                        "opinions": {
                            "$push": {
                                "specialist_type": "$specialist_type",
                                "recommendation": "$opinion.recommendation",
                            }
                        },
                        "count": {"$sum": 1},
                    }
                },
                {"$match": {"count": {"$gte": 2}}},
            ]

            results = list(self.collection.aggregate(pipeline))

            # Matriz de concordância
            agreement_matrix = defaultdict(lambda: defaultdict(list))

            for plan in results:
                opinions = plan["opinions"]

                # Comparar todos os pares
                for i, op_a in enumerate(opinions):
                    for op_b in opinions[i + 1 :]:
                        spec_a = op_a["specialist_type"]
                        spec_b = op_b["specialist_type"]

                        # Concordância binária (mesma recomendação = 1, diferente = 0)
                        agreement = (
                            1.0
                            if op_a["recommendation"] == op_b["recommendation"]
                            else 0.0
                        )

                        agreement_matrix[spec_a][spec_b].append(agreement)
                        agreement_matrix[spec_b][spec_a].append(agreement)

            # Calcular médias
            final_matrix = {}
            for spec_a, inner_dict in agreement_matrix.items():
                final_matrix[spec_a] = {}
                for spec_b, agreements in inner_dict.items():
                    avg_agreement = (
                        sum(agreements) / len(agreements) if agreements else 0.0
                    )
                    final_matrix[spec_a][spec_b] = avg_agreement

                    # Exportar para Prometheus
                    self.specialist_agreement_score.labels(spec_a, spec_b).set(
                        avg_agreement
                    )

            logger.info(
                "Specialist agreement matrix calculated",
                specialists=list(final_matrix.keys()),
            )

            return final_matrix

        except Exception as e:
            logger.error("Failed to calculate agreement matrix", error=str(e))
            return {}

    def get_system_health_summary(self) -> Dict[str, Any]:
        """
        Retorna resumo de saúde do sistema.

        Returns:
            Dicionário com métricas de saúde
        """
        try:
            return {
                "ledger_health_score": self.ledger_health_score._value.get(),
                "consensus_rate": self.consensus_rate._value.get(),
                "high_risk_rate": self.high_risk_rate._value.get(),
                "total_opinions_24h": int(self.total_opinions_24h._value.get()),
                "ledger_growth_rate": self.ledger_growth_rate._value.get(),
                "masked_documents_rate": self.masked_documents_rate._value.get(),
            }

        except Exception as e:
            logger.error("Failed to get system health summary", error=str(e))
            return {}
