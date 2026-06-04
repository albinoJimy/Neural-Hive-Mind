"""
PII Masking e Privacy para Neural Hive-Mind.

Fornece processadores para mascarar dados sensíveis em logs
(GDPR/LGPD compliance - Artigo 25: Privacy by Design).
"""

import hashlib
from typing import Any

# Campos que contêm PII e devem ser mascarados
PII_FIELDS = {
    "user_id",
    "email",
    "username",
    "cpf",
    "phone",
    "telefone",
    "nome",
    "name",
    "full_name",
}


def hash_pii(value: str, salt: str = "nhm_pii_salt") -> str:
    """
    Faz hash de valor PII usando SHA-256.

    O hash permite correlação entre logs sem expor o valor original.

    Args:
        value: Valor sensível a fazer hash
        salt: Salt para hash (deve ser constante em produção)

    Returns:
        Hash SHA-256 do valor (primeiros 16 caracteres)

    Example:
        >>> hash_pii("user@example.com")
        'a1b2c3d4e5f6g7h8'
    """
    if not value:
        return ""

    combined = f"{salt}{value}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def mask_pii_processor(logger, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Processor structlog que mascarar campos PII.

    Campos configurados em PII_FIELDS são substituídos pelo seu hash.
    Um campo com o sufixo "_hash" é adicionado com o valor original mascarado.

    Args:
        logger: Logger (ignorado)
        method_name: Nome do método (ignorado)
        event_dict: Dicionário de eventos do structlog

    Returns:
        event_dict com campos PII mascarados

    Example:
        >>> event_dict = {"user_id": "alice@example.com", "action": "login"}
        >>> mask_pii_processor(None, "info", event_dict)
        {'user_id': 'a1b2c3d4...', 'user_id_hash': 'a1b2c3d4e5f6g7h8', 'action': 'login'}
    """
    for field in PII_FIELDS:
        if field in event_dict:
            original_value = event_dict[field]
            if isinstance(original_value, str) and original_value:
                hashed_value = hash_pii(original_value)
                # Substituir valor original por hash truncado
                event_dict[field] = f"{hashed_value[:8]}..."
                # Adicionar campo _hash para correlação
                event_dict[f"{field}_hash"] = hashed_value

    return event_dict


def mask_pii_deep(value: Any, pii_fields: set[str] = PII_FIELDS) -> Any:
    """
    Mascara PII em estruturas aninhadas (dicts, lists).

    Útil para sanitizar dados antes de enviar para serviços externos.

    Args:
        value: Valor a sanitizar (dict, list, ou primitivo)
        pii_fields: Conjunto de campos considerados PII

    Returns:
        Valor sanitizado com mesma estrutura
    """
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if k in pii_fields and isinstance(v, str):
                result[k] = hash_pii(v)[:8] + "..."
            else:
                result[k] = mask_pii_deep(v, pii_fields)
        return result

    if isinstance(value, list):
        return [mask_pii_deep(item, pii_fields) for item in value]

    return value


def get_safe_user_id(user_id: str) -> str:
    """
    Retorna versão segura de user_id para logs.

    Args:
        user_id: user_id original

    Returns:
        user_id mascarado (hash)
    """
    return hash_pii(user_id)


def get_safe_email(email: str) -> str:
    """
    Retorna versão segura de email para logs.

    Preserva domínio para análise, mas faz hash do usuário.

    Args:
        email: Email original

    Returns:
        Email mascarado (hash@domínio)

    Example:
        >>> get_safe_email("alice@example.com")
        'a1b2c3d4@example.com'
    """
    if not email or "@" not in email:
        return email

    username, domain = email.rsplit("@", 1)
    hashed_username = hash_pii(username)
    return f"{hashed_username}@{domain}"
