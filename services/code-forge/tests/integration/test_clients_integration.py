"""
Testes de integração para clients do Code Forge.

Estes testes requerem serviços reais rodando e são marcados com @pytest.mark.integration.
Execute com: pytest tests/integration/ -m integration

Variáveis de ambiente necessárias:
- MONGODB_URL: URL de conexão MongoDB
- POSTGRES_URL: URL de conexão PostgreSQL
- REDIS_URL: URL de conexão Redis
"""
import pytest
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.clients.mongodb_client import MongoDBClient
from src.clients.postgres_client import PostgresClient
from src.clients.redis_client import RedisClient
from src.models.artifact import PipelineResult, PipelineStatus


# ============================================================================
# Testes de Integração MongoDB
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_mongodb_roundtrip():
    """Teste real com MongoDB (requer MongoDB rodando)"""
    mongodb_url = os.getenv('MONGODB_URL')
    if not mongodb_url:
        pytest.skip('MONGODB_URL não configurada')

    client = MongoDBClient(mongodb_url, 'test_code_forge')
    await client.start()

    try:
        artifact_id = f'test-art-{datetime.utcnow().timestamp()}'

        # Salvar artefato
        await client.save_artifact_content(artifact_id, 'print("test")')

        # Recuperar artefato
        content = await client.get_artifact_content(artifact_id)
        assert content == 'print("test")'

        # Deletar artefato
        deleted = await client.delete_artifact(artifact_id)
        assert deleted is True

        # Verificar que foi deletado
        content = await client.get_artifact_content(artifact_id)
        assert content is None

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mongodb_pipeline_logs():
    """Teste de logs de pipeline com MongoDB"""
    mongodb_url = os.getenv('MONGODB_URL')
    if not mongodb_url:
        pytest.skip('MONGODB_URL não configurada')

    client = MongoDBClient(mongodb_url, 'test_code_forge')
    await client.start()

    try:
        pipeline_id = f'test-pipe-{datetime.utcnow().timestamp()}'
        logs = [
            {'stage': 'build', 'status': 'success', 'duration_ms': 1000},
            {'stage': 'test', 'status': 'success', 'duration_ms': 2000},
        ]

        # Salvar logs
        await client.save_pipeline_logs(pipeline_id, logs)

        # Recuperar logs
        retrieved = await client.get_pipeline_logs(pipeline_id)
        assert len(retrieved) >= 1
        assert retrieved[0]['logs'] == logs

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mongodb_health_check():
    """Teste de health check MongoDB"""
    mongodb_url = os.getenv('MONGODB_URL')
    if not mongodb_url:
        pytest.skip('MONGODB_URL não configurada')

    client = MongoDBClient(mongodb_url, 'test_code_forge')
    await client.start()

    try:
        healthy = await client.health_check()
        assert healthy is True
    finally:
        await client.stop()


# ============================================================================
# Testes de Integração PostgreSQL
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_roundtrip():
    """Teste real com PostgreSQL (requer Postgres rodando)"""
    postgres_url = os.getenv('POSTGRES_URL')
    if not postgres_url:
        pytest.skip('POSTGRES_URL não configurada')

    client = PostgresClient(postgres_url)
    await client.start()

    try:
        pipeline_id = f'test-pipe-{datetime.utcnow().timestamp()}'

        result = PipelineResult(
            pipeline_id=pipeline_id,
            ticket_id='test-ticket-1',
            plan_id='test-plan-1',
            intent_id='test-intent-1',
            decision_id='test-decision-1',
            status=PipelineStatus.COMPLETED,
            artifacts=[],
            pipeline_stages=[],
            total_duration_ms=1000,
            approval_required=False,
            created_at=datetime.utcnow()
        )

        # Salvar pipeline
        await client.save_pipeline(result)

        # Recuperar pipeline
        retrieved = await client.get_pipeline(pipeline_id)
        assert retrieved is not None
        assert retrieved.pipeline_id == pipeline_id
        assert retrieved.status == PipelineStatus.COMPLETED

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_list_pipelines():
    """Teste de listagem de pipelines com filtros"""
    postgres_url = os.getenv('POSTGRES_URL')
    if not postgres_url:
        pytest.skip('POSTGRES_URL não configurada')

    client = PostgresClient(postgres_url)
    await client.start()

    try:
        ticket_id = f'test-ticket-{datetime.utcnow().timestamp()}'

        # Criar alguns pipelines
        for i in range(3):
            result = PipelineResult(
                pipeline_id=f'test-pipe-list-{i}-{datetime.utcnow().timestamp()}',
                ticket_id=ticket_id,
                plan_id='test-plan-1',
                intent_id='test-intent-1',
                decision_id='test-decision-1',
                status=PipelineStatus.COMPLETED if i % 2 == 0 else PipelineStatus.FAILED,
                artifacts=[],
                pipeline_stages=[],
                total_duration_ms=1000,
                approval_required=False,
                created_at=datetime.utcnow()
            )
            await client.save_pipeline(result)

        # Listar por ticket_id
        pipelines = await client.list_pipelines({'ticket_id': ticket_id})
        assert len(pipelines) >= 3

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_update_status():
    """Teste de atualização de status de pipeline"""
    postgres_url = os.getenv('POSTGRES_URL')
    if not postgres_url:
        pytest.skip('POSTGRES_URL não configurada')

    client = PostgresClient(postgres_url)
    await client.start()

    try:
        pipeline_id = f'test-pipe-update-{datetime.utcnow().timestamp()}'

        result = PipelineResult(
            pipeline_id=pipeline_id,
            ticket_id='test-ticket-1',
            plan_id='test-plan-1',
            intent_id='test-intent-1',
            decision_id='test-decision-1',
            status=PipelineStatus.COMPLETED,
            artifacts=[],
            pipeline_stages=[],
            total_duration_ms=1000,
            approval_required=False,
            created_at=datetime.utcnow()
        )
        await client.save_pipeline(result)

        # Atualizar status
        updated = await client.update_pipeline_status(
            pipeline_id,
            PipelineStatus.FAILED,
            error_message='Test error'
        )
        assert updated is True

        # Verificar atualização
        retrieved = await client.get_pipeline(pipeline_id)
        assert retrieved.status == PipelineStatus.FAILED

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_statistics():
    """Teste de estatísticas agregadas"""
    postgres_url = os.getenv('POSTGRES_URL')
    if not postgres_url:
        pytest.skip('POSTGRES_URL não configurada')

    client = PostgresClient(postgres_url)
    await client.start()

    try:
        stats = await client.get_pipeline_statistics()
        assert 'total_pipelines' in stats
        assert 'average_duration_ms' in stats
        assert 'status_counts' in stats

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_health_check():
    """Teste de health check PostgreSQL"""
    postgres_url = os.getenv('POSTGRES_URL')
    if not postgres_url:
        pytest.skip('POSTGRES_URL não configurada')

    client = PostgresClient(postgres_url)
    await client.start()

    try:
        healthy = await client.health_check()
        assert healthy is True
    finally:
        await client.stop()


# ============================================================================
# Testes de Integração Redis
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_template():
    """Teste real de cache de templates com Redis"""
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        pytest.skip('REDIS_URL não configurada')

    client = RedisClient(redis_url)
    await client.start()

    try:
        template_id = f'test-tpl-{datetime.utcnow().timestamp()}'
        template = {'name': 'test', 'content': 'print("hello")'}

        # Cachear template
        await client.cache_template(template_id, template, ttl=60)

        # Recuperar do cache
        cached = await client.get_cached_template(template_id)
        assert cached == template

        # Invalidar
        deleted = await client.invalidate_template(template_id)
        assert deleted is True

        # Verificar que foi invalidado
        cached = await client.get_cached_template(template_id)
        assert cached is None

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_pipeline_state():
    """Teste de estado de pipeline com Redis"""
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        pytest.skip('REDIS_URL não configurada')

    client = RedisClient(redis_url)
    await client.start()

    try:
        pipeline_id = f'test-pipe-{datetime.utcnow().timestamp()}'
        state = {
            'stage': 'build',
            'progress': 50,
            'artifacts': ['art-1', 'art-2']
        }

        # Salvar estado
        await client.set_pipeline_state(pipeline_id, state)

        # Recuperar estado
        retrieved = await client.get_pipeline_state(pipeline_id)
        assert retrieved is not None
        assert retrieved['stage'] == 'build'
        assert retrieved['progress'] == '50' or retrieved['progress'] == 50

        # Atualizar estado
        await client.update_pipeline_state(pipeline_id, {'stage': 'test', 'progress': 75})
        updated = await client.get_pipeline_state(pipeline_id)
        assert updated['stage'] == 'test'

        # Deletar estado
        deleted = await client.delete_pipeline_state(pipeline_id)
        assert deleted is True

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_distributed_lock():
    """Teste de lock distribuído com Redis"""
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        pytest.skip('REDIS_URL não configurada')

    client = RedisClient(redis_url)
    await client.start()

    try:
        resource_id = f'test-resource-{datetime.utcnow().timestamp()}'

        # Adquirir lock
        acquired = await client.acquire_lock(resource_id, timeout=30, owner='test-owner')
        assert acquired is True

        # Tentar adquirir novamente (deve falhar)
        acquired_again = await client.acquire_lock(resource_id, timeout=30, owner='another-owner')
        assert acquired_again is False

        # Liberar com owner errado (deve falhar)
        released_wrong = await client.release_lock(resource_id, owner='wrong-owner')
        assert released_wrong is False

        # Liberar com owner correto
        released = await client.release_lock(resource_id, owner='test-owner')
        assert released is True

        # Agora outro pode adquirir
        acquired_new = await client.acquire_lock(resource_id, timeout=30, owner='another-owner')
        assert acquired_new is True

        # Cleanup
        await client.release_lock(resource_id)

    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_health_check():
    """Teste de health check Redis"""
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        pytest.skip('REDIS_URL não configurada')

    client = RedisClient(redis_url)
    await client.start()

    try:
        healthy = await client.health_check()
        assert healthy is True
    finally:
        await client.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_generic_values():
    """Teste de valores genéricos com Redis"""
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        pytest.skip('REDIS_URL não configurada')

    client = RedisClient(redis_url)
    await client.start()

    try:
        key = f'test-key-{datetime.utcnow().timestamp()}'

        # Salvar valor com TTL
        await client.set_value(key, 'test-value', ttl=60)

        # Recuperar valor
        value = await client.get_value(key)
        assert value == 'test-value'

    finally:
        await client.stop()
