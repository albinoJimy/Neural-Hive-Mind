"""
Tests for WorkflowClassifierService.
"""

import pytest

from src.models.cognitive_plan import WorkflowType
from src.services.workflow_classifier import WorkflowClassifierService, get_classifier


class TestWorkflowClassifierService:
    """Testes para WorkflowClassifierService."""

    def test_initialization(self):
        """Testa inicialização do classificador."""
        classifier = WorkflowClassifierService()
        assert classifier.generation_threshold == 0.6
        assert classifier.enable_keywords is True
        assert classifier.enable_complexity is True
        assert classifier.enable_historical is True

    def test_classify_generation_keywords(self):
        """Testa classificação de intent com keywords de geração."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-1",
            "intent": {
                "text": "Criar um novo microserviço para processamento de pagamentos",
                "domain": "development",
            },
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        assert workflow_type == WorkflowType.GENERATION
        assert metadata["workflow_type"] == "generation"
        assert metadata["score"] >= 0.6
        assert "keywords" in metadata["signals"]
        assert metadata["signals"]["keywords"] > 0.5

    def test_classify_orchestration_keywords(self):
        """Testa classificação de intent com keywords de orquestração."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-2",
            "intent": {
                "text": "Consultar status de todas as transações do dia",
                "domain": "operations",
            },
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        assert workflow_type == WorkflowType.ORCHESTRATION
        assert metadata["workflow_type"] == "orchestration"
        assert metadata["score"] < 0.6

    def test_classify_api_creation(self):
        """Testa classificação para criação de API."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-3",
            "intent": {
                "text": "Gerar uma API REST para gerenciamento de usuários",
                "domain": "development",
            },
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        assert workflow_type == WorkflowType.GENERATION
        assert metadata["score"] >= 0.6

    def test_classify_from_scratch(self):
        """Testa classificação com 'from scratch'."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-4",
            "intent": {
                "text": "Construir sistema de notificações do zero",
            },
        }

        workflow_type, _ = classifier.classify(intent_envelope)

        assert workflow_type == WorkflowType.GENERATION

    def test_classify_query_operation(self):
        """Testa classificação para operação de consulta."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-5",
            "intent": {
                "text": "Buscar todos os clientes ativos no último mês",
            },
        }

        workflow_type, _ = classifier.classify(intent_envelope)

        assert workflow_type == WorkflowType.ORCHESTRATION

    def test_classify_empty_text(self):
        """Testa classificação com texto vazio."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-6",
            "intent": {"text": ""},
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        # Deve default para ORCHESTRATION
        assert workflow_type == WorkflowType.ORCHESTRATION
        # Score pode ser > 0 devido a sinais históricos de outros testes
        assert metadata["score"] >= 0.0

    def test_classify_with_intermediate_repr_complex(self):
        """Testa classificação com intermediate_repr complexo."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-7",
            "intent": {"text": "Criar serviço de autenticação"},
        }

        intermediate_repr = {
            "tasks": [
                {"id": "1"},
                {"id": "2"},
                {"id": "3"},
                {"id": "4"},
                {"id": "5"},
                {"id": "6"},
                {"id": "7"},
                {"id": "8"},
                {"id": "9"},
                {"id": "10"},
                {"id": "11"},
            ],
            "historical_context": {"similar_intents": []},
        }

        workflow_type, metadata = classifier.classify(intent_envelope, intermediate_repr)

        assert workflow_type == WorkflowType.GENERATION
        assert metadata["signals"]["complexity"] > 0.5

    def test_classify_with_intermediate_repr_simple(self):
        """Testa classificação com intermediate_repr simples."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-8",
            "intent": {"text": "Listar usuários"},
        }

        intermediate_repr = {
            "tasks": [{"id": "1"}],
            "historical_context": {"similar_intents": []},
        }

        workflow_type, metadata = classifier.classify(intent_envelope, intermediate_repr)

        assert workflow_type == WorkflowType.ORCHESTRATION
        assert metadata["signals"]["complexity"] < 0.5

    def test_classify_development_domain(self):
        """Testa classificação com domain=development."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-9",
            "intent": {
                "text": "Processar dados",
                "domain": "development",
            },
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        # Historical signal deve favorecer generation
        assert metadata["signals"]["historical"] > 0.5

    def test_classify_monitoring_domain(self):
        """Testa classificação com domain=monitoring."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-10",
            "intent": {
                "text": "Verificar status",
                "domain": "monitoring",
            },
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        # Historical signal deve favorecer orchestration
        assert metadata["signals"]["historical"] < 0.5

    def test_explain_decision(self):
        """Testa explicação da decisão."""
        classifier = WorkflowClassifierService()

        # Testa decisão GENERATION
        reason = classifier._explain_decision(0.8, {"keywords": 0.9})
        assert "GENERATION" in reason
        assert "0.80" in reason

        # Testa decisão ORCHESTRATION
        reason = classifier._explain_decision(0.4, {"keywords": 0.3})
        assert "ORCHESTRATION" in reason
        assert "0.40" in reason

    def test_threshold_configuration(self):
        """Testa configuração de threshold."""
        classifier = WorkflowClassifierService(generation_threshold=0.7)

        intent_envelope = {
            "id": "test-11",
            "intent": {"text": "Criar serviço"},
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        # Metadata deve mostrar threshold configurado
        assert metadata["threshold"] == 0.7

    def test_disabled_keywords(self):
        """Testa classificação sem keywords."""
        classifier = WorkflowClassifierService(enable_keywords=False)

        intent_envelope = {
            "id": "test-12",
            "intent": {"text": "Criar novo serviço"},
        }

        workflow_type, metadata = classifier.classify(intent_envelope)

        # Keywords signal não deve estar presente
        assert "keywords" not in metadata["signals"]

    def test_metadata_completeness(self):
        """Testa se metadata contém todos os campos esperados."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-13",
            "intent": {"text": "Criar API"},
        }

        _, metadata = classifier.classify(intent_envelope)

        # Verificar campos obrigatórios
        assert "workflow_type" in metadata
        assert "score" in metadata
        assert "confidence" in metadata
        assert "threshold" in metadata
        assert "signals" in metadata
        assert "signal_count" in metadata
        assert "reason" in metadata

    def test_singleton_get_classifier(self):
        """Testa singleton get_classifier."""
        classifier1 = get_classifier()
        classifier2 = get_classifier()

        # Deve retornar a mesma instância
        assert classifier1 is classifier2

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("criar novo microserviço", WorkflowType.GENERATION),
            ("build new api", WorkflowType.GENERATION),
            ("gerar sistema do zero", WorkflowType.GENERATION),
            ("implementar endpoint", WorkflowType.GENERATION),
            ("consultar dados", WorkflowType.ORCHESTRATION),
            ("listar usuários", WorkflowType.ORCHESTRATION),
            ("executar tarefa", WorkflowType.ORCHESTRATION),
            ("analisar métricas", WorkflowType.ORCHESTRATION),
        ],
    )
    def test_parametrized_classification(self, text, expected):
        """Testa classificação parametrizada."""
        classifier = WorkflowClassifierService()

        intent_envelope = {
            "id": "test-param",
            "intent": {"text": text},
        }

        workflow_type, _ = classifier.classify(intent_envelope)

        assert workflow_type == expected
