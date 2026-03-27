"""Unit tests for Settings security validation"""
import pytest
from pydantic import ValidationError
from src.config.settings import Settings

def test_jwt_secret_key_required_in_production():
    """Test that jwt_secret_key is required in production"""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            environment="prod",
            # jwt_secret_key intentionally omitted
        )

    assert "jwt_secret_key" in str(exc_info.value).lower()

def test_cors_origins_parse_from_string():
    """Test that CORS_ORIGINS string is parsed to list"""
    settings = Settings(
        environment="dev",
        jwt_secret_key="test-secret",
        allowed_origins="http://localhost:3000,https://example.com"
    )

    assert settings.allowed_origins == ["http://localhost:3000", "https://example.com"]

def test_cors_origins_accepts_list():
    """Test that allowed_origins accepts list directly"""
    settings = Settings(
        environment="dev",
        jwt_secret_key="test-secret",
        allowed_origins=["http://localhost:3000", "https://example.com"]
    )

    assert settings.allowed_origins == ["http://localhost:3000", "https://example.com"]

def test_cors_origins_default_removed():
    """Test that wildcard '*' is no longer the default"""
    # This test ensures settings require explicit CORS configuration
    with pytest.raises(ValidationError):
        Settings(
            environment="prod",
            jwt_secret_key="test-secret"
            # allowed_origins omitted - should fail
        )
