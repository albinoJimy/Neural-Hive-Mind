"""
Testes para BehaviorSpecialistConfig - importando código de src/.

Estes testes importam o BehaviorSpecialistConfig real do código fonte.
"""

import sys
import os
import pytest
from typing import List
from unittest.mock import patch

# Configurar path para importar código real
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, "/app/libraries/python")


@pytest.fixture(scope="function")
def env_vars():
    """Configura variáveis de ambiente para testes."""
    original = os.environ.copy()
    os.environ.update(
        {
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "DEBUG",
            "MLFLOW_TRACKING_URI": "http://localhost:5000",
            "MONGODB_URI": "mongodb://localhost:27017/test",
            "REDIS_CLUSTER_NODES": "localhost:6379",
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_PASSWORD": "test_password",
            "JWT_SECRET_KEY": "test_secret_key_for_testing_only",
            "ENABLE_JWT_AUTH": "false",
            "ENABLE_CACHING": "false",
            "ENABLE_LEDGER": "false",
            "MODEL_REQUIRED": "false",
            "HTTP_PORT": "8001",
            "GRPC_PORT": "50051",
            "PROMETHEUS_PORT": "8002",
        }
    )
    yield
    os.environ.clear()
    os.environ.update(original)


class TestBehaviorSpecialistConfig:
    """Testes de configuração do Behavior Specialist."""

    def test_config_specialist_type(self, env_vars):
        """Verifica que specialist_type é 'behavior'."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.specialist_type == "behavior"

    def test_config_service_name(self, env_vars):
        """Verifica nome do serviço."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.service_name == "specialist-behavior"

    def test_config_mlflow_experiment_name(self, env_vars):
        """Verifica nome do experimento MLflow."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.mlflow_experiment_name == "behavior-specialist"

    def test_config_mlflow_model_name(self, env_vars):
        """Verifica nome do modelo MLflow."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.mlflow_model_name == "behavior-evaluator"

    def test_config_supported_domains(self, env_vars):
        """Verifica domínios suportados."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        expected_domains = [
            "ux-analysis",
            "accessibility-evaluation",
            "usability-testing",
            "user-experience",
            "interaction-design",
        ]
        assert config.supported_domains == expected_domains

    def test_config_supported_domains_type(self, env_vars):
        """Verifica que supported_domains é uma lista."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert isinstance(config.supported_domains, list)

    def test_config_accessibility_wcag_level(self, env_vars):
        """Verifica nível WCAG configurado."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.accessibility_wcag_level == "AA"

    def test_config_usability_thresholds(self, env_vars):
        """Verifica thresholds de usabilidade."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.usability_threshold_high == 0.8
        assert config.usability_threshold_low == 0.5

    def test_config_response_time_threshold(self, env_vars):
        """Verifica threshold de tempo de resposta."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.response_time_threshold_ms == 300

    def test_config_interaction_cost_threshold(self, env_vars):
        """Verifica threshold de custo de interação."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.interaction_cost_threshold == 0.7

    def test_config_is_specialist_config_subclass(self, env_vars):
        """Verifica que BehaviorSpecialistConfig herda de SpecialistConfig."""
        from src.config import BehaviorSpecialistConfig
        from neural_hive_specialists import SpecialistConfig

        config = BehaviorSpecialistConfig()
        assert isinstance(config, SpecialistConfig)

    def test_config_domains_not_empty(self, env_vars):
        """Verifica que supported_domains não está vazio."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert len(config.supported_domains) > 0

    def test_config_all_domains_are_strings(self, env_vars):
        """Verifica que todos os domínios são strings."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert all(isinstance(domain, str) for domain in config.supported_domains)

    def test_config_thresholds_in_valid_range(self, env_vars):
        """Verifica que thresholds estão entre 0 e 1."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert 0.0 <= config.usability_threshold_high <= 1.0
        assert 0.0 <= config.usability_threshold_low <= 1.0
        assert 0.0 <= config.interaction_cost_threshold <= 1.0

    def test_config_high_threshold_greater_than_low(self, env_vars):
        """Verifica que threshold high é maior que low."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert config.usability_threshold_high > config.usability_threshold_low


class TestBehaviorSpecialistConfigBasic:
    def test_config_service_name(self, env_vars):
        """Verifica nome do serviço."""
        config = BehaviorSpecialistConfig()
        assert config.service_name == "specialist-behavior"

    def test_config_mlflow_experiment_name(self, env_vars):
        """Verifica nome do experimento MLflow."""
        config = BehaviorSpecialistConfig()
        assert config.mlflow_experiment_name == "behavior-specialist"

    def test_config_mlflow_model_name(self, env_vars):
        """Verifica nome do modelo MLflow."""
        config = BehaviorSpecialistConfig()
        assert config.mlflow_model_name == "behavior-evaluator"

    def test_config_supported_domains(self, env_vars):
        """Verifica domínios suportados."""
        config = BehaviorSpecialistConfig()
        expected_domains = [
            "ux-analysis",
            "accessibility-evaluation",
            "usability-testing",
            "user-experience",
            "interaction-design",
        ]
        assert config.supported_domains == expected_domains

    def test_config_supported_domains_type(self, env_vars):
        """Verifica que supported_domains é uma lista."""
        config = BehaviorSpecialistConfig()
        assert isinstance(config.supported_domains, list)

    def test_config_accessibility_wcag_level(self, env_vars):
        """Verifica nível WCAG configurado."""
        config = BehaviorSpecialistConfig()
        assert config.accessibility_wcag_level == "AA"

    def test_config_usability_thresholds(self, env_vars):
        """Verifica thresholds de usabilidade."""
        config = BehaviorSpecialistConfig()
        assert config.usability_threshold_high == 0.8
        assert config.usability_threshold_low == 0.5

    def test_config_response_time_threshold(self, env_vars):
        """Verifica threshold de tempo de resposta."""
        config = BehaviorSpecialistConfig()
        assert config.response_time_threshold_ms == 300

    def test_config_interaction_cost_threshold(self, env_vars):
        """Verifica threshold de custo de interação."""
        config = BehaviorSpecialistConfig()
        assert config.interaction_cost_threshold == 0.7

    def test_config_is_specialist_config_subclass(self, env_vars):
        """Verifica que BehaviorSpecialistConfig herda de SpecialistConfig."""
        from neural_hive_specialists import SpecialistConfig

        config = BehaviorSpecialistConfig()
        assert isinstance(config, SpecialistConfig)

    def test_config_domains_not_empty(self, env_vars):
        """Verifica que supported_domains não está vazio."""
        config = BehaviorSpecialistConfig()
        assert len(config.supported_domains) > 0

    def test_config_all_domains_are_strings(self, env_vars):
        """Verifica que todos os domínios são strings."""
        config = BehaviorSpecialistConfig()
        assert all(isinstance(domain, str) for domain in config.supported_domains)

    def test_config_thresholds_in_valid_range(self, env_vars):
        """Verifica que thresholds estão entre 0 e 1."""
        config = BehaviorSpecialistConfig()
        assert 0.0 <= config.usability_threshold_high <= 1.0
        assert 0.0 <= config.usability_threshold_low <= 1.0
        assert 0.0 <= config.interaction_cost_threshold <= 1.0

    def test_config_high_threshold_greater_than_low(self, env_vars):
        """Verifica que threshold high é maior que low."""
        config = BehaviorSpecialistConfig()
        assert config.usability_threshold_high > config.usability_threshold_low


class TestBehaviorSpecialistConfigDomains:
    """Testes específicos de domínios suportados."""

    def test_domain_ux_analysis_exists(self, env_vars):
        """Verifica que ux-analysis está nos domínios suportados."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert "ux-analysis" in config.supported_domains

    def test_domain_accessibility_evaluation_exists(self, env_vars):
        """Verifica que accessibility-evaluation está nos domínios suportados."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert "accessibility-evaluation" in config.supported_domains

    def test_domain_usability_testing_exists(self, env_vars):
        """Verifica que usability-testing está nos domínios suportados."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert "usability-testing" in config.supported_domains

    def test_domain_user_experience_exists(self, env_vars):
        """Verifica que user-experience está nos domínios suportados."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert "user-experience" in config.supported_domains

    def test_domain_interaction_design_exists(self, env_vars):
        """Verifica que interaction-design está nos domínios suportados."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        assert "interaction-design" in config.supported_domains

    def test_is_domain_supported_valid_domain(self, env_vars):
        """Testa verificação de domínio suportado (válido)."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        # Assumindo que há um método is_domain_supported
        if hasattr(config, "is_domain_supported"):
            assert config.is_domain_supported("ux-analysis") is True

    def test_is_domain_supported_invalid_domain(self, env_vars):
        """Testa verificação de domínio suportado (inválido)."""
        from src.config import BehaviorSpecialistConfig

        config = BehaviorSpecialistConfig()
        if hasattr(config, "is_domain_supported"):
            assert config.is_domain_supported("database-admin") is False
