package neuralhive.orchestrator.resource_limits_duration_floor_test

# Testes do piso de duração da regra estimated_duration_unrealistic.
# Piso baixado de 1000ms -> 100ms (FIX-C): o STE gera durações de 300-900ms
# POR DESIGN (decomposition_templates.py); 1000ms causava 100% de falsos
# positivos. 100ms ainda apanha estimativas quase-zero.

import data.neuralhive.orchestrator.resource_limits

# Test: duração realista do STE (800ms) é PERMITIDA (acima do novo piso de 100ms)
test_estimated_duration_800ms_allowed {
    input := {
        "resource": {
            "ticket_id": "ste-800",
            "risk_band": "low",
            "sla": {"timeout_ms": 60000, "max_retries": 1},
            "estimated_duration_ms": 800,
            "required_capabilities": ["read", "analyze"]
        },
        "parameters": {
            "allowed_capabilities": ["read", "analyze"],
            "max_concurrent_tickets": 100
        },
        "context": {"total_tickets": 1}
    }

    result := resource_limits.result with input as input
    result.allow == true

    # Garantir que NÃO há violação de duração irrealista
    not duration_violation(result)
}

# Test: duração quase-zero (50ms < 100ms) é REJEITADA
test_estimated_duration_below_floor_rejected {
    input := {
        "resource": {
            "ticket_id": "near-zero-50",
            "risk_band": "low",
            "sla": {"timeout_ms": 60000, "max_retries": 1},
            "estimated_duration_ms": 50,
            "required_capabilities": ["read"]
        },
        "parameters": {
            "allowed_capabilities": ["read"],
            "max_concurrent_tickets": 100
        },
        "context": {"total_tickets": 1}
    }

    result := resource_limits.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "estimated_duration_unrealistic"
    violation.severity == "low"
}

# Helper: indica se existe violação de duração irrealista no resultado
duration_violation(result) {
    some i
    result.violations[i].rule == "estimated_duration_unrealistic"
}
