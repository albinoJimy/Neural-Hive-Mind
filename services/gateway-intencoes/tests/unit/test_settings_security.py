"""Unit tests for Settings security validation"""

import pytest
import os
from unittest.mock import patch
from pydantic import ValidationError
from src.config.settings import Settings


def test_jwt_secret_key_optional_with_vault_support():
    """Test that jwt_secret_key is optional (can come from Vault or JWT_SECRET env var)"""
    # jwt_secret_key eh opcional pois pode vir do Vault ou JWT_SECRET env var
    settings = Settings(
        environment="prod",
        jwt_secret_key=None,  # opcional agora
        vault_enabled=False,
        allowed_hosts=["api.prod.com"],
    )
    # JWT_SECRET property deve buscar de JWT_SECRET env var se disponivel
    with pytest.raises(ValueError, match="JWT_SECRET não encontrado"):
        _ = settings.JWT_SECRET  # Deve falhar se nao ha Vault nem JWT_SECRET env var


def test_jwt_secret_from_env_variable():
    """Test que JWT_SECRET pode vir de environment variable"""
    with patch.dict(os.environ, {"JWT_SECRET": "env-secret-key"}):
        settings = Settings(
            environment="prod",
            jwt_secret_key=None,
            vault_enabled=False,
            allowed_hosts=["api.prod.com"],
        )
        assert settings.JWT_SECRET == "env-secret-key"


def test_jwt_secret_from_config():
    """Test que jwt_secret_key config tem prioridade sobre env (se Vault desabilitado)"""
    settings = Settings(
        environment="prod",
        jwt_secret_key="config-secret-key",
        vault_enabled=False,
        allowed_hosts=["api.prod.com"],
    )
    assert settings.JWT_SECRET == "config-secret-key"


def test_cors_origins_parse_from_string():
    """Test that CORS_ORIGINS string is parsed to list"""
    settings = Settings(
        environment="dev",
        jwt_secret_key="test-secret",
        cors_origins_override="http://localhost:3000,https://example.com",
    )

    assert settings.cors_origins_override == ["http://localhost:3000", "https://example.com"]


def test_cors_origins_accepts_list():
    """Test that cors_origins_override accepts list directly"""
    settings = Settings(
        environment="dev",
        jwt_secret_key="test-secret",
        cors_origins_override=["http://localhost:3000", "https://example.com"],
    )

    assert settings.cors_origins_override == ["http://localhost:3000", "https://example.com"]


def test_cors_origins_default_removed():
    """Test que CORS usa configuracao automatica quando cors_origins_override omitted"""
    # Quando cors_origins_override nao eh fornecido, usa configuracao automatica
    settings = Settings(
        environment="prod", jwt_secret_key="test-secret", allowed_hosts=["api.prod.com"]
    )
    # Verifica que retorna origens configuradas automaticamente (sem wildcard)
    assert "*" not in settings.allowed_origins
    assert settings.allowed_origins == ["https://neural-hive.com"]
