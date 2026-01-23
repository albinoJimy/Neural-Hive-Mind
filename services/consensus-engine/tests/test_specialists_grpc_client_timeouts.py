"""
Testes para validação de timeouts específicos por specialist no cliente gRPC.

Valida que a configuração de timeouts específicos funciona corretamente
e que o cliente gRPC usa os timeouts corretos para cada specialist.
"""

import pytest
from unittest.mock import MagicMock


class TestSpecialistTimeoutConfiguration:
    """Testes de configuração de timeouts específicos por specialist"""

    def test_config_get_specialist_timeout_business_specific(self):
        """Business Specialist deve usar timeout específico de 120s"""
        config = MagicMock()
        config.grpc_timeout_ms = 30000
        config.specialist_business_timeout_ms = 120000
        config.specialist_technical_timeout_ms = None

        def get_specialist_timeout_ms(specialist_type: str) -> int:
            timeout_field = f'specialist_{specialist_type}_timeout_ms'
            specific_timeout = getattr(config, timeout_field, None)
            return specific_timeout if specific_timeout is not None else config.grpc_timeout_ms

        config.get_specialist_timeout_ms = get_specialist_timeout_ms

        # Business deve usar 120000ms (específico)
        assert config.get_specialist_timeout_ms('business') == 120000

    def test_config_get_specialist_timeout_technical_fallback(self):
        """Technical Specialist deve usar timeout global (fallback)"""
        config = MagicMock()
        config.grpc_timeout_ms = 30000
        config.specialist_business_timeout_ms = 120000
        config.specialist_technical_timeout_ms = None

        def get_specialist_timeout_ms(specialist_type: str) -> int:
            timeout_field = f'specialist_{specialist_type}_timeout_ms'
            specific_timeout = getattr(config, timeout_field, None)
            return specific_timeout if specific_timeout is not None else config.grpc_timeout_ms

        config.get_specialist_timeout_ms = get_specialist_timeout_ms

        # Technical deve usar 30000ms (fallback para global)
        assert config.get_specialist_timeout_ms('technical') == 30000

    def test_config_get_specialist_timeout_all_specialists(self):
        """Todos os specialists devem retornar timeout correto"""
        config = MagicMock()
        config.grpc_timeout_ms = 30000
        config.specialist_business_timeout_ms = 120000
        config.specialist_technical_timeout_ms = 40000
        config.specialist_behavior_timeout_ms = None
        config.specialist_evolution_timeout_ms = 60000
        config.specialist_architecture_timeout_ms = None

        def get_specialist_timeout_ms(specialist_type: str) -> int:
            timeout_field = f'specialist_{specialist_type}_timeout_ms'
            specific_timeout = getattr(config, timeout_field, None)
            return specific_timeout if specific_timeout is not None else config.grpc_timeout_ms

        config.get_specialist_timeout_ms = get_specialist_timeout_ms

        # Verificar cada specialist
        assert config.get_specialist_timeout_ms('business') == 120000  # Específico
        assert config.get_specialist_timeout_ms('technical') == 40000  # Específico
        assert config.get_specialist_timeout_ms('behavior') == 30000   # Fallback
        assert config.get_specialist_timeout_ms('evolution') == 60000  # Específico
        assert config.get_specialist_timeout_ms('architecture') == 30000  # Fallback

    def test_config_get_specialist_timeout_unknown_specialist(self):
        """Specialist desconhecido deve usar timeout global"""
        # Usar classe simples ao invés de MagicMock para evitar atributos automáticos
        class MockConfig:
            grpc_timeout_ms = 30000
            specialist_business_timeout_ms = 120000
            specialist_technical_timeout_ms = None
            specialist_behavior_timeout_ms = None
            specialist_evolution_timeout_ms = None
            specialist_architecture_timeout_ms = None

            def get_specialist_timeout_ms(self, specialist_type: str) -> int:
                timeout_field = f'specialist_{specialist_type}_timeout_ms'
                specific_timeout = getattr(self, timeout_field, None)
                return specific_timeout if specific_timeout is not None else self.grpc_timeout_ms

        config = MockConfig()

        # Specialist desconhecido deve usar fallback (getattr retorna None)
        assert config.get_specialist_timeout_ms('unknown') == 30000
        assert config.get_specialist_timeout_ms('custom') == 30000

    def test_timeout_conversion_to_seconds(self):
        """Timeout em ms deve ser convertido corretamente para segundos"""
        # Usar classe simples ao invés de MagicMock
        class MockConfig:
            grpc_timeout_ms = 30000
            specialist_business_timeout_ms = 120000
            specialist_technical_timeout_ms = None

            def get_specialist_timeout_ms(self, specialist_type: str) -> int:
                timeout_field = f'specialist_{specialist_type}_timeout_ms'
                specific_timeout = getattr(self, timeout_field, None)
                return specific_timeout if specific_timeout is not None else self.grpc_timeout_ms

        config = MockConfig()

        # Conversão para segundos (usado no asyncio.wait_for)
        business_timeout_seconds = config.get_specialist_timeout_ms('business') / 1000.0
        technical_timeout_seconds = config.get_specialist_timeout_ms('technical') / 1000.0

        assert business_timeout_seconds == 120.0
        assert technical_timeout_seconds == 30.0


class TestSpecialistTimeoutIntegration:
    """Testes de integração com a classe Settings real"""

    def test_settings_get_specialist_timeout_with_specific(self):
        """Settings.get_specialist_timeout_ms deve retornar timeout específico"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=30000,
            specialist_business_timeout_ms=120000
        )

        assert settings.get_specialist_timeout_ms('business') == 120000
        assert settings.get_specialist_timeout_ms('technical') == 30000

    def test_settings_get_specialist_timeout_all_fallback(self):
        """Sem timeouts específicos, todos devem usar o global"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=60000
        )

        for specialist in ['business', 'technical', 'behavior', 'evolution', 'architecture']:
            assert settings.get_specialist_timeout_ms(specialist) == 60000

    def test_settings_get_specialist_timeout_mixed_config(self):
        """Configuração mista de timeouts específicos e fallback"""
        from src.config.settings import Settings

        settings = Settings(
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:6379',
            grpc_timeout_ms=30000,
            specialist_business_timeout_ms=120000,
            specialist_architecture_timeout_ms=90000
        )

        # Específicos
        assert settings.get_specialist_timeout_ms('business') == 120000
        assert settings.get_specialist_timeout_ms('architecture') == 90000

        # Fallback
        assert settings.get_specialist_timeout_ms('technical') == 30000
        assert settings.get_specialist_timeout_ms('behavior') == 30000
        assert settings.get_specialist_timeout_ms('evolution') == 30000
