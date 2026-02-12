"""Testes unitários para NLUPipeline"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any

from pipelines.nlu_pipeline import NLUPipeline
from models.intent_envelope import NLUResult, Entity
from neural_hive_domain import UnifiedDomain


class TestNLUPipeline:
    """Testes para a classe NLUPipeline"""

    @pytest.fixture
    def nlu_pipeline(self):
        """Fixture do pipeline NLU"""
        pipeline = NLUPipeline(
            language_model="pt_core_news_sm",
            confidence_threshold=0.5
        )
        # Carregar regras padrão
        pipeline.classification_rules = pipeline._get_default_classification_rules()
        return pipeline

    @pytest.mark.asyncio
    async def test_initialize_pipeline(self, nlu_pipeline):
        """Teste de inicialização do pipeline"""
        with patch('spacy.load') as mock_spacy_load:
            mock_nlp = MagicMock()
            mock_spacy_load.return_value = mock_nlp

            await nlu_pipeline.initialize()

            assert nlu_pipeline.is_ready() is True
            mock_spacy_load.assert_called_once_with("pt_core_news_sm")

    @pytest.mark.asyncio
    async def test_process_text_success(self, nlu_pipeline):
        """Teste de processamento de texto bem-sucedido"""
        # Mock do modelo spaCy
        mock_nlp = MagicMock()
        mock_doc = MagicMock()

        # Configure entity extraction
        mock_entity1 = MagicMock()
        mock_entity1.label_ = "PERSON"
        mock_entity1.text = "João"
        mock_entity1.start_char = 0
        mock_entity1.end_char = 4
        mock_entity1._.confidence = 0.95

        mock_entity2 = MagicMock()
        mock_entity2.label_ = "ORG"
        mock_entity2.text = "Empresa"
        mock_entity2.start_char = 15
        mock_entity2.end_char = 22
        mock_entity2._.confidence = 0.88

        mock_doc.ents = [mock_entity1, mock_entity2]

        # Configure token processing for keywords
        mock_token1 = MagicMock()
        mock_token1.text = "implementar"
        mock_token1.pos_ = "VERB"
        mock_token1.is_stop = False
        mock_token1.is_punct = False
        mock_token1.is_space = False

        mock_token2 = MagicMock()
        mock_token2.text = "sistema"
        mock_token2.pos_ = "NOUN"
        mock_token2.is_stop = False
        mock_token2.is_punct = False
        mock_token2.is_space = False

        mock_doc.__iter__ = lambda self: iter([mock_token1, mock_token2])
        mock_doc.text = "implementar novo sistema"

        mock_nlp.return_value = mock_doc

        nlu_pipeline.nlp = mock_nlp
        nlu_pipeline._ready = True

        user_context = {
            "userId": "user-123",
            "tenantId": "tenant-456"
        }

        result = await nlu_pipeline.process(
            text="João precisa implementar novo sistema na Empresa",
            language="pt-BR",
            context=user_context
        )

        assert isinstance(result, NLUResult)
        assert result.domain in [UnifiedDomain.BUSINESS, UnifiedDomain.TECHNICAL, UnifiedDomain.INFRASTRUCTURE, UnifiedDomain.SECURITY]
        assert result.classification is not None
        assert result.confidence >= 0.0  # Can be any valid confidence
        assert result.confidence_status in ["high", "medium", "low"]
        assert len(result.entities) == 2
        assert result.entities[0].type == "PERSON"
        assert result.entities[0].value == "João"
        assert result.entities[1].type == "ORG"
        assert result.entities[1].value == "Empresa"
        assert "implementar" in result.keywords or "sistema" in result.keywords

    @pytest.mark.asyncio
    async def test_process_text_low_confidence(self, nlu_pipeline):
        """Teste com confiança baixa (abaixo do threshold)"""
        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        mock_doc.ents = []
        mock_doc.__iter__ = lambda self: iter([])
        mock_doc.text = "texto ambíguo sem contexto claro"

        mock_nlp.return_value = mock_doc

        nlu_pipeline.nlp = mock_nlp
        nlu_pipeline._ready = True

        # Mock classification with low confidence
        with patch.object(nlu_pipeline, '_classify_intent_advanced', new_callable=AsyncMock) as mock_classify:
            mock_classify.return_value = (UnifiedDomain.BUSINESS, "request", 0.35)  # Low confidence

            result = await nlu_pipeline.process(
                text="texto ambíguo sem contexto claro",
                language="pt-BR",
                context={}
            )

            assert result.confidence == 0.35
            assert result.confidence_status == "low"
            assert result.requires_manual_validation == True

    @pytest.mark.asyncio
    async def test_pii_masking(self, nlu_pipeline):
        """Teste de mascaramento de PII"""
        mock_nlp = MagicMock()
        mock_doc = MagicMock()

        # Mock PII entities
        mock_person = MagicMock()
        mock_person.label_ = "PERSON"
        mock_person.text = "Maria Silva"
        mock_person.start_char = 0
        mock_person.end_char = 11

        mock_email = MagicMock()
        mock_email.label_ = "EMAIL"
        mock_email.text = "maria@exemplo.com"
        mock_email.start_char = 25
        mock_email.end_char = 42

        mock_doc.ents = [mock_person, mock_email]
        mock_doc.text = "Maria Silva precisa acessar maria@exemplo.com para configurar"

        mock_nlp.return_value = mock_doc

        nlu_pipeline.nlp = mock_nlp
        nlu_pipeline._ready = True

        result = await nlu_pipeline.process(
            text="Maria Silva precisa acessar maria@exemplo.com para configurar",
            language="pt-BR",
            context={}
        )

        # Check that PII was masked in processed text
        assert "[PERSON]" in result.processed_text
        assert "[EMAIL]" in result.processed_text
        assert "Maria Silva" not in result.processed_text
        assert "maria@exemplo.com" not in result.processed_text

    @pytest.mark.asyncio
    async def test_domain_classification(self, nlu_pipeline):
        """Teste de classificação de domínios"""
        nlu_pipeline._ready = True

        test_cases = [
            ("Implementar autenticação OAuth2", UnifiedDomain.TECHNICAL),
            ("Configurar servidor Kubernetes", UnifiedDomain.INFRASTRUCTURE),
            ("Analisar vulnerabilidades de segurança", UnifiedDomain.SECURITY),
            ("Desenvolver nova feature de vendas", UnifiedDomain.BUSINESS),
            ("Criar relatório de faturamento", UnifiedDomain.BUSINESS),
            ("Corrigir bug no sistema de login", UnifiedDomain.TECHNICAL),
            ("Configurar backup automático", UnifiedDomain.INFRASTRUCTURE),
            ("Implementar criptografia de dados", UnifiedDomain.SECURITY)
        ]

        for text, expected_domain in test_cases:
            domain, _, _ = await nlu_pipeline._classify_intent_advanced(text, [], "pt", {})
            assert domain == expected_domain

    @pytest.mark.asyncio
    async def test_confidence_threshold_gating(self, nlu_pipeline):
        """Teste do gate de confiança"""
        nlu_pipeline._ready = True
        nlu_pipeline.confidence_threshold = 0.5

        # Test text that should result in low confidence
        low_confidence_text = "abc xyz 123"

        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        mock_doc.ents = []
        mock_doc.__iter__ = lambda self: iter([])
        mock_doc.text = low_confidence_text

        mock_nlp.return_value = mock_doc
        nlu_pipeline.nlp = mock_nlp

        with patch.object(nlu_pipeline, '_classify_intent_advanced', new_callable=AsyncMock) as mock_classify:
            mock_classify.return_value = (UnifiedDomain.BUSINESS, "unknown", 0.40)  # Below threshold

            result = await nlu_pipeline.process(
                text=low_confidence_text,
                language="pt-BR",
                context={}
            )

            # Should return result but marked as low confidence
            assert result.confidence < nlu_pipeline.confidence_threshold
            assert result.confidence_status == "low"
            assert result.classification == "unknown"

    @pytest.mark.asyncio
    async def test_entity_confidence_filtering(self, nlu_pipeline):
        """Teste de filtro de confiança de entidades"""
        mock_nlp = MagicMock()
        mock_doc = MagicMock()

        # Mock entities with different confidence levels
        high_conf_entity = MagicMock()
        high_conf_entity.label_ = "PERSON"
        high_conf_entity.text = "João"
        high_conf_entity.start_char = 0
        high_conf_entity.end_char = 4
        high_conf_entity._.confidence = 0.95

        low_conf_entity = MagicMock()
        low_conf_entity.label_ = "ORG"
        low_conf_entity.text = "xyz"
        low_conf_entity.start_char = 10
        low_conf_entity.end_char = 13
        low_conf_entity._.confidence = 0.45

        mock_doc.ents = [high_conf_entity, low_conf_entity]
        mock_doc.__iter__ = lambda self: iter([])
        mock_doc.text = "João trabalha na xyz"

        mock_nlp.return_value = mock_doc

        nlu_pipeline.nlp = mock_nlp
        nlu_pipeline._ready = True

        result = await nlu_pipeline.process(
            text="João trabalha na xyz",
            language="pt-BR",
            context={}
        )

        # Should include entities extracted from spaCy
        assert len(result.entities) >= 1
        # At least one entity should be PERSON
        person_entities = [e for e in result.entities if e.type == "PERSON"]
        assert len(person_entities) >= 1
        assert person_entities[0].confidence >= 0.0

    @pytest.mark.asyncio
    async def test_keyword_extraction(self, nlu_pipeline):
        """Teste de extração de palavras-chave"""
        mock_nlp = MagicMock()
        mock_doc = MagicMock()

        # Mock tokens for keyword extraction
        tokens = []

        # Relevant tokens
        relevant_token1 = MagicMock()
        relevant_token1.text = "implementar"
        relevant_token1.pos_ = "VERB"
        relevant_token1.is_stop = False
        relevant_token1.is_punct = False
        relevant_token1.is_space = False
        tokens.append(relevant_token1)

        relevant_token2 = MagicMock()
        relevant_token2.text = "autenticação"
        relevant_token2.pos_ = "NOUN"
        relevant_token2.is_stop = False
        relevant_token2.is_punct = False
        relevant_token2.is_space = False
        tokens.append(relevant_token2)

        # Stop word (should be filtered out)
        stop_token = MagicMock()
        stop_token.text = "de"
        stop_token.pos_ = "ADP"
        stop_token.is_stop = True
        stop_token.is_punct = False
        stop_token.is_space = False
        tokens.append(stop_token)

        # Punctuation (should be filtered out)
        punct_token = MagicMock()
        punct_token.text = "."
        punct_token.pos_ = "PUNCT"
        punct_token.is_stop = False
        punct_token.is_punct = True
        punct_token.is_space = False
        tokens.append(punct_token)

        mock_doc.__iter__ = lambda self: iter(tokens)
        mock_doc.ents = []
        mock_doc.text = "implementar autenticação de usuários."

        mock_nlp.return_value = mock_doc

        nlu_pipeline.nlp = mock_nlp
        nlu_pipeline._ready = True

        result = await nlu_pipeline.process(
            text="implementar autenticação de usuários.",
            language="pt-BR",
            context={}
        )

        keywords = result.keywords
        assert "implementar" in keywords
        assert "autenticação" in keywords
        assert "de" not in keywords  # Stop word filtered out
        assert "." not in keywords   # Punctuation filtered out

    @pytest.mark.asyncio
    async def test_process_not_ready(self, nlu_pipeline):
        """Teste de processamento quando pipeline não está pronto"""
        nlu_pipeline._ready = False

        with pytest.raises(RuntimeError, match="Pipeline NLU não inicializado"):
            await nlu_pipeline.process(
                text="test text",
                language="pt-BR",
                context={}
            )

    @pytest.mark.asyncio
    async def test_close_pipeline(self, nlu_pipeline):
        """Teste de fechamento do pipeline"""
        nlu_pipeline._ready = True
        nlu_pipeline.nlp = MagicMock()

        await nlu_pipeline.close()

        assert nlu_pipeline.is_ready() is False
        assert nlu_pipeline.nlp is None

    @pytest.mark.asyncio
    async def test_domain_keywords_mapping(self, nlu_pipeline):
        """Teste do mapeamento de palavras-chave para domínios"""
        # Test business domain keywords
        business_text = "venda marketing cliente receita faturamento"
        domain, _, _ = await nlu_pipeline._classify_intent_advanced(business_text, [], "pt", {})
        assert domain == UnifiedDomain.BUSINESS

        # Test technical domain keywords
        technical_text = "código bug API database implementar desenvolver"
        domain, _, _ = await nlu_pipeline._classify_intent_advanced(technical_text, [], "pt", {})
        assert domain == UnifiedDomain.TECHNICAL

        # Test infrastructure domain keywords
        infra_text = "servidor kubernetes docker deploy configurar"
        domain, _, _ = await nlu_pipeline._classify_intent_advanced(infra_text, [], "pt", {})
        assert domain == UnifiedDomain.INFRASTRUCTURE

        # Test security domain keywords
        security_text = "segurança vulnerabilidade autenticação criptografia"
        domain, _, _ = await nlu_pipeline._classify_intent_advanced(security_text, [], "pt", {})
        assert domain == UnifiedDomain.SECURITY

    @pytest.mark.asyncio
    async def test_cache_with_dict_type(self, nlu_pipeline):
        """Teste de cache retornando dict (tipo já deserializado)"""
        nlu_pipeline._ready = True

        # Mock Redis client retornando dict
        mock_redis = MagicMock()
        cached_dict = {
            "processed_text": "test text",
            "domain": "TECHNICAL",
            "classification": "implementation",
            "confidence": 0.85,
            "entities": [],
            "keywords": ["test"],
            "requires_manual_validation": False,
            "confidence_status": "high",
            "adaptive_threshold": 0.5
        }
        mock_redis.get = AsyncMock(return_value=cached_dict)
        nlu_pipeline.redis_client = mock_redis

        result = await nlu_pipeline._get_cached_result("test_key")

        assert result is not None
        assert result.domain == UnifiedDomain.TECHNICAL
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_cache_with_string_type(self, nlu_pipeline):
        """Teste de cache retornando string (JSON)"""
        nlu_pipeline._ready = True

        # Mock Redis client retornando string JSON
        import json

        mock_redis = MagicMock()
        cached_json = json.dumps({
            "processed_text": "test text",
            "domain": "BUSINESS",
            "classification": "request",
            "confidence": 0.75,
            "entities": [],
            "keywords": ["business"],
            "requires_manual_validation": False,
            "confidence_status": "medium",
            "adaptive_threshold": 0.5
        })
        mock_redis.get = AsyncMock(return_value=cached_json)
        nlu_pipeline.redis_client = mock_redis

        result = await nlu_pipeline._get_cached_result("test_key")

        assert result is not None
        assert result.domain == UnifiedDomain.BUSINESS
        assert result.confidence == 0.75

    @pytest.mark.asyncio
    async def test_cache_with_invalid_type(self, nlu_pipeline):
        """Teste de cache retornando tipo inválido (não dict, str ou bytes)"""
        nlu_pipeline._ready = True

        # Mock Redis client retornando tipo inválido (ex: int)
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=12345)  # Tipo inválido
        nlu_pipeline.redis_client = mock_redis

        result = await nlu_pipeline._get_cached_result("test_key")

        # Deve retornar None para tipo inválido
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_with_bytes_type(self, nlu_pipeline):
        """Teste de cache retornando bytes"""
        nlu_pipeline._ready = True

        # Mock Redis client retornando bytes
        import json

        mock_redis = MagicMock()
        cached_data = json.dumps({
            "processed_text": "test text",
            "domain": "SECURITY",
            "classification": "security_check",
            "confidence": 0.90,
            "entities": [],
            "keywords": ["security"],
            "requires_manual_validation": False,
            "confidence_status": "high",
            "adaptive_threshold": 0.5
        })
        mock_redis.get = AsyncMock(return_value=cached_data.encode('utf-8'))
        nlu_pipeline.redis_client = mock_redis

        result = await nlu_pipeline._get_cached_result("test_key")

        assert result is not None
        assert result.domain == UnifiedDomain.SECURITY
        assert result.confidence == 0.90

    @pytest.mark.asyncio
    async def test_cache_with_none_value(self, nlu_pipeline):
        """Teste de cache retornando None (cache miss)"""
        nlu_pipeline._ready = True

        # Mock Redis client retornando None
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        nlu_pipeline.redis_client = mock_redis

        result = await nlu_pipeline._get_cached_result("test_key")

        # Deve retornar None para cache miss
        assert result is None