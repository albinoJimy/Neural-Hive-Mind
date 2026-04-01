"""
Testes de validação de segurança para configurações do Consensus Engine.

Estes testes garantem que:
1. Endpoints hardcoded não sejam usados em produção
2. Credenciais com padrões suspeitos sejam detectados
3. HTTPS seja obrigatório em produção
"""
import pytest
import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.config.settings import Settings, get_settings


class TestProductionSecurityValidation:
    """Testes de validação de segurança para ambiente de produção."""

    def test_rejects_hardcoded_endpoints_in_production(self):
        """Endpoints hardcoded devem ser rejeitados em produção."""
        with pytest.raises(ValueError, match="Configuração insegura"):
            Settings(
                environment='production',
                kafka_bootstrap_servers='kafka:9092',
                mongodb_uri='mongodb://localhost:27017',
                redis_cluster_nodes='redis:7000',
                # Usando valores padrão hardcoded
                specialist_business_endpoint='specialist-business.neural-hive.svc.cluster.local:50051',
                specialist_technical_endpoint='specialist-technical.neural-hive.svc.cluster.local:50051',
                specialist_architecture_endpoint='specialist-architecture.neural-hive.svc.cluster.local:50051',
                queen_agent_grpc_host='queen-agent.production.svc.cluster.local',
                analyst_agent_grpc_host='analyst-agents.production.svc.cluster.local',
            )

    def test_rejects_hardcoded_endpoints_in_staging(self):
        """Endpoints hardcoded devem ser rejeitados em staging."""
        with pytest.raises(ValueError, match="Configuração insegura"):
            Settings(
                environment='staging',
                kafka_bootstrap_servers='kafka:9092',
                mongodb_uri='mongodb://localhost:27017',
                redis_cluster_nodes='redis:7000',
                # Usando valores padrão hardcoded
                specialist_business_endpoint='specialist-business.production.svc.cluster.local:50051',
                specialist_technical_endpoint='specialist-technical.production.svc.cluster.local:50051',
                specialist_architecture_endpoint='specialist-architecture.production.svc.cluster.local:50051',
                queen_agent_grpc_host='queen-agent.neural-hive.svc.cluster.local',
                analyst_agent_grpc_host='analyst-agents.neural-hive.svc.cluster.local',
            )

    def test_allows_custom_endpoints_in_production(self):
        """Endpoints customizados devem ser aceitos em produção."""
        settings = Settings(
            environment='production',
            kafka_bootstrap_servers='kafka.prod.example.com:9092',
            mongodb_uri='mongodb://prod.example.com:27017',
            redis_cluster_nodes='redis.prod.example.com:7000',
            # Endpoints customizados de produção
            specialist_business_endpoint='specialist-business.production.svc.cluster.local:50051',
            specialist_technical_endpoint='specialist-technical.production.svc.cluster.local:50051',
            specialist_architecture_endpoint='specialist-architecture.production.svc.cluster.local:50051',
            queen_agent_grpc_host='queen-agent.production.svc.cluster.local',
            analyst_agent_grpc_host='analyst-agents.production.svc.cluster.local',
        )
        assert settings.environment == 'production'

    def test_allows_hardcoded_endpoints_in_development(self):
        """Endpoints hardcoded são permitidos em desenvolvimento."""
        settings = Settings(
            environment='dev',
            kafka_bootstrap_servers='kafka:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='redis:7000',
            # Usando valores padrão hardcoded - OK em dev
            specialist_business_endpoint='specialist-business.neural-hive.svc.cluster.local:50051',
        )
        assert settings.environment == 'dev'


class TestSensitiveCredentialValidation:
    """Testes de validação de credenciais sensíveis."""

    def test_rejects_password_pattern_in_mongodb_uri(self):
        """URI com 'password' deve ser rejeitada em produção."""
        with pytest.raises(ValueError, match="padrões inseguros"):
            Settings(
                environment='production',
                kafka_bootstrap_servers='kafka:9092',
                mongodb_uri='mongodb://user:password@localhost:27017',  # 'password' detectado
                redis_cluster_nodes='redis:7000',
                specialist_business_endpoint='custom.production:50051',
                specialist_technical_endpoint='custom.production:50051',
                specialist_architecture_endpoint='custom.production:50051',
                queen_agent_grpc_host='queen-agent.production:50053',
                analyst_agent_grpc_host='analyst-agents.production:50051',
            )

    def test_rejects_localhost_in_mongodb_uri_production(self):
        """localhost em MongoDB URI deve ser rejeitado em produção."""
        with pytest.raises(ValueError, match="padrões inseguros"):
            Settings(
                environment='production',
                kafka_bootstrap_servers='kafka.prod:9092',
                mongodb_uri='mongodb://user:secret@localhost:27017',  # localhost detectado
                redis_cluster_nodes='redis.prod:7000',
                specialist_business_endpoint='custom.production:50051',
                specialist_technical_endpoint='custom.production:50051',
                specialist_architecture_endpoint='custom.production:50051',
                queen_agent_grpc_host='queen-agent.production:50053',
                analyst_agent_grpc_host='analyst-agents.production:50051',
            )

    def test_rejects_common_password_patterns(self):
        """Senhas com padrões comuns devem ser rejeitadas em produção."""
        with pytest.raises(ValueError, match="padrões inseguros"):
            Settings(
                environment='production',
                kafka_bootstrap_servers='kafka.prod:9092',
                mongodb_uri='mongodb://prod.example.com:27017',
                redis_cluster_nodes='redis.prod:7000',
                redis_password='changeme',  # Padrão suspeito
                specialist_business_endpoint='custom.production:50051',
                specialist_technical_endpoint='custom.production:50051',
                specialist_architecture_endpoint='custom.production:50051',
                queen_agent_grpc_host='queen-agent.production:50053',
                analyst_agent_grpc_host='analyst-agents.production:50051',
            )

    def test_allows_strong_passwords_in_production(self):
        """Senhas fortes devem ser aceitas em produção."""
        settings = Settings(
            environment='production',
            kafka_bootstrap_servers='kafka.prod:9092',
            mongodb_uri='mongodb://user:a7b3c9d2e5f1@mongodb.prod:27017',
            redis_cluster_nodes='redis.prod:7000',
            redis_password='xK9$mP2@nQ8vL5',  # Senha forte
            specialist_business_endpoint='custom.production:50051',
            specialist_technical_endpoint='custom.production:50051',
            specialist_architecture_endpoint='custom.production:50051',
            queen_agent_grpc_host='queen-agent.production:50053',
            analyst_agent_grpc_host='analyst-agents.production:50051',
        )
        assert settings.redis_password == 'xK9$mP2@nQ8vL5'

    def test_allows_development_credentials_in_development(self):
        """Credenciais de desenvolvimento são OK em dev."""
        settings = Settings(
            environment='dev',
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:7000',
            redis_password='devpassword',  # OK em dev
        )
        assert settings.environment == 'dev'


class TestHTTPSValidation:
    """Testes de validação de HTTPS em produção."""

    def test_rejects_http_otel_endpoint_in_production(self):
        """Endpoint HTTP deve ser rejeitado em produção."""
        with pytest.raises(ValueError, match="Endpoints HTTP inseguros"):
            Settings(
                environment='production',
                kafka_bootstrap_servers='kafka:9092',
                mongodb_uri='mongodb://prod:27017',
                redis_cluster_nodes='redis:7000',
                specialist_business_endpoint='custom.production:50051',
                specialist_technical_endpoint='custom.production:50051',
                specialist_architecture_endpoint='custom.production:50051',
                queen_agent_grpc_host='queen-agent.production:50053',
                analyst_agent_grpc_host='analyst-agents.production:50051',
                otel_endpoint='http://opentelemetry:4317',  # HTTP em produção
            )

    def test_allows_https_otel_endpoint_in_production(self):
        """Endpoint HTTPS deve ser aceito em produção."""
        settings = Settings(
            environment='production',
            kafka_bootstrap_servers='kafka.prod:9092',
            mongodb_uri='mongodb://prod:27017',
            redis_cluster_nodes='redis.prod:7000',
            specialist_business_endpoint='custom.production:50051',
            specialist_technical_endpoint='custom.production:50051',
            specialist_architecture_endpoint='custom.production:50051',
            queen_agent_grpc_host='queen-agent.production:50053',
            analyst_agent_grpc_host='analyst-agents.production:50051',
            otel_endpoint='https://opentelemetry.prod:4317',  # HTTPS OK
        )
        assert 'https://' in settings.otel_endpoint

    def test_allows_http_in_development(self):
        """HTTP é permitido em desenvolvimento."""
        settings = Settings(
            environment='dev',
            kafka_bootstrap_servers='localhost:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='localhost:7000',
            otel_endpoint='http://localhost:4317',  # OK em dev
        )
        assert settings.otel_endpoint == 'http://localhost:4317'


class TestSettingsValidation:
    """Testes de validação geral de configurações."""

    def test_requires_kafka_bootstrap_servers(self):
        """kafka_bootstrap_servers é obrigatório."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Settings(
                environment='dev',
                mongodb_uri='mongodb://localhost:27017',
                redis_cluster_nodes='redis:7000',
            )

    def test_requires_mongodb_uri(self):
        """mongodb_uri é obrigatório."""
        with pytest.raises(Exception):
            Settings(
                environment='dev',
                kafka_bootstrap_servers='kafka:9092',
                redis_cluster_nodes='redis:7000',
            )

    def test_requires_redis_cluster_nodes(self):
        """redis_cluster_nodes é obrigatório."""
        with pytest.raises(Exception):
            Settings(
                environment='dev',
                kafka_bootstrap_servers='kafka:9092',
                mongodb_uri='mongodb://localhost:27017',
            )

    def test_validates_specialist_timeout_positive(self):
        """Timeouts devem ser positivos."""
        settings = Settings(
            environment='dev',
            kafka_bootstrap_servers='kafka:9092',
            mongodb_uri='mongodb://localhost:27017',
            redis_cluster_nodes='redis:7000',
            grpc_timeout_ms=5000,  # Positivo OK
        )
        assert settings.grpc_timeout_ms == 5000

    def test_validates_specialist_timeout_negative_fails(self):
        """Timeouts negativos devem falhar a validação."""
        # Pydantic levanta ValidationError para valores fora do range
        with pytest.raises(Exception):
            Settings(
                environment='dev',
                kafka_bootstrap_servers='kafka:9092',
                mongodb_uri='mongodb://localhost:27017',
                redis_cluster_nodes='redis:7000',
                grpc_timeout_ms=-100,  # Negativo inválido
            )

    def test_validates_endpoint_format(self):
        """Endpoints devem ter formato host:port."""
        with pytest.raises(ValueError, match="Endpoint deve estar no formato"):
            Settings(
                environment='dev',
                kafka_bootstrap_servers='kafka:9092',
                mongodb_uri='mongodb://localhost:27017',
                redis_cluster_nodes='redis:7000',
                specialist_business_endpoint='invalid-endpoint',  # Sem porta
            )
