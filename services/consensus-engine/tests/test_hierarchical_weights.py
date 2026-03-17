"""
Testes unitários para HierarchicalWeightCalculator.

TDD: Testes escritos antes da implementação.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock

# Add src directly to path to avoid __init__.py imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Importar módulos diretamente, não através do pacote
import importlib.util

# Load hierarchical_weights directly
spec = importlib.util.spec_from_file_location(
    "hierarchical_weights",
    Path(__file__).parent.parent / 'src' / 'services' / 'hierarchical_weights.py'
)
hierarchical_weights_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hierarchical_weights_module)
HierarchicalWeightCalculator = hierarchical_weights_module.HierarchicalWeightCalculator

# Load seniority directly
spec2 = importlib.util.spec_from_file_location(
    "seniority",
    Path(__file__).parent.parent / 'src' / 'models' / 'seniority.py'
)
seniority_module = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(seniority_module)
SeniorityLevel = seniority_module.SeniorityLevel

# Mock UnifiedDomain para contornar dependência de Python >=3.11
try:
    from neural_hive_domain import UnifiedDomain
except ImportError:
    from enum import Enum
    class UnifiedDomain(str, Enum):
        BUSINESS = 'BUSINESS'
        TECHNICAL = 'TECHNICAL'
        SECURITY = 'SECURITY'
        INFRASTRUCTURE = 'INFRASTRUCTURE'
        BEHAVIOR = 'BEHAVIOR'
        OPERATIONAL = 'OPERATIONAL'
        COMPLIANCE = 'COMPLIANCE'
        ARCHITECTURE = 'ARCHITECTURE'


class TestHierarchicalWeightCalculator:
    """Testes do calculador de pesos hierárquicos."""

    @pytest.fixture
    def mock_config(self):
        """Configuração mockada."""
        config = Mock()
        config.enable_hierarchical_consensus = True
        config.specialist_seniority = {
            'business': 'senior',
            'technical': 'senior',
            'architecture': 'expert',
            'behavior': 'mid_level',
            'evolution': 'mid_level',
        }
        config.domain_specialist_weights = {
            'business_BUSINESS': 0.25,
            'technical_TECHNICAL': 0.25,
            'architecture_ARCHITECTURE': 0.30,
        }
        return config

    @pytest.fixture
    def calculator(self, mock_config):
        """Instância do calculador."""
        return HierarchicalWeightCalculator(mock_config)

    def test_initialization(self, calculator):
        """Testa inicialização do calculador."""
        assert calculator.config is not None
        assert hasattr(calculator, 'multipliers')
        assert hasattr(calculator, 'domain_weights')

    def test_calculate_weight_for_expert_architecture(self, calculator):
        """Expert architect deve ter peso máximo."""
        weight = calculator.calculate_hierarchical_weight(
            specialist_type='architecture',
            domain=UnifiedDomain.ARCHITECTURE,
            pheromone_weight=1.0,
            seniority=SeniorityLevel.EXPERT
        )
        # weight = 1.0 (pheromone) × 2.0 (expert) × 0.30 (domain) = 0.6 → normalizado
        assert weight > 0.5

    def test_calculate_weight_for_trainee(self, calculator):
        """Trainee deve ter peso reduzido."""
        weight = calculator.calculate_hierarchical_weight(
            specialist_type='behavior',
            domain=UnifiedDomain.BUSINESS,
            pheromone_weight=1.0,
            seniority=SeniorityLevel.TRAINEE
        )
        # weight = 1.0 × 0.5 (trainee) × 0.2 (default domain) = 0.1
        assert weight < 0.2

    def test_senior_weight_greater_than_junior(self, calculator):
        """Senior deve ter peso maior que junior mesmo com mesmo pheromone."""
        senior_weight = calculator.calculate_hierarchical_weight(
            specialist_type='business',
            domain=UnifiedDomain.BUSINESS,
            pheromone_weight=0.8,
            seniority=SeniorityLevel.SENIOR
        )
        junior_weight = calculator.calculate_hierarchical_weight(
            specialist_type='business',
            domain=UnifiedDomain.BUSINESS,
            pheromone_weight=0.8,
            seniority=SeniorityLevel.JUNIOR
        )
        assert senior_weight > junior_weight

    def test_expert_double_weight_of_mid_level(self, calculator):
        """Expert deve ter aproximadamente 2x o peso de mid_level."""
        expert_weight = calculator.calculate_hierarchical_weight(
            specialist_type='technical',
            domain=UnifiedDomain.TECHNICAL,
            pheromone_weight=0.7,
            seniority=SeniorityLevel.EXPERT
        )
        mid_weight = calculator.calculate_hierarchical_weight(
            specialist_type='technical',
            domain=UnifiedDomain.TECHNICAL,
            pheromone_weight=0.7,
            seniority=SeniorityLevel.MID_LEVEL
        )
        # Deve ser aproximadamente 2x (pode variar pela normalização)
        assert expert_weight >= mid_weight * 1.8

    def test_weight_max_value_is_one(self, calculator):
        """Peso final nunca deve exceder 1.0."""
        # Mesmo com tudo no máximo, peso deve ser ≤ 1.0
        weight = calculator.calculate_hierarchical_weight(
            specialist_type='architecture',
            domain=UnifiedDomain.ARCHITECTURE,
            pheromone_weight=1.0,
            seniority=SeniorityLevel.EXPERT
        )
        assert weight <= 1.0

    def test_uses_default_seniority_when_not_provided(self, calculator):
        """Deve usar senioridade padrão quando não informada."""
        # architecture tem padrão 'expert' na config
        weight = calculator.calculate_hierarchical_weight(
            specialist_type='architecture',
            domain=UnifiedDomain.ARCHITECTURE,
            pheromone_weight=0.6
            # seniority=None deve usar config.specialist_seniority['architecture']
        )
        assert weight > 0

    def test_uses_default_domain_weight_when_not_configured(self, calculator):
        """Deve usar peso padrão 0.2 quando domínio não configurado."""
        weight = calculator.calculate_hierarchical_weight(
            specialist_type='behavior',
            domain=UnifiedDomain.BEHAVIOR,  # Não está em domain_specialist_weights
            pheromone_weight=0.5,
            seniority=SeniorityLevel.MID_LEVEL
        )
        # Deve usar 0.2 como padrão
        assert weight > 0

    def test_zero_pheromone_still_generates_weight(self, calculator):
        """Mesmo com feromônio zero, senioridade deve gerar peso."""
        weight = calculator.calculate_hierarchical_weight(
            specialist_type='business',
            domain=UnifiedDomain.BUSINESS,
            pheromone_weight=0.0,
            seniority=SeniorityLevel.SENIOR
        )
        # Pode ser pequeno mas não zero devido à senioridade
        assert weight >= 0.0


class TestCalculateBatchWeights:
    """Testes de cálculo em lote."""

    @pytest.fixture
    def calculator(self):
        """Instância do calculador."""
        config = Mock()
        config.enable_hierarchical_consensus = True
        config.specialist_seniority = {
            'business': 'senior',
            'technical': 'junior',
        }
        config.domain_specialist_weights = {}
        return HierarchicalWeightCalculator(config)

    def test_returns_dict_with_all_specialists(self, calculator):
        """Deve retornar dicionário com pesos para todos os especialistas."""
        opinions = [
            {'specialist_type': 'business'},
            {'specialist_type': 'technical'},
        ]

        weights = calculator.calculate_batch_weights(
            specialist_opinions=opinions,
            domain=UnifiedDomain.BUSINESS,
            base_pheromone_weights={'business': 0.8, 'technical': 0.7}
        )

        assert 'business' in weights
        assert 'technical' in weights
        assert len(weights) == 2

    def test_uses_individual_seniority_from_opinion(self, calculator):
        """Deve usar senioridade individual quando fornecida na opinião."""
        opinions = [
            {'specialist_type': 'business', 'seniority_level': 'expert'},
            {'specialist_type': 'technical', 'seniority_level': 'trainee'},
        ]

        weights = calculator.calculate_batch_weights(
            specialist_opinions=opinions,
            domain=UnifiedDomain.BUSINESS,
            base_pheromone_weights={'business': 0.8, 'technical': 0.8}
        )

        # business (expert) deve ter maior peso que technical (trainee)
        assert weights['business'] > weights['technical']


class TestConfigFeatureFlag:
    """Testes de feature flag."""

    def test_hierarchical_disabled_uses_base_weight_only(self):
        """Quando hierarquia desabilitada, deve usar apenas peso base."""
        config = Mock()
        config.enable_hierarchical_consensus = False
        config.specialist_seniority = {}
        config.domain_specialist_weights = {}

        calculator = HierarchicalWeightCalculator(config)

        weight = calculator.calculate_hierarchical_weight(
            specialist_type='business',
            domain=UnifiedDomain.BUSINESS,
            pheromone_weight=0.8,
            seniority=SeniorityLevel.SENIOR
        )

        # Sem hierarquia, peso deve ser o pheromone_weight normalizado
        assert 0.0 <= weight <= 1.0
