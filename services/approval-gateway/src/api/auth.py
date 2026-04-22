"""Middleware JWT para Approval Gateway.

Fornece dependências FastAPI para autenticação e autorização
via tokens JWT.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.services.token_service import TokenPayload, TokenService, get_token_service

# Security scheme para FastAPI (Bearer token)
security = HTTPBearer(auto_error=False)


class UnauthorizedError(HTTPException):
    """Erro para requisições não autorizadas."""

    def __init__(self, detail: str = "Não autenticado"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenError(HTTPException):
    """Erro para requisições sem permissão."""

    def __init__(self, detail: str = "Sem permissão"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token_service: TokenService = Depends(get_token_service),
) -> Optional[TokenPayload]:
    """
    Obtém o usuário atual do token JWT (opcional).

    Retorna None se não houver token ou se for inválido.
    Útil para endpoints que funcionam com ou sem autenticação.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = token_service.verify_access_token(token)

    return payload


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token_service: TokenService = Depends(get_token_service),
) -> TokenPayload:
    """
    Obtém o usuário atual do token JWT (obrigatório).

    Raises:
        UnauthorizedError: Se não houver token ou for inválido
    """
    if credentials is None:
        raise UnauthorizedError("Token de acesso não fornecido")

    token = credentials.credentials
    payload = token_service.verify_access_token(token)

    if payload is None:
        raise UnauthorizedError("Token inválido ou expirado")

    return payload


async def get_current_user_with_permissions(
    required_permissions: list[str],
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token_service: TokenService = Depends(get_token_service),
) -> TokenPayload:
    """
    Obtém o usuário atual com verificação de permissões.

    Args:
        required_permissions: Lista de permissões obrigatórias

    Raises:
        UnauthorizedError: Se não houver token ou for inválido
        ForbiddenError: Se o usuário não tiver as permissões necessárias
    """
    if credentials is None:
        raise UnauthorizedError("Token de acesso não fornecido")

    token = credentials.credentials
    payload = token_service.verify_access_token(token, required_permissions)

    if payload is None:
        # Verificar se é token inválido ou falta de permissão
        base_payload = token_service.decode_token(token)
        if base_payload is None:
            raise UnauthorizedError("Token inválido ou expirado")
        else:
            raise ForbiddenError(f"Permissões insuficientes. Requerido: {required_permissions}")

    return payload


class PermissionChecker:
    """Factory para criar dependências de verificação de permissões."""

    def __init__(self, required_permissions: list[str]):
        """
        Inicializa o verificador.

        Args:
            required_permissions: Lista de permissões obrigatórias
        """
        self.required_permissions = required_permissions

    def __call__(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        token_service: TokenService = Depends(get_token_service),
    ) -> TokenPayload:
        """
        Verifica o token e as permissões.

        Raises:
            UnauthorizedError: Se não houver token ou for inválido
            ForbiddenError: Se o usuário não tiver as permissões necessárias
        """
        if credentials is None:
            raise UnauthorizedError("Token de acesso não fornecido")

        token = credentials.credentials
        payload = token_service.verify_access_token(token, self.required_permissions)

        if payload is None:
            # Verificar se é token inválido ou falta de permissão
            base_payload = token_service.decode_token(token)
            if base_payload is None:
                raise UnauthorizedError("Token inválido ou expirado")
            else:
                raise ForbiddenError(
                    f"Permissões insuficientes. Requerido: {self.required_permissions}"
                )

        return payload


# Dependências comuns para reuse
require_admin = PermissionChecker(["admin"])
require_approver = PermissionChecker(["approve"])
require_reviewer = PermissionChecker(["review"])


def get_user_id_from_payload(payload: TokenPayload) -> str:
    """
    Extrai o user_id do TokenPayload.

    Args:
        payload: Token payload

    Returns:
        User ID (subject do token)
    """
    return payload.sub


def require_permission(permission: str) -> PermissionChecker:
    """
    Cria um verificador para uma permissão única.

    Args:
        permission: Permissão obrigatória

    Returns:
        PermissionChecker configurado
    """
    return PermissionChecker([permission])


def require_any_permission(*permissions: str) -> PermissionChecker:
    """
    Cria um verificador que aceita qualquer uma das permissões.

    Nota: A implementação atual exige todas. Para OR logic,
    use verificação manual no endpoint.

    Args:
        *permissions: Permissões aceitas (qualquer uma)

    Returns:
        PermissionChecker configurado (com lógica AND por padrão)
    """
    return PermissionChecker(list(permissions))
