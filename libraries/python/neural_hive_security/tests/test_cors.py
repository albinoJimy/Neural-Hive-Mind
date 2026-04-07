"""
Unit tests para CORSConfig.

Testa configuração centralizada de CORS por ambiente e validação de segurança.
"""
import pytest

from neural_hive_security.cors import CORSConfig, get_cors_origins


class TestCORSConfigOrigins:
    """Testes de origens por ambiente."""

    def test_dev_origins_for_public_api(self):
        """Dev deve retornar localhost origens para API pública."""
        origins = CORSConfig.get_origins_for_environment("dev", is_public_api=True)

        assert "http://localhost:3000" in origins
        assert "http://localhost:8000" in origins
        assert "http://127.0.0.1:3000" in origins
        assert len(origins) >= 6

    def test_development_variant(self):
        """'development' deve funcionar igual a 'dev'."""
        dev_origins = CORSConfig.get_origins_for_environment("dev", is_public_api=True)
        development_origins = CORSConfig.get_origins_for_environment(
            "development", is_public_api=True
        )

        assert dev_origins == development_origins

    def test_staging_origins_for_public_api(self):
        """Staging deve retornar domínios de staging."""
        origins = CORSConfig.get_origins_for_environment("staging", is_public_api=True)

        assert "https://staging.neural-hive.local" in origins
        assert "https://gateway-staging.neural-hive.local" in origins
        assert len(origins) >= 4

    def test_stage_variant(self):
        """'stage' deve funcionar igual a 'staging'."""
        staging_origins = CORSConfig.get_origins_for_environment("staging", is_public_api=True)
        stage_origins = CORSConfig.get_origins_for_environment("stage", is_public_api=True)

        assert staging_origins == stage_origins

    def test_prod_origins_for_public_api(self):
        """Prod deve retornar domínios de produção."""
        origins = CORSConfig.get_origins_for_environment("prod", is_public_api=True)

        assert "https://neural-hive.com" in origins
        assert "https://app.neural-hive.com" in origins
        assert "https://approval.neural-hive.com" in origins
        assert len(origins) >= 5

    def test_production_variant(self):
        """'production' deve funcionar igual a 'prod'."""
        prod_origins = CORSConfig.get_origins_for_environment("prod", is_public_api=True)
        production_origins = CORSConfig.get_origins_for_environment(
            "production", is_public_api=True
        )

        assert prod_origins == production_origins

    def test_internal_service_empty_origins(self):
        """Serviços internos devem ter origens vazias."""
        origins = CORSConfig.get_origins_for_environment("prod", is_public_api=False)

        assert origins == []

    def test_unknown_environment_defaults_to_dev(self):
        """Ambiente desconhecido deve defaultar para dev."""
        origins = CORSConfig.get_origins_for_environment("unknown", is_public_api=True)

        # Deve ser igual ao dev
        dev_origins = CORSConfig.get_origins_for_environment("dev", is_public_api=True)
        assert origins == dev_origins

    def test_environment_with_dashes_and_underscores(self):
        """Nomes de ambiente com - e _ devem funcionar."""
        origins1 = CORSConfig.get_origins_for_environment("prod-env", is_public_api=True)
        origins2 = CORSConfig.get_origins_for_environment("prod_env", is_public_api=True)
        prod_origins = CORSConfig.get_origins_for_environment("prod", is_public_api=True)

        assert origins1 == prod_origins
        assert origins2 == prod_origins


class TestCORSConfigValidation:
    """Testes de validação de segurança."""

    def test_wildcard_allowed_in_dev(self):
        """Wildcard deve ser permitido em dev."""
        assert CORSConfig.validate_no_wildcard(["*"], "dev") is True

    def test_wildcard_allowed_in_development(self):
        """Wildcard deve ser permitido em development."""
        assert CORSConfig.validate_no_wildcard(["*"], "development") is True

    def test_wildcard_allowed_in_staging(self):
        """Wildcard deve ser permitido em staging."""
        assert CORSConfig.validate_no_wildcard(["*"], "staging") is True

    def test_wildcard_forbidden_in_prod(self):
        """Wildcard deve ser PROIBIDO em prod."""
        with pytest.raises(ValueError, match="Wildcard CORS"):
            CORSConfig.validate_no_wildcard(["*"], "prod")

    def test_wildcard_forbidden_in_production(self):
        """Wildcard deve ser PROIBIDO em production."""
        with pytest.raises(ValueError, match="Wildcard CORS"):
            CORSConfig.validate_no_wildcard(["*"], "production")

    def test_specific_origins_allowed_in_prod(self):
        """Origens específicas devem ser permitidas em prod."""
        origins = ["https://app.neural-hive.com", "https://admin.neural-hive.com"]
        assert CORSConfig.validate_no_wildcard(origins, "prod") is True

    def test_wildcard_in_list_forbidden_in_prod(self):
        """Lista com wildcard deve ser proibida em prod."""
        origins = ["https://app.neural-hive.com", "*"]
        with pytest.raises(ValueError, match="Wildcard CORS"):
            CORSConfig.validate_no_wildcard(origins, "prod")

    def test_validation_case_insensitive(self):
        """Validação deve ser case-insensitive."""
        with pytest.raises(ValueError, match="Wildcard CORS"):
            CORSConfig.validate_no_wildcard(["*"], "PROD")

        with pytest.raises(ValueError, match="Wildcard CORS"):
            CORSConfig.validate_no_wildcard(["*"], "Production")


class TestCORSConfigMiddleware:
    """Testes de configuração para CORSMiddleware."""

    def test_middleware_config_for_public_api(self):
        """Config de middleware para API pública."""
        config = CORSConfig.get_cors_middleware_config("dev", is_public_api=True)

        assert "allow_origins" in config
        assert "allow_credentials" in config
        assert "allow_methods" in config
        assert "allow_headers" in config
        assert config["allow_credentials"] is True
        assert "GET" in config["allow_methods"]
        assert config["allow_headers"] == ["*"]

    def test_middleware_config_for_internal_service(self):
        """Config de middleware para serviço interno."""
        config = CORSConfig.get_cors_middleware_config("prod", is_public_api=False)

        assert config["allow_origins"] == []
        assert config["allow_credentials"] is False

    def test_middleware_validates_prod_wildcard(self):
        """Config de middleware deve validar wildcard em prod."""
        # Sobrescreve momentaneamente para teste
        original_origins = CORSConfig.PROD_ORIGINS
        CORSConfig.PROD_ORIGINS = ["*"]  # Simula wildcard

        with pytest.raises(ValueError, match="Wildcard CORS"):
            CORSConfig.get_cors_middleware_config("prod", is_public_api=True)

        # Restaura
        CORSConfig.PROD_ORIGINS = original_origins

    def test_expose_headers_in_config(self):
        """Config deve incluir expose_headers."""
        config = CORSConfig.get_cors_middleware_config("prod", is_public_api=True)

        assert "expose_headers" in config
        assert "X-Request-ID" in config["expose_headers"]
        assert "X-Correlation-ID" in config["expose_headers"]


class TestGetCorsOriginsHelper:
    """Testes da função helper get_cors_origins."""

    def test_helper_function(self):
        """Função helper deve funcionar igual ao método de classe."""
        origins1 = get_cors_origins("dev", is_public_api=True)
        origins2 = CORSConfig.get_origins_for_environment("dev", is_public_api=True)

        assert origins1 == origins2

    def test_helper_default_is_public_false(self):
        """Helper deve defaultar is_public_api para False."""
        origins = get_cors_origins("prod")

        # Sem is_public_api, deve ser serviço interno (vazio)
        assert origins == []


class TestSecurityCompliance:
    """Testes de compliance de segurança."""

    def test_prod_origins_no_wildcard(self):
        """Origens de produção não devem conter wildcard."""
        assert "*" not in CORSConfig.PROD_ORIGINS
        assert all("http" in origin or "https" in origin for origin in CORSConfig.PROD_ORIGINS)

    def test_staging_origins_no_wildcard(self):
        """Origens de staging não devem conter wildcard."""
        assert "*" not in CORSConfig.STAGING_ORIGINS
        assert all("http" in origin or "https" in origin for origin in CORSConfig.STAGING_ORIGINS)

    def test_dev_origins_no_wildcard(self):
        """Origens de dev devem ser específicas (localhost)."""
        assert "*" not in CORSConfig.DEV_ORIGINS
        assert all(
            "localhost" in origin or "127.0.0.1" in origin for origin in CORSConfig.DEV_ORIGINS
        )

    def test_internal_services_empty(self):
        """Serviços internos devem ter lista vazia."""
        assert CORSConfig.INTERNAL_SERVICES == []

    def test_all_prod_origins_are_https(self):
        """Todas as origens de produção devem ser HTTPS."""
        assert all(origin.startswith("https://") for origin in CORSConfig.PROD_ORIGINS)

    def test_all_staging_origins_are_https_or_local(self):
        """Origens de staging devem ser HTTPS ou .local."""
        assert all(
            origin.startswith("https://") or ".local" in origin
            for origin in CORSConfig.STAGING_ORIGINS
        )
