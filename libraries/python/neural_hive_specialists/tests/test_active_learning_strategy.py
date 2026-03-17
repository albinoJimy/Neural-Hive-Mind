"""
Testes para ActiveLearningStrategy.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-17-active-learning-feedback/
"""

import pytest
from unittest.mock import Mock
from datetime import datetime

from neural_hive_specialists.feedback.active_learning.learning_strategy import (
    ActiveLearningStrategy,
    InformationValue,
    DEFAULT_CONFIDENCE_WEIGHT,
    DEFAULT_REPRESENTATION_WEIGHT,
    DEFAULT_NOVELTY_WEIGHT
)


class TestActiveLearningStrategy:
    """Testes do ActiveLearningStrategy."""

    @pytest.fixture
    def strategy(self):
        """Instância padrão da estratégia."""
        return ActiveLearningStrategy()

    @pytest.fixture
    def strategy_custom_weights(self):
        """Instância com pesos customizados."""
        return ActiveLearningStrategy(
            confidence_weight=0.6,
            representation_weight=0.3,
            novelty_weight=0.1
        )

    def test_strategy_initialization(self, strategy):
        """Testa que a estratégia pode ser inicializada."""
        assert strategy.confidence_weight == DEFAULT_CONFIDENCE_WEIGHT
        assert strategy.representation_weight == DEFAULT_REPRESENTATION_WEIGHT
        assert strategy.novelty_weight == DEFAULT_NOVELTY_WEIGHT

    def test_strategy_custom_weights(self, strategy_custom_weights):
        """Testa inicialização com pesos customizados."""
        assert strategy_custom_weights.confidence_weight == 0.6
        assert strategy_custom_weights.representation_weight == 0.3
        assert strategy_custom_weights.novelty_weight == 0.1

    def test_calculate_information_value_high_uncertainty(self, strategy):
        """Testa cálculo com alta incerteza (baixa confiança)."""
        value = strategy.calculate_information_value({
            'confidence': 0.3,
            'representation': 0.5,
            'domain_novelty': 0.5
        })

        # Incerteza alta (1 - 0.3 = 0.7) deve aumentar valor
        assert value > 0.5
        assert value <= 1.0

    def test_calculate_information_value_low_uncertainty(self, strategy):
        """Testa cálculo com baixa incerteza (alta confiança)."""
        value = strategy.calculate_information_value({
            'confidence': 0.95,
            'representation': 0.5,
            'domain_novelty': 0.5
        })

        # Incerteza baixa (1 - 0.95 = 0.05) deve diminuir valor
        assert value < 0.5

    def test_calculate_information_value_low_representation(self, strategy):
        """Testa cálculo com baixa representação."""
        value = strategy.calculate_information_value({
            'confidence': 0.5,
            'representation': 0.05,  # Muito baixo
            'domain_novelty': 0.5
        })

        # Baixa representação deve aumentar valor
        assert value > 0.4

    def test_calculate_information_value_high_novelty(self, strategy):
        """Testa cálculo com alto novidade de domínio."""
        value = strategy.calculate_information_value({
            'confidence': 0.5,
            'representation': 0.5,
            'domain_novelty': 1.0  # Domínio completamente novo
        })

        # Alta novidade deve aumentar valor
        assert value > 0.5

    def test_calculate_information_value_all_low(self, strategy):
        """Testa cálculo com todos os fatores baixos."""
        value = strategy.calculate_information_value({
            'confidence': 0.95,  # Baixa incerteza
            'representation': 1.0,  # Alta representação
            'domain_novelty': 0.0  # Baixa novidade
        })

        # Todos baixos = valor informacional muito baixo
        assert value < 0.2

    def test_calculate_information_value_all_high(self, strategy):
        """Testa cálculo com todos os fatores altos."""
        value = strategy.calculate_information_value({
            'confidence': 0.1,  # Alta incerteza
            'representation': 0.0,  # Baixa representação
            'domain_novelty': 1.0  # Alta novidade
        })

        # Todos altos = valor informacional muito alto
        assert value > 0.8

    def test_calculate_information_value_returns_float(self, strategy):
        """Testa que retorna float entre 0 e 1."""
        value = strategy.calculate_information_value({
            'confidence': 0.5,
            'representation': 0.5,
            'domain_novelty': 0.5
        })

        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0

    def test_should_collect_feedback_with_high_value(self, strategy):
        """Testa que deve coletar feedback com valor alto."""
        case = {
            'confidence': 0.2,
            'representation': 0.1,
            'domain_novelty': 0.8
        }

        # Valor alto deve retornar True
        assert strategy.should_collect_feedback(case) is True

    def test_should_collect_feedback_with_low_value(self, strategy):
        """Testa que NÃO deve coletar feedback com valor baixo."""
        case = {
            'confidence': 0.95,
            'representation': 0.9,
            'domain_novelty': 0.0
        }

        # Valor baixo deve retornar False
        assert strategy.should_collect_feedback(case) is False

    def test_should_collect_feedback_respects_threshold(self, strategy):
        """Testa que respeita threshold configurado."""
        strategy.threshold = 0.8  # Aumentar threshold

        case = {
            'confidence': 0.5,
            'representation': 0.5,
            'domain_novelty': 0.5
        }

        # Valor médio (0.5) < threshold (0.8) = False
        assert strategy.should_collect_feedback(case) is False

    def test_calculate_information_value_weights(self, strategy_custom_weights):
        """Testa que pesos customizados afetam cálculo."""
        # Confiança tem peso maior (0.6)
        case_low_conf = {
            'confidence': 0.9,
            'representation': 0.0,
            'domain_novelty': 0.0
        }
        case_high_conf = {
            'confidence': 0.1,
            'representation': 0.0,
            'domain_novelty': 0.0
        }

        value_low_conf = strategy_custom_weights.calculate_information_value(case_low_conf)
        value_high_conf = strategy_custom_weights.calculate_information_value(case_high_conf)

        # Alta incerteza (baixa confiança) deve ter valor maior
        assert value_high_conf > value_low_conf

    def test_calculate_from_prediction(self, strategy):
        """Testa cálculo a partir de objeto de predição."""
        prediction = {
            'decision': 'reject',
            'confidence': 0.45,
            'nlp_features': {'primary_domain': 'security'}
        }

        # Dataset stats simulados
        dataset_stats = {
            'class_distribution': {'approve': 0.9, 'reject': 0.1},
            'domain_distribution': {
                'technical': 0.5,
                'business': 0.4,
                'security': 0.1  # Security é raro
            }
        }

        value = strategy.calculate_from_prediction(
            prediction,
            dataset_stats
        )

        assert 0.0 <= value <= 1.0
        # Security é raro (10%) + baixa confiança = valor alto
        assert value > 0.3

    def test_calculate_from_prediction_missing_fields(self, strategy):
        """Testa cálculo com campos faltantes."""
        prediction = {'decision': 'approve'}  # Sem confiança ou features

        dataset_stats = {
            'class_distribution': {'approve': 0.5, 'reject': 0.5}
        }

        value = strategy.calculate_from_prediction(
            prediction,
            dataset_stats
        )

        # Deve usar defaults e não crashar
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0

    def test_calculate_from_prediction_unknown_domain(self, strategy):
        """Testa cálculo com domínio desconhecido (alta novidade)."""
        prediction = {
            'decision': 'approve',
            'confidence': 0.5,
            'nlp_features': {'primary_domain': 'unknown_domain'}
        }

        dataset_stats = {
            'class_distribution': {'approve': 0.5, 'reject': 0.5},
            'domain_distribution': {
                'technical': 0.5,
                'business': 0.5
                # unknown_domain não está presente
            }
        }

        value = strategy.calculate_from_prediction(
            prediction,
            dataset_stats
        )

        # Domínio desconhecido = novidade máxima = valor alto
        assert value > 0.5


class TestInformationValue:
    """Testes do modelo InformationValue."""

    def test_information_value_creation(self):
        """Testa criação de InformationValue."""
        value = InformationValue(
            value=0.75,
            confidence=0.3,
            representation=0.1,
            domain_novelty=0.9,
            reason='High uncertainty, low representation'
        )

        assert value.value == 0.75
        assert value.confidence == 0.3
        assert value.reason == 'High uncertainty, low representation'

    def test_information_value_to_dict(self):
        """Testa conversão para dicionário."""
        value = InformationValue(
            value=0.75,
            confidence=0.3,
            representation=0.1,
            domain_novelty=0.9
        )

        data = value.to_dict()

        assert data['value'] == 0.75
        assert data['confidence'] == 0.3
        assert 'reason' in data

    def test_information_value_reason_generation(self):
        """Testa geração automática de razão."""
        value = InformationValue(
            value=0.85,
            confidence=0.2,
            representation=0.05,
            domain_novelty=1.0
        )

        # Razão deve ser gerada automaticamente
        assert value.reason
        assert 'incerteza' in value.reason.lower() or 'uncertainty' in value.reason.lower()
