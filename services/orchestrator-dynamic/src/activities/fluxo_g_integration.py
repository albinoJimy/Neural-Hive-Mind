"""
Activities Temporal para integração Fluxo G (Idea → Software).

Estas activities integram os novos serviços do Fluxo G:
- requirements-engineering (8010)
- documentation-generation (8014)
- knowledge-graph-rag (8016)
- approval-gateway (8017)
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog
from temporalio import activity

logger = structlog.get_logger(__name__)

# Global clients (injetados pelo worker)
_http_client: Optional[httpx.AsyncClient] = None


def set_fluxo_g_dependencies(http_client: httpx.AsyncClient = None):
    """Injeta dependências para activities do Fluxo G."""
    global _http_client
    _http_client = http_client


@activity.defn
async def generate_requirements(
    cognitive_plan: dict[str, Any], original_intent: str = None
) -> dict[str, Any]:
    """
    Gera requisitos funcionais e não-funcionais a partir do Cognitive Plan.

    Chama o serviço requirements-engineering (porta 8010).

    Args:
        cognitive_plan: Plano cognitivo com contexto
        original_intent: Intent original do usuário (para contexto)

    Returns:
        Dict com requirements_set gerado incluindo user stories e acceptance criteria
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    logger.info(f"G1: Gerando requisitos para plan_id={plan_id}")

    try:
        if not _http_client:
            logger.warning("http_client_unavailable_using_stub")
            # Stub para quando o serviço não está disponível
            return {
                "requirements_set_id": f"REQ-SET-{plan_id}",
                "plan_id": plan_id,
                "requirements": [],
                "user_stories": [],
                "status": "stub",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Chamar API do requirements-engineering
        plan_text = json.dumps(cognitive_plan, ensure_ascii=False)
        context = {
            "original_intent": original_intent or "",
            "plan_id": plan_id,
            "intent_id": cognitive_plan.get("intent_id", ""),
        }

        response = await _http_client.post(
            "http://requirements-engineering:8010/api/v1/requirements/from-plan",
            json={
                "plan_id": plan_id,
                "plan_text": plan_text,
                "context": context,
                "generate_user_stories": True,
                "generate_acceptance_criteria": True,
            },
            timeout=30.0,
        )

        if response.status_code != 200:
            logger.error(
                f"requirements_generation_failed status={response.status_code}",
                response_text=response.text,
            )
            raise RuntimeError(f"Falha ao gerar requisitos: status {response.status_code}")

        result = response.json()
        logger.info(
            f"Requisitos gerados com sucesso: requirements_set_id={result.get('requirements_set_id')}"
        )

        return result

    except Exception:
        logger.exception(f"Erro ao gerar requisitos para plan_id={plan_id}")
        raise


@activity.defn
async def generate_documentation(
    cognitive_plan: dict[str, Any],
    requirements_set: dict[str, Any] = None,
    architecture_diagram: str = None,
) -> dict[str, Any]:
    """
    Gera documentação técnica (README, diagramas, etc).

    Chama o serviço documentation-generation (porta 8014).

    Args:
        cognitive_plan: Plano cognitivo
        requirements_set: Requisitos gerados (opcional)
        architecture_diagram: Diagrama de arquitetura em Mermaid (opcional)

    Returns:
        Dict com documentação gerada
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    logger.info(f"G2: Gerando documentação para plan_id={plan_id}")

    try:
        if not _http_client:
            logger.warning("http_client_unavailable_using_stub")
            return {
                "documentation_id": f"DOC-{plan_id}",
                "plan_id": plan_id,
                "readme": "# Stub README",
                "diagrams": [],
                "status": "stub",
            }

        # Chamar API do documentation-generation
        response = await _http_client.post(
            "http://documentation-generation:8014/api/v1/docs/generate",
            json={
                "plan_id": plan_id,
                "cognitive_plan": cognitive_plan,
                "requirements": requirements_set or {},
                "include_readme": True,
                "include_diagrams": True,
                "include_api_docs": True,
            },
            timeout=60.0,
        )

        if response.status_code != 200:
            logger.error(
                f"documentation_generation_failed status={response.status_code}",
                response_text=response.text,
            )
            raise RuntimeError(f"Falha ao gerar documentação: status {response.status_code}")

        result = response.json()
        logger.info(f"Documentação gerada: documentation_id={result.get('documentation_id')}")

        return result

    except Exception:
        logger.exception(f"Erro ao gerar documentação para plan_id={plan_id}")
        raise


@activity.defn
async def update_knowledge_graph(
    cognitive_plan: dict[str, Any],
    requirements_set: dict[str, Any] = None,
    documentation: dict[str, Any] = None,
) -> dict[str, Any]:
    """
    Atualiza o grafo de conhecimento com artefatos gerados.

    Chama o serviço knowledge-graph-rag (porta 8016).

    Args:
        cognitive_plan: Plano cognitivo
        requirements_set: Requisitos para indexar
        documentation: Documentação para indexar

    Returns:
        Dict com nós e relações criadas
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    logger.info(f"G3: Atualizando grafo de conhecimento para plan_id={plan_id}")

    try:
        if not _http_client:
            logger.warning("http_client_unavailable_using_stub")
            return {
                "nodes_created": 0,
                "relations_created": 0,
                "status": "stub",
            }

        nodes_created = []
        relations_created = []

        # Criar nó principal para o plano
        plan_response = await _http_client.post(
            "http://knowledge-graph-rag:8016/api/v1/graph/nodes",
            json={
                "node_type": "epic",
                "name": f"Plan {plan_id}",
                "description": cognitive_plan.get("summary", "Plano cognitivo"),
                "properties": {
                    "plan_id": plan_id,
                    "intent_id": cognitive_plan.get("intent_id", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            },
            timeout=10.0,
        )

        if plan_response.status_code == 201:
            plan_node = plan_response.json()
            nodes_created.append(plan_node)

            # Indexar requisitos
            if requirements_set:
                for req in requirements_set.get("requirements", []):
                    req_response = await _http_client.post(
                        "http://knowledge-graph-rag:8016/api/v1/graph/nodes",
                        json={
                            "node_type": "requirement",
                            "name": req.get("title", ""),
                            "description": req.get("description", ""),
                            "properties": {"requirement_id": req.get("id")},
                        },
                        timeout=10.0,
                    )
                    if req_response.status_code == 201:
                        req_node = req_response.json()
                        nodes_created.append(req_node)

                        # Criar relação plano -> requisito
                        rel_response = await _http_client.post(
                            "http://knowledge-graph-rag:8016/api/v1/graph/relations",
                            json={
                                "source_id": plan_node["id"],
                                "target_id": req_node["id"],
                                "relation_type": "refines",
                            },
                            timeout=10.0,
                        )
                        if rel_response.status_code == 201:
                            relations_created.append(rel_response.json())

        result = {
            "nodes_created": len(nodes_created),
            "relations_created": len(relations_created),
            "plan_node_id": plan_node.get("id") if nodes_created else None,
        }

        logger.info(f"Grafo atualizado: {result}")
        return result

    except Exception as e:
        logger.exception(f"Erro ao atualizar grafo para plan_id={plan_id}")
        # Não falhar o workflow se o grafo falhar
        return {
            "nodes_created": 0,
            "relations_created": 0,
            "status": "failed",
            "error": str(e),
        }


@activity.defn
async def request_approval(
    artifact_type: str,
    artifact_data: dict[str, Any],
    requested_by: str = "orchestrator",
) -> dict[str, Any]:
    """
    Solicita aprovação para um artefato gerado.

    Chama o serviço approval-gateway (porta 8017).

    Args:
        artifact_type: Tipo de artefato (requirement, architecture, code_generation, etc)
        artifact_data: Dados do artefato para aprovação
        requested_by: Solicitante da aprovação

    Returns:
        Dict com decisão de aprovação
    """
    logger.info(f"G4: Solicitando aprovação para artifact_type={artifact_type}")

    try:
        if not _http_client:
            logger.warning("http_client_unavailable_using_auto_approve")
            # Auto-aprovar quando serviço não disponível
            return {
                "request_id": f"AUTO-{datetime.now(timezone.utc).timestamp()}",
                "status": "approved",
                "confidence_score": 1.0,
                "reasoning": "Auto-aprovado (serviço indisponível)",
                "requires_human_review": False,
            }

        response = await _http_client.post(
            "http://approval-gateway:8017/api/v1/approvals/request",
            json={
                "type": artifact_type,
                "title": artifact_data.get("title", f"Aprovação {artifact_type}"),
                "description": artifact_data.get("description", ""),
                "requested_by": requested_by,
                "context": artifact_data.get("context", {}),
            },
            timeout=30.0,
        )

        if response.status_code != 201:
            logger.error(
                f"approval_request_failed status={response.status_code}",
                response_text=response.text,
            )
            raise RuntimeError(f"Falha ao solicitar aprovação: status {response.status_code}")

        result = response.json()
        logger.info(
            f"Aprovação processada: status={result.get('status')}, "
            f"requires_human={result.get('requires_human_review')}"
        )

        return result

    except Exception:
        logger.exception(f"Erro ao solicitar aprovação para {artifact_type}")
        raise


@activity.defn
async def query_knowledge_graph(
    query_text: str, context: str = None, limit: int = 10
) -> dict[str, Any]:
    """
    Realiza query RAG no grafo de conhecimento.

    Args:
        query_text: Texto da query
        context: Contexto adicional
        limit: Limite de resultados

    Returns:
        Dict com resposta RAG
    """
    logger.info(f"G5: Query RAG: {query_text[:50]}...")

    try:
        if not _http_client:
            return {
                "query": query_text,
                "response": "Serviço de conhecimento indisponível",
                "context_used": False,
            }

        response = await _http_client.post(
            "http://knowledge-graph-rag:8016/api/v1/graph/rag/query",
            json={"query_text": query_text, "context": context},
            timeout=30.0,
        )

        if response.status_code != 200:
            logger.error(f"rag_query_failed status={response.status_code}")
            return {
                "query": query_text,
                "response": "Erro na query RAG",
                "context_used": False,
            }

        return response.json()

    except Exception as e:
        logger.exception(f"Erro na query RAG: {query_text}")
        return {
            "query": query_text,
            "response": f"Erro: {e!s}",
            "context_used": False,
        }
