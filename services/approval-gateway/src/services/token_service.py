"""Serviço de Token JWT para Approval Gateway.

Gerencia geração, validação e refresh de tokens JWT
para autenticação e autorização.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from pydantic import BaseModel, Field

from src.config.settings import get_settings

settings = get_settings()


class TokenPayload(BaseModel):
    """Payload do token JWT."""

    sub: str = Field(..., description="Subject - user ID")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")
    jti: str = Field(..., description="JWT ID - unique token identifier")
    type: str = Field(..., description="Token type: access/refresh")
    permissions: list[str] = Field(
        default_factory=list,
        description="User permissions"
    )


class TokenPair(BaseModel):
    """Par de tokens (access + refresh)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class TokenService:
    """Serviço para gerenciamento de tokens JWT."""

    def __init__(self):
        """Inicializa o serviço de tokens."""
        self._secret_key = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._access_expire_minutes = settings.jwt_access_token_expire_minutes
        self._refresh_expire_days = settings.jwt_refresh_token_expire_days

    def create_access_token(
        self,
        user_id: str,
        permissions: Optional[list[str]] = None,
        extra_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Cria um token de acesso.

        Args:
            user_id: ID do usuário
            permissions: Lista de permissões do usuário
            extra_claims: Claims adicionais

        Returns:
            Token JWT codificado
        """
        now_ts = int(time.time())
        expire_ts = now_ts + (self._access_expire_minutes * 60)

        payload = {
            "sub": user_id,
            "exp": expire_ts,
            "iat": now_ts,
            "jti": str(uuid.uuid4()),
            "type": "access",
            "permissions": permissions or [],
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(
        self,
        user_id: str,
        permissions: Optional[list[str]] = None,
        extra_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Cria um token de refresh.

        Args:
            user_id: ID do usuário
            permissions: Lista de permissões (para preservar no refresh)
            extra_claims: Claims adicionais

        Returns:
            Token JWT codificado
        """
        now_ts = int(time.time())
        expire_ts = now_ts + (self._refresh_expire_days * 86400)

        payload = {
            "sub": user_id,
            "exp": expire_ts,
            "iat": now_ts,
            "jti": str(uuid.uuid4()),
            "type": "refresh",
            "permissions": permissions or [],  # Preservar permissões para refresh
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_token_pair(
        self,
        user_id: str,
        permissions: Optional[list[str]] = None
    ) -> TokenPair:
        """
        Cria um par de tokens (access + refresh).

        Args:
            user_id: ID do usuário
            permissions: Lista de permissões do usuário

        Returns:
            TokenPair com access_token e refresh_token
        """
        access_token = self.create_access_token(user_id, permissions)
        refresh_token = self.create_refresh_token(user_id, permissions)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self._access_expire_minutes * 60
        )

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """
        Decodifica e valida um token JWT.

        Args:
            token: Token JWT codificado

        Returns:
            TokenPayload se válido, None se inválido
        """
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm]
            )

            return TokenPayload(**payload)

        except JWTError as e:
            # Token inválido ou expirado
            return None

    def verify_access_token(
        self,
        token: str,
        required_permissions: Optional[list[str]] = None
    ) -> Optional[TokenPayload]:
        """
        Verifica um token de acesso.

        Args:
            token: Token JWT codificado
            required_permissions: Permissões obrigatórias

        Returns:
            TokenPayload se válido, None se inválido
        """
        payload = self.decode_token(token)

        if not payload:
            return None

        # Verificar se é token de acesso
        if payload.type != "access":
            return None

        # Verificar permissões
        if required_permissions:
            user_permissions = set(payload.permissions)
            required = set(required_permissions)
            if not required.issubset(user_permissions):
                return None

        return payload

    def verify_refresh_token(self, token: str) -> Optional[TokenPayload]:
        """
        Verifica um token de refresh.

        Args:
            token: Token JWT codificado

        Returns:
            TokenPayload se válido, None se inválido
        """
        payload = self.decode_token(token)

        if not payload:
            return None

        # Verificar se é token de refresh
        if payload.type != "refresh":
            return None

        return payload

    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Gera um novo access_token usando um refresh_token.

        Args:
            refresh_token: Token de refresh válido

        Returns:
            Novo access_token ou None se refresh inválido
        """
        payload = self.verify_refresh_token(refresh_token)

        if not payload:
            return None

        # Criar novo access token com as mesmas permissões
        return self.create_access_token(
            user_id=payload.sub,
            permissions=payload.permissions
        )

    def get_user_id_from_token(self, token: str) -> Optional[str]:
        """
        Extrai o user_id de um token.

        Args:
            token: Token JWT codificado

        Returns:
            User ID ou None se inválido
        """
        payload = self.decode_token(token)
        return payload.sub if payload else None


# Singleton
_token_service: Optional[TokenService] = None


def get_token_service() -> TokenService:
    """Retorna instância singleton do TokenService."""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service
