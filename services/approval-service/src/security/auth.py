"""
Autenticacao JWT com Keycloak

Fornece validacao de tokens JWT e verificacao de roles para admin.
"""

import structlog
import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer

from src.config.settings import Settings, get_settings

logger = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Cache de chaves publicas do Keycloak
_jwks_client: Optional[PyJWKClient] = None
_jwks_cache_time: Optional[datetime] = None
_JWKS_CACHE_TTL = timedelta(hours=1)


def get_jwks_client(settings: Settings) -> PyJWKClient:
    """
    Obtem cliente JWKS com cache

    Args:
        settings: Configuracoes da aplicacao

    Returns:
        PyJWKClient configurado
    """
    global _jwks_client, _jwks_cache_time

    now = datetime.utcnow()

    # Verifica se cache ainda e valido
    if _jwks_client and _jwks_cache_time:
        if now - _jwks_cache_time < _JWKS_CACHE_TTL:
            return _jwks_client

    # Cria novo cliente JWKS
    jwks_uri = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"

    _jwks_client = PyJWKClient(jwks_uri)
    _jwks_cache_time = now

    logger.info('JWKS client atualizado', jwks_uri=jwks_uri)

    return _jwks_client


async def verify_token(
    token: str,
    settings: Settings
) -> Dict[str, Any]:
    """
    Verifica e decodifica token JWT do Keycloak

    Args:
        token: Token JWT
        settings: Configuracoes da aplicacao

    Returns:
        Payload decodificado do token

    Raises:
        HTTPException: Se token invalido ou expirado
    """
    try:
        # Obtem cliente JWKS
        jwks_client = get_jwks_client(settings)

        # Obtem chave de assinatura
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Configura validacao
        issuer = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        audience = settings.keycloak_client_id

        # Decodifica e valida token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256'],
            issuer=issuer,
            audience=audience,
            options={
                'verify_exp': True,
                'verify_nbf': True,
                'verify_iat': True,
                'verify_iss': True,
                'verify_aud': True,
            }
        )

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning('Token expirado')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token expirado',
            headers={'WWW-Authenticate': 'Bearer'}
        )
    except jwt.InvalidTokenError as e:
        logger.warning('Token invalido', error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token invalido',
            headers={'WWW-Authenticate': 'Bearer'}
        )
    except Exception as e:
        logger.error('Erro ao verificar token', error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Falha na autenticacao',
            headers={'WWW-Authenticate': 'Bearer'}
        )


def extract_user_info(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrai informacoes do usuario do payload do token

    Args:
        payload: Payload decodificado do JWT

    Returns:
        Dicionario com informacoes do usuario
    """
    return {
        'user_id': payload.get('sub'),
        'email': payload.get('email'),
        'name': payload.get('name'),
        'preferred_username': payload.get('preferred_username'),
        'roles': extract_roles(payload),
    }


def extract_roles(payload: Dict[str, Any]) -> list:
    """
    Extrai roles do payload do token

    Args:
        payload: Payload decodificado do JWT

    Returns:
        Lista de roles do usuario
    """
    roles = []

    # Roles de realm
    realm_access = payload.get('realm_access', {})
    roles.extend(realm_access.get('roles', []))

    # Roles de resource (client)
    resource_access = payload.get('resource_access', {})
    for client_roles in resource_access.values():
        roles.extend(client_roles.get('roles', []))

    return list(set(roles))


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """
    Dependencia FastAPI para obter usuario atual

    Args:
        token: Token JWT do header Authorization
        settings: Configuracoes da aplicacao

    Returns:
        Informacoes do usuario autenticado

    Raises:
        HTTPException: Se nao autenticado
    """
    # Auth bypass for testing when REQUIRE_AUTH is disabled
    if getattr(settings, 'require_auth', True) == False:
        return {
            'user_id': 'test-admin',
            'email': 'admin@test.com',
            'name': 'Test Admin',
            'preferred_username': 'admin',
            'roles': ['neural-hive-admin', 'user'],
        }

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Autenticacao obrigatoria',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    payload = await verify_token(token, settings)
    user_info = extract_user_info(payload)

    logger.debug(
        'Usuario autenticado',
        user_id=user_info['user_id'],
        email=user_info.get('email')
    )

    return user_info


async def get_current_admin_user(
    user: Dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """
    Dependencia FastAPI para obter usuario admin atual

    Args:
        user: Usuario autenticado
        settings: Configuracoes da aplicacao

    Returns:
        Informacoes do usuario admin

    Raises:
        HTTPException: Se nao for admin
    """
    admin_role = settings.admin_role_name

    if admin_role not in user.get('roles', []):
        logger.warning(
            'Acesso negado - usuario nao e admin',
            user_id=user['user_id'],
            required_role=admin_role,
            user_roles=user.get('roles', [])
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f'Acesso negado. Role {admin_role} obrigatoria.'
        )

    logger.debug(
        'Admin autenticado',
        user_id=user['user_id'],
        email=user.get('email')
    )

    return user
