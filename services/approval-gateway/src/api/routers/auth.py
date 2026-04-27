"""Router REST para Autenticação JWT.

Endpoints para login, refresh de token e validação.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from src.api.auth import TokenPayload, get_current_user
from src.services.token_service import TokenService, get_token_service
from structlog import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# Request/Response Schemas
class LoginRequest(BaseModel):
    """Requisição de login."""

    username: str = Field(..., description="Nome de usuário")
    password: str = Field(..., description="Senha (será validada externamente)")
    email: Optional[EmailStr] = Field(None, description="Email do usuário")


class LoginResponse(BaseModel):
    """Resposta de login com tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
    user_id: str
    permissions: list[str]


class RefreshRequest(BaseModel):
    """Requisição de refresh."""

    refresh_token: str = Field(..., description="Token de refresh válido")


class RefreshResponse(BaseModel):
    """Resposta de refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class ValidateResponse(BaseModel):
    """Resposta de validação."""

    valid: bool
    user_id: Optional[str] = None
    permissions: list[str] = []
    expires_at: Optional[int] = None


# Mock user database - em produção, usar serviço real de usuários
MOCK_USERS = {
    "admin": {
        "user_id": "admin-001",
        "password": "admin123",  # Em produção: hash
        "permissions": ["admin", "approve", "review", "read"],
    },
    "approver": {
        "user_id": "approver-001",
        "password": "approve123",
        "permissions": ["approve", "review", "read"],
    },
    "reviewer": {
        "user_id": "reviewer-001",
        "password": "review123",
        "permissions": ["review", "read"],
    },
    "reader": {"user_id": "reader-001", "password": "read123", "permissions": ["read"]},
}


def verify_credentials(username: str, password: str) -> Optional[dict]:
    """
    Verifica credenciais do usuário (MOCK).

    Args:
        username: Nome de usuário
        password: Senha

    Returns:
        Dados do usuário se válido, None caso contrário
    """
    user = MOCK_USERS.get(username)

    if user and user["password"] == password:
        return {"user_id": user["user_id"], "permissions": user["permissions"]}

    return None


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Login e geração de tokens",
)
async def login(
    request: LoginRequest, token_service: TokenService = Depends(get_token_service)
) -> LoginResponse:
    """
    Autentica usuário e retorna par de tokens (access + refresh).

    O access token é usado para autenticar requisições.
    O refresh token é usado para obter um novo access token quando expirar.
    """
    # Verificar credenciais
    user_data = verify_credentials(request.username, request.password)

    if not user_data:
        logger.warning("login_failed", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Gerar tokens
    token_pair = token_service.create_token_pair(
        user_id=user_data["user_id"], permissions=user_data["permissions"]
    )

    logger.info("login_success", username=request.username, user_id=user_data["user_id"])

    return LoginResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
        expires_in=token_pair.expires_in,
        user_id=user_data["user_id"],
        permissions=user_data["permissions"],
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Renovar access token",
)
async def refresh(
    request: RefreshRequest, token_service: TokenService = Depends(get_token_service)
) -> RefreshResponse:
    """
    Renova o access token usando um refresh token válido.

    O refresh token não é renovado - o cliente deve usar o access token
    para obter um novo par quando necessário.
    """
    new_token = token_service.refresh_access_token(request.refresh_token)

    if not new_token:
        logger.warning("refresh_failed", token_prefix=request.refresh_token[:10])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Obter tempo de expiração
    payload = token_service.decode_token(new_token)

    logger.info("refresh_success")

    return RefreshResponse(
        access_token=new_token,
        token_type="bearer",
        expires_in=int(payload.exp - payload.iat) if payload else 1800,
    )


@router.post(
    "/validate",
    response_model=ValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validar token",
)
async def validate_token(
    current_user: Optional[TokenPayload] = Depends(get_current_user),
) -> ValidateResponse:
    """
    Valida um token de acesso e retorna informações do usuário.

    Se o token for inválido, retorna valid=False.
    """
    if not current_user:
        return ValidateResponse(valid=False)

    return ValidateResponse(
        valid=True,
        user_id=current_user.sub,
        permissions=current_user.permissions,
        expires_at=current_user.exp,
    )


@router.get("/me", response_model=dict, summary="Informações do usuário atual")
async def get_current_user_info(current_user: TokenPayload = Depends(get_current_user)) -> dict:
    """
    Retorna informações do usuário autenticado.
    """
    return {
        "user_id": current_user.sub,
        "permissions": current_user.permissions,
        "token_id": current_user.jti,
        "issued_at": current_user.iat,
        "expires_at": current_user.exp,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout")
async def logout(current_user: TokenPayload = Depends(get_current_user)) -> None:
    """
    Faz logout do usuário.

    Nota: Em uma implementação real, o token seria adicionado
    a uma blacklist. Como JWTs são stateless, o cliente deve
    simplesmente descartar o token.
    """
    logger.info("logout", user_id=current_user.sub)
    # Em produção: adicionar token à blacklist no Redis
