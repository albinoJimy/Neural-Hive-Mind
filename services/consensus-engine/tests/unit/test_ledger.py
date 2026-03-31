"""
Testes unitários para MongoDBClient (ledger de decisões consolidadas).

Cobertura de:
- Persistência de decisões no ledger
- Consultas ao ledger (por decision_id, plan_id)
- Validações de integridade
- Erro handling (duplicatas, conexões)
- Configuração e inicialização
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

# Adicionar src ao path
src_path = Path(__file__).parent.parent.parent / 'src'
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Importar módulos diretamente para evitar __init__.py issues
import importlib.util

# Import ConsolidatedDecision models
spec = importlib.util.spec_from_file_location(
    "consolidated_decision",
    src_path / 'models' / 'consolidated_decision.py'
)
consolidated_decision_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consolidated_decision_module)

DecisionType = consolidated_decision_module.DecisionType
ConsensusMethod = consolidated_decision_module.ConsensusMethod
SpecialistVote = consolidated_decision_module.SpecialistVote
ConsensusMetrics = consolidated_decision_module.ConsensusMetrics
ConsolidatedDecision = consolidated_decision_module.ConsolidatedDecision

# Import MongoDBClient directly
spec = importlib.util.spec_from_file_location(
    "mongodb_client",
    src_path / 'clients' / 'mongodb_client.py'
)
mongodb_client_module = importlib.util.module_from_spec(spec)

# Mock structlog antes de importar mongodb_client
sys.modules['structlog'] = MagicMock()
sys.modules['structlog'].get_logger = MagicMock(return_value=MagicMock())

spec.loader.exec_module(mongodb_client_module)

MongoDBClient = mongodb_client_module.MongoDBClient


# ===========================
# Fixtures
# ===========================

@pytest.fixture
def mock_mongodb_config():
    """Configuração mock para MongoDBClient."""
    config = MagicMock()
    config.mongodb_uri = 'mongodb://localhost:27017'
    config.mongodb_database = 'consensus_test'
    config.mongodb_consensus_collection = 'consensus_decisions'
    return config


@pytest.fixture
def sample_consolidated_decision():
    """Decisão consolidada válida para testes."""
    votes = [
        SpecialistVote(
            specialist_type='business',
            opinion_id='op-1',
            confidence_score=0.85,
            risk_score=0.2,
            recommendation='approve',
            weight=0.85,
            processing_time_ms=100,
            seniority_level='senior',
            seniority_multiplier=1.5
        ),
        SpecialistVote(
            specialist_type='architecture',
            opinion_id='op-2',
            confidence_score=0.90,
            risk_score=0.1,
            recommendation='approve',
            weight=0.95,
            processing_time_ms=120,
            seniority_level='expert',
            seniority_multiplier=2.0
        )
    ]

    metrics = ConsensusMetrics(
        divergence_score=0.10,
        convergence_time_ms=300,
        unanimous=True,
        fallback_used=False,
        pheromone_strength=0.9,
        bayesian_confidence=0.88,
        voting_confidence=0.90,
        weighted_by_seniority=True,
        seniority_distribution={'senior': 1, 'expert': 1},
        consensus_method_hierarchical=True
    )

    decision = ConsolidatedDecision(
        decision_id='decision-123',
        plan_id='plan-123',
        intent_id='intent-123',
        correlation_id='corr-123',
        final_decision=DecisionType.APPROVE,
        consensus_method=ConsensusMethod.BAYESIAN,
        aggregated_confidence=0.88,
        aggregated_risk=0.15,
        specialist_votes=votes,
        consensus_metrics=metrics,
        explainability_token='token-abc',
        reasoning_summary='All specialists approved'
    )
    # Calcular hash
    decision.hash = decision.calculate_hash()

    return decision


@pytest.fixture
def mongodb_client(mock_mongodb_config):
    """Cliente MongoDB para testes."""
    return MongoDBClient(mock_mongodb_config)


# ===========================
# Testes de Inicialização
# ===========================

class TestMongoDBClientInitialization:
    """Testes de inicialização do MongoDBClient."""

    def test_client_initialization_with_config(self, mock_mongodb_config):
        """Cliente deve ser inicializado com configuração."""
        client = MongoDBClient(mock_mongodb_config)

        assert client.config == mock_mongodb_config
        assert client.client is None
        assert client.db is None
        assert client.consensus_collection is None
        assert client.explainability_collection is None

    def test_client_has_required_attributes(self, mongodb_client):
        """Cliente deve ter todos os atributos necessários."""
        assert hasattr(mongodb_client, 'config')
        assert hasattr(mongodb_client, 'client')
        assert hasattr(mongodb_client, 'db')
        assert hasattr(mongodb_client, 'consensus_collection')
        assert hasattr(mongodb_client, 'explainability_collection')
        assert hasattr(mongodb_client, 'initialize')
        assert hasattr(mongodb_client, 'save_consensus_decision')
        assert hasattr(mongodb_client, 'get_decision')
        assert hasattr(mongodb_client, 'get_decision_by_plan')
        assert hasattr(mongodb_client, 'verify_integrity')
        assert hasattr(mongodb_client, 'close')


# ===========================
# Testes de Conexão
# ===========================

class TestMongoDBClientConnection:
    """Testes de conexão com MongoDB."""

    @pytest.mark.asyncio
    async def test_initialize_creates_motor_client(self, mongodb_client):
        """initialize() deve criar cliente Motor."""
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_motor:
            mock_motor.return_value = MagicMock()
            mock_motor.return_value.__getitem__ = MagicMock()
            mock_motor.return_value.admin.command = AsyncMock()

            await mongodb_client.initialize()

            mock_motor.assert_called_once_with(
                'mongodb://localhost:27017',
                maxPoolSize=50,
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
                retryWrites=True,
                w='majority'
            )

    @pytest.mark.asyncio
    async def test_initialize_sets_database_and_collections(self, mongodb_client):
        """initialize() deve configurar database e coleções."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.admin.command = AsyncMock()

        with patch('motor.motor_asyncio.AsyncIOMotorClient', return_value=mock_client):
            await mongodb_client.initialize()

            assert mongodb_client.db == mock_db
            assert mongodb_client.consensus_collection == mock_collection
            assert mongodb_client.explainability_collection == mock_collection

    @pytest.mark.asyncio
    async def test_initialize_calls_create_indexes(self, mongodb_client):
        """initialize() deve criar índices."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.admin.command = AsyncMock()
        mock_collection.create_index = AsyncMock()

        with patch('motor.motor_asyncio.AsyncIOMotorClient', return_value=mock_client):
            await mongodb_client.initialize()

            # Verificar que create_index foi chamado para os índices de consensus
            assert mock_collection.create_index.call_count >= 6

    @pytest.mark.asyncio
    async def test_initialize_verifies_connectivity_with_ping(self, mongodb_client):
        """initialize() deve verificar conectividade com ping."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_ping = AsyncMock()
        mock_client.admin.command = mock_ping

        with patch('motor.motor_asyncio.AsyncIOMotorClient', return_value=mock_client):
            await mongodb_client.initialize()

            mock_ping.assert_called_once_with('ping')


# ===========================
# Testes de Criação de Índices
# ===========================

class TestMongoDBClientIndexes:
    """Testes de criação de índices."""

    @pytest.mark.asyncio
    async def test_create_consensus_indexes(self, mongodb_client):
        """Deve criar todos os índices para consensus_collection."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.create_index = AsyncMock()

        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.admin.command = AsyncMock()

        with patch('motor.motor_asyncio.AsyncIOMotorClient', return_value=mock_client):
            await mongodb_client.initialize()

            # Verificar índices criados
            index_calls = [
                call[0][0] if call[0] else call[0][1]
                for call in mock_collection.create_index.call_args_list
            ]

            # Índices esperados
            expected_indexes = ['decision_id', 'plan_id', 'intent_id', 'created_at', 'hash']

            for expected in expected_indexes:
                assert any(expected in str(call) for call in index_calls), \
                    f'Índice {expected} não encontrado'

    @pytest.mark.asyncio
    async def test_create_explainability_indexes(self, mongodb_client):
        """Deve criar índices para explainability_collection."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.create_index = AsyncMock()

        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.admin.command = AsyncMock()

        # Chamar _create_indexes diretamente após inicialização
        with patch('motor.motor_asyncio.AsyncIOMotorClient', return_value=mock_client):
            await mongodb_client.initialize()

            # Verificar que índices foram criados (total de calls para ambas coleções)
            # 6 para consensus + 2 para explainability = 8 mínimo
            assert mock_collection.create_index.call_count >= 8

    @pytest.mark.asyncio
    async def test_create_indexes_handles_existing_indexes_gracefully(self, mongodb_client):
        """Deve lidar com índices já existentes sem erro."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Simular erro de índice já existente
        mock_collection.create_index = AsyncMock(side_effect=Exception('Index already exists'))

        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.admin.command = AsyncMock()

        with patch('motor.motor_asyncio.AsyncIOMotorClient', return_value=mock_client):
            # Não deve levantar exceção
            await mongodb_client.initialize()


# ===========================
# Testes de Persistência
# ===========================

class TestMongoDBClientPersistence:
    """Testes de persistência de decisões no ledger."""

    @pytest.mark.asyncio
    async def test_save_consensus_decision_inserts_document(self, mongodb_client, sample_consolidated_decision):
        """Deve inserir decisão no ledger."""
        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        await mongodb_client.save_consensus_decision(sample_consolidated_decision)

        # Verificar que insert_one foi chamado
        mock_collection.insert_one.assert_called_once()

        # Verificar documento inserido
        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args['decision_id'] == 'decision-123'
        assert call_args['plan_id'] == 'plan-123'
        assert call_args['_id'] == 'decision-123'
        assert call_args['immutable'] is True
        assert call_args['hash'] == sample_consolidated_decision.hash

    @pytest.mark.asyncio
    async def test_save_converts_enums_to_json_mode(self, mongodb_client):
        """Deve converter enums para valores JSON ao salvar."""
        decision = ConsolidatedDecision(
            decision_id='decision-456',
            plan_id='plan-456',
            intent_id='intent-456',
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.85,
            aggregated_risk=0.2,
            specialist_votes=[],
            consensus_metrics=ConsensusMetrics(
                divergence_score=0.1,
                convergence_time_ms=300,
                unanimous=True,
                fallback_used=False,
                pheromone_strength=0.8,
                bayesian_confidence=0.85,
                voting_confidence=0.88
            ),
            explainability_token='token-xyz',
            reasoning_summary='Test'
        )

        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        await mongodb_client.save_consensus_decision(decision)

        # Verificar que enums foram convertidos para strings
        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args['final_decision'] == 'approve'
        assert call_args['consensus_method'] == 'bayesian'

    @pytest.mark.asyncio
    async def test_save_with_duplicate_key_raises_error(self, mongodb_client, sample_consolidated_decision):
        """Deve levantar DuplicateKeyError para decisões duplicadas."""
        mock_collection = AsyncMock()
        mock_collection.insert_one = AsyncMock(side_effect=DuplicateKeyError('E11000 duplicate key'))
        mongodb_client.consensus_collection = mock_collection

        with pytest.raises(DuplicateKeyError):
            await mongodb_client.save_consensus_decision(sample_consolidated_decision)

    @pytest.mark.asyncio
    async def test_save_includes_all_required_fields(self, mongodb_client, sample_consolidated_decision):
        """Deve incluir todos os campos obrigatórios."""
        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        await mongodb_client.save_consensus_decision(sample_consolidated_decision)

        call_args = mock_collection.insert_one.call_args[0][0]

        # Campos obrigatórios
        required_fields = [
            'decision_id', 'plan_id', 'intent_id', 'final_decision',
            'consensus_method', 'aggregated_confidence', 'aggregated_risk',
            'specialist_votes', 'consensus_metrics', 'explainability_token',
            'reasoning_summary', 'created_at', 'hash', 'schema_version'
        ]

        for field in required_fields:
            assert field in call_args, f'Campo obrigatório {field} não encontrado'

    @pytest.mark.asyncio
    async def test_save_preserves_hierarchical_fields(self, mongodb_client):
        """Deve preservar campos hierárquicos ao salvar."""
        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        decision = ConsolidatedDecision(
            decision_id='decision-hier',
            plan_id='plan-hier',
            intent_id='intent-hier',
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.88,
            aggregated_risk=0.15,
            specialist_votes=[
                SpecialistVote(
                    specialist_type='business',
                    opinion_id='op-1',
                    confidence_score=0.85,
                    risk_score=0.2,
                    recommendation='approve',
                    weight=0.85,
                    processing_time_ms=100,
                    seniority_level='senior',
                    seniority_multiplier=1.5
                )
            ],
            consensus_metrics=ConsensusMetrics(
                divergence_score=0.10,
                convergence_time_ms=300,
                unanimous=True,
                fallback_used=False,
                pheromone_strength=0.9,
                bayesian_confidence=0.88,
                voting_confidence=0.90,
                weighted_by_seniority=True,
                seniority_distribution={'senior': 1},
                consensus_method_hierarchical=True
            ),
            explainability_token='token-abc',
            reasoning_summary='Test'
        )

        await mongodb_client.save_consensus_decision(decision)

        call_args = mock_collection.insert_one.call_args[0][0]

        # Verificar campos hierárquicos nos votos
        vote = call_args['specialist_votes'][0]
        assert vote['seniority_level'] == 'senior'
        assert vote['seniority_multiplier'] == 1.5

        # Verificar campos hierárquicos nas métricas
        metrics = call_args['consensus_metrics']
        assert metrics['weighted_by_seniority'] is True
        assert metrics['seniority_distribution'] == {'senior': 1}
        assert metrics['consensus_method_hierarchical'] is True


# ===========================
# Testes de Consultas
# ===========================

class TestMongoDBClientQueries:
    """Testes de consulta ao ledger."""

    @pytest.mark.asyncio
    async def test_get_decision_by_id(self, mongodb_client):
        """Deve buscar decisão por decision_id."""
        mock_collection = AsyncMock()
        mock_decision = {
            'decision_id': 'decision-123',
            'plan_id': 'plan-123',
            'final_decision': 'approve'
        }
        mock_collection.find_one = AsyncMock(return_value=mock_decision)
        mongodb_client.consensus_collection = mock_collection

        result = await mongodb_client.get_decision('decision-123')

        assert result == mock_decision
        mock_collection.find_one.assert_called_once_with({'decision_id': 'decision-123'})

    @pytest.mark.asyncio
    async def test_get_decision_returns_none_for_not_found(self, mongodb_client):
        """Deve retornar None quando decisão não existe."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mongodb_client.consensus_collection = mock_collection

        result = await mongodb_client.get_decision('nonexistent')

        assert result is None

    @pytest.mark.asyncio
    async def test_get_decision_by_plan_id(self, mongodb_client):
        """Deve buscar decisão por plan_id."""
        mock_collection = AsyncMock()
        mock_decision = {
            'decision_id': 'decision-456',
            'plan_id': 'plan-456',
            'final_decision': 'reject'
        }
        mock_collection.find_one = AsyncMock(return_value=mock_decision)
        mongodb_client.consensus_collection = mock_collection

        result = await mongodb_client.get_decision_by_plan('plan-456')

        assert result == mock_decision
        mock_collection.find_one.assert_called_once_with({'plan_id': 'plan-456'})

    @pytest.mark.asyncio
    async def test_get_decision_by_plan_returns_none_for_not_found(self, mongodb_client):
        """Deve retornar None quando plan_id não existe."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mongodb_client.consensus_collection = mock_collection

        result = await mongodb_client.get_decision_by_plan('nonexistent-plan')

        assert result is None

    @pytest.mark.asyncio
    async def test_get_decision_query_with_correct_filter(self, mongodb_client):
        """Deve usar filtro correto para buscar decisão."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value={'decision_id': 'test-123'})
        mongodb_client.consensus_collection = mock_collection

        await mongodb_client.get_decision('test-123')

        # Verificar filtro
        call_args = mock_collection.find_one.call_args[0][0]
        assert call_args == {'decision_id': 'test-123'}

    @pytest.mark.asyncio
    async def test_get_decision_by_plan_query_with_correct_filter(self, mongodb_client):
        """Deve usar filtro correto para buscar por plan_id."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value={'plan_id': 'plan-789'})
        mongodb_client.consensus_collection = mock_collection

        await mongodb_client.get_decision_by_plan('plan-789')

        # Verificar filtro
        call_args = mock_collection.find_one.call_args[0][0]
        assert call_args == {'plan_id': 'plan-789'}


# ===========================
# Testes de Validação de Integridade
# ===========================

class TestMongoDBClientIntegrity:
    """Testes de validação de integridade do ledger."""

    @pytest.mark.asyncio
    async def test_verify_integrity_with_valid_decision(self, mongodb_client, sample_consolidated_decision):
        """Deve retornar True para decisão com hash válido."""
        mock_collection = AsyncMock()
        mock_decision = sample_consolidated_decision.model_dump(mode='json')
        mock_collection.find_one = AsyncMock(return_value=mock_decision)
        mongodb_client.consensus_collection = mock_collection

        result = await mongodb_client.verify_integrity('decision-123')

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_integrity_with_invalid_decision(self, mongodb_client, sample_consolidated_decision):
        """Deve retornar False para decisão com hash inválido."""
        mock_collection = AsyncMock()
        mock_decision = sample_consolidated_decision.model_dump(mode='json')
        # Corromper hash
        mock_decision['hash'] = 'invalid_hash'
        mock_collection.find_one = AsyncMock(return_value=mock_decision)
        mongodb_client.consensus_collection = mock_collection

        result = await mongodb_client.verify_integrity('decision-123')

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_integrity_returns_false_for_nonexistent_decision(self, mongodb_client):
        """Deve retornar False para decisão inexistente."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mongodb_client.consensus_collection = mock_collection

        result = await mongodb_client.verify_integrity('nonexistent')

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_integrity_recovers_from_malformed_data(self, mongodb_client):
        """Deve retornar False para dados malformados."""
        mock_collection = AsyncMock()
        # Dados sem campos necessários para calcular hash
        mock_decision = {
            'decision_id': 'decision-123',
            'plan_id': 'plan-123',
            # Faltam campos obrigatórios
        }
        mock_collection.find_one = AsyncMock(return_value=mock_decision)
        mongodb_client.consensus_collection = mock_collection

        # Deve retornar False ou levantar exceção tratável
        try:
            result = await mongodb_client.verify_integrity('decision-123')
            assert result is False
        except (KeyError, ValueError):
            # Comportamento aceitável para dados malformados
            pass


# ===========================
# Testes de Fechamento
# ===========================

class TestMongoDBClientClose:
    """Testes de fechamento do cliente."""

    @pytest.mark.asyncio
    async def test_close_closes_client_connection(self, mongodb_client):
        """Deve fechar a conexão do cliente."""
        mock_client = MagicMock()
        mock_client.close = MagicMock()
        mongodb_client.client = mock_client

        await mongodb_client.close()

        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_none_client_does_not_raise(self, mongodb_client):
        """Não deve levantar erro quando client é None."""
        mongodb_client.client = None

        # Não deve levantar exceção
        await mongodb_client.close()


# ===========================
# Testes de Tratamento de Erros
# ===========================

class TestMongoDBClientErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_initialize_handles_connection_timeout(self, mock_mongodb_config):
        """Deve tratar timeout de conexão."""
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_motor:
            mock_client = MagicMock()
            mock_client.admin.command = AsyncMock(
                side_effect=ServerSelectionTimeoutError('Connection timeout')
            )
            mock_motor.return_value = mock_client

            client = MongoDBClient(mock_mongodb_config)

            with pytest.raises(ServerSelectionTimeoutError):
                await client.initialize()

    @pytest.mark.asyncio
    async def test_initialize_handles_connection_error(self, mock_mongodb_config):
        """Deve tratar erro de conexão."""
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_motor:
            mock_motor.side_effect = ConnectionError('Cannot connect to MongoDB')

            client = MongoDBClient(mock_mongodb_config)

            with pytest.raises(ConnectionError):
                await client.initialize()

    @pytest.mark.asyncio
    async def test_save_handles_database_error(self, mongodb_client, sample_consolidated_decision):
        """Deve propagar erro do banco de dados."""
        mock_collection = AsyncMock()
        mock_collection.insert_one = AsyncMock(
            side_effect=Exception('Database error')
        )
        mongodb_client.consensus_collection = mock_collection

        with pytest.raises(Exception, match='Database error'):
            await mongodb_client.save_consensus_decision(sample_consolidated_decision)

    @pytest.mark.asyncio
    async def test_get_decision_handles_query_error(self, mongodb_client):
        """Deve tratar erro na consulta."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            side_effect=Exception('Query error')
        )
        mongodb_client.consensus_collection = mock_collection

        with pytest.raises(Exception, match='Query error'):
            await mongodb_client.get_decision('decision-123')


# ===========================
# Testes de Configuração
# ===========================

class TestMongoDBClientConfiguration:
    """Testes de configuração do cliente."""

    def test_client_uses_config_uri(self, mock_mongodb_config):
        """Deve usar URI da configuração."""
        mock_mongodb_config.mongodb_uri = 'mongodb://custom:27017'

        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_motor:
            mock_motor.return_value = MagicMock()
            mock_motor.return_value.__getitem__ = MagicMock()
            mock_motor.return_value.admin.command = AsyncMock()

            client = MongoDBClient(mock_mongodb_config)
            import asyncio
            asyncio.run(client.initialize())

            # Verificar que URI customizada foi usada
            call_args = mock_motor.call_args[0][0]
            assert 'custom' in call_args

    def test_client_uses_config_database(self, mongodb_client):
        """Deve usar database da configuração."""
        assert mongodb_client.config.mongodb_database == 'consensus_test'

    def test_client_uses_config_collection(self, mongodb_client):
        """Deve usar coleção da configuração."""
        assert mongodb_client.config.mongodb_consensus_collection == 'consensus_decisions'


# ===========================
# Testes de Imutabilidade
# ===========================

class TestMongoDBClientImmutability:
    """Testes de imutabilidade do ledger."""

    @pytest.mark.asyncio
    async def test_saved_decision_has_immutable_flag(self, mongodb_client, sample_consolidated_decision):
        """Decisão salva deve ter flag immutable=True."""
        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        await mongodb_client.save_consensus_decision(sample_consolidated_decision)

        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args['immutable'] is True

    @pytest.mark.asyncio
    async def test_saved_decision_preserves_id(self, mongodb_client, sample_consolidated_decision):
        """Decisão salva deve preservar _id igual ao decision_id."""
        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        await mongodb_client.save_consensus_decision(sample_consolidated_decision)

        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args['_id'] == sample_consolidated_decision.decision_id


# ===========================
# Testes de Campos Opcionais
# ===========================

class TestMongoDBClientOptionalFields:
    """Testes de campos opcionais nas decisões."""

    @pytest.mark.asyncio
    async def test_save_decision_with_all_optional_fields(self, mongodb_client):
        """Deve salvar decisão com todos os campos opcionais."""
        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        decision = ConsolidatedDecision(
            decision_id='decision-full',
            plan_id='plan-full',
            intent_id='intent-full',
            correlation_id='corr-full',
            trace_id='trace-full',
            span_id='span-full',
            final_decision=DecisionType.REVIEW_REQUIRED,
            consensus_method=ConsensusMethod.VOTING,
            aggregated_confidence=0.75,
            aggregated_risk=0.35,
            specialist_votes=[],
            consensus_metrics=ConsensusMetrics(
                divergence_score=0.3,
                convergence_time_ms=500,
                unanimous=False,
                fallback_used=True,
                pheromone_strength=0.5,
                bayesian_confidence=0.7,
                voting_confidence=0.75
            ),
            explainability_token='token-full',
            reasoning_summary='Full decision',
            compliance_checks={'gdpr': True, 'sox': False},
            guardrails_triggered=['rate_limit', 'data_volume'],
            requires_human_review=True,
            valid_until=datetime(2026, 12, 31, tzinfo=timezone.utc),
            metadata={'key1': 'value1', 'key2': 42}
        )

        await mongodb_client.save_consensus_decision(decision)

        call_args = mock_collection.insert_one.call_args[0][0]

        assert call_args['correlation_id'] == 'corr-full'
        assert call_args['trace_id'] == 'trace-full'
        assert call_args['span_id'] == 'span-full'
        assert call_args['compliance_checks'] == {'gdpr': True, 'sox': False}
        assert call_args['guardrails_triggered'] == ['rate_limit', 'data_volume']
        assert call_args['requires_human_review'] is True
        assert 'valid_until' in call_args
        assert call_args['metadata'] == {'key1': 'value1', 'key2': 42}

    @pytest.mark.asyncio
    async def test_save_decision_with_minimal_fields(self, mongodb_client):
        """Deve salvar decisão apenas com campos obrigatórios."""
        mock_collection = AsyncMock()
        mongodb_client.consensus_collection = mock_collection

        decision = ConsolidatedDecision(
            decision_id='decision-minimal',
            plan_id='plan-minimal',
            intent_id='intent-minimal',
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.UNANIMOUS,
            aggregated_confidence=0.95,
            aggregated_risk=0.05,
            specialist_votes=[],
            consensus_metrics=ConsensusMetrics(
                divergence_score=0.0,
                convergence_time_ms=100,
                unanimous=True,
                fallback_used=False,
                pheromone_strength=1.0,
                bayesian_confidence=0.95,
                voting_confidence=0.95
            ),
            explainability_token='token-minimal',
            reasoning_summary='Minimal decision'
        )

        await mongodb_client.save_consensus_decision(decision)

        call_args = mock_collection.insert_one.call_args[0][0]

        # Campos opcionais devem ter valores padrão
        assert call_args['correlation_id'] is None
        assert call_args['trace_id'] is None
        assert call_args['span_id'] is None
        assert call_args['compliance_checks'] == {}
        assert call_args['guardrails_triggered'] == []
        assert call_args['requires_human_review'] is False
        assert call_args['valid_until'] is None
        assert call_args['metadata'] == {}
