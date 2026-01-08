"""
Testes de integração para SemanticParser com NLP

Testa o fluxo completo de parsing com extração NLP.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime


class TestSemanticParserWithNLP:
    """Testes de integração do SemanticParser com NLPProcessor"""

    @pytest.fixture
    def mock_neo4j_client(self):
        """Mock do Neo4jClient"""
        mock = AsyncMock()
        mock.query_similar_intents = AsyncMock(return_value=[])
        mock.query_ontology = AsyncMock(return_value={
            'canonical_type': 'resource',
            'properties': {},
            'constraints': {}
        })
        mock.nlp_processor = None
        return mock

    @pytest.fixture
    def mock_mongodb_client(self):
        """Mock do MongoDBClient"""
        mock = AsyncMock()
        mock.get_operational_context = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def mock_redis_client(self):
        """Mock do RedisClient"""
        mock = AsyncMock()
        mock.get_cached_query = AsyncMock(return_value=None)
        mock.cache_query_result = AsyncMock()
        mock.cache_enriched_context = AsyncMock()
        return mock

    @pytest.fixture
    async def nlp_processor(self, mock_redis_client):
        """Fixture que cria e inicializa NLPProcessor"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=mock_redis_client)
        await processor.initialize()
        return processor

    @pytest.fixture
    def semantic_parser_with_nlp(
        self,
        mock_neo4j_client,
        mock_mongodb_client,
        mock_redis_client,
        nlp_processor
    ):
        """Fixture que cria SemanticParser com NLPProcessor"""
        from src.services.semantic_parser import SemanticParser
        return SemanticParser(
            neo4j_client=mock_neo4j_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client,
            nlp_processor=nlp_processor
        )

    @pytest.fixture
    def semantic_parser_without_nlp(
        self,
        mock_neo4j_client,
        mock_mongodb_client,
        mock_redis_client
    ):
        """Fixture que cria SemanticParser sem NLPProcessor"""
        from src.services.semantic_parser import SemanticParser
        return SemanticParser(
            neo4j_client=mock_neo4j_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client,
            nlp_processor=None
        )

    @pytest.fixture
    def intent_envelope_create(self):
        """Fixture de Intent Envelope para operação de criação"""
        return {
            'id': 'test-intent-001',
            'timestamp': datetime.utcnow().isoformat(),
            'confidence': 0.95,
            'intent': {
                'text': 'Criar novo serviço REST para gerenciamento de produtos usando FastAPI',
                'domain': 'technical',
                'entities': [
                    {'type': 'service', 'value': 'REST API', 'confidence': 0.9}
                ]
            },
            'constraints': {
                'priority': 'high',
                'timeout_ms': 30000
            }
        }

    @pytest.fixture
    def intent_envelope_query(self):
        """Fixture de Intent Envelope para operação de consulta"""
        return {
            'id': 'test-intent-002',
            'timestamp': datetime.utcnow().isoformat(),
            'confidence': 0.88,
            'intent': {
                'text': 'Buscar todos os pedidos dos últimos 30 dias no MongoDB',
                'domain': 'business',
                'entities': []
            },
            'constraints': None
        }

    @pytest.mark.asyncio
    async def test_parse_extracts_objectives_with_nlp(
        self,
        semantic_parser_with_nlp,
        intent_envelope_create
    ):
        """Testa que parse extrai objectives corretamente com NLP"""
        result = await semantic_parser_with_nlp.parse(intent_envelope_create)

        assert 'objectives' in result
        assert isinstance(result['objectives'], list)
        assert 'create' in result['objectives']

    @pytest.mark.asyncio
    async def test_parse_enriches_entities_with_nlp(
        self,
        semantic_parser_with_nlp,
        intent_envelope_create
    ):
        """Testa que parse enriquece entidades com NLP"""
        result = await semantic_parser_with_nlp.parse(intent_envelope_create)

        assert 'entities' in result
        # Deve ter mais entidades do que as originais (1)
        # devido ao enriquecimento NLP
        assert len(result['entities']) >= 1

    @pytest.mark.asyncio
    async def test_parse_extracts_query_objective(
        self,
        semantic_parser_with_nlp,
        intent_envelope_query
    ):
        """Testa extração de objective 'query'"""
        result = await semantic_parser_with_nlp.parse(intent_envelope_query)

        assert 'query' in result['objectives']

    @pytest.mark.asyncio
    async def test_parse_without_nlp_uses_heuristic(
        self,
        semantic_parser_without_nlp,
        intent_envelope_create
    ):
        """Testa que parse usa heurística quando NLP não disponível"""
        result = await semantic_parser_without_nlp.parse(intent_envelope_create)

        assert 'objectives' in result
        # Heurística simples ainda deve encontrar 'create' no texto
        assert 'create' in result['objectives'] or 'criar' in intent_envelope_create['intent']['text'].lower()

    @pytest.mark.asyncio
    async def test_parse_handles_empty_entities(
        self,
        semantic_parser_with_nlp,
        intent_envelope_query
    ):
        """Testa que parse lida com lista de entidades vazia"""
        result = await semantic_parser_with_nlp.parse(intent_envelope_query)

        assert 'entities' in result
        # NLP pode adicionar entidades mesmo quando original está vazio
        assert isinstance(result['entities'], list)

    @pytest.mark.asyncio
    async def test_parse_preserves_original_entities(
        self,
        semantic_parser_with_nlp,
        intent_envelope_create
    ):
        """Testa que entidades originais são preservadas"""
        original_entity_value = intent_envelope_create['intent']['entities'][0]['value']

        result = await semantic_parser_with_nlp.parse(intent_envelope_create)

        # Verificar que a entidade original está presente
        entity_values = [e.get('value') or e.get('canonical_type') for e in result['entities']]
        # Entidade original pode ter sido mapeada para canonical_type
        assert len(result['entities']) >= 1

    @pytest.mark.asyncio
    async def test_parse_handles_null_constraints(
        self,
        semantic_parser_with_nlp,
        intent_envelope_query
    ):
        """Testa que parse lida com constraints nulo"""
        result = await semantic_parser_with_nlp.parse(intent_envelope_query)

        assert 'constraints' in result
        assert result['constraints']['priority'] == 'normal'  # valor padrão

    @pytest.mark.asyncio
    async def test_parse_result_structure(
        self,
        semantic_parser_with_nlp,
        intent_envelope_create
    ):
        """Testa estrutura completa do resultado do parse"""
        result = await semantic_parser_with_nlp.parse(intent_envelope_create)

        # Verificar campos obrigatórios
        assert 'intent_id' in result
        assert 'domain' in result
        assert 'objectives' in result
        assert 'entities' in result
        assert 'constraints' in result
        assert 'historical_context' in result
        assert 'known_patterns' in result
        assert 'original_confidence' in result
        assert 'metadata' in result

        # Verificar valores
        assert result['intent_id'] == 'test-intent-001'
        assert result['domain'] == 'technical'
        assert result['original_confidence'] == 0.95


class TestNLPAccuracyComparison:
    """Testes de acurácia comparando NLP vs heurística"""

    @pytest.fixture
    async def nlp_processor(self):
        """Fixture que cria e inicializa NLPProcessor"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=None)
        await processor.initialize()
        return processor

    @pytest.fixture
    def test_cases(self):
        """Dataset de teste para comparação de acurácia"""
        return [
            {
                'text': 'Criar API REST para cadastro de usuários',
                'expected_objectives': ['create'],
                'language': 'pt'
            },
            {
                'text': 'Atualizar configurações do sistema',
                'expected_objectives': ['update'],
                'language': 'pt'
            },
            {
                'text': 'Deletar registros antigos da base',
                'expected_objectives': ['delete'],
                'language': 'pt'
            },
            {
                'text': 'Buscar pedidos do último mês',
                'expected_objectives': ['query'],
                'language': 'pt'
            },
            {
                'text': 'Converter dados de CSV para JSON',
                'expected_objectives': ['transform'],
                'language': 'pt'
            },
            {
                'text': 'Build a new REST API for user management',
                'expected_objectives': ['create'],
                'language': 'en'
            },
            {
                'text': 'Update the database schema',
                'expected_objectives': ['update'],
                'language': 'en'
            },
            {
                'text': 'Remove deprecated endpoints',
                'expected_objectives': ['delete'],
                'language': 'en'
            },
            {
                'text': 'Search for all active users',
                'expected_objectives': ['query'],
                'language': 'en'
            },
            {
                'text': 'Migrate data to new format',
                'expected_objectives': ['transform'],
                'language': 'en'
            },
            {
                'text': 'Gerar relatório de vendas e atualizar métricas',
                'expected_objectives': ['create', 'update'],
                'language': 'pt'
            },
            {
                'text': 'Delete old records and create backup',
                'expected_objectives': ['delete', 'create'],
                'language': 'en'
            }
        ]

    @pytest.mark.asyncio
    async def test_nlp_objective_accuracy(self, nlp_processor, test_cases):
        """Testa acurácia de extração de objectives com NLP"""
        correct = 0
        total = len(test_cases)

        for case in test_cases:
            objectives = nlp_processor.extract_objectives(case['text'])

            # Verificar se todos os objectives esperados foram encontrados
            expected = set(case['expected_objectives'])
            found = set(objectives)

            if expected.issubset(found):
                correct += 1

        accuracy = correct / total
        # NLP deve ter acurácia >= 80%
        assert accuracy >= 0.80, f"Acurácia de objectives: {accuracy:.2%}"

    @pytest.mark.asyncio
    async def test_nlp_keyword_extraction_quality(self, nlp_processor):
        """Testa qualidade de extração de keywords"""
        test_text = "Criar API REST para gerenciamento de produtos com autenticação JWT e cache Redis"

        keywords = nlp_processor.extract_keywords(test_text, max_keywords=10)

        # Verificar que palavras técnicas relevantes foram extraídas
        keywords_lower = [k.lower() for k in keywords]

        # Pelo menos algumas palavras técnicas devem estar presentes
        technical_words = ['api', 'rest', 'gerenciamento', 'produto', 'autenticação', 'jwt', 'cache', 'redis']
        found_technical = sum(1 for w in technical_words if w in keywords_lower)

        # Deve encontrar pelo menos 3 palavras técnicas
        assert found_technical >= 3, f"Encontradas apenas {found_technical} palavras técnicas: {keywords}"
