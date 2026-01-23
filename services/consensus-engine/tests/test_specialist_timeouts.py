"""
Testes para configuração de timeouts específicos por specialist.

Valida que o sistema suporta timeouts configuráveis por specialist type
com fallback para o timeout global (grpc_timeout_ms).
"""

import pytest
from unittest.mock import patch, MagicMock


class TestSpecialistTimeouts:
    """Testes para configuração de timeouts específicos por specialist"""

    def test_get_specialist_timeout_with_specific_config(self):
        """Deve retornar timeout específico quando configurado"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=30000,
            specialist_business_timeout_ms=120000
        )

        assert settings.get_specialist_timeout_ms('business') == 120000
        assert settings.get_specialist_timeout_ms('technical') == 30000  # Fallback

    def test_get_specialist_timeout_fallback_to_global(self):
        """Deve usar timeout global quando específico não configurado"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=60000
        )

        for specialist_type in ['business', 'technical', 'behavior', 'evolution', 'architecture']:
            assert settings.get_specialist_timeout_ms(specialist_type) == 60000

    def test_get_specialist_timeout_all_configured(self):
        """Deve retornar timeout específico para cada specialist quando todos configurados"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=30000,
            specialist_business_timeout_ms=120000,
            specialist_technical_timeout_ms=40000,
            specialist_behavior_timeout_ms=50000,
            specialist_evolution_timeout_ms=60000,
            specialist_architecture_timeout_ms=70000
        )

        assert settings.get_specialist_timeout_ms('business') == 120000
        assert settings.get_specialist_timeout_ms('technical') == 40000
        assert settings.get_specialist_timeout_ms('behavior') == 50000
        assert settings.get_specialist_timeout_ms('evolution') == 60000
        assert settings.get_specialist_timeout_ms('architecture') == 70000

    def test_specialist_timeout_validation_positive(self):
        """Deve validar que timeout específico é positivo"""
        from src.config.settings import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(
                kafka_bootstrap_servers='localhost:9092',
                mongodb_uri='mongodb://localhost:27017',
                redis_cluster_nodes='localhost:6379',
                grpc_timeout_ms=30000,
                specialist_business_timeout_ms=0
            )

    def test_specialist_timeout_from_env(self):
        """Deve carregar timeout específico de variável de ambiente"""
        from src.config.settings import Settings

        with patch.dict('os.environ', {
            'KAFKA_BOOTSTRAP_SERVERS': 'localhost:9092',
            'MONGODB_URI': 'mongodb://localhost:27017',
            'REDIS_CLUSTER_NODES': 'localhost:6379',
            'GRPC_TIMEOUT_MS': '30000',
            'SPECIALIST_BUSINESS_TIMEOUT_MS': '120000'
        }):
            settings = Settings()
            assert settings.get_specialist_timeout_ms('business') == 120000
            assert settings.get_specialist_timeout_ms('technical') == 30000  # Fallback

    def test_specialist_timeout_partial_configuration(self):
        """Deve permitir configuração parcial de timeouts"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=30000,
            specialist_business_timeout_ms=120000,
            specialist_architecture_timeout_ms=90000
        )

        # Configurados explicitamente
        assert settings.get_specialist_timeout_ms('business') == 120000
        assert settings.get_specialist_timeout_ms('architecture') == 90000

        # Fallback para global
        assert settings.get_specialist_timeout_ms('technical') == 30000
        assert settings.get_specialist_timeout_ms('behavior') == 30000
        assert settings.get_specialist_timeout_ms('evolution') == 30000

    def test_specialist_timeout_unknown_type_fallback(self):
        """Deve usar fallback para specialist type desconhecido"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=30000,
            specialist_business_timeout_ms=120000
        )

        # Specialist type desconhecido usa fallback
        assert settings.get_specialist_timeout_ms('unknown') == 30000
        assert settings.get_specialist_timeout_ms('custom') == 30000
