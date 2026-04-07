"""Unit tests for JWT security - environment variables

TDD NOTE: Este teste é escrito ANTES da implementação e é EXPECTED que falhe.
O teste servirá como contrato para a implementação na Task 2, onde auth.py
será modificado para importar e usar settings.get_settings().
"""

import pytest
from unittest.mock import patch, Mock, PropertyMock
from src.security.auth import verify_token


@pytest.mark.asyncio
async def test_verify_token_uses_secret_from_settings():
    """Test that verify_token uses JWT_SECRET from settings (with Vault support)"""
    # Mock settings with the expected secret
    mock_settings = Mock()
    # Simular a propriedade JWT_SECRET que busca do Vault
    type(mock_settings).JWT_SECRET = PropertyMock(return_value="test-secret-from-env")
    mock_settings.jwt_algorithm = "HS256"

    # Patch onde settings sera importado em auth.py (apos implementacao na Task 2)
    # Precisamos patchar antes da importacao em auth.py acontecer.
    # Como auth.py faz "from config.settings import get_settings", precisamos
    # patchar no modulo onde ele e usado (auth), nao onde e definido (settings).
    with patch("src.security.auth.get_settings", return_value=mock_settings):
        # Create a valid token with the same secret
        import jwt

        test_payload = {"sub": "user123", "exp": 9999999999}
        test_token = jwt.encode(test_payload, "test-secret-from-env", algorithm="HS256")

        # Should decode successfully once auth.py uses settings
        result = await verify_token(test_token)
        assert result["sub"] == "user123"


@pytest.mark.asyncio
async def test_verify_token_raises_for_invalid_token():
    """Test that verify_token raises HTTPException for invalid tokens"""
    from fastapi import HTTPException

    # Mock settings com JWT_SECRET válido para não falhar na validação
    mock_settings = Mock()
    type(mock_settings).JWT_SECRET = PropertyMock(return_value="valid-test-secret")
    mock_settings.jwt_algorithm = "HS256"

    with patch("src.security.auth.get_settings", return_value=mock_settings):
        with pytest.raises(HTTPException) as exc_info:
            await verify_token("invalid-token")

        assert exc_info.value.status_code == 401
        assert "Token inválido" in exc_info.value.detail
