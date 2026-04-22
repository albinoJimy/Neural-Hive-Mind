"""Testes unitários para TokenService."""

from src.services.token_service import TokenPair, TokenPayload, TokenService, get_token_service


class TestTokenService:
    """Testes para TokenService."""

    def test_singleton(self):
        """Testa se get_token_service retorna singleton."""
        service1 = get_token_service()
        service2 = get_token_service()
        assert service1 is service2

    def test_create_access_token(self):
        """Testa criação de access token."""
        service = TokenService()
        token = service.create_access_token("user-123", ["read", "write"])

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_permissions(self):
        """Testa criação de access token com permissões."""
        service = TokenService()
        permissions = ["read", "write", "delete"]
        token = service.create_access_token("user-123", permissions)

        payload = service.decode_token(token)
        assert payload is not None
        assert payload.permissions == permissions

    def test_create_access_token_with_extra_claims(self):
        """Testa criação de access token com claims extras."""
        service = TokenService()
        extra_claims = {"name": "John Doe", "role": "admin"}
        token = service.create_access_token("user-123", ["admin"], extra_claims)

        payload = service.decode_token(token)
        assert payload is not None
        assert payload.sub == "user-123"

    def test_create_refresh_token(self):
        """Testa criação de refresh token."""
        service = TokenService()
        token = service.create_refresh_token("user-123")

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_pair(self):
        """Testa criação de par de tokens."""
        service = TokenService()
        token_pair = service.create_token_pair("user-123", ["read", "write"])

        assert isinstance(token_pair, TokenPair)
        assert token_pair.access_token is not None
        assert token_pair.refresh_token is not None
        assert token_pair.token_type == "bearer"
        assert token_pair.expires_in > 0

    def test_decode_valid_token(self):
        """Testa decodificação de token válido."""
        service = TokenService()
        original_token = service.create_access_token("user-123", ["read"])

        payload = service.decode_token(original_token)

        assert payload is not None
        assert isinstance(payload, TokenPayload)
        assert payload.sub == "user-123"
        assert payload.type == "access"

    def test_decode_invalid_token(self):
        """Testa decodificação de token inválido."""
        service = TokenService()
        payload = service.decode_token("invalid.token.here")

        assert payload is None

    def test_verify_access_token_valid(self):
        """Testa verificação de access token válido."""
        service = TokenService()
        token = service.create_access_token("user-123", ["read", "write"])

        payload = service.verify_access_token(token)

        assert payload is not None
        assert payload.sub == "user-123"
        assert payload.type == "access"

    def test_verify_access_token_with_permissions(self):
        """Testa verificação de access token com permissões."""
        service = TokenService()
        token = service.create_access_token("user-123", ["read", "write"])

        # Permissões suficientes
        payload = service.verify_access_token(token, ["read"])
        assert payload is not None

        # Permissões insuficientes
        payload = service.verify_access_token(token, ["admin"])
        assert payload is None

    def test_verify_access_token_refresh_rejected(self):
        """Testa que refresh token é rejeitado como access token."""
        service = TokenService()
        refresh_token = service.create_refresh_token("user-123")

        payload = service.verify_access_token(refresh_token)
        assert payload is None

    def test_verify_refresh_token_valid(self):
        """Testa verificação de refresh token válido."""
        service = TokenService()
        token = service.create_refresh_token("user-123")

        payload = service.verify_refresh_token(token)

        assert payload is not None
        assert payload.sub == "user-123"
        assert payload.type == "refresh"

    def test_verify_refresh_token_access_rejected(self):
        """Testa que access token é rejeitado como refresh token."""
        service = TokenService()
        access_token = service.create_access_token("user-123", ["read"])

        payload = service.verify_refresh_token(access_token)
        assert payload is None

    def test_refresh_access_token(self):
        """Testa renovação de access token."""
        service = TokenService()
        refresh_token = service.create_refresh_token("user-123", permissions=["read", "write"])

        # Mock para manter permissões no refresh
        new_access = service.refresh_access_token(refresh_token)

        assert new_access is not None

        payload = service.verify_access_token(new_access)
        assert payload is not None
        assert payload.sub == "user-123"

    def test_refresh_with_invalid_token(self):
        """Testa renovação com token inválido."""
        service = TokenService()
        new_access = service.refresh_access_token("invalid.token")

        assert new_access is None

    def test_get_user_id_from_token(self):
        """Testa extração de user_id do token."""
        service = TokenService()
        token = service.create_access_token("user-123", ["read"])

        user_id = service.get_user_id_from_token(token)

        assert user_id == "user-123"

    def test_get_user_id_from_invalid_token(self):
        """Testa extração de user_id de token inválido."""
        service = TokenService()
        user_id = service.get_user_id_from_token("invalid.token")

        assert user_id is None

    def test_token_expiration(self):
        """Testa que token expirado é rejeitado."""
        import time

        service = TokenService()
        # Criar token expirado (timestamp no passado)
        import jwt

        now_ts = int(time.time())
        expired_payload = {
            "sub": "user-123",
            "exp": now_ts - 3600,  # expirou há 1 hora
            "iat": now_ts - 7200,  # criado há 2 horas
            "jti": "test-jti",
            "type": "access",
            "permissions": [],
        }
        expired_token = jwt.encode(
            expired_payload, service._secret_key, algorithm=service._algorithm
        )

        payload = service.verify_access_token(expired_token)
        assert payload is None

    def test_token_payload_fields(self):
        """Testa campos do TokenPayload."""
        service = TokenService()
        token = service.create_access_token("user-456", ["admin", "write"])

        payload = service.decode_token(token)

        assert payload.sub == "user-456"
        assert payload.type == "access"
        assert payload.permissions == ["admin", "write"]
        assert payload.iat > 0
        assert payload.exp > payload.iat
        assert len(payload.jti) > 0
