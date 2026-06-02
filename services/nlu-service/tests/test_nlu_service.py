"""Testes para o NLU Service."""

import pytest

from src.models.nlu import (
    CalculateConfidenceRequest,
    ClassifyDomainRequest,
    Entity,
    EntityType,
    ExtractEntitiesRequest,
    NLUResult,
    ParseRequest,
    UnifiedDomain,
)
from src.services.nlu_pipeline import NLUPipelineService


@pytest.fixture
async def nlu_service():
    """Fixture para o serviço NLU."""
    service = NLUPipelineService()
    # Mock spacy loading for tests
    service.nlp = type("MockSpacy", (), {"ents": []})()
    service.nlp_models = {"default": service.nlp, "pt": service.nlp}
    service._ready = True
    service._load_classification_rules = lambda: None
    service.classification_rules = service._get_default_rules()
    service._prepare_optimized_structures()
    return service


class TestNLUPipelineService:
    """Testes do pipeline NLU."""

    @pytest.mark.asyncio
    async def test_validate_text_valid(self, nlu_service: NLUPipelineService):
        """Testar validação de texto válido."""
        assert nlu_service._validate_text("Texto válido") is True
        assert nlu_service._validate_text("deploy em produção") is True

    @pytest.mark.asyncio
    async def test_validate_text_invalid(self, nlu_service: NLUPipelineService):
        """Testar validação de texto inválido."""
        assert nlu_service._validate_text("") is False
        assert nlu_service._validate_text("a") is False
        assert nlu_service._validate_text("111") is False  # Apenas números

    def test_normalize_text(self, nlu_service: NLUPipelineService):
        """Testar normalização de texto."""
        assert nlu_service._normalize_text("  texto   com  espaços  ") == "texto com espaços"

    def test_map_entity_type(self, nlu_service: NLUPipelineService):
        """Testar mapeamento de tipos de entidade."""
        assert nlu_service._map_entity_type("PERSON") == EntityType.PERSON
        assert nlu_service._map_entity_type("ORG") == EntityType.ORG
        assert nlu_service._map_entity_type("UNKNOWN") == EntityType.UNKNOWN

    @pytest.mark.asyncio
    async def test_classify_domain_business(self, nlu_service: NLUPipelineService):
        """Testar classificação de domínio BUSINESS."""
        text = "Relatório de vendas do cliente"
        entities = []
        domain, classification, confidence = nlu_service._classify_domain(
            text, entities, "pt", None
        )

        assert domain == UnifiedDomain.BUSINESS
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_domain_technical(self, nlu_service: NLUPipelineService):
        """Testar classificação de domínio TECHNICAL."""
        text = "Debugar bug na API"
        entities = []
        domain, classification, confidence = nlu_service._classify_domain(
            text, entities, "pt", None
        )

        assert domain == UnifiedDomain.TECHNICAL
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_domain_infrastructure(self, nlu_service: NLUPipelineService):
        """Testar classificação de domínio INFRASTRUCTURE."""
        text = "Deploy no Kubernetes"
        entities = []
        domain, classification, confidence = nlu_service._classify_domain(
            text, entities, "pt", None
        )

        assert domain == UnifiedDomain.INFRASTRUCTURE
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_domain_security(self, nlu_service: NLUPipelineService):
        """Testar classificação de domínio SECURITY."""
        text = "Configurar autenticação JWT"
        entities = []
        domain, classification, confidence = nlu_service._classify_domain(
            text, entities, "pt", None
        )

        assert domain == UnifiedDomain.SECURITY
        assert confidence > 0.5

    def test_calculate_adaptive_threshold(self, nlu_service: NLUPipelineService):
        """Testar cálculo de threshold adaptativo."""
        # Texto curto, sem entidades
        threshold1 = nlu_service._calculate_adaptive_threshold("curto", None, 0.6, [])
        assert threshold1 >= 0.3

        # Texto longo com entidades
        long_text = "Este é um texto muito longo com várias palavras " * 10
        entities = [Entity(type=EntityType.ORG, value="Test", confidence=0.9)]
        threshold2 = nlu_service._calculate_adaptive_threshold(long_text, None, 0.6, entities)
        assert threshold2 < 0.6  # Threshold deve diminuir

    def test_get_cache_key(self, nlu_service: NLUPipelineService):
        """Testar geração de chave de cache."""
        key1 = nlu_service._get_cache_key("texto", "pt", {"user": "1"})
        key2 = nlu_service._get_cache_key("texto", "pt", {"user": "1"})
        key3 = nlu_service._get_cache_key("texto", "pt", {"user": "2"})

        assert key1 == key2  # Mesmo input, mesma key
        assert key1 != key3  # Contexto diferente, key diferente

    @pytest.mark.asyncio
    async def test_extract_entities_mock(self, nlu_service: NLUPipelineService):
        """Testar extração de entidades com mock."""

        # Criar mock doc
        class MockToken:
            def __init__(self, text, label, start, end):
                self.text = text
                self.label_ = label
                self.start_char = start
                self.end_char = end

        class MockDoc:
            def __init__(self):
                self.ents = [
                    MockToken("Google", "ORG", 0, 6),
                    MockToken("João", "PERSON", 7, 12),
                ]

        mock_doc = MockDoc()
        entities = nlu_service._extract_entities(mock_doc)

        assert len(entities) == 2
        assert entities[0].type == EntityType.ORG
        assert entities[0].value == "Google"
        assert entities[1].type == EntityType.PERSON
        assert entities[1].value == "João"


class TestNLUModels:
    """Testes dos modelos NLU."""

    def test_parse_request_validation(self):
        """Testar validação de ParseRequest."""
        # Request válido
        request = ParseRequest(
            text="Deploy em produção",
            language="pt",
        )
        assert request.text == "Deploy em produção"
        assert request.language == "pt"
        assert request.enable_cache is True

    def test_nlu_result_inv1_compliance(self):
        """
        Testar que NLUResult satisfaz INV-1:
        - domain: UnifiedDomain
        - entities: list[Entity] com type, value, confidence, start, end
        - confidence: float 0-1
        - keywords: list[str]
        """
        result = NLUResult(
            processed_text="Deploy em produção",
            domain=UnifiedDomain.INFRASTRUCTURE,
            classification="deployment",
            confidence=0.85,
            entities=[
                Entity(
                    type=EntityType.ORG,
                    value="Kubernetes",
                    confidence=0.9,
                    start=10,
                    end=20,
                )
            ],
            keywords=["deploy", "produção", "kubernetes"],
            original_language="pt",
        )

        assert result.domain == UnifiedDomain.INFRASTRUCTURE
        assert len(result.entities) == 1
        assert result.entities[0].type == EntityType.ORG
        assert result.entities[0].value == "Kubernetes"
        assert result.entities[0].confidence == 0.9
        assert result.entities[0].start == 10
        assert result.entities[0].end == 20
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.keywords) == 3
        assert "deploy" in result.keywords

    def test_entity_inv1_compliance(self):
        """
        Testar que Entity satisfaz INV-1:
        - type: EntityType
        - value: str
        - confidence: float 0-1
        - start: int (opcional)
        - end: int (opcional)
        """
        entity = Entity(
            type=EntityType.EMAIL,
            value="user@example.com",
            confidence=0.95,
            start=0,
            end=16,
        )

        assert entity.type == EntityType.EMAIL
        assert entity.value == "user@example.com"
        assert 0.0 <= entity.confidence <= 1.0
        assert entity.start == 0
        assert entity.end == 16


class TestAPIRequests:
    """Testes de request models."""

    def test_classify_domain_request(self):
        """Testar ClassifyDomainRequest."""
        request = ClassifyDomainRequest(
            text="Deploy no Kubernetes",
            language="pt",
            context={"tenant_id": "123"},
        )
        assert request.text == "Deploy no Kubernetes"
        assert request.language == "pt"
        assert request.context["tenant_id"] == "123"

    def test_extract_entities_request(self):
        """Testar ExtractEntitiesRequest."""
        request = ExtractEntitiesRequest(
            text="João Silva entrou na empresa Google",
            language="pt",
            entity_types=[EntityType.PERSON, EntityType.ORG],
        )
        assert request.text == "João Silva entrou na empresa Google"
        assert len(request.entity_types) == 2

    def test_calculate_confidence_request(self):
        """Testar CalculateConfidenceRequest."""
        nlu_result = NLUResult(
            processed_text="Teste",
            domain=UnifiedDomain.TECHNICAL,
            classification="general",
            confidence=0.75,
            keywords=["teste"],
        )
        request = CalculateConfidenceRequest(nlu_result=nlu_result)
        assert request.nlu_result.confidence == 0.75
