"""Módulo de autenticação OAuth2 + mTLS"""
import jwt
from typing import Dict, Any
from fastapi import HTTPException, status


async def verify_token(token: str) -> Dict[str, Any]:
    """Verificar e decodificar token JWT"""
    try:
        # Placeholder - implementar verificação real
        payload = jwt.decode(token, "secret", algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
        )


async def get_current_user(token: str) -> Dict[str, Any]:
    """Obter usuário atual do token"""
    return await verify_token(token)
