"""Validadores para testes E2E do Fluxo C.

Fornece funções de validação para verificar:
- Transições de status válidas
- Completude de mensagens de telemetria
- Conformidade com SLAs
- Estrutura de resultados publicados
- Métricas de workflow Temporal
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# Transições de status válidas no Fluxo C
VALID_STATUS_TRANSITIONS: Dict[str, Set[str]] = {
    "PENDING": {"RUNNING", "FAILED", "CANCELLED"},
    "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
    "COMPLETED": set(),  # Estado final
    "FAILED": set(),  # Estado final
    "CANCELLED": set(),  # Estado final
}

# Campos obrigatórios em mensagens de telemetria
REQUIRED_TELEMETRY_FIELDS = [
    "plan_id",
    "workflow_id",
    "total_duration_ms",
    "tickets_generated",
    "tickets_completed",
    "tickets_failed",
]

# Campos obrigatórios em resultados de execução
REQUIRED_RESULT_FIELDS = [
    "ticket_id",
    "status",
    "actual_duration_ms",
]


@dataclass
class ValidationResult:
    """Resultado de uma validação."""

    valid: bool
    message: str
    details: Optional[Dict[str, Any]] = None


def validate_ticket_status_transition(
    from_status: Optional[str],
    to_status: str,
) -> ValidationResult:
    """
    Valida se transição de status é permitida.

    Args:
        from_status: Status de origem (None para inicial)
        to_status: Status de destino

    Returns:
        ValidationResult indicando se transição é válida
    """
    # Primeira transição (criação)
    if from_status is None:
        if to_status == "PENDING":
            return ValidationResult(
                valid=True,
                message="Transição inicial para PENDING é válida",
            )
        return ValidationResult(
            valid=False,
            message=f"Status inicial deve ser PENDING, não {to_status}",
        )

    # Verificar transição
    valid_next_statuses = VALID_STATUS_TRANSITIONS.get(from_status, set())

    if to_status in valid_next_statuses:
        return ValidationResult(
            valid=True,
            message=f"Transição {from_status} -> {to_status} é válida",
        )

    return ValidationResult(
        valid=False,
        message=f"Transição inválida: {from_status} -> {to_status}",
        details={
            "from_status": from_status,
            "to_status": to_status,
            "valid_transitions": list(valid_next_statuses),
        },
    )


def validate_status_sequence(
    sequence: List[str],
) -> ValidationResult:
    """
    Valida sequência completa de transições de status.

    Args:
        sequence: Lista de status na ordem observada

    Returns:
        ValidationResult com detalhes da validação
    """
    if not sequence:
        return ValidationResult(
            valid=False,
            message="Sequência de status vazia",
        )

    # Verificar status inicial
    if sequence[0] != "PENDING":
        return ValidationResult(
            valid=False,
            message=f"Sequência deve começar com PENDING, não {sequence[0]}",
        )

    invalid_transitions = []
    for i in range(len(sequence) - 1):
        from_status = sequence[i]
        to_status = sequence[i + 1]
        result = validate_ticket_status_transition(from_status, to_status)
        if not result.valid:
            invalid_transitions.append({
                "index": i,
                "from": from_status,
                "to": to_status,
            })

    if invalid_transitions:
        return ValidationResult(
            valid=False,
            message=f"Encontradas {len(invalid_transitions)} transições inválidas",
            details={"invalid_transitions": invalid_transitions},
        )

    return ValidationResult(
        valid=True,
        message="Sequência de status válida",
        details={"sequence": sequence, "length": len(sequence)},
    )


def validate_telemetry_completeness(
    telemetry_message: Dict[str, Any],
) -> ValidationResult:
    """
    Verifica se mensagem de telemetria contém todos os campos obrigatórios.

    Args:
        telemetry_message: Mensagem de telemetria do tópico telemetry.orchestration

    Returns:
        ValidationResult com campos faltantes se houver
    """
    if not telemetry_message:
        return ValidationResult(
            valid=False,
            message="Mensagem de telemetria vazia",
        )

    missing_fields = []
    for field in REQUIRED_TELEMETRY_FIELDS:
        if field not in telemetry_message:
            missing_fields.append(field)

    if missing_fields:
        return ValidationResult(
            valid=False,
            message=f"Campos obrigatórios faltando: {missing_fields}",
            details={
                "missing_fields": missing_fields,
                "present_fields": list(telemetry_message.keys()),
            },
        )

    # Validar valores
    warnings = []
    if telemetry_message.get("total_duration_ms", 0) <= 0:
        warnings.append("total_duration_ms deve ser positivo")

    if telemetry_message.get("tickets_generated", 0) == 0:
        warnings.append("tickets_generated é zero")

    return ValidationResult(
        valid=True,
        message="Telemetria completa",
        details={
            "warnings": warnings if warnings else None,
            "plan_id": telemetry_message.get("plan_id"),
            "workflow_id": telemetry_message.get("workflow_id"),
            "tickets_generated": telemetry_message.get("tickets_generated"),
            "tickets_completed": telemetry_message.get("tickets_completed"),
            "tickets_failed": telemetry_message.get("tickets_failed"),
        },
    )


def validate_telemetry_step_metrics(
    telemetry_message: Dict[str, Any],
    expected_steps: List[str] = None,
) -> ValidationResult:
    """
    Valida métricas de cada etapa na telemetria.

    Args:
        telemetry_message: Mensagem de telemetria
        expected_steps: Etapas esperadas (default: C1-C6)

    Returns:
        ValidationResult com detalhes de cada etapa
    """
    if expected_steps is None:
        expected_steps = ["C1", "C2", "C3", "C4", "C5", "C6"]

    steps = telemetry_message.get("steps", [])
    if not steps:
        return ValidationResult(
            valid=False,
            message="Sem métricas de etapas na telemetria",
        )

    step_names = [s.get("name") or s.get("step_name") for s in steps]
    missing_steps = []
    for expected in expected_steps:
        if expected not in step_names:
            missing_steps.append(expected)

    if missing_steps:
        return ValidationResult(
            valid=False,
            message=f"Etapas faltando: {missing_steps}",
            details={
                "missing_steps": missing_steps,
                "found_steps": step_names,
            },
        )

    # Verificar campos em cada etapa
    step_issues = []
    for step in steps:
        step_name = step.get("name") or step.get("step_name")
        if "duration_ms" not in step and "duration" not in step:
            step_issues.append(f"{step_name}: sem duration_ms")
        if "status" not in step:
            step_issues.append(f"{step_name}: sem status")

    if step_issues:
        return ValidationResult(
            valid=False,
            message="Campos faltando em etapas",
            details={"issues": step_issues},
        )

    return ValidationResult(
        valid=True,
        message="Métricas de etapas válidas",
        details={"step_count": len(steps), "steps": step_names},
    )


def validate_sla_compliance(
    ticket: Dict[str, Any],
    actual_duration_ms: int,
) -> ValidationResult:
    """
    Verifica se execução respeitou SLA definido.

    Args:
        ticket: Dados do ticket com configuração de SLA
        actual_duration_ms: Duração real da execução em ms

    Returns:
        ValidationResult indicando conformidade com SLA
    """
    sla = ticket.get("sla", {})
    timeout_ms = sla.get("timeout_ms")
    deadline = sla.get("deadline")

    violations = []

    # Verificar timeout
    if timeout_ms and actual_duration_ms > timeout_ms:
        violations.append({
            "type": "timeout",
            "limit_ms": timeout_ms,
            "actual_ms": actual_duration_ms,
            "exceeded_by_ms": actual_duration_ms - timeout_ms,
        })

    # Verificar deadline
    if deadline:
        try:
            if isinstance(deadline, (int, float)):
                deadline_dt = datetime.fromtimestamp(deadline / 1000)
            else:
                deadline_dt = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))

            now = datetime.utcnow()
            if now > deadline_dt:
                violations.append({
                    "type": "deadline",
                    "deadline": deadline_dt.isoformat(),
                    "completed_at": now.isoformat(),
                })
        except (ValueError, TypeError) as e:
            logger.warning(f"Erro ao parsear deadline: {e}")

    if violations:
        return ValidationResult(
            valid=False,
            message=f"SLA violado: {len(violations)} violação(ões)",
            details={"violations": violations, "actual_duration_ms": actual_duration_ms},
        )

    return ValidationResult(
        valid=True,
        message="SLA respeitado",
        details={
            "timeout_ms": timeout_ms,
            "actual_duration_ms": actual_duration_ms,
            "margin_ms": (timeout_ms - actual_duration_ms) if timeout_ms else None,
        },
    )


def validate_result_structure(
    result_message: Dict[str, Any],
) -> ValidationResult:
    """
    Valida estrutura de resultado publicado.

    Args:
        result_message: Mensagem de resultado do tópico execution.results

    Returns:
        ValidationResult com campos validados
    """
    if not result_message:
        return ValidationResult(
            valid=False,
            message="Mensagem de resultado vazia",
        )

    missing_fields = []
    for field in REQUIRED_RESULT_FIELDS:
        if field not in result_message:
            missing_fields.append(field)

    if missing_fields:
        return ValidationResult(
            valid=False,
            message=f"Campos obrigatórios faltando: {missing_fields}",
            details={"missing_fields": missing_fields},
        )

    # Validar status
    status = result_message.get("status")
    valid_statuses = {"COMPLETED", "FAILED", "CANCELLED"}
    if status not in valid_statuses:
        return ValidationResult(
            valid=False,
            message=f"Status inválido: {status}",
            details={"valid_statuses": list(valid_statuses)},
        )

    # Validar campos condicionais
    warnings = []
    if status == "FAILED" and not result_message.get("error_message"):
        warnings.append("Resultado FAILED sem error_message")

    if result_message.get("actual_duration_ms", 0) <= 0:
        warnings.append("actual_duration_ms deve ser positivo")

    return ValidationResult(
        valid=True,
        message="Estrutura de resultado válida",
        details={
            "ticket_id": result_message.get("ticket_id"),
            "status": status,
            "actual_duration_ms": result_message.get("actual_duration_ms"),
            "warnings": warnings if warnings else None,
        },
    )


async def extract_workflow_metrics(
    workflow_id: str,
    temporal_client,
) -> Dict[str, Any]:
    """
    Extrai métricas de workflow Temporal.

    Args:
        workflow_id: ID do workflow
        temporal_client: Cliente Temporal conectado

    Returns:
        Dict com métricas do workflow
    """
    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        describe = await handle.describe()

        metrics = {
            "workflow_id": workflow_id,
            "run_id": describe.run_id,
            "status": describe.status,
        }

        if describe.start_time:
            metrics["started_at"] = describe.start_time.isoformat()

        if describe.close_time:
            metrics["closed_at"] = describe.close_time.isoformat()

        if describe.start_time and describe.close_time:
            duration = describe.close_time - describe.start_time
            metrics["duration_ms"] = int(duration.total_seconds() * 1000)

        # Tentar obter resultado
        try:
            result = await handle.result()
            metrics["result"] = result
        except Exception:
            pass

        # Obter histórico de atividades
        activity_count = 0
        async for event in handle.fetch_history_events():
            if "ACTIVITY" in str(event.event_type):
                activity_count += 1

        metrics["activity_count"] = activity_count

        return metrics

    except Exception as e:
        logger.error(f"Erro ao extrair métricas do workflow: {e}")
        return {
            "workflow_id": workflow_id,
            "error": str(e),
        }


def validate_dependency_chain(
    tickets: List[Dict[str, Any]],
) -> ValidationResult:
    """
    Valida que dependências entre tickets são respeitadas.

    Args:
        tickets: Lista de tickets com suas dependências

    Returns:
        ValidationResult indicando se ordem de execução é válida
    """
    completed_tickets = set()
    violations = []

    # Ordenar por timestamp de início
    sorted_tickets = sorted(
        tickets,
        key=lambda t: t.get("started_at") or t.get("created_at") or 0,
    )

    for ticket in sorted_tickets:
        ticket_id = ticket.get("ticket_id")
        dependencies = ticket.get("dependencies", [])

        # Verificar se todas as dependências foram completadas
        for dep in dependencies:
            if dep not in completed_tickets:
                violations.append({
                    "ticket_id": ticket_id,
                    "dependency": dep,
                    "issue": "Dependência não completada antes da execução",
                })

        # Marcar como completado se status é COMPLETED
        if ticket.get("status") == "COMPLETED":
            completed_tickets.add(ticket_id)

    if violations:
        return ValidationResult(
            valid=False,
            message=f"Encontradas {len(violations)} violações de dependência",
            details={"violations": violations},
        )

    return ValidationResult(
        valid=True,
        message="Cadeia de dependências respeitada",
        details={"total_tickets": len(tickets)},
    )


def validate_trace_correlation(
    telemetry: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> ValidationResult:
    """
    Valida correlação de traces entre telemetria e resultados.

    Args:
        telemetry: Mensagem de telemetria
        results: Lista de mensagens de resultado

    Returns:
        ValidationResult indicando correlação válida
    """
    telemetry_trace_id = telemetry.get("trace_id")
    telemetry_correlation_id = telemetry.get("correlation_id")

    if not telemetry_trace_id and not telemetry_correlation_id:
        return ValidationResult(
            valid=False,
            message="Telemetria sem trace_id ou correlation_id",
        )

    mismatched = []
    for result in results:
        result_trace_id = result.get("trace_id")
        result_correlation_id = result.get("correlation_id")

        # Verificar correlação
        if telemetry_trace_id and result_trace_id:
            if result_trace_id != telemetry_trace_id:
                mismatched.append({
                    "ticket_id": result.get("ticket_id"),
                    "expected_trace_id": telemetry_trace_id,
                    "actual_trace_id": result_trace_id,
                })
        elif telemetry_correlation_id and result_correlation_id:
            if result_correlation_id != telemetry_correlation_id:
                mismatched.append({
                    "ticket_id": result.get("ticket_id"),
                    "expected_correlation_id": telemetry_correlation_id,
                    "actual_correlation_id": result_correlation_id,
                })

    if mismatched:
        return ValidationResult(
            valid=False,
            message=f"Encontrados {len(mismatched)} resultados com traces divergentes",
            details={"mismatched": mismatched},
        )

    return ValidationResult(
        valid=True,
        message="Correlação de traces válida",
        details={
            "trace_id": telemetry_trace_id,
            "correlation_id": telemetry_correlation_id,
            "results_validated": len(results),
        },
    )
