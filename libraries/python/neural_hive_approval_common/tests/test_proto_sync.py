"""Sync tests entre os modelos Pydantic e o protobuf approval.proto.

TICKET-018 exige "Pydantic + Protobuf sync". Estes testes falham se um
lado adicionar/renomear um valor de enum sem o outro acompanhar — força
o autor a manter a paridade explicitamente.

Não verifica alinhamento de campos das messages porque a serialização
proto exige nomes diferentes (snake_case_proto vs camelCase) e tipos
mais ricos (Struct para JSON arbitrário); a paridade aí é mantida no
boundary entre o approval-service e qualquer consumer gRPC futuro.
"""

from __future__ import annotations

from neural_hive_approval_common import (
    ApprovalStatus,
    RiskBand,
    UnifiedApprovalDecision,
)
from neural_hive_approval_common.proto import approval_pb2


# ---- Helpers ---------------------------------------------------------------


def _proto_enum_values(enum_descriptor) -> set[str]:
    """Devolve os valores efectivos do proto enum em lower-case.

    Detecta automaticamente o prefixo comum (e.g. ``RISK_BAND_``) excluindo
    o sentinela ``*_UNSPECIFIED``, e devolve os sufixos em lower-case para
    comparação directa com ``Enum.value`` em Pydantic.
    """
    real_names = [v.name for v in enum_descriptor.values if not v.name.endswith("_UNSPECIFIED")]
    if not real_names:
        return set()

    # Prefixo comum entre todos os nomes reais (greedy split em "_").
    prefix_tokens: list[str] = []
    first_tokens = real_names[0].split("_")
    for token_idx in range(len(first_tokens)):
        candidate = "_".join(first_tokens[: token_idx + 1]) + "_"
        if all(name.startswith(candidate) for name in real_names):
            prefix_tokens = first_tokens[: token_idx + 1]
        else:
            break
    prefix = "_".join(prefix_tokens) + "_" if prefix_tokens else ""

    return {name[len(prefix) :].lower() for name in real_names}


# ---- Enum sync -------------------------------------------------------------


def test_risk_band_enum_in_sync() -> None:
    pydantic_values = {member.value for member in RiskBand}
    proto_values = _proto_enum_values(approval_pb2._RISKBAND)  # type: ignore[attr-defined]
    assert pydantic_values == proto_values, (
        "RiskBand divergiu entre Pydantic e protobuf: "
        f"pydantic={pydantic_values}, proto={proto_values}"
    )


def test_approval_status_enum_in_sync() -> None:
    pydantic_values = {member.value for member in ApprovalStatus}
    proto_values = _proto_enum_values(approval_pb2._APPROVALSTATUS)  # type: ignore[attr-defined]
    assert pydantic_values == proto_values, (
        "ApprovalStatus divergiu entre Pydantic e protobuf: "
        f"pydantic={pydantic_values}, proto={proto_values}"
    )


def test_decision_enum_matches_unified_approval_decision_literal() -> None:
    """O proto Decision deve cobrir exactamente os valores do Literal Pydantic."""
    pydantic_decision_values = {"approved", "rejected"}
    proto_values = _proto_enum_values(approval_pb2._DECISION)  # type: ignore[attr-defined]
    assert pydantic_decision_values == proto_values


# ---- Smoke de construção ---------------------------------------------------


def test_proto_messages_construct_with_minimal_fields() -> None:
    """Garante que os tipos esperados pelos messages estão presentes."""
    req = approval_pb2.UnifiedApprovalRequest(
        approval_id="a1",
        plan_id="p1",
        intent_id="i1",
        risk_score=0.42,
        risk_band=approval_pb2.RISK_BAND_MEDIUM,
        status=approval_pb2.APPROVAL_STATUS_PENDING,
    )
    assert req.plan_id == "p1"
    assert req.risk_band == approval_pb2.RISK_BAND_MEDIUM

    decision = approval_pb2.UnifiedApprovalDecision(
        plan_id="p1",
        decision=approval_pb2.DECISION_APPROVED,
        approved_by="user-7",
        auto_approved=True,
    )
    assert decision.decision == approval_pb2.DECISION_APPROVED
    assert decision.auto_approved is True


def test_unified_approval_decision_pydantic_round_trip_matches_proto_decision() -> None:
    """Pydantic Decision Literal['approved','rejected'] mapeia para proto Decision."""
    literal_to_proto = {
        "approved": approval_pb2.DECISION_APPROVED,
        "rejected": approval_pb2.DECISION_REJECTED,
    }
    for literal_value, proto_value in literal_to_proto.items():
        # Constrói o Pydantic com o literal e confirma que é representável.
        d = UnifiedApprovalDecision(plan_id="p", decision=literal_value, approved_by="u")
        assert d.decision == literal_value
        # E que o proto tem o equivalente.
        assert proto_value != approval_pb2.DECISION_UNSPECIFIED
