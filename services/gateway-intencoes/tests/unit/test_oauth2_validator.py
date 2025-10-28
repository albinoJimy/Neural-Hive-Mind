"""
Unit tests for OAuth2 Validator
Test token validation, JWKS caching, and Keycloak integration
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx
from jose import jwt, JWTError

from src.security.oauth2_validator import (
    OAuth2Validator,
    JWKSCache,
    TokenValidationError,
    get_oauth2_validator,
    close_oauth2_validator
)


def create_test_token(
    payload: dict = None,
    headers: dict = None,
    secret: str = "test_secret",
    algorithm: str = "HS256",
    expired: bool = False,
    not_yet_valid: bool = False
) -> str:
    """Helper to create test JWT tokens"""
    now = datetime.now()

    default_payload = {
        'sub': 'test-user-id',
        'preferred_username': 'testuser',
        'email': 'test@example.com',
        'name': 'Test User',
        'azp': 'test-client',
        'scope': 'openid profile email',
        'realm_access': {
            'roles': ['neural-hive-user', 'user']
        },
        'iss': 'https://keycloak.example.com/auth/realms/neural-hive',
        'aud': ['test-client', 'account'],
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(hours=1)).timestamp()),
        'session_state': 'test-session'
    }

    if expired:
        default_payload['exp'] = int((now - timedelta(hours=1)).timestamp())

    if not_yet_valid:
        default_payload['iat'] = int((now + timedelta(hours=1)).timestamp())

    if payload:
        default_payload.update(payload)

    default_headers = {'kid': 'test-key-id'}
    if headers:
        default_headers.update(headers)

    return jwt.encode(default_payload, secret, algorithm=algorithm, headers=default_headers)


@pytest.fixture
async def mock_settings():
    """Mock settings for testing"""
    settings = Mock()
    settings.keycloak_url = "https://keycloak.example.com"
    settings.keycloak_realm = "neural-hive"
    settings.keycloak_client_id = "test-client"
    settings.keycloak_client_secret = "test-secret"
    settings.jwks_uri = "https://keycloak.example.com/auth/realms/neural-hive/protocol/openid-connect/certs"
    return settings


@pytest.fixture
async def mock_jwks():
    """Mock JWKS response"""
    return {
        'keys': [
            {
                'kid': 'test-key-id',
                'kty': 'RSA',
                'alg': 'RS256',
                'use': 'sig',
                'n': 'test_modulus',
                'e': 'AQAB'
            },
            {
                'kid': 'another-key-id',
                'kty': 'RSA',
                'alg': 'RS256',
                'use': 'sig',
                'n': 'another_modulus',
                'e': 'AQAB'
            }
        ]
    }


class TestJWKSCache:
    """Test JWKS caching functionality"""

    @pytest.mark.asyncio
    async def test_initial_fetch(self, mock_jwks):
        """Test initial JWKS fetch from server"""
        cache = JWKSCache(cache_duration=300)

        mock_response = AsyncMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        cache.http_client = mock_client

        result = await cache.get_jwks("https://example.com/jwks")

        assert result == mock_jwks
        assert cache.jwks == mock_jwks
        assert cache.last_fetch is not None
        mock_client.get.assert_called_once_with("https://example.com/jwks")

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_jwks):
        """Test JWKS cache hit within TTL"""
        cache = JWKSCache(cache_duration=300)
        cache.jwks = mock_jwks
        cache.last_fetch = datetime.now()

        # Mock HTTP client should not be called
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        cache.http_client = mock_client

        result = await cache.get_jwks("https://example.com/jwks")

        assert result == mock_jwks
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_expired(self, mock_jwks):
        """Test JWKS cache miss when TTL expired"""
        cache = JWKSCache(cache_duration=300)
        cache.jwks = {'keys': []}  # Old cached data
        cache.last_fetch = datetime.now() - timedelta(seconds=301)  # Expired

        mock_response = AsyncMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        cache.http_client = mock_client

        result = await cache.get_jwks("https://example.com/jwks")

        assert result == mock_jwks
        assert cache.jwks == mock_jwks
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_error_with_fallback(self, mock_jwks):
        """Test using expired cache when fetch fails"""
        cache = JWKSCache(cache_duration=300)
        cache.jwks = mock_jwks  # Expired but valid cache
        cache.last_fetch = datetime.now() - timedelta(seconds=301)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
        cache.http_client = mock_client

        result = await cache.get_jwks("https://example.com/jwks")

        assert result == mock_jwks  # Returns expired cache
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_error_no_fallback(self):
        """Test error when fetch fails with no cache"""
        cache = JWKSCache(cache_duration=300)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
        cache.http_client = mock_client

        with pytest.raises(TokenValidationError):
            await cache.get_jwks("https://example.com/jwks")


class TestOAuth2Validator:
    """Test OAuth2 token validation"""

    @pytest.mark.asyncio
    async def test_initialize(self, mock_settings, mock_jwks):
        """Test validator initialization"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            # Mock JWKS cache
            validator.jwks_cache.get_jwks = AsyncMock(return_value=mock_jwks)

            await validator.initialize()

            assert validator.http_client is not None
            validator.jwks_cache.get_jwks.assert_called_once_with(mock_settings.jwks_uri)

    @pytest.mark.asyncio
    async def test_validate_token_success(self, mock_settings, mock_jwks):
        """Test successful token validation"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()
            validator.jwks_cache.get_jwks = AsyncMock(return_value=mock_jwks)

            # Create a valid token
            test_payload = {
                'sub': 'user123',
                'azp': 'test-client',
                'realm_access': {'roles': ['neural-hive-user']}
            }

            # Mock jwt.decode to return our payload
            with patch('src.security.oauth2_validator.jwt.get_unverified_header') as mock_header:
                with patch('src.security.oauth2_validator.jwt.decode') as mock_decode:
                    mock_header.return_value = {'kid': 'test-key-id'}
                    mock_decode.return_value = test_payload

                    result = await validator.validate_token("fake.jwt.token")

                    assert result == test_payload
                    validator.jwks_cache.get_jwks.assert_called_once()
                    mock_decode.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_token_missing_kid(self, mock_settings):
        """Test validation fails when token has no kid"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            with patch('src.security.oauth2_validator.jwt.get_unverified_header') as mock_header:
                mock_header.return_value = {}  # No kid

                with pytest.raises(TokenValidationError, match="Token JWT não contém 'kid'"):
                    await validator.validate_token("fake.jwt.token")

    @pytest.mark.asyncio
    async def test_validate_token_expired(self, mock_settings, mock_jwks):
        """Test validation fails for expired token"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()
            validator.jwks_cache.get_jwks = AsyncMock(return_value=mock_jwks)

            expired_payload = {
                'exp': int((datetime.now() - timedelta(hours=1)).timestamp()),
                'realm_access': {'roles': ['neural-hive-user']}
            }

            with patch('src.security.oauth2_validator.jwt.get_unverified_header') as mock_header:
                with patch('src.security.oauth2_validator.jwt.decode') as mock_decode:
                    mock_header.return_value = {'kid': 'test-key-id'}
                    mock_decode.return_value = expired_payload

                    with pytest.raises(TokenValidationError, match="Token expirado"):
                        await validator.validate_token("fake.jwt.token")

    @pytest.mark.asyncio
    async def test_validate_token_invalid_client_id(self, mock_settings, mock_jwks):
        """Test validation fails for wrong client ID"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()
            validator.jwks_cache.get_jwks = AsyncMock(return_value=mock_jwks)

            payload = {
                'exp': int((datetime.now() + timedelta(hours=1)).timestamp()),
                'iat': int(datetime.now().timestamp()),
                'azp': 'wrong-client',
                'realm_access': {'roles': ['neural-hive-user']}
            }

            with patch('src.security.oauth2_validator.jwt.get_unverified_header') as mock_header:
                with patch('src.security.oauth2_validator.jwt.decode') as mock_decode:
                    mock_header.return_value = {'kid': 'test-key-id'}
                    mock_decode.return_value = payload

                    with pytest.raises(TokenValidationError, match="Client ID inválido"):
                        await validator.validate_token("fake.jwt.token", client_id="expected-client")

    @pytest.mark.asyncio
    async def test_validate_token_missing_scopes(self, mock_settings, mock_jwks):
        """Test validation fails for missing required scopes"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()
            validator.jwks_cache.get_jwks = AsyncMock(return_value=mock_jwks)

            payload = {
                'exp': int((datetime.now() + timedelta(hours=1)).timestamp()),
                'iat': int(datetime.now().timestamp()),
                'scope': 'openid profile',
                'realm_access': {'roles': ['neural-hive-user']}
            }

            with patch('src.security.oauth2_validator.jwt.get_unverified_header') as mock_header:
                with patch('src.security.oauth2_validator.jwt.decode') as mock_decode:
                    mock_header.return_value = {'kid': 'test-key-id'}
                    mock_decode.return_value = payload

                    with pytest.raises(TokenValidationError, match="Scopes insuficientes"):
                        await validator.validate_token("fake.jwt.token", required_scopes=['email', 'admin'])

    @pytest.mark.asyncio
    async def test_validate_token_invalid_roles(self, mock_settings, mock_jwks):
        """Test validation fails without Neural Hive roles"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()
            validator.jwks_cache.get_jwks = AsyncMock(return_value=mock_jwks)

            payload = {
                'exp': int((datetime.now() + timedelta(hours=1)).timestamp()),
                'iat': int(datetime.now().timestamp()),
                'realm_access': {'roles': ['some-other-role']}
            }

            with patch('src.security.oauth2_validator.jwt.get_unverified_header') as mock_header:
                with patch('src.security.oauth2_validator.jwt.decode') as mock_decode:
                    mock_header.return_value = {'kid': 'test-key-id'}
                    mock_decode.return_value = payload

                    with pytest.raises(TokenValidationError, match="Token não tem roles válidos"):
                        await validator.validate_token("fake.jwt.token")

    @pytest.mark.asyncio
    async def test_validate_offline(self, mock_settings):
        """Test offline token validation"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            payload = {
                'exp': int((datetime.now() + timedelta(hours=1)).timestamp()),
                'iss': f"{mock_settings.keycloak_url}/auth/realms/{mock_settings.keycloak_realm}",
                'sub': 'user123'
            }

            with patch('src.security.oauth2_validator.jwt.get_unverified_claims') as mock_claims:
                mock_claims.return_value = payload

                result = await validator.validate_offline("fake.jwt.token")

                assert result == payload
                mock_claims.assert_called_once_with("fake.jwt.token")

    @pytest.mark.asyncio
    async def test_validate_offline_expired(self, mock_settings):
        """Test offline validation fails for expired token"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            payload = {
                'exp': int((datetime.now() - timedelta(hours=1)).timestamp()),
                'iss': f"{mock_settings.keycloak_url}/auth/realms/{mock_settings.keycloak_realm}"
            }

            with patch('src.security.oauth2_validator.jwt.get_unverified_claims') as mock_claims:
                mock_claims.return_value = payload

                with pytest.raises(TokenValidationError, match="Token expirado"):
                    await validator.validate_offline("fake.jwt.token")

    @pytest.mark.asyncio
    async def test_introspect_token_active(self, mock_settings):
        """Test token introspection for active token"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            mock_response = AsyncMock()
            mock_response.json.return_value = {
                'active': True,
                'sub': 'user123',
                'username': 'testuser'
            }
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            validator.http_client = mock_client

            result = await validator.introspect_token("fake.token")

            assert result['active'] is True
            assert result['sub'] == 'user123'
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_introspect_token_inactive(self, mock_settings):
        """Test token introspection for inactive token"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            mock_response = AsyncMock()
            mock_response.json.return_value = {'active': False}
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            validator.http_client = mock_client

            with pytest.raises(TokenValidationError, match="Token inativo"):
                await validator.introspect_token("fake.token")

    @pytest.mark.asyncio
    async def test_get_user_info(self, mock_settings):
        """Test fetching user info"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            user_info = {
                'sub': 'user123',
                'preferred_username': 'testuser',
                'email': 'test@example.com',
                'name': 'Test User'
            }

            mock_response = AsyncMock()
            mock_response.json.return_value = user_info
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            validator.http_client = mock_client

            result = await validator.get_user_info("fake.token")

            assert result == user_info
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert 'Authorization' in call_args[1]['headers']
            assert call_args[1]['headers']['Authorization'] == 'Bearer fake.token'

    def test_extract_user_context(self, mock_settings):
        """Test extracting user context from JWT payload"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            payload = {
                'sub': 'user123',
                'preferred_username': 'testuser',
                'email': 'test@example.com',
                'name': 'Test User',
                'realm_access': {'roles': ['neural-hive-admin', 'user']},
                'scope': 'openid profile email',
                'azp': 'test-client',
                'session_state': 'session123'
            }

            context = validator.extract_user_context(payload)

            assert context['user_id'] == 'user123'
            assert context['username'] == 'testuser'
            assert context['email'] == 'test@example.com'
            assert context['name'] == 'Test User'
            assert 'neural-hive-admin' in context['roles']
            assert 'openid' in context['scopes']
            assert context['client_id'] == 'test-client'
            assert context['session_id'] == 'session123'
            assert context['is_admin'] is True

    def test_find_key_success(self, mock_settings, mock_jwks):
        """Test finding JWKS key by kid"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            key = validator._find_key(mock_jwks, 'test-key-id')

            assert key['kid'] == 'test-key-id'
            assert key['kty'] == 'RSA'

    def test_find_key_not_found(self, mock_settings, mock_jwks):
        """Test error when JWKS key not found"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            validator = OAuth2Validator()

            with pytest.raises(TokenValidationError, match="Chave JWKS não encontrada"):
                validator._find_key(mock_jwks, 'non-existent-key')


class TestOAuth2ValidatorSingleton:
    """Test singleton pattern for OAuth2 validator"""

    @pytest.mark.asyncio
    async def test_get_oauth2_validator_singleton(self, mock_settings):
        """Test that get_oauth2_validator returns the same instance"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            with patch('src.security.oauth2_validator.OAuth2Validator') as MockValidator:
                mock_instance = Mock()
                mock_instance.initialize = AsyncMock()
                MockValidator.return_value = mock_instance

                # Reset global validator
                import src.security.oauth2_validator
                src.security.oauth2_validator._oauth2_validator = None

                validator1 = await get_oauth2_validator()
                validator2 = await get_oauth2_validator()

                assert validator1 is validator2
                MockValidator.assert_called_once()
                mock_instance.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_oauth2_validator(self, mock_settings):
        """Test closing the global OAuth2 validator"""
        with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
            with patch('src.security.oauth2_validator.OAuth2Validator') as MockValidator:
                mock_instance = Mock()
                mock_instance.initialize = AsyncMock()
                mock_instance.close = AsyncMock()
                MockValidator.return_value = mock_instance

                # Reset and create validator
                import src.security.oauth2_validator
                src.security.oauth2_validator._oauth2_validator = None

                validator = await get_oauth2_validator()
                await close_oauth2_validator()

                mock_instance.close.assert_called_once()
                assert src.security.oauth2_validator._oauth2_validator is None


@pytest.mark.asyncio
async def test_jwks_cache_close():
    """Test closing JWKS cache resources"""
    cache = JWKSCache()

    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()
    cache.http_client = mock_client

    await cache.close()

    mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_validator_close(mock_settings):
    """Test closing validator resources"""
    with patch('src.security.oauth2_validator.get_settings', return_value=mock_settings):
        validator = OAuth2Validator()

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        validator.http_client = mock_client

        validator.jwks_cache.close = AsyncMock()

        await validator.close()

        validator.jwks_cache.close.assert_called_once()
        mock_client.aclose.assert_called_once()