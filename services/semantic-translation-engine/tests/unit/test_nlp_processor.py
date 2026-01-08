"""
Testes unitários para o NLP Processor

Testa extração de keywords, objectives e entidades usando spaCy.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestNLPProcessorExtractKeywords:
    """Testes para extração de keywords"""

    @pytest.fixture
    def nlp_processor(self):
        """Fixture que cria NLPProcessor sem Redis"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=None)
        return processor

    @pytest.fixture
    async def initialized_nlp_processor(self, nlp_processor):
        """Fixture que inicializa o NLPProcessor"""
        await nlp_processor.initialize()
        return nlp_processor

    @pytest.mark.asyncio
    async def test_extract_keywords_portuguese(self, initialized_nlp_processor):
        """Testa extração de keywords para texto em português"""
        text = "Criar API REST para gerenciar produtos com operações CRUD"
        keywords = initialized_nlp_processor.extract_keywords(text, max_keywords=10)

        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # Verificar que palavras relevantes foram extraídas
        keywords_lower = [k.lower() for k in keywords]
        assert any(k in keywords_lower for k in ['api', 'rest', 'produto', 'operação', 'crud', 'criar', 'gerenciar'])

    @pytest.mark.asyncio
    async def test_extract_keywords_english(self, initialized_nlp_processor):
        """Testa extração de keywords para texto em inglês"""
        text = "Build GraphQL API for user management with authentication"
        keywords = initialized_nlp_processor.extract_keywords(text, max_keywords=10)

        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # Verificar que palavras relevantes foram extraídas
        keywords_lower = [k.lower() for k in keywords]
        assert any(k in keywords_lower for k in ['graphql', 'api', 'user', 'management', 'authentication', 'build'])

    @pytest.mark.asyncio
    async def test_extract_keywords_respects_max_limit(self, initialized_nlp_processor):
        """Testa que max_keywords é respeitado"""
        text = "Criar sistema completo de gerenciamento de usuários com autenticação, autorização, perfis, preferências e configurações avançadas"
        keywords = initialized_nlp_processor.extract_keywords(text, max_keywords=3)

        assert len(keywords) <= 3

    @pytest.mark.asyncio
    async def test_extract_keywords_empty_text(self, initialized_nlp_processor):
        """Testa extração com texto vazio"""
        keywords = initialized_nlp_processor.extract_keywords("", max_keywords=5)
        assert keywords == []

    def test_extract_keywords_fallback_without_initialization(self, nlp_processor):
        """Testa fallback heurístico quando NLP não está inicializado"""
        text = "Criar API REST para produtos"
        keywords = nlp_processor.extract_keywords(text, max_keywords=5)

        assert isinstance(keywords, list)
        assert len(keywords) > 0


class TestNLPProcessorExtractObjectives:
    """Testes para extração de objectives"""

    @pytest.fixture
    def nlp_processor(self):
        """Fixture que cria NLPProcessor sem Redis"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=None)
        return processor

    @pytest.fixture
    async def initialized_nlp_processor(self, nlp_processor):
        """Fixture que inicializa o NLPProcessor"""
        await nlp_processor.initialize()
        return nlp_processor

    @pytest.mark.asyncio
    async def test_extract_objectives_create(self, initialized_nlp_processor):
        """Testa extração de objective 'create'"""
        text = "Criar novo endpoint REST para cadastro de usuários"
        objectives = initialized_nlp_processor.extract_objectives(text)

        assert 'create' in objectives

    @pytest.mark.asyncio
    async def test_extract_objectives_update(self, initialized_nlp_processor):
        """Testa extração de objective 'update'"""
        text = "Atualizar configurações do sistema de cache"
        objectives = initialized_nlp_processor.extract_objectives(text)

        assert 'update' in objectives

    @pytest.mark.asyncio
    async def test_extract_objectives_delete(self, initialized_nlp_processor):
        """Testa extração de objective 'delete'"""
        text = "Remover registros antigos da base de dados"
        objectives = initialized_nlp_processor.extract_objectives(text)

        assert 'delete' in objectives

    @pytest.mark.asyncio
    async def test_extract_objectives_query(self, initialized_nlp_processor):
        """Testa extração de objective 'query'"""
        text = "Buscar todos os pedidos do último mês"
        objectives = initialized_nlp_processor.extract_objectives(text)

        assert 'query' in objectives

    @pytest.mark.asyncio
    async def test_extract_objectives_transform(self, initialized_nlp_processor):
        """Testa extração de objective 'transform'"""
        text = "Converter dados CSV para formato JSON"
        objectives = initialized_nlp_processor.extract_objectives(text)

        assert 'transform' in objectives

    @pytest.mark.asyncio
    async def test_extract_objectives_multiple(self, initialized_nlp_processor):
        """Testa extração de múltiplos objectives"""
        text = "Atualizar os registros e depois deletar os duplicados"
        objectives = initialized_nlp_processor.extract_objectives(text)

        assert 'update' in objectives
        assert 'delete' in objectives

    @pytest.mark.asyncio
    async def test_extract_objectives_fallback_to_query(self, initialized_nlp_processor):
        """Testa fallback para 'query' quando nenhum objective identificado"""
        text = "Analisar a performance do sistema atual"
        objectives = initialized_nlp_processor.extract_objectives(text)

        # Deve ter pelo menos um objective (fallback para query)
        assert len(objectives) > 0
        assert 'query' in objectives

    def test_extract_objectives_fallback_without_initialization(self, nlp_processor):
        """Testa fallback heurístico quando NLP não está inicializado"""
        text = "Criar novo serviço"
        objectives = nlp_processor.extract_objectives(text)

        assert isinstance(objectives, list)
        assert 'create' in objectives


class TestNLPProcessorExtractEntities:
    """Testes para extração avançada de entidades"""

    @pytest.fixture
    def nlp_processor(self):
        """Fixture que cria NLPProcessor sem Redis"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=None)
        return processor

    @pytest.fixture
    async def initialized_nlp_processor(self, nlp_processor):
        """Fixture que inicializa o NLPProcessor"""
        await nlp_processor.initialize()
        return nlp_processor

    @pytest.mark.asyncio
    async def test_extract_entities_technology(self, initialized_nlp_processor):
        """Testa extração de entidades de tecnologia"""
        text = "Implementar API REST usando FastAPI e MongoDB"
        entities = initialized_nlp_processor.extract_entities_advanced(text)

        # Verificar que tecnologias foram identificadas
        tech_values = [e['value'] for e in entities if e['type'] == 'TECHNOLOGY']
        assert any(t in ['REST', 'FastAPI', 'MongoDB'] for t in tech_values)

    @pytest.mark.asyncio
    async def test_extract_entities_resource(self, initialized_nlp_processor):
        """Testa extração de entidades de recurso"""
        text = "Criar sistema de gerenciamento de produtos para e-commerce"
        entities = initialized_nlp_processor.extract_entities_advanced(text)

        assert isinstance(entities, list)
        # Verificar estrutura das entidades
        if entities:
            entity = entities[0]
            assert 'type' in entity
            assert 'value' in entity
            assert 'confidence' in entity

    @pytest.mark.asyncio
    async def test_extract_entities_empty_text(self, initialized_nlp_processor):
        """Testa extração com texto vazio"""
        entities = initialized_nlp_processor.extract_entities_advanced("")

        assert entities == []

    def test_extract_entities_without_initialization(self, nlp_processor):
        """Testa que retorna lista vazia quando não inicializado"""
        entities = nlp_processor.extract_entities_advanced("Criar API REST")

        assert entities == []


class TestNLPProcessorLanguageDetection:
    """Testes para detecção de idioma"""

    @pytest.fixture
    def nlp_processor(self):
        """Fixture que cria NLPProcessor"""
        from src.services.nlp_processor import NLPProcessor
        return NLPProcessor(redis_client=None)

    @pytest.fixture
    async def initialized_nlp_processor(self, nlp_processor):
        """Fixture que inicializa o NLPProcessor"""
        await nlp_processor.initialize()
        return nlp_processor

    @pytest.mark.asyncio
    async def test_detect_portuguese(self, initialized_nlp_processor):
        """Testa detecção de português"""
        text = "Criar uma API para gerenciar os usuários do sistema"
        lang = initialized_nlp_processor._detect_language(text)
        assert lang == 'pt'

    @pytest.mark.asyncio
    async def test_detect_english(self, initialized_nlp_processor):
        """Testa detecção de inglês"""
        text = "Create an API to manage the users of the system"
        lang = initialized_nlp_processor._detect_language(text)
        assert lang == 'en'


class TestNLPProcessorCache:
    """Testes para cache Redis"""

    @pytest.fixture
    def mock_redis_client(self):
        """Fixture que cria mock do RedisClient"""
        mock = AsyncMock()
        mock.get_cached_query = AsyncMock(return_value=None)
        mock.cache_query_result = AsyncMock()
        return mock

    @pytest.fixture
    def nlp_processor_with_cache(self, mock_redis_client):
        """Fixture que cria NLPProcessor com mock de Redis"""
        from src.services.nlp_processor import NLPProcessor
        return NLPProcessor(redis_client=mock_redis_client)

    def test_generate_cache_key(self, nlp_processor_with_cache):
        """Testa geração de chave de cache"""
        key = nlp_processor_with_cache._generate_cache_key('keywords', 'test text')

        assert key.startswith('nlp:keywords:')
        assert len(key) > len('nlp:keywords:')

    def test_generate_cache_key_deterministic(self, nlp_processor_with_cache):
        """Testa que mesma entrada gera mesma chave"""
        key1 = nlp_processor_with_cache._generate_cache_key('keywords', 'test text')
        key2 = nlp_processor_with_cache._generate_cache_key('keywords', 'test text')

        assert key1 == key2

    def test_generate_cache_key_different_operations(self, nlp_processor_with_cache):
        """Testa que operações diferentes geram chaves diferentes"""
        key1 = nlp_processor_with_cache._generate_cache_key('keywords', 'test text')
        key2 = nlp_processor_with_cache._generate_cache_key('objectives', 'test text')

        assert key1 != key2


class TestNLPProcessorInitialization:
    """Testes para inicialização do processador"""

    @pytest.fixture
    def nlp_processor(self):
        """Fixture que cria NLPProcessor"""
        from src.services.nlp_processor import NLPProcessor
        return NLPProcessor(redis_client=None)

    def test_is_ready_before_initialization(self, nlp_processor):
        """Testa que is_ready retorna False antes de inicialização"""
        assert nlp_processor.is_ready() is False

    @pytest.mark.asyncio
    async def test_is_ready_after_initialization(self, nlp_processor):
        """Testa que is_ready retorna True após inicialização"""
        await nlp_processor.initialize()
        assert nlp_processor.is_ready() is True

    @pytest.mark.asyncio
    async def test_double_initialization_safe(self, nlp_processor):
        """Testa que inicialização dupla não causa erro"""
        await nlp_processor.initialize()
        await nlp_processor.initialize()  # Segunda vez deve ser segura
        assert nlp_processor.is_ready() is True
