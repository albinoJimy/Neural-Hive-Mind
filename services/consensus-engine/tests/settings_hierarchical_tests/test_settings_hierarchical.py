"""
Testes unitários para configurações de senioridade hierárquica.

TDD: Testes escritos antes da implementação (RED phase).
"""

import pytest
from pydantic import ValidationError
import os


class TestHierarchicalConsensusSettings:
    """Testes das configurações de consenso hierárquico."""

    def test_default_enable_hierarchical_consensus_is_true(self):
        """Por padrão, consenso hierárquico deve estar habilitado."""
        # Arrange: Configurar environment variables mínimas
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        # Import depois de setar env vars
        from src.config.settings import Settings

        # Act: Criar Settings sem passar enable_hierarchical_consensus
        settings = Settings()

        # Assert: Deve vir True por padrão
        assert settings.enable_hierarchical_consensus is True

    def test_enable_hierarchical_consensus_can_be_disabled(self):
        """Feature flag permite desabilitar consenso hierárquico."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'
        os.environ['ENABLE_HIERARCHICAL_CONSENSUS'] = 'false'

        from src.config.settings import Settings

        settings = Settings()

        assert settings.enable_hierarchical_consensus is False

    def test_specialist_seniority_has_default_values(self):
        """Senioridade padrão deve ser configurada para todos os especialistas."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        from src.config.settings import Settings

        settings = Settings()

        # Verificar que todos os 5 especialistas têm senioridade padrão
        assert hasattr(settings, 'specialist_seniority')
        assert 'business' in settings.specialist_seniority
        assert 'technical' in settings.specialist_seniority
        assert 'behavior' in settings.specialist_seniority
        assert 'evolution' in settings.specialist_seniority
        assert 'architecture' in settings.specialist_seniority

    def test_specialist_seniority_accepts_valid_levels(self):
        """Deve aceitar níveis de senioridade válidos."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        from src.config.settings import Settings

        settings = Settings()

        # Todos os valores devem ser um dos níveis válidos
        valid_levels = {'trainee', 'junior', 'mid_level', 'senior', 'expert'}

        for specialist, level in settings.specialist_seniority.items():
            assert level in valid_levels, f"{specialist} tem nível inválido: {level}"

    def test_specialist_seniority_rejects_invalid_level(self):
        """Deve rejeitar nível de senioridade inválido."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'
        # Usar JSON para dict (Pydantic Settings suporta isso)
        os.environ['SPECIALIST_SENIORITY'] = '{"business": "invalid_level"}'

        from src.config.settings import Settings
        from pydantic import ValidationError

        # Deve levantar ValidationError ao criar Settings com nível inválido
        with pytest.raises(ValidationError) as exc_info:
            settings = Settings()

        # Verificar mensagem de erro contém informações úteis
        assert 'invalid_level' in str(exc_info.value)
        assert 'business' in str(exc_info.value)

    def test_default_seniority_level_exists(self):
        """Deve existir configuração de senioridade padrão."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        from src.config.settings import Settings

        settings = Settings()

        assert hasattr(settings, 'default_seniority_level')
        assert settings.default_seniority_level in {
            'trainee', 'junior', 'mid_level', 'senior', 'expert'
        }

    def test_domain_specialist_weights_exists(self):
        """Deve existir configuração de pesos por domínio."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        from src.config.settings import Settings

        settings = Settings()

        assert hasattr(settings, 'domain_specialist_weights')
        assert isinstance(settings.domain_specialist_weights, dict)

    def test_domain_specialist_weights_valid_range(self):
        """Pesos de domínio devem estar entre 0.0 e 1.0."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        from src.config.settings import Settings

        settings = Settings()

        for key, weight in settings.domain_specialist_weights.items():
            assert 0.0 <= weight <= 1.0, f"{key} tem peso inválido: {weight}"

    def test_architecture_specialist_has_highest_default_seniority(self):
        """Architecture specialist deve ter senioridade mais alta por padrão."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        from src.config.settings import Settings

        settings = Settings()

        # Architecture deve ser senior ou expert
        arch_seniority = settings.specialist_seniority.get('architecture')
        assert arch_seniority in {'senior', 'expert'}


class TestHierarchicalConsensusIntegration:
    """Testes de integração com HierarchicalWeightCalculator."""

    def test_settings_compatible_with_calculator(self):
        """Settings deve ser compatível com HierarchicalWeightCalculator."""
        os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092'
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        os.environ['REDIS_CLUSTER_NODES'] = 'localhost:6379'

        from src.config.settings import Settings
        import importlib.util
        from pathlib import Path
        from unittest.mock import Mock, MagicMock
        from enum import Enum

        # Mock neural_hive_domain
        class UnifiedDomain(str, Enum):
            BUSINESS = 'BUSINESS'
            TECHNICAL = 'TECHNICAL'
            ARCHITECTURE = 'ARCHITECTURE'

        import sys
        sys.modules['neural_hive_domain'] = MagicMock()
        sys.modules['neural_hive_domain'].UnifiedDomain = UnifiedDomain

        # Load seniority
        seniority_path = Path('src/models/seniority.py')
        spec = importlib.util.spec_from_file_location('seniority', seniority_path)
        seniority = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seniority)

        sys.modules['src.models.seniority'] = seniority

        # Load hierarchical_weights
        hw_path = Path('src/services/hierarchical_weights.py')
        spec2 = importlib.util.spec_from_file_location('hierarchical_weights', hw_path)
        hw = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(hw)

        # Act: Criar Settings e Calculator
        settings = Settings()
        calculator = hw.HierarchicalWeightCalculator(settings)

        # Assert: Calculator deve inicializar sem erros
        assert calculator is not None
        assert calculator.config == settings
        assert calculator.config.enable_hierarchical_consensus == settings.enable_hierarchical_consensus
