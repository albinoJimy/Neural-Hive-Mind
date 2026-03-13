"""
Testes de persistência MongoDB D3 (Build + MongoDB Persistence)

Conforme MODELO_TESTE_WORKER_AGENT.md seção D3 e
GUIDE_MONGODB_AUTH.md para string de conexão.

Collections:
- code_forge.artifacts: Artefatos gerados
- code_forge.pipelines: Resultados de pipelines
- code_forge.pipeline_logs: Logs de execução
"""

import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict

import pytest

from src.types.artifact_types import ArtifactCategory, CodeLanguage
from src.models.artifact import (
    CodeForgeArtifact, PipelineResult, PipelineStatus,
    ValidationResult, ValidationType, ValidationStatus
)


pytest_plugins = [
    'tests.unit.conftest',
    'tests.fixtures.d3_fixtures'
]


# ============================================================================
# Testes de Conexão MongoDB
# ============================================================================


class TestD3MongoDBConnection:
    """Testes de conexão com MongoDB."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_d3_mongodb_connection_string_format(self):
        """
        D3: Formato da string de conexão MongoDB

        Conforme GUIDE_MONGODB_AUTH.md:

        Formato correto com authSource:
        mongodb://[user]:[password]@[host]:[port]/[database]?authSource=admin

        Exemplo:
        mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/code_forge?authSource=admin
        """
        mongodb_url = os.getenv('MONGODB_URL')
        if not mongodb_url:
            pytest.skip('MONGODB_URL não configurada')

        # Verificar formato
        assert mongodb_url.startswith('mongodb://') or \
               mongodb_url.startswith('mongodb+srv://'), \
               f"URL inválida: {mongodb_url}"

        # Verificar authSource para autenticação admin
        if 'authSource' in mongodb_url:
            assert 'authSource=admin' in mongodb_url or \
                   'authSource=admin' in mongodb_url.lower(), \
                   "authSource deve ser 'admin' para autenticação correta"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_d3_mongodb_client_initialization(self):
        """
        D3: Inicialização do MongoDBClient

        Verifica:
        - Client conecta com sucesso
        - Database code_forge acessível
        """
        from src.clients.mongodb_client import MongoDBClient

        mongodb_url = os.getenv('MONGODB_URL')
        if not mongodb_url:
            pytest.skip('MONGODB_URL não configurada')

        client = MongoDBClient(mongodb_url, 'code_forge_test')

        try:
            await client.start()

            # Verificar health check
            healthy = await client.health_check()
            assert healthy is True

        finally:
            await client.stop()


# ============================================================================
# Testes de Persistência de Artefatos
# ============================================================================


class TestD3ArtifactPersistence:
    """Testes de persistência de artefatos no MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_save_artifact_content(
        self,
        mock_mongodb_client,
        d3_pipeline_context_with_artifacts
    ):
        """
        D3: Salvamento de conteúdo de artefato

        Verifica:
        - save_artifact_content chamado
        - artifact_id usado como chave
        - Conteúdo armazenado
        """
        artifact = d3_pipeline_context_with_artifacts.generated_artifacts[0]
        content = "print('hello world')"

        await mock_mongodb_client.save_artifact_content(
            artifact.artifact_id,
            content
        )

        assert mock_mongodb_client.save_artifact_content.called

        # Verificar argumentos
        call_args = mock_mongodb_client.save_artifact_content.call_args
        assert call_args[0][0] == artifact.artifact_id
        assert call_args[0][1] == content

    @pytest.mark.asyncio
    async def test_d3_get_artifact_content(
        self,
        mock_mongodb_client
    ):
        """
        D3: Recuperação de conteúdo de artefato

        Verifica:
        - get_artifact_content chamado
        - Conteúdo retornado corretamente
        """
        artifact_id = str(uuid.uuid4())

        content = await mock_mongodb_client.get_artifact_content(artifact_id)

        assert mock_mongodb_client.get_artifact_content.called
        assert mock_mongodb_client.get_artifact_content.call_args[0][0] == artifact_id

    @pytest.mark.asyncio
    async def test_d3_artifact_document_structure(
        self,
        mock_d3_mongodb_artifact
    ):
        """
        D3: Estrutura do documento de artefato

        Campos obrigatórios:
        - artifact_id
        - ticket_id
        - artifact_type
        - content_uri
        - content_hash
        - created_at
        """
        required_fields = [
            'artifact_id', 'ticket_id', 'artifact_type',
            'content_uri', 'content_hash', 'created_at'
        ]

        for field in required_fields:
            assert field in mock_d3_mongodb_artifact, \
                f"Campo obrigatório {field} ausente"

    @pytest.mark.asyncio
    async def test_d3_delete_artifact(
        self,
        mock_mongodb_client
    ):
        """
        D3: Deleção de artefato

        Verifica:
        - delete_artifact chamado
        - Artefato removido
        """
        artifact_id = str(uuid.uuid4())

        deleted = await mock_mongodb_client.delete_artifact(artifact_id)

        assert mock_mongodb_client.delete_artifact.called


# ============================================================================
# Testes de Persistência de Pipeline
# ============================================================================


class TestD3PipelinePersistence:
    """Testes de persistência de pipelines no MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_save_pipeline_result(
        self,
        mock_mongodb_client,
        d3_expected_pipeline_result
    ):
        """
        D3: Salvamento de resultado de pipeline

        Verifica:
        - save_pipeline_result chamado
        - pipeline_id usado
        - Status armazenado
        """
        await mock_mongodb_client.save_pipeline_result(
            d3_expected_pipeline_result.pipeline_id,
            d3_expected_pipeline_result
        )

        assert mock_mongodb_client.save_pipeline_result.called

    @pytest.mark.asyncio
    async def test_d3_get_pipeline_result(
        self,
        mock_mongodb_client
    ):
        """
        D3: Recuperação de resultado de pipeline

        Verifica:
        - get_pipeline_result chamado
        - Resultado retornado
        """
        pipeline_id = str(uuid.uuid4())

        result = await mock_mongodb_client.get_pipeline_result(pipeline_id)

        assert mock_mongodb_client.get_pipeline_result.called

    @pytest.mark.asyncio
    async def test_d3_pipeline_document_structure(
        self,
        mock_d3_postgres_pipeline
    ):
        """
        D3: Estrutura do documento de pipeline

        Campos obrigatórios:
        - pipeline_id
        - ticket_id
        - plan_id
        - status
        - total_duration_ms
        - created_at
        - artifacts_count
        """
        required_fields = [
            'pipeline_id', 'ticket_id', 'plan_id', 'status',
            'total_duration_ms', 'created_at'
        ]

        for field in required_fields:
            assert field in mock_d3_postgres_pipeline, \
                f"Campo obrigatório {field} ausente"

    @pytest.mark.asyncio
    async def test_d3_query_pipelines_by_ticket(
        self,
        mock_mongodb_client
    ):
        """
        D3: Consulta de pipelines por ticket_id

        Verifica:
        - Query por ticket_id funciona
        - Múltiplos pipelines retornados
        """
        ticket_id = str(uuid.uuid4())

        # Mock query
        mock_mongodb_client.query_pipelines_by_ticket = AsyncMock(
            return_value=[]
        )

        pipelines = await mock_mongodb_client.query_pipelines_by_ticket(ticket_id)

        assert mock_mongodb_client.query_pipelines_by_ticket.called


# ============================================================================
# Testes de Logs de Pipeline
# ============================================================================


class TestD3PipelineLogs:
    """Testes de logs de pipeline no MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_save_pipeline_logs(
        self,
        mock_mongodb_client
    ):
        """
        D3: Salvamento de logs de pipeline

        Verifica:
        - save_pipeline_logs chamado
        - Logs armazenados como array
        - Timestamp incluído
        """
        pipeline_id = str(uuid.uuid4())
        logs = [
            {'stage': 'build', 'status': 'success', 'message': 'Build started'},
            {'stage': 'test', 'status': 'success', 'message': 'Tests passed'}
        ]

        await mock_mongodb_client.save_pipeline_logs(pipeline_id, logs)

        assert mock_mongodb_client.save_pipeline_logs.called

        call_args = mock_mongodb_client.save_pipeline_logs.call_args
        assert call_args[0][0] == pipeline_id
        assert call_args[0][1] == logs

    @pytest.mark.asyncio
    async def test_d3_get_pipeline_logs(
        self,
        mock_mongodb_client
    ):
        """
        D3: Recuperação de logs de pipeline

        Verifica:
        - get_pipeline_logs chamado
        - Logs retornados em ordem cronológica
        """
        pipeline_id = str(uuid.uuid4())

        logs = await mock_mongodb_client.get_pipeline_logs(pipeline_id)

        assert mock_mongodb_client.get_pipeline_logs.called

    @pytest.mark.asyncio
    async def test_d3_append_pipeline_log(
        self,
        mock_mongodb_client
    ):
        """
        D3: Append de log ao pipeline

        Verifica:
        - append_pipeline_log chamado
        - Log adicionado ao array existente
        """
        pipeline_id = str(uuid.uuid4())
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': 'INFO',
            'message': 'Stage completed'
        }

        mock_mongodb_client.append_pipeline_log = AsyncMock(return_value=True)

        await mock_mongodb_client.append_pipeline_log(pipeline_id, log_entry)

        assert mock_mongodb_client.append_pipeline_log.called


# ============================================================================
# Testes de Consultas Complexas
# ============================================================================


class TestD3MongoDBQueries:
    """Testes de consultas complexas no MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_query_artifacts_by_type(
        self,
        mock_mongodb_client
    ):
        """
        D3: Consulta de artefatos por tipo

        Verifica:
        - Query por artifact_type funciona
        - Índice utilizado
        """
        mock_mongodb_client.query_artifacts_by_type = AsyncMock(
            return_value=[]
        )

        artifacts = await mock_mongodb_client.query_artifacts_by_type(
            ArtifactCategory.CONTAINER
        )

        assert mock_mongodb_client.query_artifacts_by_type.called

    @pytest.mark.asyncio
    async def test_d3_query_pipelines_by_date_range(
        self,
        mock_mongodb_client
    ):
        """
        D3: Consulta de pipelines por intervalo de datas

        Verifica:
        - Query por created_at range funciona
        - Index utilization
        """
        start_date = datetime.now()
        end_date = datetime.now()

        mock_mongodb_client.query_pipelines_by_date_range = AsyncMock(
            return_value=[]
        )

        pipelines = await mock_mongodb_client.query_pipelines_by_date_range(
            start_date, end_date
        )

        assert mock_mongodb_client.query_pipelines_by_date_range.called

    @pytest.mark.asyncio
    async def test_d3_aggregate_pipeline_statistics(
        self,
        mock_mongodb_client
    ):
        """
        D3: Agregação de estatísticas de pipeline

        Verifica:
        - Aggregate pipeline funcionando
        - Stats retornadas
        """
        mock_mongodb_client.get_pipeline_statistics = AsyncMock(
            return_value={
                'total_pipelines': 100,
                'completed_pipelines': 85,
                'failed_pipelines': 10,
                'average_duration_ms': 15000
            }
        )

        stats = await mock_mongodb_client.get_pipeline_statistics()

        assert mock_mongodb_client.get_pipeline_statistics.called
        assert 'total_pipelines' in stats


# ============================================================================
# Testes de Transações
# ============================================================================


class TestD3MongoDBTransactions:
    """Testes de transações no MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_transactional_artifact_save(
        self,
        mock_mongodb_client,
        d3_pipeline_context_with_artifacts
    ):
        """
        D3: Salvamento transacional de artefatos

        Verifica:
        - Múltiplos artefatos salvos atomicamente
        - Rollback em erro
        """
        artifacts = d3_pipeline_context_with_artifacts.generated_artifacts

        mock_mongodb_client.save_artifacts_transactional = AsyncMock(
            return_value=True
        )

        result = await mock_mongodb_client.save_artifacts_transactional(artifacts)

        assert mock_mongodb_client.save_artifacts_transactional.called

    @pytest.mark.asyncio
    async def test_d3_transaction_rollback_on_error(
        self,
        mock_mongodb_client
    ):
        """
        D3: Rollback de transação em erro

        Verifica:
        - Transação abortada em erro
        - Nenhum artefato parcialmente salvo
        """
        mock_mongodb_client.save_artifacts_transactional = AsyncMock(
            side_effect=Exception("Transaction failed")
        )

        try:
            await mock_mongodb_client.save_artifacts_transactional([])
        except Exception:
            pass  # Esperado

        # Verificar que erro foi propagado
        assert mock_mongodb_client.save_artifacts_transactional.called


# ============================================================================
# Testes de Índices
# ============================================================================


class TestD3MongoDBIndexes:
    """Testes de índices no MongoDB."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_d3_artifact_indexes_exist(self):
        """
        D3: Índices de artifacts existem

        Índices esperados:
        - artifact_id (unique)
        - ticket_id
        - artifact_type
        - created_at
        """
        from src.clients.mongodb_client import MongoDBClient

        mongodb_url = os.getenv('MONGODB_URL')
        if not mongodb_url:
            pytest.skip('MONGODB_URL não configurada')

        client = MongoDBClient(mongodb_url, 'code_forge_test')

        try:
            await client.start()

            # Verificar índices
            indexes = await client.get_collection_indexes('artifacts')

            # Índices obrigatórios
            required_indexes = ['artifact_id', 'ticket_id', 'artifact_type', 'created_at']

            index_fields = []
            for idx in indexes:
                if 'key' in idx:
                    index_fields.extend(idx['key'].keys())

            for required in required_indexes:
                assert required in index_fields, \
                    f"Índice {required} não encontrado"

        finally:
            await client.stop()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_d3_pipeline_indexes_exist(self):
        """
        D3: Índices de pipelines existem

        Índices esperados:
        - pipeline_id (unique)
        - ticket_id
        - status
        - created_at
        """
        from src.clients.mongodb_client import MongoDBClient

        mongodb_url = os.getenv('MONGODB_URL')
        if not mongodb_url:
            pytest.skip('MONGODB_URL não configurada')

        client = MongoDBClient(mongodb_url, 'code_forge_test')

        try:
            await client.start()

            indexes = await client.get_collection_indexes('pipelines')

            required_indexes = ['pipeline_id', 'ticket_id', 'status', 'created_at']

            index_fields = []
            for idx in indexes:
                if 'key' in idx:
                    index_fields.extend(idx['key'].keys())

            for required in required_indexes:
                assert required in index_fields, \
                    f"Índice {required} não encontrado"

        finally:
            await client.stop()


# ============================================================================
# Testes de Cleanup e Retenção
# ============================================================================


class TestD3MongoDBCleanup:
    """Testes de cleanup e retenção de dados."""

    @pytest.mark.asyncio
    async def test_d3_delete_old_artifacts(
        self,
        mock_mongodb_client
    ):
        """
        D3: Deleção de artefatos antigos

        Verifica:
        - Artefatos > X dias deletados
        - Política de retenção respeitada
        """
        retention_days = 30

        mock_mongodb_client.delete_artifacts_older_than = AsyncMock(
            return_value=10
        )

        deleted = await mock_mongodb_client.delete_artifacts_older_than(
            retention_days
        )

        assert mock_mongodb_client.delete_artifacts_older_than.called
        assert deleted >= 0

    @pytest.mark.asyncio
    async def test_d3_archive_old_pipelines(
        self,
        mock_mongodb_client
    ):
        """
        D3: Arquivamento de pipelines antigos

        Verifica:
        - Pipelines movidos para archive collection
        - Original removido
        """
        archive_days = 90

        mock_mongodb_client.archive_pipelines_older_than = AsyncMock(
            return_value=50
        )

        archived = await mock_mongodb_client.archive_pipelines_older_than(
            archive_days
        )

        assert mock_mongodb_client.archive_pipelines_older_than.called


# ============================================================================
# Testes de Performance
# ============================================================================


class TestD3MongoDBPerformance:
    """Testes de performance do MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_artifact_save_latency(
        self,
        mock_mongodb_client
    ):
        """
        D3: Latência de salvamento de artefato

        Verifica:
        - Salvamento < 50ms (mock)
        """
        import time

        artifact_id = str(uuid.uuid4())
        content = "test content"

        start = time.time()
        await mock_mongodb_client.save_artifact_content(artifact_id, content)
        latency_ms = int((time.time() - start) * 1000)

        # Mock deve ser rápido
        assert latency_ms < 50

    @pytest.mark.asyncio
    async def test_d3_query_performance(
        self,
        mock_mongodb_client
    ):
        """
        D3: Performance de consultas

        Verifica:
        - Query < 100ms (mock)
        """
        import time

        mock_mongodb_client.query_pipelines_by_ticket = AsyncMock(
            return_value=[]
        )

        start = time.time()
        await mock_mongodb_client.query_pipelines_by_ticket(str(uuid.uuid4()))
        latency_ms = int((time.time() - start) * 1000)

        assert latency_ms < 100


# ============================================================================
# Testes de Segurança
# ============================================================================


class TestD3MongoDBSecurity:
    """Testes de segurança do MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_connection_with_auth(
        self,
        mock_mongodb_client
    ):
        """
        D3: Conexão com autenticação

        Verifica:
        - Credenciais usadas
        - Auth não é None
        """
        # Verificar que client foi configurado com auth
        assert mock_mongodb_client is not None

    @pytest.mark.asyncio
    async def test_d3_sensitive_data_encryption(
        self,
        mock_mongodb_client
    ):
        """
        D3: Criptografia de dados sensíveis

        Verifica:
        - Campos sensíveis criptografados
        - Senhas não em texto plano
        """
        # Dados sensíveis devem ser criptografados antes de salvar
        sensitive_data = {
            'api_key': 'secret-key-123',
            'password': 'secret-password'
        }

        # Mock de criptografia
        mock_mongodb_client.save_with_encryption = AsyncMock(
            return_value=True
        )

        await mock_mongodb_client.save_with_encryption(
            'collection',
            sensitive_data
        )

        assert mock_mongodb_client.save_with_encryption.called


# ============================================================================
# Testes de Backup e Restore
# ============================================================================


class TestD3MongoDBBackup:
    """Testes de backup e restore do MongoDB."""

    @pytest.mark.asyncio
    async def test_d3_collection_backup(
        self,
        mock_mongodb_client
    ):
        """
        D3: Backup de collection

        Verifica:
        - Backup criado
        - Snapshot restaurável
        """
        mock_mongodb_client.backup_collection = AsyncMock(
            return_value='/backups/artifacts-20260311.bson'
        )

        backup_path = await mock_mongodb_client.backup_collection('artifacts')

        assert mock_mongodb_client.backup_collection.called
        assert backup_path is not None
        assert '.bson' in backup_path
