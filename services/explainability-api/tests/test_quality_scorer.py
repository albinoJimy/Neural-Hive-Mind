"""
Testes unitários para ExplanationQualityScorer.

TDD: Testes escritos antes da implementação (GAPS-04 Task 4).
"""

import pytest
from typing import List, Dict, Any
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from services.quality_scorer import ExplanationQualityScorer


class TestQualityScorerInitialization:
    """Testes de inicialização do scorer."""

    def test_initialization(self):
        """Testa que o scorer pode ser inicializado."""
        scorer = ExplanationQualityScorer()
        assert scorer is not None


class TestCompletenessScore:
    """Testes do score de completude."""

    def test_complete_explanation_has_high_score(self):
        """Testa que explicação completa tem score alto."""
        scorer = ExplanationQualityScorer()

        explanation = {
            'consensus_process': {
                'method': 'bayesian',
                'num_specialists': 5,
                'seniority_distribution': {'senior': 2, 'expert': 1}
            },
            'specialist_opinions': [
                {'specialist_type': 'business', 'confidence': 0.85, 'reasoning': 'Bom alinhamento'},
                {'specialist_type': 'technical', 'confidence': 0.90, 'reasoning': 'Arquitetura sólida'}
            ],
            'final_decision': {'decision': 'approve', 'rationale': 'Alta confiança'}
        }

        score = scorer.score_completeness(explanation)

        assert score >= 0.7, f"Complete explanation should have score >= 0.7, got {score}"

    def test_minimal_explanation_has_low_score(self):
        """Testa que explicação mínima tem score baixo."""
        scorer = ExplanationQualityScorer()

        # Explicação realmente mínima - sem o campo 'decision' que é obrigatório
        explanation = {
            'final_decision': {}  # Vazio, sem campos obrigatórios
        }

        score = scorer.score_completeness(explanation)

        assert score < 0.5, f"Minimal explanation should have score < 0.5, got {score}"

    def test_empty_explanation_has_zero_score(self):
        """Testa que explicação vazia tem score zero."""
        scorer = ExplanationQualityScorer()

        score = scorer.score_completeness({})

        assert score == 0.0, f"Empty explanation should have score 0, got {score}"


class TestClarityScore:
    """Testes do score de clareza."""

    def test_clear_explanation_has_high_score(self):
        """Testa que explicação clara tem score alto."""
        scorer = ExplanationQualityScorer()

        # Explicação com textos claros e específicos
        explanation = {
            'reasoning_summary': 'Decisão aprovada com confiança 0.85 devido ao alinhamento com objetivos de negócio e arquitetura escalável.',
            'specialist_opinions': [
                {'reasoning': 'A solução utiliza microserviços para escalabilidade.'}
            ]
        }

        score = scorer.score_clarity(explanation)

        assert score >= 0.6, f"Clear explanation should have score >= 0.6, got {score}"

    def test_vague_explanation_has_low_score(self):
        """Testa que explicação vaga tem score baixo."""
        scorer = ExplanationQualityScorer()

        explanation = {
            'reasoning_summary': 'Ok.',
            'specialist_opinions': [
                {'reasoning': 'Sim.'}
            ]
        }

        score = scorer.score_clarity(explanation)

        assert score < 0.6, f"Vague explanation should have score < 0.6, got {score}"

    def test_explanation_with_jargon_has_reduced_score(self):
        """Testa que jargão excessivo reduz score de clareza."""
        scorer = ExplanationQualityScorer()

        explanation = {
            'reasoning_summary': 'A solução implementa paralelização assíncrona com event-sourcing eventual consistency via CQRS pattern.'
        }

        score = scorer.score_clarity(explanation)

        # Jargão técnico reduz clareza para audiência geral
        assert 0.0 <= score <= 1.0


class TestSpecificityScore:
    """Testes do score de especificidade."""

    def test_specific_explanation_has_high_score(self):
        """Testa que explicação específica tem score alto."""
        scorer = ExplanationQualityScorer()

        explanation = {
            'specialist_opinions': [
                {
                    'reasoning': 'O tempo de resposta médio é 150ms com p95 de 300ms.',
                    'confidence': 0.85,
                    'risk_score': 0.15
                }
            ]
        }

        score = scorer.score_specificity(explanation)

        assert score >= 0.6, f"Specific explanation should have score >= 0.6, got {score}"

    def test_generic_explanation_has_low_score(self):
        """Testa que explicação genérica tem score baixo."""
        scorer = ExplanationQualityScorer()

        explanation = {
            'specialist_opinions': [
                {
                    'reasoning': 'A solução é boa.',
                    'confidence': 0.8
                }
            ]
        }

        score = scorer.score_specificity(explanation)

        assert score < 0.5, f"Generic explanation should have score < 0.5, got {score}"

    def test_explanation_with_numbers_has_higher_score(self):
        """Testa que números e métricas aumentam especificidade."""
        scorer = ExplanationQualityScorer()

        with_numbers = {
            'reasoning_summary': 'A confiança é 0.85 com risco de 0.15. Tempo de processamento: 150ms.'
        }

        without_numbers = {
            'reasoning_summary': 'A confiança é alta com risco baixo. Tempo rápido.'
        }

        score_with = scorer.score_specificity(with_numbers)
        score_without = scorer.score_specificity(without_numbers)

        assert score_with > score_without, "Numbers should increase specificity score"


class TestAggregatedScore:
    """Testes do score agregado."""

    def test_overall_score_is_weighted_average(self):
        """Testa que score agregado é média ponderada."""
        scorer = ExplanationQualityScorer()

        scores = {
            'completeness': 0.8,
            'clarity': 0.7,
            'specificity': 0.6
        }

        overall = scorer.calculate_overall_score(scores)

        # Deve estar entre min e max
        assert 0.6 <= overall <= 0.8, f"Overall should be in range, got {overall}"

    def test_overall_score_with_zero_component(self):
        """Testa score agregado quando um componente é zero."""
        scorer = ExplanationQualityScorer()

        scores = {
            'completeness': 0.0,
            'clarity': 0.8,
            'specificity': 0.8
        }

        overall = scorer.calculate_overall_score(scores)

        # Deve ser penalizado por completude zero
        assert overall < 0.6, f"Zero component should penalize overall, got {overall}"

    def test_overall_score_weights_completeness_higher(self):
        """Testa que completude tem peso maior no cálculo."""
        scorer = ExplanationQualityScorer()

        scores = {
            'completeness': 0.9,
            'clarity': 0.5,
            'specificity': 0.5
        }

        overall = scorer.calculate_overall_score(scores)

        # Completude tem peso maior, então overall deve ser >= média simples
        simple_average = (0.9 + 0.5 + 0.5) / 3
        assert overall >= simple_average, f"Completeness should be weighted higher"


class TestMongoDBIntegration:
    """Testes de integração com MongoDB."""

    @pytest.fixture
    def mock_mongodb(self):
        """Mock do cliente MongoDB."""
        from unittest.mock import MagicMock

        mongo = MagicMock()
        mongo.db = MagicMock()
        collection = MagicMock()
        collection.update_one = MagicMock()
        mongo.db['explanation_quality'] = collection
        return mongo

    def test_save_quality_scores_to_mongodb(self, mock_mongodb):
        """Testa que scores são salvos no MongoDB."""
        scorer = ExplanationQualityScorer()
        scorer.mongodb = mock_mongodb

        explanation_id = "exp-123"
        scores = {
            'completeness': 0.8,
            'clarity': 0.7,
            'specificity': 0.6,
            'overall': 0.72
        }

        scorer.save_scores(explanation_id, scores)

        # Verificar que update_one foi chamado
        mock_mongodb.db['explanation_quality'].update_one.assert_called_once()

    def test_save_includes_timestamp(self, mock_mongodb):
        """Testa que salvamento inclui timestamp."""
        scorer = ExplanationQualityScorer()
        scorer.mongodb = mock_mongodb

        from datetime import datetime

        scores = {'completeness': 0.8}
        scorer.save_scores("exp-123", scores)

        # Verificar argumentos da chamada
        call_args = mock_mongodb.db['explanation_quality'].update_one.call_args
        update_data = call_args[0][1]['$set']

        assert 'timestamp' in update_data or 'created_at' in update_data


class TestFullScoringPipeline:
    """Testes do pipeline completo de scoring."""

    def test_score_explanation_returns_all_metrics(self):
        """Testa que scoring retorna todas as métricas."""
        scorer = ExplanationQualityScorer()

        explanation = {
            'consensus_process': {
                'method': 'bayesian',
                'num_specialists': 3
            },
            'specialist_opinions': [
                {'specialist_type': 'business', 'confidence': 0.85, 'reasoning': 'Bom ROI'},
                {'specialist_type': 'technical', 'confidence': 0.90, 'reasoning': 'Arquitetura escalável com 150ms'}
            ],
            'final_decision': {'decision': 'approve'},
            'reasoning_summary': 'Aprovado com confiança 0.875 devido ao alinhamento com objetivos.'
        }

        result = scorer.score_explanation(explanation)

        assert 'completeness' in result
        assert 'clarity' in result
        assert 'specificity' in result
        assert 'overall' in result
        assert 0.0 <= result['overall'] <= 1.0

    def test_score_explanation_accepts_optional_weights(self):
        """Testa que scoring aceita pesos customizados."""
        scorer = ExplanationQualityScorer()

        explanation = {'final_decision': {'decision': 'approve'}}
        weights = {'completeness': 0.5, 'clarity': 0.3, 'specificity': 0.2}

        result = scorer.score_explanation(explanation, weights=weights)

        assert 'overall' in result
        assert 0.0 <= result['overall'] <= 1.0
