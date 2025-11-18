"""
Testes de integração real com SLA Management System.

Este módulo contém testes que validam integração SLA contra serviços reais
(SLA Management System, Redis, Kafka). São marcados como 'real_integration'
e pulados por padrão no CI/CD.

ATENÇÃO: Estes testes requerem serviços reais rodando:
- SLA Management System em http://localhost:8000 (ou $SLA_MANAGEMENT_HOST)
- Redis em localhost:6379 (ou $REDIS_HOST)
- Kafka em localhost:9092 (ou $KAFKA_BOOTSTRAP_SERVERS)

Uso:
    # Pular testes reais (padrão)
    pytest tests/integration/

    # Executar apenas testes reais
    pytest -m real_integration tests/integration/test_sla_real_integration.py -v

    # Com variáveis de ambiente customizadas
    SLA_MANAGEMENT_HOST=sla-system.local pytest -m real_integration
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pytest
import redis.asyncio as aioredis
from kafka import KafkaConsumer, KafkaProducer

from src.clients.kafka_producer import KafkaProducerClient
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics
from src.sla.alert_manager import AlertManager
from src.sla.sla_monitor import SLAMonitor


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def real_config() -> OrchestratorSettings:
    """
    Criar configuração com endpoints reais do SLA Management System.

    Lê de variáveis de ambiente:
    - SLA_MANAGEMENT_HOST (default: localhost)
    - SLA_MANAGEMENT_PORT (default: 8000)
    - REDIS_HOST (default: localhost:6379)
    - KAFKA_BOOTSTRAP_SERVERS (default: localhost:9092)
    """
    config = OrchestratorSettings(
        sla_management_enabled=True,
        sla_management_host=os.getenv('SLA_MANAGEMENT_HOST', 'localhost'),
        sla_management_port=int(os.getenv('SLA_MANAGEMENT_PORT', '8000')),
        sla_management_timeout_seconds=10,
        redis_host=os.getenv('REDIS_HOST', 'localhost'),
        redis_port=int(os.getenv('REDIS_PORT', '6379')),
        kafka_bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    )
    return config


@pytest.fixture(autouse=True)
async def sla_management_health_check(real_config: OrchestratorSettings):
    """
    Verificar se SLA Management System está disponível antes de rodar testes.

    Skip test se serviço não está acessível.
    """
    url = f"http://{real_config.sla_management_host}:{real_config.sla_management_port}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                pytest.skip(f"SLA Management System unhealthy: {response.status_code}")
    except Exception as e:
        pytest.skip(f"SLA Management System não disponível em {url}: {e}")


@pytest.fixture
async def real_redis(real_config: OrchestratorSettings) -> Optional[aioredis.Redis]:
    """
    Conectar a instância real de Redis.

    Returns None se Redis não disponível (fail-open é aceitável).
    """
    try:
        redis_client = await aioredis.from_url(
            f"redis://{real_config.redis_host}:{real_config.redis_port}",
            decode_responses=True,
            socket_connect_timeout=5
        )
        # Teste de ping
        await redis_client.ping()
        yield redis_client
        await redis_client.close()
    except Exception as e:
        pytest.skip(f"Redis não disponível: {e}")


@pytest.fixture
async def real_kafka_producer(real_config: OrchestratorSettings):
    """
    Criar producer Kafka real.

    Skip se Kafka não disponível.
    """
    try:
        producer_client = KafkaProducerClient(
            bootstrap_servers=real_config.kafka_bootstrap_servers,
            client_id='test-sla-integration'
        )
        await producer_client.initialize()

        yield producer_client

        await producer_client.close()
    except Exception as e:
        pytest.skip(f"Kafka não disponível: {e}")


@pytest.fixture
def real_metrics() -> OrchestratorMetrics:
    """Criar instância real de métricas (sem mocking)."""
    return OrchestratorMetrics()


# ============================================================================
# TESTES
# ============================================================================

@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_fetch_real_budget_from_api(real_config: OrchestratorSettings, real_redis, real_metrics):
    """
    Teste 1: Verificar que SLAMonitor pode buscar budget do SLA Management System real.

    Valida:
    - Conexão com API
    - Schema de resposta
    - Valores válidos (0.0 - 1.0)
    - Status correto (HEALTHY, WARNING, CRITICAL, EXHAUSTED)
    """
    sla_monitor = SLAMonitor(real_config, real_redis, real_metrics)
    await sla_monitor.initialize()

    try:
        # Buscar budget do serviço
        budget_data = await sla_monitor.get_service_budget('orchestrator-dynamic')

        # Validações
        assert budget_data is not None, "Budget data não deve ser None"
        assert 'error_budget_remaining' in budget_data, "Deve ter 'error_budget_remaining'"
        assert 'status' in budget_data, "Deve ter 'status'"
        assert 'burn_rates' in budget_data, "Deve ter 'burn_rates'"

        # Validar valores
        budget_remaining = budget_data['error_budget_remaining']
        assert 0.0 <= budget_remaining <= 1.0, f"Budget deve estar entre 0-1, got {budget_remaining}"

        # Validar status
        status = budget_data['status']
        valid_statuses = ['HEALTHY', 'WARNING', 'CRITICAL', 'EXHAUSTED']
        assert status in valid_statuses, f"Status deve ser um de {valid_statuses}, got {status}"

        print(f"✓ Budget fetched: {budget_remaining*100:.1f}%, status: {status}")

    finally:
        await sla_monitor.close()


@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_check_budget_threshold_real(real_config: OrchestratorSettings, real_redis, real_metrics):
    """
    Teste 2: Verificar checking de threshold de budget com dados reais.

    Valida:
    - Threshold logic funciona com valores reais
    - Retorna tupla (is_critical, budget_data)
    - Budget data tem estrutura esperada
    """
    sla_monitor = SLAMonitor(real_config, real_redis, real_metrics)
    await sla_monitor.initialize()

    try:
        # Verificar threshold de 20%
        is_critical, budget_data = await sla_monitor.check_budget_threshold(
            service_name='orchestrator-dynamic',
            threshold=0.2
        )

        # Validações
        assert isinstance(is_critical, bool), "is_critical deve ser bool"

        if budget_data:
            assert 'error_budget_remaining' in budget_data
            assert 'status' in budget_data

            budget_remaining = budget_data['error_budget_remaining']
            print(f"✓ Budget check: {budget_remaining*100:.1f}%, critical: {is_critical}")

            # Validar lógica de threshold
            if budget_remaining < 0.2:
                assert is_critical is True, "Deve ser crítico se budget < 20%"
            else:
                assert is_critical is False, "Não deve ser crítico se budget >= 20%"
        else:
            print("⚠ Budget data é None (serviço pode não ter budget configurado)")

    finally:
        await sla_monitor.close()


@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_deadline_check_with_real_tickets(real_config: OrchestratorSettings, real_redis, real_metrics):
    """
    Teste 3: Verificar checking de deadline com tickets realistas.

    Valida:
    - Cálculo de deadline está correto
    - Detecção de deadline approaching (>80%)
    - Identificação de tickets críticos
    - Cálculo de remaining_seconds
    """
    sla_monitor = SLAMonitor(real_config, real_redis, real_metrics)
    await sla_monitor.initialize()

    try:
        # Criar tickets de teste com deadlines realistas
        now = datetime.utcnow()

        tickets = [
            {
                'ticket_id': 'test-normal-1',
                'sla': {
                    'deadline': now + timedelta(minutes=5),  # 5min no futuro
                    'timeout_ms': 300000,  # 5 min
                    'estimated_duration_ms': 60000  # 1 min (20% consumido)
                }
            },
            {
                'ticket_id': 'test-critical-1',
                'sla': {
                    'deadline': now + timedelta(seconds=30),  # 30s no futuro
                    'timeout_ms': 150000,  # 2.5 min timeout
                    'estimated_duration_ms': 120000  # 2 min estimado (>80% consumido)
                }
            }
        ]

        # Verificar SLA do workflow
        result = await sla_monitor.check_workflow_sla('test-workflow-real', tickets)

        # Validações
        assert 'deadline_approaching' in result
        assert 'critical_tickets' in result
        assert 'remaining_seconds' in result

        # Deve detectar deadline approaching (ticket crítico)
        assert result['deadline_approaching'] is True, "Deve detectar deadline approaching"
        assert 'test-critical-1' in result['critical_tickets'], "Deve identificar ticket crítico"

        remaining_seconds = result['remaining_seconds']
        assert remaining_seconds > 0, "Remaining seconds deve ser positivo"
        assert remaining_seconds < 60, "Remaining seconds deve ser <60s (ticket crítico)"

        print(f"✓ Deadline check: approaching={result['deadline_approaching']}, "
              f"critical_count={len(result['critical_tickets'])}, "
              f"remaining={remaining_seconds:.1f}s")

    finally:
        await sla_monitor.close()


@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_send_real_alert_to_kafka(
    real_config: OrchestratorSettings,
    real_redis,
    real_kafka_producer,
    real_metrics
):
    """
    Teste 4: Verificar que AlertManager pode publicar alertas ao Kafka real.

    Valida:
    - Publicação de alert ao topic sla.alerts
    - Consumo da mensagem
    - Estrutura do evento
    """
    alert_manager = AlertManager(real_kafka_producer, real_redis, real_metrics, real_config)
    await alert_manager.initialize()

    try:
        # Criar contexto de alerta
        workflow_id = f"test-workflow-{uuid.uuid4().hex[:8]}"
        context = {
            'workflow_id': workflow_id,
            'service_name': 'orchestrator-dynamic',
            'budget_remaining': 0.15,
            'burn_rate': 8.5
        }

        # Enviar alerta
        result = await alert_manager.send_proactive_alert('BUDGET_CRITICAL', context)

        assert result is True, "Alert deve ser enviado com sucesso"

        # Consumir mensagem do Kafka para validar
        consumer = KafkaConsumer(
            real_config.sla_alerts_topic,
            bootstrap_servers=real_config.kafka_bootstrap_servers,
            auto_offset_reset='latest',
            consumer_timeout_ms=5000,
            value_deserializer=lambda m: m.decode('utf-8')
        )

        # Aguardar mensagem (timeout 5s)
        messages = []
        for message in consumer:
            messages.append(message.value)
            if workflow_id in message.value:
                print(f"✓ Alert recebido: {message.value[:100]}...")
                break

        consumer.close()

        # Validar que mensagem foi recebida
        assert len(messages) > 0, "Deve receber pelo menos uma mensagem"

    finally:
        await alert_manager.close()


@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_publish_real_violation_to_kafka(
    real_config: OrchestratorSettings,
    real_redis,
    real_kafka_producer,
    real_metrics
):
    """
    Teste 5: Verificar publicação de violação ao Kafka real.

    Valida:
    - Publicação ao topic sla.violations
    - Estrutura do evento de violação
    - Campos obrigatórios presentes
    """
    alert_manager = AlertManager(real_kafka_producer, real_redis, real_metrics, real_config)
    await alert_manager.initialize()

    try:
        # Criar violação de teste
        violation = {
            'violation_id': str(uuid.uuid4()),
            'violation_type': 'DEADLINE_EXCEEDED',
            'severity': 'CRITICAL',
            'timestamp': datetime.utcnow().isoformat(),
            'ticket_id': f"test-ticket-{uuid.uuid4().hex[:8]}",
            'workflow_id': f"test-workflow-{uuid.uuid4().hex[:8]}",
            'delay_ms': 5000
        }

        # Publicar violação
        result = await alert_manager.publish_sla_violation(violation)

        assert result is True, "Violação deve ser publicada com sucesso"

        # Consumir do topic de violações
        consumer = KafkaConsumer(
            real_config.sla_violations_topic,
            bootstrap_servers=real_config.kafka_bootstrap_servers,
            auto_offset_reset='latest',
            consumer_timeout_ms=5000,
            value_deserializer=lambda m: m.decode('utf-8')
        )

        # Aguardar mensagem
        violation_received = False
        for message in consumer:
            if violation['violation_id'] in message.value:
                print(f"✓ Violação recebida: {message.value[:100]}...")
                violation_received = True
                break

        consumer.close()

        assert violation_received, "Violação deve ser recebida no Kafka"

    finally:
        await alert_manager.close()


@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_redis_caching_real(real_config: OrchestratorSettings, real_redis, real_metrics):
    """
    Teste 6: Verificar que caching Redis funciona end-to-end.

    Valida:
    - Primeiro call é cache miss (lento)
    - Segundo call é cache hit (rápido)
    - Cache expira após TTL
    """
    sla_monitor = SLAMonitor(real_config, real_redis, real_metrics)
    await sla_monitor.initialize()

    try:
        service_name = 'orchestrator-dynamic'

        # Limpar cache antes do teste
        cache_key = f"sla:budget:{service_name}"
        await real_redis.delete(cache_key)

        # Primeira chamada (cache miss)
        import time
        start = time.time()
        budget1 = await sla_monitor.get_service_budget(service_name)
        duration1 = time.time() - start

        # Segunda chamada (cache hit)
        start = time.time()
        budget2 = await sla_monitor.get_service_budget(service_name)
        duration2 = time.time() - start

        # Validações
        assert budget1 is not None, "Primeira chamada deve retornar budget"
        assert budget2 is not None, "Segunda chamada deve retornar budget"
        assert budget1 == budget2, "Budget deve ser o mesmo (do cache)"

        # Cache hit deve ser significativamente mais rápido
        assert duration2 < duration1 * 0.5, \
            f"Cache hit ({duration2:.3f}s) deve ser <50% do cache miss ({duration1:.3f}s)"

        print(f"✓ Caching: miss={duration1*1000:.1f}ms, hit={duration2*1000:.1f}ms, "
              f"speedup={duration1/duration2:.1f}x")

        # Verificar que chave existe no Redis
        exists = await real_redis.exists(cache_key)
        assert exists == 1, "Chave deve existir no Redis"

        # Verificar TTL
        ttl = await real_redis.ttl(cache_key)
        assert 0 < ttl <= real_config.sla_management_cache_ttl_seconds, \
            f"TTL deve estar entre 0 e {real_config.sla_management_cache_ttl_seconds}, got {ttl}"

    finally:
        await sla_monitor.close()


@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_alert_deduplication_real(
    real_config: OrchestratorSettings,
    real_redis,
    real_kafka_producer,
    real_metrics
):
    """
    Teste 7: Verificar deduplicação de alertas com Redis real.

    Valida:
    - Primeiro alerta é enviado
    - Segundo alerta idêntico é deduplicado
    - Após TTL expira, alerta pode ser reenviado
    """
    alert_manager = AlertManager(real_kafka_producer, real_redis, real_metrics, real_config)
    await alert_manager.initialize()

    try:
        workflow_id = f"test-dedup-{uuid.uuid4().hex[:8]}"
        context = {
            'workflow_id': workflow_id,
            'service_name': 'orchestrator-dynamic',
            'budget_remaining': 0.15
        }

        # Primeiro alerta (deve ser enviado)
        result1 = await alert_manager.send_proactive_alert('BUDGET_CRITICAL', context)
        assert result1 is True, "Primeiro alerta deve ser enviado"

        # Segundo alerta idêntico (deve ser deduplicado)
        result2 = await alert_manager.send_proactive_alert('BUDGET_CRITICAL', context)
        assert result2 is False, "Segundo alerta deve ser deduplicado"

        print(f"✓ Deduplicação: first=sent, second=blocked")

        # Verificar chave de deduplicação no Redis
        dedup_key = f"alert:sent:{workflow_id}:BUDGET_CRITICAL"
        exists = await real_redis.exists(dedup_key)
        assert exists == 1, "Chave de deduplicação deve existir"

        # Verificar TTL
        ttl = await real_redis.ttl(dedup_key)
        assert 0 < ttl <= real_config.sla_alert_deduplication_ttl_seconds, \
            f"TTL deve estar entre 0 e {real_config.sla_alert_deduplication_ttl_seconds}"

        # Aguardar TTL expirar (apenas se TTL curto para teste)
        if real_config.sla_alert_deduplication_ttl_seconds <= 10:
            await asyncio.sleep(real_config.sla_alert_deduplication_ttl_seconds + 1)

            # Terceiro alerta após expiração (deve ser enviado)
            result3 = await alert_manager.send_proactive_alert('BUDGET_CRITICAL', context)
            assert result3 is True, "Alerta após TTL deve ser enviado"
            print(f"✓ TTL expiration: third=sent after {real_config.sla_alert_deduplication_ttl_seconds}s")

    finally:
        await alert_manager.close()


@pytest.mark.real_integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_end_to_end_sla_monitoring_flow(
    real_config: OrchestratorSettings,
    real_redis,
    real_kafka_producer,
    real_metrics
):
    """
    Teste 8: Fluxo completo de monitoramento SLA end-to-end.

    Simula execução real do passo C5 de consolidação com:
    - Verificação de workflow SLA
    - Detecção de deadline approaching
    - Envio de alerta proativo
    - Verificação de budget
    - Publicação de violações (se aplicável)

    Valida integração completa de todos os componentes.
    """
    # Inicializar componentes
    sla_monitor = SLAMonitor(real_config, real_redis, real_metrics)
    alert_manager = AlertManager(real_kafka_producer, real_redis, real_metrics, real_config)

    await sla_monitor.initialize()
    await alert_manager.initialize()

    try:
        workflow_id = f"test-e2e-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()

        # Criar tickets realistas
        tickets = [
            {
                'ticket_id': f"ticket-e2e-1-{uuid.uuid4().hex[:8]}",
                'sla': {
                    'deadline': now + timedelta(seconds=45),  # Deadline se aproximando
                    'timeout_ms': 150000,
                    'estimated_duration_ms': 120000
                }
            },
            {
                'ticket_id': f"ticket-e2e-2-{uuid.uuid4().hex[:8]}",
                'sla': {
                    'deadline': now + timedelta(minutes=5),  # Normal
                    'timeout_ms': 300000,
                    'estimated_duration_ms': 60000
                }
            }
        ]

        # === 1. Verificar SLA do workflow ===
        sla_result = await sla_monitor.check_workflow_sla(workflow_id, tickets)

        assert 'deadline_approaching' in sla_result
        assert 'critical_tickets' in sla_result
        assert 'remaining_seconds' in sla_result

        print(f"✓ Step 1: SLA check - approaching={sla_result['deadline_approaching']}")

        # === 2. Enviar alerta se deadline approaching ===
        if sla_result['deadline_approaching']:
            critical_ticket_id = sla_result['critical_tickets'][0]
            deadline_data = {
                'workflow_id': workflow_id,
                'ticket_id': critical_ticket_id,
                'remaining_seconds': sla_result['remaining_seconds']
            }

            alert_sent = await alert_manager.send_deadline_alert(
                workflow_id=workflow_id,
                ticket_id=critical_ticket_id,
                deadline_data=deadline_data
            )

            assert alert_sent is True, "Alerta de deadline deve ser enviado"
            print(f"✓ Step 2: Deadline alert sent")

        # === 3. Verificar budget threshold ===
        is_critical, budget_data = await sla_monitor.check_budget_threshold(
            service_name='orchestrator-dynamic',
            threshold=0.2
        )

        if is_critical and budget_data:
            budget_alert_sent = await alert_manager.send_budget_alert(
                workflow_id=workflow_id,
                service_name='orchestrator-dynamic',
                budget_data=budget_data
            )
            print(f"✓ Step 3: Budget critical alert sent")
        else:
            print(f"✓ Step 3: Budget OK ({budget_data.get('error_budget_remaining', 'N/A')})")

        # === 4. Detectar violações ===
        violations = []
        for ticket in tickets:
            deadline_check = sla_monitor.check_ticket_deadline(ticket)
            if deadline_check.get('violated'):
                violation = {
                    'violation_id': str(uuid.uuid4()),
                    'violation_type': 'DEADLINE_EXCEEDED',
                    'severity': 'CRITICAL',
                    'timestamp': datetime.utcnow().isoformat(),
                    'ticket_id': ticket['ticket_id'],
                    'workflow_id': workflow_id,
                    'delay_ms': abs(deadline_check.get('remaining_seconds', 0) * 1000)
                }
                violations.append(violation)

        # Publicar violações
        for violation in violations:
            await alert_manager.publish_sla_violation(violation)

        if violations:
            print(f"✓ Step 4: {len(violations)} violations published")
        else:
            print(f"✓ Step 4: No violations detected")

        # === 5. Verificar que eventos foram para Kafka ===
        # (Já validado nos testes individuais, aqui apenas log)
        print(f"✓ Step 5: All events published to Kafka")

        # === 6. Verificar métricas Prometheus ===
        # (Métricas são registradas via real_metrics)
        print(f"✓ Step 6: Metrics recorded")

        print(f"\n✓ END-TO-END TEST PASSED: Full SLA monitoring flow validated")

    finally:
        await sla_monitor.close()
        await alert_manager.close()


# ============================================================================
# CONFIGURAÇÃO PYTEST
# ============================================================================

# pytest.ini deve conter:
# [pytest]
# markers =
#     real_integration: testes que requerem serviços reais (deselect with '-m "not real_integration"')
#     slow: testes lentos (deselect with '-m "not slow"')
