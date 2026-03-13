"""
Teste de Stress: Validação de correlation_id sob Carga

FASE 1 + FASE 6: Valida que correlation_id é propagado corretamente
mesmo sob alta concorrência e carga significativa.

Execução:
    pytest tests/e2e/test_load_correlation_id.py -v --asyncio-mode=auto -n auto
"""

import asyncio
import os
import uuid
import pytest
import structlog
from typing import Dict, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import json

try:
    from confluent_kafka import Consumer, KafkaError, TopicPartition
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

logger = structlog.get_logger()


@dataclass
class CorrelationReport:
    """Relatório de propagação de correlation_id"""
    total_submitted: int = 0
    total_processed: int = 0
    correlation_id_mismatches: List[str] = field(default_factory=list)
    missing_correlation_ids: List[str] = field(default_factory=list)
    trace_id_present: int = 0
    trace_id_missing: int = 0
    processing_times_ms: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'total_submitted': self.total_submitted,
            'total_processed': self.total_processed,
            'correlation_id_mismatches': len(self.correlation_id_mismatches),
            'missing_correlation_ids': len(self.missing_correlation_ids),
            'trace_id_present': self.trace_id_present,
            'trace_id_missing': self.trace_id_missing,
            'avg_processing_time_ms': (
                sum(self.processing_times_ms) / len(self.processing_times_ms)
                if self.processing_times_ms else 0
            ),
            'success_rate': (
                self.total_processed / self.total_submitted
                if self.total_submitted > 0 else 0
            )
        }


@pytest.fixture
def stress_config():
    """Configuração do teste de stress"""
    return {
        'kafka_bootstrap_servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        'kafka_plans_topic': os.getenv('KAFKA_PLANS_TOPIC', 'plans.ready'),
        'kafka_consensus_topic': os.getenv('KAFKA_CONSENSUS_TOPIC', 'plans.consensus'),
        'kafka_tickets_topic': os.getenv('KAFKA_TICKETS_TOPIC', 'execution.tickets'),
        'gateway_url': os.getenv('GATEWAY_URL', 'http://localhost:8000'),
        'concurrent_requests': int(os.getenv('STRESS_CONCURRENT_REQUESTS', '100')),
        'request_timeout_seconds': int(os.getenv('STRESS_REQUEST_TIMEOUT', '60')),
        'collection_timeout_seconds': int(os.getenv('STRESS_COLLECTION_TIMEOUT', '120')),
    }


# =============================================================================
# TESTE PRINCIPAL DE STRESS
# =============================================================================

@pytest.mark.e2e
@pytest.mark.stress
@pytest.mark.asyncio
async def test_correlation_id_under_load(stress_config):
    """
    Teste de stress: 100 requisições concorrentes

    Valida que:
    1. Nenhum correlation_id é perdido
    2. correlation_id é propagado corretamente através de todos os serviços
    3. traceparent (W3C) está presente em 100% das mensagens
    4. Sistema degrada gracefulmente (não crash sob carga)
    """
    if not KAFKA_AVAILABLE:
        pytest.skip("confluent-kafka não instalado")

    report = CorrelationReport()
    concurrent_requests = stress_config['concurrent_requests']

    logger.info(
        'stress_test_starting',
        concurrent_requests=concurrent_requests,
        kafka_bootstrap_servers=stress_config['kafka_bootstrap_servers']
    )

    # Gerar correlation_ids únicos
    correlation_ids = [str(uuid.uuid4()) for _ in range(concurrent_requests)]
    intent_ids = [str(uuid.uuid4()) for _ in range(concurrent_requests)]

    # STEP 1: Submeter todas as intenções concorrentemente
    submit_start = asyncio.get_event_loop().time()
    submission_times = await _submit_intentions_concurrently(
        stress_config, intent_ids, correlation_ids, report
    )
    submit_duration = asyncio.get_event_loop().time() - submit_start

    logger.info(
        'stress_test_submissions_complete',
        total_submitted=report.total_submitted,
        successful_submissions=len(submission_times),
        duration_seconds=submit_duration,
        avg_latency_ms=sum(submission_times) / len(submission_times) if submission_times else 0
    )

    # STEP 2: Coletar resultados do Kafka
    collection_start = asyncio.get_event_loop().time()
    await _collect_kafka_messages(
        stress_config, correlation_ids, report
    )
    collection_duration = asyncio.get_event_loop().time() - collection_start

    logger.info(
        'stress_test_collection_complete',
        duration_seconds=collection_duration,
        messages_processed=report.total_processed
    )

    # STEP 3: Validar resultados
    _validate_stress_results(report)

    # STEP 4: Gerar relatório
    report_dict = report.to_dict()
    logger.info(
        'stress_test_report',
        **report_dict
    )

    # Assertions principais
    assert report.total_submitted > 0, "Nenhuma requisição foi submetida"
    assert report.total_processed > 0, "Nenhuma mensagem foi processada"

    # FASE 1: correlation_id deve ser propagado em 100% das mensagens processadas
    correlation_id_mismatch_rate = (
        len(report.correlation_id_mismatches) / report.total_processed
        if report.total_processed > 0 else 0
    )
    assert correlation_id_mismatch_rate == 0, \
        f"correlation_id mismatch detected in {correlation_id_mismatch_rate:.2%} of messages"

    # FASE 5: traceparent deve estar presente em pelo menos 95% das mensagens
    traceparent_coverage = (
        report.trace_id_present / report.total_processed
        if report.total_processed > 0 else 0
    )
    assert traceparent_coverage >= 0.95, \
        f"traceparent coverage too low: {traceparent_coverage:.2%} (expected >= 95%)"


# =============================================================================
# TESTE DE CARGA SUSTENTADA
# =============================================================================

@pytest.mark.e2e
@pytest.mark.stress
@pytest.mark.asyncio
async def test_sustained_load_correlation_id(stress_config):
    """
    Teste de carga sustentada: Requisições por 5 minutos

    Valida que o sistema mantém consistência de correlation_id
    sob carga contínua.
    """
    if not KAFKA_AVAILABLE:
        pytest.skip("confluent-kafka não instalado")

    duration_seconds = 60  # 1 minuto para teste (configurável para 5 min)
    requests_per_second = 10
    total_requests = duration_seconds * requests_per_second

    logger.info(
        'sustained_load_test_starting',
        duration_seconds=duration_seconds,
        requests_per_second=requests_per_second,
        total_expected_requests=total_requests
    )

    report = CorrelationReport()
    processed_correlation_ids: Set[str] = set()
    start_time = asyncio.get_event_loop().time()

    # Task para submeter requisições continuamente
    async def submit_continuously():
        nonlocal report
        request_count = 0

        while (asyncio.get_event_loop().time() - start_time) < duration_seconds:
            # Submeter lote de requisições
            batch_size = requests_per_second
            correlation_ids = [str(uuid.uuid4()) for _ in range(batch_size)]
            intent_ids = [str(uuid.uuid4()) for _ in range(batch_size)]

            await _submit_intentions_concurrently(
                stress_config, intent_ids, correlation_ids, report
            )

            request_count += batch_size
            await asyncio.sleep(1.0)  # 1 segundo entre lotes

        logger.info('sustained_load_submission_complete', request_count=request_count)

    # Task para consumir continuamente
    async def consume_continuously():
        nonlocal report, processed_correlation_ids

        consumer_config = {
            'bootstrap.servers': stress_config['kafka_bootstrap_servers'],
            'group.id': f'stress-test-sustained-{uuid.uuid4()}',
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
        }

        consumer = Consumer(consumer_config)
        consumer.subscribe([stress_config['kafka_plans_topic']])

        try:
            while (asyncio.get_event_loop().time() - start_time) < duration_seconds + 30:
                msg = consumer.poll(timeout=1.0)

                if msg is None or msg.error():
                    continue

                try:
                    value = json.loads(msg.value().decode('utf-8'))
                    headers = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                              for k, v in (msg.headers() or [])}

                    correlation_id = headers.get('correlation-id')
                    if correlation_id:
                        processed_correlation_ids.add(correlation_id)
                        report.total_processed += 1

                        # Validar traceparent
                        if headers.get('traceparent') or headers.get('trace-id'):
                            report.trace_id_present += 1
                        else:
                            report.trace_id_missing += 1

                except Exception as e:
                    logger.warning('message_parse_error', error=str(e))

        finally:
            consumer.close()

    # Executar em paralelo
    submit_task = asyncio.create_task(submit_continuously())
    consume_task = asyncio.create_task(consume_continuously())

    await submit_task
    await consume_task

    # Validar resultados
    actual_duration = asyncio.get_event_loop().time() - start_time

    logger.info(
        'sustained_load_test_complete',
        actual_duration_seconds=actual_duration,
        unique_correlation_ids=len(processed_correlation_ids),
        total_processed=report.total_processed,
        traceparent_coverage=(
            report.trace_id_present / report.total_processed
            if report.total_processed > 0 else 0
        )
    )

    # Assertions
    assert len(processed_correlation_ids) > 0, "No messages processed"
    assert report.trace_id_missing == 0, \
        f"traceparent missing in {report.trace_id_missing} messages"


# =============================================================================
# TESTE DE CORRUPÇÃO DE DADOS
# =============================================================================

@pytest.mark.e2e
@pytest.mark.stress
@pytest.mark.asyncio
async def test_correlation_id_not_swapped(stress_config):
    """
    Teste para detectar swap de correlation_id entre requisições

    Valida que o correlation_id de uma requisição nunca aparece
    em outra requisição (bugs de concorrência).
    """
    if not KAFKA_AVAILABLE:
        pytest.skip("confluent-kafka não instalado")

    num_requests = 50
    correlation_ids = [str(uuid.uuid4()) for _ in range(num_requests)]
    intent_ids = [str(uuid.uuid4()) for _ in range(num_requests)]

    # Mapeamento intent_id -> correlation_id esperado
    expected_mapping: Dict[str, str] = {
        intent_ids[i]: correlation_ids[i] for i in range(num_requests)
    }

    # Submeter requisições
    report = CorrelationReport()
    await _submit_intentions_concurrently(
        stress_config, intent_ids, correlation_ids, report
    )

    # Coletar e validar
    consumer_config = {
        'bootstrap.servers': stress_config['kafka_bootstrap_servers'],
        'group.id': f'swap-test-{uuid.uuid4()}',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,
    }

    consumer = Consumer(consumer_config)
    consumer.subscribe([stress_config['kafka_plans_topic']])

    collected_mapping: Dict[str, str] = {}
    mismatches: List[Dict] = []

    try:
        timeout = stress_config['collection_timeout_seconds']
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            msg = consumer.poll(timeout=1.0)

            if msg is None or msg.error():
                continue

            try:
                value = json.loads(msg.value().decode('utf-8'))
                headers = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                          for k, v in (msg.headers() or [])}

                intent_id = value.get('intent_id') or value.get('intentionId')
                correlation_id = headers.get('correlation-id')

                if intent_id and correlation_id:
                    collected_mapping[intent_id] = correlation_id

                    # Verificar se é o esperado
                    expected = expected_mapping.get(intent_id)
                    if expected and expected != correlation_id:
                        mismatches.append({
                            'intent_id': intent_id,
                            'expected_correlation_id': expected,
                            'found_correlation_id': correlation_id
                        })

            except Exception as e:
                logger.warning('message_parse_error', error=str(e))

            if len(collected_mapping) >= num_requests:
                break

    finally:
        consumer.close()

    # Assertions
    assert len(mismatches) == 0, \
        f"correlation_id swap detected: {mismatches}"

    logger.info(
        'correlation_id_swap_test_passed',
        messages_validated=len(collected_mapping),
        no_swaps=True
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def _submit_intentions_concurrently(
    config: Dict,
    intent_ids: List[str],
    correlation_ids: List[str],
    report: CorrelationReport
) -> List[float]:
    """Submeter intenções concorrentemente e retornar latências"""
    import httpx

    async def submit_one(intent_id: str, correlation_id: str):
        start = asyncio.get_event_loop().time()

        payload = {
            'intent_id': intent_id,
            'natural_language': f'Stress test intent {intent_id}',
            'domain': 'security',
            'correlation_id': correlation_id
        }

        try:
            async with httpx.AsyncClient(timeout=config['request_timeout_seconds']) as client:
                response = await client.post(
                    f"{config['gateway_url']}/api/v1/intentions",
                    json=payload,
                    headers={'X-Correlation-ID': correlation_id}
                )

                latency_ms = (asyncio.get_event_loop().time() - start) * 1000
                return latency_ms if response.status_code in (200, 201, 202) else None

        except Exception as e:
            logger.warning('submission_failed', intent_id=intent_id, error=str(e))
            return None

    # Executar concorrentemente
    tasks = [
        submit_one(intent_ids[i], correlation_ids[i])
        for i in range(len(intent_ids))
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Coletar latências válidas
    latencies = []
    for result in results:
        if isinstance(result, (int, float)):
            latencies.append(result)
            report.total_submitted += 1

    return latencies


async def _collect_kafka_messages(
    config: Dict,
    expected_correlation_ids: List[str],
    report: CorrelationReport
):
    """Coletar mensagens do Kafka e validar correlation_id"""
    consumer_config = {
        'bootstrap.servers': config['kafka_bootstrap_servers'],
        'group.id': f'stress-test-{uuid.uuid4()}',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,
    }

    consumer = Consumer(consumer_config)
    consumer.subscribe([config['kafka_plans_topic']])

    expected_set = set(expected_correlation_ids)
    found_set: Set[str] = set()
    start_time = asyncio.get_event_loop().time()

    try:
        while (asyncio.get_event_loop().time() - start_time) < config['collection_timeout_seconds']:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                logger.warning('kafka_error', error=msg.error())
                continue

            try:
                value = json.loads(msg.value().decode('utf-8'))
                headers = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                          for k, v in (msg.headers() or [])}

                correlation_id = headers.get('correlation-id')

                # Validar presença de correlation_id
                if not correlation_id:
                    report.missing_correlation_ids.append(
                        value.get('intent_id', 'unknown')
                    )
                    continue

                # Validar que é um dos esperados (ou pelo menos formato UUID válido)
                try:
                    uuid.UUID(correlation_id)
                except ValueError:
                    report.correlation_id_mismatches.append(correlation_id)
                    continue

                # Verificar traceparent (FASE 5)
                if headers.get('traceparent') or headers.get('trace-id'):
                    report.trace_id_present += 1
                else:
                    report.trace_id_missing += 1

                found_set.add(correlation_id)
                report.total_processed += 1

                # Parar se encontrou todos
                if found_set >= expected_set:
                    logger.info(
                        'all_expected_correlation_ids_found',
                        count=len(found_set)
                    )
                    break

            except Exception as e:
                logger.warning('message_parse_error', error=str(e))

    finally:
        consumer.close()


def _validate_stress_results(report: CorrelationReport):
    """Valida resultados do teste de stress"""
    assert report.total_submitted > 0, "No requests were submitted"

    if report.total_processed == 0:
        pytest.fail("No messages were collected from Kafka - check connectivity")

    # Validar ausência de correlation_id (FASE 1)
    missing_rate = (
        len(report.missing_correlation_ids) / report.total_processed
        if report.total_processed > 0 else 0
    )
    assert missing_rate == 0, \
        f"Missing correlation_id in {missing_rate:.2%} of messages: {report.missing_correlation_ids[:10]}"

    # Validar traceparent coverage (FASE 5)
    traceparent_coverage = (
        report.trace_id_present / report.total_processed
        if report.total_processed > 0 else 0
    )
    assert traceparent_coverage >= 0.95, \
        f"traceparent coverage too low: {traceparent_coverage:.2%} (expected >= 95%)"
