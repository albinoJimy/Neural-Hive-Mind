#!/usr/bin/env python3
"""
Coleta dados de produção para retreinamento ML de especialistas.

Consome tópico Kafka intentions.audit (90 dias de retenção) e consulta
MongoDB para histórico, filtrando decisões com confidence >= 0.7.

Gera dataset com mínimo 10k amostras por especialista.
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

# Kafka
from aiokafka import AIOKafkaConsumer
from aiokafka.structs import TopicPartition

# MongoDB
from motor.motor_asyncio import AsyncIOMotorClient

# Logging
import structlog
logger = structlog.get_logger(__name__)


class ProductionDataCollector:
    """
    Coleta dados de produção de múltiplas fontes:
    - Kafka (intentions.audit) - Eventos de intenção em tempo real
    - MongoDB (cognitive_plans) - Planos cognitivos gerados
    - MongoDB (specialist_feedback) - Feedback humano
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str = None,
        mongodb_uri: str = None,
        min_confidence: float = 0.7,
        collection_days: int = 90
    ):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers or os.getenv(
            'KAFKA_BOOTSTRAP_SERVERS',
            'neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092'
        )
        self.mongodb_uri = mongodb_uri or os.getenv(
            'MONGODB_URI',
            'mongodb://localhost:27017'
        )
        self.min_confidence = min_confidence
        self.collection_days = collection_days

        self.mongo_client: Optional[AsyncIOMotorClient] = None
        self.db = None

    async def initialize(self):
        """Inicializa conexões."""
        logger.info("Inicializando ProductionDataCollector...")

        # MongoDB
        self.mongo_client = AsyncIOMotorClient(self.mongodb_uri)
        self.db = self.mongo_client.neural_hive

        logger.info("Conexões inicializadas")

    async def close(self):
        """Fecha conexões."""
        if self.mongo_client:
            self.mongo_client.close()
        logger.info("Conexões fechadas")

    async def collect_from_kafka(
        self,
        topic: str = 'intentions.audit',
        max_messages: int = 50000
    ) -> List[Dict[str, Any]]:
        """
        Coleta eventos do tópico Kafka.

        Args:
            topic: Nome do tópico Kafka
            max_messages: Número máximo de mensagens a coletar

        Returns:
            Lista de eventos de intenção
        """
        logger.info(
            f"Coletando eventos do Kafka: {topic}",
            max_messages=max_messages
        )

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=f'production_collector_{datetime.now().strftime("%Y%m%d")}',
            auto_offset_reset='earliest',
            enable_auto_commit=False
        )

        events = []

        try:
            await consumer.start()

            # Buscar partições disponíveis
            partitions = await consumer.partitions_for_topic(topic)
            logger.info(f"Partições encontradas: {[p.partition for p in partitions]}")

            # Calcular offset alvo (90 dias atrás)
            cutoff_timestamp = int((datetime.utcnow() - timedelta(days=self.collection_days)).timestamp() * 1000)

            collected = 0
            timeout_counter = 0
            max_timeout = 100  # Número de iterações sem mensagem antes de parar

            while collected < max_messages and timeout_counter < max_timeout:
                async for msg in consumer:
                    try:
                        event = json.loads(msg.value.decode('utf-8'))

                        # Filtrar por timestamp
                        event_timestamp = event.get('timestamp', 0)
                        if isinstance(event_timestamp, str):
                            event_timestamp = int(datetime.fromisoformat(
                                event_timestamp.replace('Z', '+00:00')
                            ).timestamp() * 1000)

                        if event_timestamp < cutoff_timestamp:
                            continue

                        # Filtrar por confidence
                        confidence = event.get('confidence', 0.0)
                        if confidence >= self.min_confidence:
                            events.append(event)
                            collected += 1

                            if collected >= max_messages:
                                break

                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Evento inválido ignorado: {e}")
                        continue

                    timeout_counter = 0

                if collected >= max_messages:
                    break

                # Pequena pausa para evitar sobrecarga
                await asyncio.sleep(0.1)
                timeout_counter += 1

            logger.info(f"Coleta Kafka concluída: {len(events)} eventos")

        finally:
            await consumer.stop()

        return events

    async def collect_from_mongodb(
        self,
        specialist_types: List[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Coleta planos cognitivos do MongoDB.

        Args:
            specialist_types: Lista de tipos de especialista

        Returns:
            Dicionário com planos por especialista
        """
        if specialist_types is None:
            specialist_types = [
                'business', 'technical', 'behavior',
                'evolution', 'architecture'
            ]

        logger.info(
            "Coletando planos cognitivos do MongoDB",
            specialist_types=specialist_types
        )

        cutoff_date = datetime.utcnow() - timedelta(days=self.collection_days)

        plans_by_specialist = {stype: [] for stype in specialist_types}

        for specialist_type in specialist_types:
            cursor = self.db.cognitive_plans.find({
                'created_at': {'$gte': cutoff_date},
                'confidence_score': {'$gte': self.min_confidence}
            }).sort('created_at', -1)

            async for plan in cursor:
                plans_by_specialist[specialist_type].append(plan)

            logger.info(
                f"Planos coletados para {specialist_type}",
                count=len(plans_by_specialist[specialist_type])
            )

        return plans_by_specialist

    async def collect_feedback(
        self,
        opinion_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Coleta feedback humano para opiniões específicas.

        Args:
            opinion_ids: Lista de IDs de opinião

        Returns:
            Dicionário mapeando opinion_id -> feedback
        """
        logger.info(f"Coletando feedback para {len(opinion_ids)} opiniões")

        feedback_map = {}

        # Buscar em lotes para evitar cursor muito grande
        batch_size = 1000
        for i in range(0, len(opinion_ids), batch_size):
            batch = opinion_ids[i:i + batch_size]

            cursor = self.db.specialist_feedback.find({
                'opinion_id': {'$in': batch},
                'human_rating': {'$gte': 0.5}  # Feedback com boa qualidade
            })

            async for feedback in cursor:
                feedback_map[feedback['opinion_id']] = feedback

        logger.info(f"Feedback coletado: {len(feedback_map)} opiniões com feedback")

        return feedback_map

    async def generate_training_dataset(
        self,
        specialist_type: str,
        min_samples: int = 10000
    ) -> pd.DataFrame:
        """
        Gera dataset de treinamento para um especialista.

        Args:
            specialist_type: Tipo do especialista
            min_samples: Mínimo de amostras necessárias

        Returns:
            DataFrame com features e labels
        """
        logger.info(
            f"Gerando dataset para {specialist_type}",
            min_samples=min_samples
        )

        # 1. Coletar planos cognitivos
        cutoff_date = datetime.utcnow() - timedelta(days=self.collection_days)

        cursor = self.db.cognitive_plans.find({
            'created_at': {'$gte': cutoff_date},
            'confidence_score': {'$gte': self.min_confidence}
        }).sort('created_at', -1)

        plans = []
        opinion_ids = []

        async for plan in cursor:
            plans.append(plan)
            if 'opinion_ids' in plan:
                opinion_ids.extend(plan['opinion_ids'])

        logger.info(f"Planos coletados: {len(plans)}")

        if len(plans) < min_samples:
            logger.warning(
                f"Planos insuficientes para {specialist_type}",
                collected=len(plans),
                required=min_samples
            )

        # 2. Coletar feedback
        feedback_map = await self.collect_feedback(opinion_ids)

        # 3. Enriquecer planos com features e labels
        samples = []

        for plan in plans:
            # Extrair features básicas do plano
            features = self._extract_features_from_plan(plan, specialist_type)

            # Buscar feedback correspondente
            plan_opinion_ids = plan.get('opinion_ids', [])
            if plan_opinion_ids:
                for oid in plan_opinion_ids:
                    if oid in feedback_map:
                        feedback = feedback_map[oid]

                        # Label baseado em recomendação humana
                        human_recommendation = feedback.get('human_recommendation', 'approve')
                        features['label'] = self._recommendation_to_label(human_recommendation)
                        features['human_rating'] = feedback.get('human_rating', 0.0)

                        samples.append(features)

        logger.info(f"Amostras geradas: {len(samples)}")

        if len(samples) < min_samples:
            logger.warning(
                f"Amostras insuficientes após enriquecimento",
                samples=len(samples),
                required=min_samples
            )

        df = pd.DataFrame(samples)

        logger.info(
            f"Dataset gerado para {specialist_type}",
            total_samples=len(df),
            label_distribution=df['label'].value_counts().to_dict() if 'label' in df.columns else {}
        )

        return df

    def _extract_features_from_plan(
        self,
        plan: Dict[str, Any],
        specialist_type: str
    ) -> Dict[str, Any]:
        """Extrai features de um plano cognitivo."""
        tasks = plan.get('tasks', [])
        metadata = plan.get('metadata', {})

        # Features básicas
        features = {
            'num_tasks': len(tasks),
            'estimated_duration': plan.get('estimated_duration', 0) / 1000,  # ms -> seconds
            'complexity_score': plan.get('complexity_score', 0.5),
            'risk_score': plan.get('risk_score', 0.5),
            'specialist_type': specialist_type,
            'created_at': plan.get('created_at'),
            'plan_id': plan.get('plan_id', ''),
        }

        # Features das tarefas
        if tasks:
            durations = [t.get('estimated_duration', 0) for t in tasks]
            complexities = [t.get('complexity_score', 0.5) for t in tasks]

            features.update({
                'avg_task_duration': np.mean(durations) if durations else 0,
                'max_task_duration': np.max(durations) if durations else 0,
                'avg_task_complexity': np.mean(complexities) if complexities else 0,
                'task_count_by_type': len(set(t.get('type', 'unknown') for t in tasks)),
            })

        # Features contextuais
        context = plan.get('context', {})
        features.update({
            'has_domain_context': 1 if context.get('domain') else 0,
            'has_user_context': 1 if context.get('user') else 0,
            'has_tenant_context': 1 if context.get('tenant_id') else 0,
        })

        # Normalizar valores numéricos
        for key, value in features.items():
            if isinstance(value, (int, float)) and not np.isfinite(value):
                features[key] = 0.0

        return features

    def _recommendation_to_label(self, recommendation: str) -> int:
        """Converte recomendação em label numérico."""
        mapping = {
            'approve': 1,
            'reject': 0,
            'review_required': 2
        }
        return mapping.get(recommendation.lower(), 1)


async def main():
    """Função principal para execução standalone."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Coleta dados de produção para treinamento ML"
    )
    parser.add_argument(
        '--specialist',
        type=str,
        choices=['business', 'technical', 'behavior', 'evolution', 'architecture', 'all'],
        default='all',
        help='Especialista para coletar dados'
    )
    parser.add_argument(
        '--min-samples',
        type=int,
        default=10000,
        help='Número mínimo de amostras'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='/tmp/ml_training_data',
        help='Diretório para salvar datasets'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.7,
        help='Confiança mínima das amostras'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Dias de retenção'
    )

    args = parser.parse_args()

    # Criar diretório de saída
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Inicializar coletor
    collector = ProductionDataCollector(
        min_confidence=args.min_confidence,
        collection_days=args.days
    )

    try:
        await collector.initialize()

        # Determinar especialistas
        specialists = (
            ['business', 'technical', 'behavior', 'evolution', 'architecture']
            if args.specialist == 'all'
            else [args.specialist]
        )

        # Coletar dados para cada especialista
        for specialist in specialists:
            logger.info(f"Processando especialista: {specialist}")

            df = await collector.generate_training_dataset(
                specialist_type=specialist,
                min_samples=args.min_samples
            )

            # Salvar dataset
            output_file = output_dir / f'{specialist}_production_data.csv'
            df.to_csv(output_file, index=False)

            logger.info(f"Dataset salvo: {output_file}")

    finally:
        await collector.close()


if __name__ == '__main__':
    asyncio.run(main())
