"""
Modelos Pydantic e funções para geração/validação de tokens JWT.
"""
import time
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
import jwt as pyjwt

from . import ExecutionTicket, _get_enum_value


class JWTTokenPayload(BaseModel):
    """Claims do token JWT."""

    sub: str = Field(..., description='Subject = ticket_id')
    iss: str = Field(..., description='Issuer = neural-hive-mind')
    aud: str = Field(..., description='Audience = worker-agents')
    exp: int = Field(..., description='Expiration timestamp')
    iat: int = Field(..., description='Issued at timestamp')
    jti: str = Field(..., description='JWT ID (UUID)')
    ticket_id: str = Field(..., description='ID do ticket')
    plan_id: str = Field(..., description='ID do plano')
    intent_id: str = Field(..., description='ID da intenção')
    task_type: str = Field(..., description='Tipo de tarefa')
    security_level: str = Field(..., description='Nível de segurança')
    required_capabilities: List[str] = Field(..., description='Capacidades necessárias')
    scopes: List[str] = Field(..., description='Escopos de autorização')


class JWTToken(BaseModel):
    """Token JWT response."""

    access_token: str = Field(..., description='JWT encoded')
    token_type: str = Field(default='Bearer', description='Tipo do token')
    expires_in: int = Field(..., description='Segundos até expiração')
    expires_at: int = Field(..., description='Timestamp de expiração')
    ticket_id: str = Field(..., description='ID do ticket')
    scopes: List[str] = Field(..., description='Escopos do token')


def generate_token(
    ticket: ExecutionTicket,
    secret_key: str,
    algorithm: str = 'HS256',
    expiration_seconds: int = 3600
) -> JWTToken:
    """
    Gera token JWT escopado para o ticket.

    Args:
        ticket: Instância de ExecutionTicket
        secret_key: Chave secreta para assinatura
        algorithm: Algoritmo JWT (default: HS256)
        expiration_seconds: Tempo de expiração em segundos (default: 1 hora)

    Returns:
        JWTToken com access_token e metadados
    """
    current_time = int(time.time())
    expiration_time = current_time + expiration_seconds

    # Definir scopes baseados no task_type e security_level
    # Usar _get_enum_value para lidar com Enum ou string (use_enum_values=True)
    task_type_str = _get_enum_value(ticket.task_type)
    security_level_str = _get_enum_value(ticket.security_level)

    scopes = [
        'ticket:read',
        'ticket:update',
        f'task:{task_type_str.lower()}'
    ]

    if security_level_str in ['CONFIDENTIAL', 'RESTRICTED']:
        scopes.append('security:elevated')

    # Criar payload
    payload = JWTTokenPayload(
        sub=ticket.ticket_id,
        iss='neural-hive-mind',
        aud='worker-agents',
        exp=expiration_time,
        iat=current_time,
        jti=str(uuid.uuid4()),
        ticket_id=ticket.ticket_id,
        plan_id=ticket.plan_id,
        intent_id=ticket.intent_id,
        task_type=task_type_str,
        security_level=security_level_str,
        required_capabilities=ticket.required_capabilities,
        scopes=scopes
    )

    # Gerar JWT
    encoded_jwt = pyjwt.encode(
        payload.model_dump(),
        secret_key,
        algorithm=algorithm
    )

    return JWTToken(
        access_token=encoded_jwt,
        token_type='Bearer',
        expires_in=expiration_seconds,
        expires_at=expiration_time,
        ticket_id=ticket.ticket_id,
        scopes=scopes
    )


def decode_token(
    token: str,
    secret_key: str,
    algorithm: str = 'HS256'
) -> JWTTokenPayload:
    """
    Decodifica e valida token JWT.

    Args:
        token: Token JWT encoded
        secret_key: Chave secreta para validação
        algorithm: Algoritmo JWT (default: HS256)

    Returns:
        JWTTokenPayload com claims decodificados

    Raises:
        jwt.ExpiredSignatureError: Token expirado
        jwt.InvalidTokenError: Token inválido
    """
    decoded = pyjwt.decode(
        token,
        secret_key,
        algorithms=[algorithm],
        audience='worker-agents',
        issuer='neural-hive-mind'
    )
    return JWTTokenPayload(**decoded)


def validate_token(
    token: str,
    ticket_id: str,
    secret_key: str,
    algorithm: str = 'HS256'
) -> bool:
    """
    Valida token JWT e verifica se pertence ao ticket_id.

    Args:
        token: Token JWT encoded
        ticket_id: ID do ticket esperado
        secret_key: Chave secreta para validação
        algorithm: Algoritmo JWT (default: HS256)

    Returns:
        True se válido e pertence ao ticket_id, False caso contrário
    """
    try:
        payload = decode_token(token, secret_key, algorithm)
        return payload.ticket_id == ticket_id
    except Exception:
        return False
