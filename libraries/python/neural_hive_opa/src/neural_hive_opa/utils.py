"""
Funções utilitárias para OPA Client.

Helpers para construção de URLs, serialização, etc.
"""
import hashlib
import json
from typing import Any


def _build_opa_url(base_url: str, policy_path: str) -> str:
    """
    Constrói URL completa para chamada OPA.

    Args:
        base_url: URL base do OPA (ex: http://opa:8181)
        policy_path: Caminho da política (ex: neuralhive/orchestrator/allow)

    Returns:
        URL completa para a API do OPA
    """
    # Normalizar base_url (remover barra final se existir)
    base_url = base_url.rstrip("/")

    # Remover prefixos desnecessários do policy_path
    policy_path = policy_path.lstrip("/")

    # Construir URL no formato: {base_url}/v1/data/{policy_path}
    return f"{base_url}/v1/data/{policy_path}"


def _generate_cache_key(policy_path: str, input_data: dict[str, Any]) -> str:
    """
    Gera chave de cache única para política e input.

    Args:
        policy_path: Caminho da política
        input_data: Dados de entrada

    Returns:
        Chave hash única
    """
    # Criar hash baseado em policy + input ordenado
    cache_input = {"policy": policy_path, "input": _sort_dict(input_data)}
    cache_str = json.dumps(cache_input, sort_keys=True)
    return hashlib.sha256(cache_str.encode()).hexdigest()


def _sort_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Ordena dict recursivamente para cache key consistente.

    Args:
        data: Dicionário a ordenar

    Returns:
        Dicionário ordenado
    """
    if not isinstance(data, dict):
        return data

    return {k: _sort_dict(v) if isinstance(v, dict) else v for k, v in sorted(data.items())}


def _sanitize_input_data(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitiza dados de entrada para OPA.

    Remove valores None e converte tipos não suportados.

    Args:
        input_data: Dados de entrada

    Returns:
        Dados sanitizados
    """
    if not isinstance(input_data, dict):
        return {"value": str(input_data)}

    return {k: v for k, v in input_data.items() if v is not None}


def _extract_decision_id(raw_response: dict[str, Any]) -> str | None:
    """
    Extrai decision ID da resposta OPA.

    Args:
        raw_response: Resposta bruta do OPA

    Returns:
        Decision ID ou None
    """
    # OPA pode retornar decision_id em diferentes formatos
    return raw_response.get("decision_id") or raw_response.get("id")


def _is_success_status(status: int) -> bool:
    """
    Verifica se status HTTP indica sucesso.

    Args:
        status: Status HTTP

    Returns:
        True se sucesso (2xx)
    """
    return 200 <= status < 300
