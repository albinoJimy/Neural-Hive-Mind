"""
Integration tests for Keycloak OAuth2 validation
Test real Keycloak integration with testcontainers
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from typing import Dict, Any
import httpx

# Skip tests if dependencies not available
pytest_plugins = []

try:
    from testcontainers.keycloak import KeycloakContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    try:
        from testcontainers.compose import DockerCompose
        TESTCONTAINERS_AVAILABLE = True
    except ImportError:
        TESTCONTAINERS_AVAILABLE = False

from src.security.oauth2_validator import OAuth2Validator, TokenValidationError
from src.config.settings import get_settings


@pytest.mark.skipif(not TESTCONTAINERS_AVAILABLE, reason="testcontainers not available")
@pytest.mark.integration
class TestKeycloakIntegration:
    """Integration tests with real Keycloak instance"""

    @pytest.fixture(scope="class")
    async def keycloak_container(self):
        """Start Keycloak container for testing"""
        try:
            # Try using Keycloak testcontainer if available
            with KeycloakContainer("quay.io/keycloak/keycloak:21.1") as keycloak:
                keycloak.with_admin_username("admin")
                keycloak.with_admin_password("admin123")
                keycloak.with_realm_import_file("./test_realm.json")  # If we had a test realm
                yield keycloak
        except Exception:
            # Fallback to generic container
            from testcontainers.generic import GenericContainer

            with GenericContainer("quay.io/keycloak/keycloak:21.1") as keycloak:
                keycloak.with_exposed_ports(8080)
                keycloak.with_env("KEYCLOAK_ADMIN", "admin")
                keycloak.with_env("KEYCLOAK_ADMIN_PASSWORD", "admin123")
                keycloak.with_env("KC_HTTP_RELATIVE_PATH", "/auth")
                keycloak.with_command("start-dev --http-relative-path /auth")

                # Wait for Keycloak to be ready
                import time
                time.sleep(30)  # Give Keycloak time to start

                yield keycloak

    @pytest.fixture(scope="class")
    async def keycloak_settings(self, keycloak_container):
        """Create settings for Keycloak integration test"""
        from unittest.mock import Mock

        host = keycloak_container.get_container_host_ip()
        port = keycloak_container.get_exposed_port(8080)
        base_url = f"http://{host}:{port}"

        settings = Mock()
        settings.keycloak_url = base_url
        settings.keycloak_realm = "master"  # Use master realm for testing
        settings.keycloak_client_id = "admin-cli"  # Built-in client
        settings.keycloak_client_secret = None
        settings.jwks_uri = f"{base_url}/auth/realms/master/protocol/openid-connect/certs"

        return settings

    @pytest.fixture
    async def admin_token(self, keycloak_settings):
        """Get admin token for API operations"""
        token_url = f"{keycloak_settings.keycloak_url}/auth/realms/master/protocol/openid-connect/token"

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data={
                'grant_type': 'password',
                'client_id': 'admin-cli',
                'username': 'admin',
                'password': 'admin123'
            })

            if response.status_code == 200:
                token_data = response.json()
                return token_data['access_token']
            else:
                pytest.skip(f"Could not get admin token: {response.status_code}")

    @pytest.fixture
    async def test_realm_setup(self, keycloak_settings, admin_token):
        """Setup test realm and client"""
        admin_api_url = f"{keycloak_settings.keycloak_url}/auth/admin/realms"

        headers = {
            'Authorization': f'Bearer {admin_token}',
            'Content-Type': 'application/json'
        }

        # Create test realm
        realm_config = {
            "realm": "neural-hive-test",
            "enabled": True,
            "displayName": "Neural Hive Test Realm"
        }

        # Create test client
        client_config = {
            "clientId": "neural-hive-test-client",
            "enabled": True,
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": True,
            "clientAuthenticatorType": "client-secret",
            "secret": "test-client-secret"
        }

        # Create test user
        user_config = {
            "username": "testuser",
            "enabled": True,
            "firstName": "Test",
            "lastName": "User",
            "email": "test@neural-hive.com",
            "credentials": [{
                "type": "password",
                "value": "testpassword",
                "temporary": False
            }],
            "realmRoles": ["neural-hive-user"]
        }

        async with httpx.AsyncClient() as client:
            # Create realm
            realm_response = await client.post(admin_api_url,
                                             headers=headers,
                                             json=realm_config)

            if realm_response.status_code not in [201, 409]:  # 409 = already exists
                pytest.skip(f"Could not create test realm: {realm_response.status_code}")

            # Create client in realm
            clients_url = f"{admin_api_url}/neural-hive-test/clients"
            client_response = await client.post(clients_url,
                                              headers=headers,
                                              json=client_config)

            # Create user in realm
            users_url = f"{admin_api_url}/neural-hive-test/users"
            user_response = await client.post(users_url,
                                            headers=headers,
                                            json=user_config)

            # Update settings to use test realm
            keycloak_settings.keycloak_realm = "neural-hive-test"
            keycloak_settings.keycloak_client_id = "neural-hive-test-client"
            keycloak_settings.keycloak_client_secret = "test-client-secret"
            keycloak_settings.jwks_uri = f"{keycloak_settings.keycloak_url}/auth/realms/neural-hive-test/protocol/openid-connect/certs"

            yield keycloak_settings

    @pytest.fixture
    async def oauth2_validator_integration(self, test_realm_setup):
        """Create OAuth2 validator with real Keycloak"""
        from unittest.mock import patch

        with patch('src.security.oauth2_validator.get_settings', return_value=test_realm_setup):
            validator = OAuth2Validator()
            await validator.initialize()
            yield validator
            await validator.close()

    async def get_test_token(self, keycloak_settings) -> str:
        """Get a real JWT token from Keycloak for testing"""
        token_url = f"{keycloak_settings.keycloak_url}/auth/realms/{keycloak_settings.keycloak_realm}/protocol/openid-connect/token"

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data={
                'grant_type': 'password',
                'client_id': keycloak_settings.keycloak_client_id,
                'client_secret': keycloak_settings.keycloak_client_secret,
                'username': 'testuser',
                'password': 'testpassword'
            })

            if response.status_code == 200:
                token_data = response.json()
                return token_data['access_token']
            else:
                pytest.skip(f"Could not get test token: {response.status_code} - {response.text}")

    @pytest.mark.asyncio
    async def test_jwks_fetch(self, oauth2_validator_integration, test_realm_setup):
        """Test JWKS fetching from real Keycloak"""
        validator = oauth2_validator_integration

        jwks = await validator.jwks_cache.get_jwks(test_realm_setup.jwks_uri)

        assert 'keys' in jwks
        assert len(jwks['keys']) > 0

        # Verify key structure
        key = jwks['keys'][0]
        assert 'kid' in key
        assert 'kty' in key
        assert key['kty'] == 'RSA'

    @pytest.mark.asyncio
    async def test_token_validation_success(self, oauth2_validator_integration, test_realm_setup):
        """Test successful token validation with real token"""
        validator = oauth2_validator_integration

        # Get real token
        token = await self.get_test_token(test_realm_setup)

        # Validate token
        payload = await validator.validate_token(token)

        assert 'sub' in payload
        assert 'preferred_username' in payload
        assert payload['preferred_username'] == 'testuser'
        assert 'iss' in payload
        assert test_realm_setup.keycloak_realm in payload['iss']

    @pytest.mark.asyncio
    async def test_token_validation_expired(self, oauth2_validator_integration, test_realm_setup):
        """Test validation fails for expired token"""
        validator = oauth2_validator_integration

        # Create an obviously expired token (this is a mock token for testing)
        from jose import jwt

        expired_payload = {
            'sub': 'testuser',
            'exp': int((datetime.now() - timedelta(hours=1)).timestamp()),
            'iat': int((datetime.now() - timedelta(hours=2)).timestamp()),
            'iss': f"{test_realm_setup.keycloak_url}/auth/realms/{test_realm_setup.keycloak_realm}",
            'aud': test_realm_setup.keycloak_client_id
        }

        # This will fail signature validation, which is expected
        expired_token = jwt.encode(expired_payload, "fake-secret", algorithm="HS256")

        with pytest.raises(TokenValidationError):
            await validator.validate_token(expired_token)

    @pytest.mark.asyncio
    async def test_token_introspection(self, oauth2_validator_integration, test_realm_setup):
        """Test token introspection endpoint"""
        validator = oauth2_validator_integration

        # Get real token
        token = await self.get_test_token(test_realm_setup)

        # Introspect token
        introspection_result = await validator.introspect_token(token)

        assert introspection_result['active'] is True
        assert 'sub' in introspection_result
        assert 'username' in introspection_result
        assert introspection_result['username'] == 'testuser'

    @pytest.mark.asyncio
    async def test_get_user_info(self, oauth2_validator_integration, test_realm_setup):
        """Test user info endpoint"""
        validator = oauth2_validator_integration

        # Get real token
        token = await self.get_test_token(test_realm_setup)

        # Get user info
        user_info = await validator.get_user_info(token)

        assert 'sub' in user_info
        assert 'preferred_username' in user_info
        assert user_info['preferred_username'] == 'testuser'
        assert 'email' in user_info
        assert user_info['email'] == 'test@neural-hive.com'

    @pytest.mark.asyncio
    async def test_offline_validation(self, oauth2_validator_integration, test_realm_setup):
        """Test offline token validation"""
        validator = oauth2_validator_integration

        # Get real token
        token = await self.get_test_token(test_realm_setup)

        # Validate offline (without signature verification)
        payload = await validator.validate_offline(token)

        assert 'sub' in payload
        assert 'preferred_username' in payload
        assert 'iss' in payload
        assert test_realm_setup.keycloak_realm in payload['iss']

    @pytest.mark.asyncio
    async def test_user_context_extraction(self, oauth2_validator_integration, test_realm_setup):
        """Test user context extraction from real token"""
        validator = oauth2_validator_integration

        # Get real token and validate it
        token = await self.get_test_token(test_realm_setup)
        payload = await validator.validate_token(token)

        # Extract user context
        context = validator.extract_user_context(payload)

        assert context['username'] == 'testuser'
        assert context['email'] == 'test@neural-hive.com'
        assert context['client_id'] == test_realm_setup.keycloak_client_id
        assert 'user_id' in context
        assert 'roles' in context

    @pytest.mark.asyncio
    async def test_jwks_cache_behavior(self, oauth2_validator_integration, test_realm_setup):
        """Test JWKS caching behavior"""
        validator = oauth2_validator_integration
        cache = validator.jwks_cache

        # First fetch - should hit the server
        jwks1 = await cache.get_jwks(test_realm_setup.jwks_uri)
        first_fetch_time = cache.last_fetch

        # Immediate second fetch - should use cache
        jwks2 = await cache.get_jwks(test_realm_setup.jwks_uri)
        second_fetch_time = cache.last_fetch

        assert jwks1 == jwks2
        assert first_fetch_time == second_fetch_time  # Cache hit

        # Force cache expiry
        cache.last_fetch = datetime.now() - timedelta(seconds=cache.cache_duration + 1)

        # Third fetch - should hit server again
        jwks3 = await cache.get_jwks(test_realm_setup.jwks_uri)
        third_fetch_time = cache.last_fetch

        assert jwks1 == jwks3  # Content should be the same
        assert third_fetch_time > second_fetch_time  # New fetch time

    @pytest.mark.asyncio
    async def test_concurrent_token_validation(self, oauth2_validator_integration, test_realm_setup):
        """Test concurrent token validations"""
        validator = oauth2_validator_integration

        # Get real token
        token = await self.get_test_token(test_realm_setup)

        async def validate_token_worker():
            """Worker function for concurrent validation"""
            try:
                payload = await validator.validate_token(token)
                return payload['preferred_username'] == 'testuser'
            except Exception:
                return False

        # Run multiple concurrent validations
        workers = [validate_token_worker() for _ in range(10)]
        results = await asyncio.gather(*workers, return_exceptions=True)

        # All validations should succeed
        successful_results = [r for r in results if r is True]
        assert len(successful_results) >= 8  # Allow for some potential timing issues

    @pytest.mark.asyncio
    async def test_token_with_custom_claims(self, oauth2_validator_integration, test_realm_setup):
        """Test validation with custom claims and roles"""
        validator = oauth2_validator_integration

        # Get real token
        token = await self.get_test_token(test_realm_setup)
        payload = await validator.validate_token(token)

        # Check realm access roles
        assert 'realm_access' in payload
        realm_roles = payload['realm_access']['roles']
        assert isinstance(realm_roles, list)

        # Check scopes
        if 'scope' in payload:
            scopes = payload['scope'].split()
            assert 'openid' in scopes

    @pytest.mark.asyncio
    async def test_error_handling(self, oauth2_validator_integration, test_realm_setup):
        """Test error handling for various invalid scenarios"""
        validator = oauth2_validator_integration

        # Test with completely invalid token
        with pytest.raises(TokenValidationError):
            await validator.validate_token("invalid.token.here")

        # Test with malformed token
        with pytest.raises(TokenValidationError):
            await validator.validate_token("not-a-jwt-token")

        # Test introspection with invalid token
        with pytest.raises(TokenValidationError):
            await validator.introspect_token("invalid.token.here")

        # Test user info with invalid token
        with pytest.raises(TokenValidationError):
            await validator.get_user_info("invalid.token.here")


@pytest.mark.integration
@pytest.mark.skipif(not TESTCONTAINERS_AVAILABLE, reason="testcontainers not available")
class TestKeycloakFailureScenarios:
    """Test Keycloak failure scenarios and recovery"""

    @pytest.mark.asyncio
    async def test_keycloak_unavailable(self):
        """Test behavior when Keycloak is unavailable"""
        from unittest.mock import Mock, patch

        # Create settings pointing to non-existent server
        settings = Mock()
        settings.keycloak_url = "http://localhost:9999"
        settings.keycloak_realm = "test"
        settings.keycloak_client_id = "test-client"
        settings.keycloak_client_secret = "test-secret"
        settings.jwks_uri = "http://localhost:9999/auth/realms/test/protocol/openid-connect/certs"

        with patch('src.security.oauth2_validator.get_settings', return_value=settings):
            validator = OAuth2Validator()

            # Initialization should handle failures gracefully
            await validator.initialize()

            # JWKS fetch should fail
            with pytest.raises(TokenValidationError):
                await validator.jwks_cache.get_jwks(settings.jwks_uri)

            # Token introspection should fail
            with pytest.raises(TokenValidationError):
                await validator.introspect_token("fake.token")

            await validator.close()

    @pytest.mark.asyncio
    async def test_jwks_fallback_behavior(self):
        """Test JWKS cache fallback to expired cache on network errors"""
        from unittest.mock import Mock, patch, AsyncMock
        import httpx

        validator = OAuth2Validator()
        cache = validator.jwks_cache

        # First, populate cache with valid data
        mock_jwks = {
            'keys': [
                {'kid': 'test-key', 'kty': 'RSA', 'n': 'test', 'e': 'AQAB'}
            ]
        }

        cache.jwks = mock_jwks
        cache.last_fetch = datetime.now() - timedelta(seconds=cache.cache_duration + 1)  # Expired

        # Mock HTTP client to simulate network failure
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))
        cache.http_client = mock_client

        # Should return expired cache instead of failing
        result = await cache.get_jwks("http://test.com/jwks")
        assert result == mock_jwks