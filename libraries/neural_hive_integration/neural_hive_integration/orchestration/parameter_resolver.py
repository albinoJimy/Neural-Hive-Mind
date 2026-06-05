"""
Resolução de parâmetros semânticos → técnicos para execution tickets.

Contexto do problema (lacuna arquitetural):
O STE decompõe intents por dois caminhos com contratos de `parameters` distintos
para o mesmo `task_type`:
  - Caminho template (decomposition_templates): gera parâmetros TÉCNICOS prontos
    (ex.: query → {collection, filter, limit}).
  - Caminho heurístico (dag_generator._create_task_from_objective): gera parâmetros
    SEMÂNTICOS (ex.: query → {objective, entities, constraints}).

A cadeia de orquestração copiava os `parameters` tal-qual para o ExecutionTicket,
e os executores do worker exigem o contrato técnico (ex.: query_executor exige
`collection`). Quando uma intent caía no caminho heurístico, o ticket falhava com
`Missing required parameters: ['collection']`.

Este módulo é a camada de tradução central: recebe os `parameters` de uma task e,
quando estão em forma semântica, completa-os com o contrato técnico que o executor
espera. É **idempotente** — se os parâmetros já são técnicos (caminho template), são
devolvidos sem alteração.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Database onde residem as collections de conhecimento/contexto do NHM.
# (O default do query_executor é `neural_hive_workers`, que só contém a DLQ;
# os dados de domínio estão em `neural_hive`.)
DEFAULT_QUERY_DATABASE = "neural_hive"

# Mapeamento domínio semântico → collection MongoDB de contexto.
# Collections confirmadas em `neural_hive`. O fallback `operational_context`
# existe e serve de alvo genérico para queries de análise.
DOMAIN_COLLECTION_MAP = {
    "security": "security_incidents",
    "architecture": "operational_context",
    "technical": "operational_context",
    "business": "insights",
    "data": "insights",
    "evolution": "optimization_ledger",
    "behavior": "specialist_feedback",
    "quality": "validation_audit",
    "performance": "telemetry_buffer",
    "operational": "operational_context",
}
FALLBACK_COLLECTION = "operational_context"

# Limite conservador para queries best-effort (devolve contexto recente sem
# sobrecarregar). O caminho template define o seu próprio limit, que é respeitado.
DEFAULT_QUERY_LIMIT = 10


def _normalize_entities(raw: Any) -> list[str]:
    """Normaliza o campo `entities` para uma lista de strings.

    As entities podem chegar como lista de dicts (`[{"value": "OAuth2"}, ...]`),
    lista de strings, ou string JSON serializada (efeito do schema Avro
    `map<string,string>`). Devolve sempre uma lista de strings limpa.
    """
    if not raw:
        return []
    # String serializada (ex.: "[{'value': 'OAuth2', ...}]") → tentar desserializar.
    if isinstance(raw, str):
        try:
            raw = json.loads(raw.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            return [raw] if raw.strip() else []
    if isinstance(raw, dict):
        raw = [raw]
    result: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            value = item.get("value") or item.get("name") or item.get("text")
            if value:
                result.append(str(value))
        elif item:
            result.append(str(item))
    return result


def _resolve_query_parameters(parameters: dict[str, Any], domain: str | None) -> dict[str, Any]:
    """Completa parâmetros de uma task `query` com o contrato técnico do executor.

    - Caminho template (já tem `collection`): preserva collection/filter/limit, mas
      garante `query_type` e `database` (o template não os fornece, pelo que a query
      iria ao DB default `neural_hive_workers`, vazio, em vez de `neural_hive`).
    - Caminho heurístico (sem `collection`): deriva collection/filter/limit/database
      a partir do domínio e das entities (best-effort).
    """
    # Caminho template: já tem collection; apenas garantir query_type+database.
    if parameters.get("collection"):
        resolved = dict(parameters)
        resolved.setdefault("query_type", "mongodb")
        resolved.setdefault("database", DEFAULT_QUERY_DATABASE)
        return resolved

    domain_key = (domain or "").strip().lower()
    collection = DOMAIN_COLLECTION_MAP.get(domain_key, FALLBACK_COLLECTION)
    entities = _normalize_entities(parameters.get("entities"))

    resolved = dict(parameters)
    resolved["query_type"] = parameters.get("query_type", "mongodb")
    resolved["collection"] = collection
    resolved["database"] = parameters.get("database", DEFAULT_QUERY_DATABASE)
    # Filtro best-effort: vazio devolve o contexto mais recente da collection do
    # domínio (garante execução com sucesso). As entities resolvidas ficam
    # registadas para rastreabilidade/observabilidade.
    resolved.setdefault("filter", {})
    resolved.setdefault("limit", DEFAULT_QUERY_LIMIT)
    resolved["resolved_from_entities"] = entities

    logger.info(
        "query_parameters_resolved",
        domain=domain_key or "unknown",
        collection=collection,
        database=resolved["database"],
        entities_count=len(entities),
    )
    return resolved


def resolve_ticket_parameters(
    task_type: str,
    parameters: dict[str, Any] | None,
    *,
    domain: str | None = None,
) -> dict[str, Any]:
    """Resolve os `parameters` de uma task para o contrato técnico do executor.

    Ponto único de tradução semântica→técnica, chamado na geração de tickets
    (tanto no caminho Temporal como no flow_c/Kafka).

    Args:
        task_type: Tipo da task já normalizado (ex.: "QUERY", "TRANSFORM").
        parameters: Parâmetros da task vindos do CognitivePlan (semânticos ou técnicos).
        domain: Domínio semântico da task (ex.: "security"), usado no mapeamento.

    Returns:
        Parâmetros completados com o contrato técnico. Idempotente para parâmetros
        já técnicos e para task_types sem resolução específica.
    """
    params = dict(parameters or {})
    normalized = (task_type or "").strip().upper()

    if normalized == "QUERY":
        return _resolve_query_parameters(params, domain)

    # Outros task_types (TRANSFORM/VALIDATE/EXECUTE/...) ainda não têm resolução
    # semântica dedicada; o caminho template já fornece os seus parâmetros técnicos
    # (input_data, policy_path) e os executores aplicam defaults seguros.
    return params
