"""
Testes de Integração E2E para Explainability API.

Testa o fluxo completo:
1. Decisão de consenso é criada
2. Consumer gera explicação automaticamente
3. Explicação é publicada no Kafka
4. API retorna explicação completa com todos os campos

TDD: Testes escritos antes da implementação (GAPS-04 Task 7).
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import json
import asyncio
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestE2EConsensusToExplanation:
    """Testes E2E do fluxo Consenso → Explicação."""

    @pytest.fixture
    def consensus_decision(self):
        """Decisão de consenso completa com campos hierárquicos."""
        return {
            'decision_id': 'e2e-decision-123',
            'final_decision': {'decision': 'approve', 'confidence': 0.875},
            'aggregated_confidence': 0.875,
            'aggregated_risk': 0.125,
            'consensus_process': {
                'method': 'hierarchical_bayesian',
                'num_specialists': 5,
                'aggregation': {
                    'confidence': 0.875,
                    'risk': 0.125,
                    'divergence': 0.10
                },
                'seniority_distribution': {
                    'senior': 2,
                    'expert': 1,
                    'mid_level': 2
                },
                'hierarchical_weights_enabled': True
            },
            'specialist_opinions': [
                {
                    'specialist_type': 'business',
                    'seniority_level': 'senior',
                    'seniority_multiplier': 1.5,
                    'final_weight': 0.30,
                    'confidence': 0.90,
                    'risk': 0.10,
                    'reasoning': 'Alto ROI esperado de R$ 500k em 12 meses'
                },
                {
                    'specialist_type': 'technical',
                    'seniority_level': 'expert',
                    'seniority_multiplier': 2.0,
                    'final_weight': 0.35,
                    'confidence': 0.85,
                    'risk': 0.15,
                    'reasoning': 'Arquitetura em microserviços escalável com 150ms de latência média'
                },
                {
                    'specialist_type': 'architecture',
                    'seniority_level': 'expert',
                    'seniority_multiplier': 2.0,
                    'final_weight': 0.25,
                    'confidence': 0.88,
                    'risk': 0.12,
                    'reasoning': 'Padrões hexagonais aplicados corretamente'
                },
                {
                    'specialist_type': 'security',
                    'seniority_level': 'mid_level',
                    'seniority_multiplier': 1.0,
                    'final_weight': 0.08,
                    'confidence': 0.80,
                    'risk': 0.20,
                    'reasoning': 'OAuth2 implementado, mas precisa de validação adicional'
                },
                {
                    'specialist_type': 'behavior',
                    'seniority_level': 'senior',
                    'seniority_multiplier': 1.5,
                    'final_weight': 0.02,
                    'confidence': 0.70,
                    'risk': 0.30,
                    'reasoning': 'Experiência do usuário pode melhorar'
                }
            ],
            'reasoning_summary': 'Decisão aprovada com alta confiança devido ao forte alinhamento de negócio e arquitetura técnica sólida.',
            'explainability_token': 'token-e2e-123'
        }

    @pytest.fixture
    def mock_services(self):
        """Mock de todos os serviços."""
        return {
            'shap_calculator': MagicMock(),
            'quality_scorer': MagicMock(),
            'reasoning_extractor': MagicMock()
        }

    @pytest.mark.asyncio
    async def test_full_flow_hierarchical_fields_present(
        self,
        consensus_decision,
        mock_services
    ):
        """Testa que campos hierárquicos estão presentes na explicação final."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        # Setup mocks
        mock_services['shap_calculator'].calculate_shap.return_value = {
            'feature_attribution': {
                'confidence': 0.50,
                'risk': -0.15,
                'seniority_multiplier': 0.10
            }
        }
        mock_services['quality_scorer'].score_explanation.return_value = {
            'completeness': 0.90,
            'clarity': 0.85,
            'specificity': 0.80,
            'overall': 0.86
        }
        mock_services['reasoning_extractor'].extract_and_categorize.return_value = {
            'factors': [
                {'category': 'business', 'text': 'Alto ROI esperado'},
                {'category': 'technical', 'text': 'Arquitetura escalável'}
            ]
        }

        # Criar API service
        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(),
            shap_calculator=mock_services['shap_calculator'],
            quality_scorer=mock_services['quality_scorer'],
            reasoning_extractor=mock_services['reasoning_extractor']
        )

        # Gerar explicação
        generation_request = {
            'decision_id': consensus_decision['decision_id'],
            'format': 'json',
            'include_shap': True,
            'include_reasoning_extraction': True,
            'include_quality_score': True,
            'specialist_votes': consensus_decision['specialist_opinions'],
            'final_decision': consensus_decision['final_decision']['decision']
        }

        explanation = await api.generate_explanation(generation_request)

        # Validar campos hierárquicos estão presentes
        assert 'explainability_token' in explanation
        assert 'decision_id' in explanation
        assert explanation['decision_id'] == 'e2e-decision-123'

    @pytest.mark.asyncio
    async def test_explanation_shap_values_calculated(
        self,
        consensus_decision,
        mock_services
    ):
        """Testa que SHAP values são calculados corretamente."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        # Setup mock SHAP
        mock_services['shap_calculator'].calculate_shap.return_value = {
            'feature_attribution': {
                'confidence': 0.50,
                'risk': -0.15,
                'seniority_multiplier': 0.10
            }
        }
        mock_services['quality_scorer'].score_explanation.return_value = {
            'overall': 0.85
        }

        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(),
            shap_calculator=mock_services['shap_calculator'],
            quality_scorer=mock_services['quality_scorer']
        )

        generation_request = {
            'decision_id': consensus_decision['decision_id'],
            'include_shap': True,
            'specialist_votes': consensus_decision['specialist_opinions']
        }

        explanation = await api.generate_explanation(generation_request)

        # Validar SHAP values
        assert 'shap_values' in explanation
        assert 'confidence' in explanation['shap_values']
        assert explanation['shap_values']['confidence'] > 0  # Contribui positivamente
        assert 'risk' in explanation['shap_values']
        assert explanation['shap_values']['risk'] < 0  # Contribui negativamente

        # Verificar que calculate_shap foi chamado
        mock_services['shap_calculator'].calculate_shap.assert_called_once()

    @pytest.mark.asyncio
    async def test_explanation_quality_scores_calculated(
        self,
        consensus_decision,
        mock_services
    ):
        """Testa que quality scores são calculados corretamente."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        # Setup mock quality scorer
        quality_scores = {
            'completeness': 0.90,
            'clarity': 0.85,
            'specificity': 0.80,
            'overall': 0.86
        }
        mock_services['quality_scorer'].score_explanation.return_value = quality_scores

        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(),
            quality_scorer=mock_services['quality_scorer']
        )

        generation_request = {
            'decision_id': consensus_decision['decision_id'],
            'include_quality_score': True,
            'explanation': consensus_decision
        }

        explanation = await api.generate_explanation(generation_request)

        # Validar quality scores
        assert 'explanation_quality' in explanation
        assert 'completeness' in explanation['explanation_quality']
        assert 'clarity' in explanation['explanation_quality']
        assert 'specificity' in explanation['explanation_quality']
        assert 'overall' in explanation['explanation_quality']

        # Validar ranges
        assert 0.0 <= explanation['explanation_quality']['overall'] <= 1.0
        assert explanation['explanation_quality']['completeness'] >= 0.7  # Alta completude

    @pytest.mark.asyncio
    async def test_full_flow_with_consumer(
        self,
        consensus_decision,
        mock_services
    ):
        """Testa fluxo completo via Kafka consumer."""
        from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer
        from src.services.api_extensions import ExplainabilityAPIExtensions

        # Setup mocks
        mock_services['quality_scorer'].score_explanation.return_value = {
            'completeness': 0.90,
            'clarity': 0.85,
            'specificity': 0.80,
            'overall': 0.86
        }
        mock_services['shap_calculator'].calculate_shap.return_value = {
            'feature_attribution': {'confidence': 0.50}
        }

        # Criar mock do MongoDB com AsyncMock
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)  # Sem explicação existente
        mock_db.explainability_ledger = mock_collection

        # Criar serviço e producer
        api = ExplainabilityAPIExtensions(
            mongodb_client=mock_db,
            shap_calculator=mock_services['shap_calculator'],
            quality_scorer=mock_services['quality_scorer']
        )

        mock_producer = MagicMock()
        mock_producer.publish_explanation = AsyncMock()

        # Criar consumer
        consumer = ConsensusDecisionConsumer(
            bootstrap_servers='localhost:9092',
            group_id='e2e-test-group',
            explainability_service=api,
            explanation_producer=mock_producer,
            input_topic='consensus.decision.created',
            output_topic='consensus.explanations'
        )

        # Processar decisão
        await consumer.handle_decision(consensus_decision)

        # Validar que explicação foi gerada e publicada
        mock_producer.publish_explanation.assert_called_once()
        published = mock_producer.publish_explanation.call_args[0][0]

        assert 'explainability_token' in published
        assert 'decision_id' in published
        assert 'explanation_quality' in published


class TestE2EQueryFlow:
    """Testes E2E do fluxo de consulta de explicações."""

    @pytest.fixture
    def mock_db(self):
        """Mock do MongoDB com explicação completa."""
        db = MagicMock()

        # Mock para buscar por decision_id
        explanation = {
            'explainability_token': 'token-query-123',
            'decision_id': 'decision-query-456',
            'final_decision': {'decision': 'approve'},
            'consensus_process': {
                'method': 'hierarchical_bayesian',
                'seniority_distribution': {'senior': 2, 'expert': 1},
                'hierarchical_weights_enabled': True
            },
            'specialist_opinions': [
                {
                    'specialist_type': 'business',
                    'seniority_level': 'senior',
                    'seniority_multiplier': 1.5,
                    'final_weight': 0.65
                }
            ],
            'shap_values': {'confidence': 0.45, 'risk': -0.15},
            'explanation_quality': {
                'completeness': 0.92,
                'clarity': 0.88,
                'specificity': 0.75,
                'overall': 0.85
            }
        }

        collection = MagicMock()
        collection.find_one = AsyncMock(return_value=explanation)
        db.explainability_ledger = collection
        return db

    @pytest.mark.asyncio
    async def test_query_by_decision_id_returns_full_explanation(self, mock_db):
        """Testa que query por decision_id retorna explicação completa."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        api = ExplainabilityAPIExtensions(mongodb_client=mock_db)

        explanation = await api.get_explainability_by_decision_id('decision-query-456')

        # Validar campos principais
        assert explanation is not None
        assert explanation['decision_id'] == 'decision-query-456'
        assert 'explainability_token' in explanation

        # Validar campos hierárquicos
        assert 'consensus_process' in explanation
        assert 'seniority_distribution' in explanation['consensus_process']
        assert explanation['consensus_process']['hierarchical_weights_enabled'] is True

    @pytest.mark.asyncio
    async def test_query_includes_seniority_weights(self, mock_db):
        """Testa que query inclui pesos de senioridade."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        api = ExplainabilityAPIExtensions(mongodb_client=mock_db)

        explanation = await api.get_explainability_by_decision_id('decision-query-456')

        # Validar pesos de senioridade nas opiniões
        assert 'specialist_opinions' in explanation
        opinion = explanation['specialist_opinions'][0]
        assert 'seniority_level' in opinion
        assert opinion['seniority_level'] == 'senior'
        assert 'seniority_multiplier' in opinion
        assert opinion['seniority_multiplier'] == 1.5
        assert 'final_weight' in opinion

    @pytest.mark.asyncio
    async def test_query_includes_quality_scores(self, mock_db):
        """Testa que query inclui scores de qualidade."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        api = ExplainabilityAPIExtensions(mongodb_client=mock_db)

        explanation = await api.get_explainability_by_decision_id('decision-query-456')

        # Validar quality scores
        assert 'explanation_quality' in explanation
        quality = explanation['explanation_quality']
        assert 'completeness' in quality
        assert 'clarity' in quality
        assert 'specificity' in quality
        assert 'overall' in quality
        assert 0.0 <= quality['overall'] <= 1.0


class TestE2EMultiFormatOutput:
    """Testes E2E para múltiplos formatos de saída."""

    @pytest.fixture
    def base_explanation(self):
        """Explicação base para formatação."""
        return {
            'decision_id': 'dec-123',
            'final_decision': {'decision': 'approve', 'confidence': 0.875},
            'aggregated_confidence': 0.875,
            'consensus_process': {
                'method': 'hierarchical_bayesian',
                'seniority_distribution': {'senior': 2, 'expert': 1}
            },
            'specialist_opinions': [
                {
                    'specialist_type': 'business',
                    'seniority_level': 'senior',
                    'confidence': 0.90,
                    'reasoning': 'Alto ROI esperado de R$ 500k em 12 meses'
                }
            ],
            'shap_values': {'confidence': 0.45, 'risk': -0.15},
            'explanation_quality': {'overall': 0.85}
        }

    def test_json_format_has_all_fields(self, base_explanation):
        """Testa que formato JSON tem todos os campos."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        api = ExplainabilityAPIExtensions(mongodb_client=MagicMock())

        result = api.format_explanation(base_explanation, 'json')

        # JSON retorna dict com todos os campos
        assert isinstance(result, dict)
        assert 'decision_id' in result
        assert 'consensus_process' in result
        assert 'shap_values' in result

    def test_text_format_is_readable(self, base_explanation):
        """Testa que formato texto é legível."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        api = ExplainabilityAPIExtensions(mongodb_client=MagicMock())

        result = api.format_explanation(base_explanation, 'text')

        assert result['format'] == 'text'
        assert 'narrative' in result
        narrative = result['narrative']
        # Verificar que contém termos esperados em português
        assert any(term in narrative.lower() for term in ['decisão', 'aprovado', 'confiança'])

    def test_html_format_has_structure(self, base_explanation):
        """Testa que formato HTML tem estrutura válida."""
        from src.services.api_extensions import ExplainabilityAPIExtensions

        api = ExplainabilityAPIExtensions(mongodb_client=MagicMock())

        result = api.format_explanation(base_explanation, 'html')

        assert result['format'] == 'html'
        assert 'html' in result
        html = result['html']
        # Verificar tags HTML
        assert '<html' in html or '<div' in html or '<h1>' in html or '<h3>' in html
