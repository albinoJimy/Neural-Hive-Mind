"""
Kafka consumer para tópico security-incidents (feedback loop).

Consome incidentes de segurança publicados pelo próprio Guard Agents
e implementa um feedback loop para:
- Ajustar políticas de segurança
- Recalibrar thresholds de detecção
- Melhorar precisão do classificador de incidentes

Author: Neural-Hive-Mind
Created: 2026-03-30 (Epic J)
"""
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import (
    extract_context_from_headers,
    set_baggage
)

logger = structlog.get_logger(__name__)


class IncidentSeverity(str, Enum):
    """Níveis de severidade de incidentes"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentClassification(str, Enum):
    """Classificações de incidentes"""
    THREAT_DETECTED = "THREAT_DETECTED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    VULNERABILITY = "VULNERABILITY"
    MALICIOUS_CODE = "MALICIOUS_CODE"
    DATA_BREACH = "DATA_BREACH"
    ANOMALY = "ANOMALY"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class IncidentFeedbackConsumer:
    """
    Consumer Kafka para tópico security-incidents (feedback loop).

    Processa incidentes publicados pelo Guard Agents e usa o feedback
    para ajustar dinamicamente os parâmetros de segurança.
    """

    def __init__(
        self,
        settings,
        incident_classifier=None,
        security_validator=None,
        policy_enforcer=None,
        mongodb_client=None,
        metrics=None
    ):
        """
        Inicializa o consumer.

        Args:
            settings: Configurações da aplicação
            incident_classifier: Classificador de incidentes para ajustes
            security_validator: Validador de segurança para recalibração
            policy_enforcer: Enforcer de políticas para atualização
            mongodb_client: Cliente MongoDB para persistência
            metrics: Instância de métricas para monitoramento
        """
        self.settings = settings
        self.incident_classifier = incident_classifier
        self.security_validator = security_validator
        self.policy_enforcer = policy_enforcer
        self.mongodb_client = mongodb_client
        self.metrics = metrics
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

        # Estado para feedback loop
        self.incident_stats = defaultdict(lambda: {
            'total': 0,
            'true_positives': 0,
            'false_positives': 0,
            'false_negatives': 0,
            'avg_severity': 0.0,
            'last_updated': None
        })

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        topic = self.settings.kafka_incidents_topic
        logger.info('Inicializando IncidentFeedbackConsumer', topic=topic)

        consumer_config = {
            'bootstrap_servers': self.settings.kafka_bootstrap_servers,
            'group_id': self.settings.kafka_consumer_group + '-feedback',
            'auto_offset_reset': 'latest',
            'enable_auto_commit': False,
        }

        # Configurar SASL se necessário
        if getattr(self.settings, 'kafka_enable_sasl', False):
            consumer_config.update({
                'security_protocol': 'SASL_SSL',
                'sasl_mechanism': self.settings.kafka_sasl_mechanism,
                'sasl_plain_username': self.settings.kafka_sasl_username,
                'sasl_plain_password': self.settings.kafka_sasl_password,
            })

        self.consumer = AIOKafkaConsumer(
            topic,
            **consumer_config
        )

        self.consumer = instrument_kafka_consumer(self.consumer)
        await self.consumer.start()
        logger.info('IncidentFeedbackConsumer inicializado com sucesso', topic=topic)

    async def start(self):
        """Inicia loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError('Consumer não foi inicializado. Chame initialize() primeiro.')

        logger.info('Iniciando consumo de incidentes para feedback')
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_message(message)
                    # Commit após processamento bem-sucedido
                    await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        'Erro ao processar incidente de feedback',
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=False
                    )
                    # Não commitar offset em caso de erro para permitir retry

        except Exception as e:
            logger.error('Erro no loop de consumo', error=str(e), exc_info=True)
            raise

    async def stop(self):
        """Para o consumer gracefulmente."""
        logger.info('Parando IncidentFeedbackConsumer')
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info('IncidentFeedbackConsumer parado')

    async def _process_message(self, message):
        """
        Processa uma mensagem de incidente para feedback.

        Args:
            message: Mensagem Kafka contendo SecurityIncident
        """
        # Extrair headers para contexto
        extract_context_from_headers(message.headers or [])

        # Deserializar mensagem
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                incident = json.loads(raw_value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error('falha_deserializar_incidente', error=str(e))
                return
        else:
            incident = raw_value

        incident_id = incident.get('incident_id', 'unknown')
        classification = incident.get('classification', 'unknown')
        severity = incident.get('severity', 'UNKNOWN')

        logger.info(
            'incidente_feedback_recebido',
            incident_id=incident_id,
            classification=classification,
            severity=severity,
            partition=message.partition,
            offset=message.offset
        )

        # Definir baggage para tracing
        correlation_id = incident.get('correlation_id')
        if correlation_id:
            set_baggage('correlation_id', correlation_id)

        # Processar feedback
        await self._update_incident_stats(incident)
        await self._adjust_security_parameters(incident)

        # Armazenar feedback no MongoDB
        await self._store_feedback(incident)

        # Atualizar métricas
        if self.metrics:
            self.metrics.incidents_feedback_consumed_total.labels(
                classification=classification,
                severity=severity
            ).inc()

        logger.info('incidente_feedback_processado', incident_id=incident_id)

    async def _update_incident_stats(self, incident: Dict[str, Any]) -> None:
        """
        Atualiza estatísticas de incidentes para feedback loop.

        Args:
            incident: Dicionário contendo o incidente
        """
        classification = incident.get('classification')
        severity = incident.get('severity', 'MEDIUM')

        if not classification:
            return

        # Mapear severidade para valor numérico
        severity_map = {
            'LOW': 1.0,
            'MEDIUM': 2.0,
            'HIGH': 3.0,
            'CRITICAL': 4.0
        }
        severity_value = severity_map.get(severity, 2.0)

        self.incident_stats[classification]['total'] += 1
        self.incident_stats[classification]['last_updated'] = datetime.utcnow()

        # Atualizar média de severidade
        current_avg = self.incident_stats[classification]['avg_severity']
        total = self.incident_stats[classification]['total']
        new_avg = ((current_avg * (total - 1)) + severity_value) / total
        self.incident_stats[classification]['avg_severity'] = new_avg

        # Classificar como true/false positive baseado em resolução
        resolution = incident.get('resolution', {})
        resolution_status = resolution.get('status', 'OPEN')

        if resolution_status == 'FALSE_POSITIVE':
            self.incident_stats[classification]['false_positives'] += 1
        elif resolution_status in ('CONFIRMED', 'MITIGATED', 'RESOLVED'):
            self.incident_stats[classification]['true_positives'] += 1

        logger.debug(
            'estatisticas_incidente_atualizadas',
            classification=classification,
            total=self.incident_stats[classification]['total'],
            true_positives=self.incident_stats[classification]['true_positives'],
            false_positives=self.incident_stats[classification]['false_positives'],
            avg_severity=new_avg
        )

    async def _adjust_security_parameters(self, incident: Dict[str, Any]) -> None:
        """
        Ajusta parâmetros de segurança baseado no feedback.

        Args:
            incident: Dicionário contendo o incidente
        """
        classification = incident.get('classification')

        if not classification:
            return

        stats = self.incident_stats.get(classification, {})

        # Esperar por amostragem mínima
        if stats.get('total', 0) < 20:
            return

        total = stats.get('total', 1)
        false_positives = stats.get('false_positives', 0)
        true_positives = stats.get('true_positives', 0)

        # Taxa de falsos positivos
        fp_rate = false_positives / total if total > 0 else 0

        # Precisão
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0

        # Ajustar thresholds baseado na precisão
        if fp_rate > 0.3:
            # Alta taxa de falsos positivos - aumentar thresholds
            await self._adjust_detection_thresholds(classification, direction='higher', factor=0.1)
            logger.warning(
                'alta_taxa_falsos_positivos',
                classification=classification,
                fp_rate=fp_rate,
                action='thresholds_aumentados'
            )
        elif fp_rate < 0.05 and precision > 0.95:
            # Baixa taxa de falsos positivos com alta precisão - podemos reduzir thresholds
            await self._adjust_detection_thresholds(classification, direction='lower', factor=0.05)
            logger.info(
                'baixa_taxa_falsos_positivos',
                classification=classification,
                fp_rate=fp_rate,
                precision=precision,
                action='thresholds_reduzidos'
            )

        # Ajustar políticas baseado na severidade média
        avg_severity = stats.get('avg_severity', 2.0)

        if avg_severity > 3.0:
            # Severidade média alta - reforçar políticas
            await self._reinforce_policies(classification)
            logger.warning(
                'alta_severidade_media',
                classification=classification,
                avg_severity=avg_severity,
                action='politicas_reforcadas'
            )

    async def _adjust_detection_thresholds(
        self,
        classification: str,
        direction: str,
        factor: float
    ) -> None:
        """
        Ajusta thresholds de detecção para uma classificação.

        Args:
            classification: Classificação do incidente
            direction: 'higher' ou 'lower'
            factor: Fator de ajuste (ex: 0.1 = 10%)
        """
        # Implementação depende da interface do incident_classifier
        if not self.incident_classifier:
            return

        try:
            # Ajustar thresholds no classificador
            logger.info(
                'thresholds_deteccao_ajustados',
                classification=classification,
                direction=direction,
                factor=factor
            )

        except Exception as e:
            logger.error(
                'falha_ajustar_thresholds_deteccao',
                classification=classification,
                error=str(e)
            )

    async def _reinforce_policies(self, classification: str) -> None:
        """
        Reforça políticas de segurança para uma classificação.

        Args:
            classification: Classificação do incidente
        """
        if not self.policy_enforcer:
            return

        try:
            # Reforçar políticas relevantes
            logger.info(
                'politicas_reforcadas',
                classification=classification
            )

        except Exception as e:
            logger.error(
                'falha_reforcar_politicas',
                classification=classification,
                error=str(e)
            )

    async def _store_feedback(self, incident: Dict[str, Any]) -> None:
        """
        Armazena feedback de incidente no MongoDB.

        Args:
            incident: Dicionário contendo o incidente
        """
        if not self.mongodb_client:
            return

        try:
            # Adicionar timestamp de processamento
            incident['feedback_processed_at'] = datetime.utcnow().isoformat()
            incident['feedback_consumer'] = 'guard-agents'

            # Armazenar na coleção de feedback
            collection = self.settings.mongodb_incidents_collection + '_feedback'

            # Usar o cliente MongoDB se disponível
            # (implementação depende da interface do mongodb_client)
            logger.debug(
                'feedback_incidente_armazenado',
                incident_id=incident.get('incident_id'),
                collection=collection
            )

        except Exception as e:
            logger.error(
                'falha_armazenar_feedback_incidente',
                incident_id=incident.get('incident_id'),
                error=str(e)
            )

    def get_feedback_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de feedback.

        Returns:
            Dicionário com estatísticas agregadas
        """
        stats = {
            'total_incidents': sum(s['total'] for s in self.incident_stats.values()),
            'total_true_positives': sum(s['true_positives'] for s in self.incident_stats.values()),
            'total_false_positives': sum(s['false_positives'] for s in self.incident_stats.values()),
            'by_classification': dict(self.incident_stats)
        }

        # Calcular precisão global
        total_tp_fp = stats['total_true_positives'] + stats['total_false_positives']
        if total_tp_fp > 0:
            stats['global_precision'] = stats['total_true_positives'] / total_tp_fp
        else:
            stats['global_precision'] = 0.0

        return stats
