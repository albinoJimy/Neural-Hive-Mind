"""Módulo de autenticação OAuth2 + mTLS"""

from typing import Any

import jwt
from config.settings import get_settings
from fastapi import HTTPException, status


async def verify_token(token: str) -> dict[str, Any]:
    """Verificar e decodificar token JWT.

    Usa JWT_SECRET da Settings que tem prioridade:
    1. Vault (se habilitado e disponível)
    2. jwt_secret_key (config)
    3. JWT_SECRET environment variable
    """
    try:
        settings = get_settings()
        # Usar a propriedade JWT_SECRET que busca do Vault se disponível
        secret = settings.JWT_SECRET
        return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


async def get_current_user(token: str) -> dict[str, Any]:
    """Obter usuário atual do token"""
    return await verify_token(token)
