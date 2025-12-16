package neuralhive.orchestrator.sla_enforcement_test

import data.neuralhive.orchestrator.sla_enforcement

# Test: Valid SLA
test_valid_sla {
    current_time := 1700000000000
    deadline := 1700003600000  # +1h
    
    input := {
        "resource": {
            "ticket_id": "sla-123",
            "risk_band": "critical",
            "sla": {"timeout_ms": 120000, "deadline": deadline},
            "qos": {"delivery_mode": "EXACTLY_ONCE", "consistency": "STRONG"},
            "priority": "CRITICAL",
            "estimated_duration_ms": 60000
        },
        "context": {"current_time": current_time}
    }
    
    result := sla_enforcement.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# Test: Deadline in past
test_deadline_in_past {
    current_time := 1700000000000
    deadline := 1699996400000  # -1h
    
    input := {
        "resource": {
            "ticket_id": "sla-456",
            "risk_band": "high",
            "sla": {"timeout_ms": 60000, "deadline": deadline},
            "qos": {"delivery_mode": "EXACTLY_ONCE", "consistency": "STRONG"},
            "priority": "HIGH",
            "estimated_duration_ms": 30000
        },
        "context": {"current_time": current_time}
    }
    
    result := sla_enforcement.result with input as input
    result.allow == false
    
    violation := result.violations[_]
    violation.rule == "deadline_in_past"
    violation.severity == "critical"
}

# Test: QoS mismatch for critical
test_qos_mismatch_critical {
    current_time := 1700000000000
    deadline := 1700003600000
    
    input := {
        "resource": {
            "ticket_id": "sla-789",
            "risk_band": "critical",
            "sla": {"timeout_ms": 120000, "deadline": deadline},
            "qos": {"delivery_mode": "AT_LEAST_ONCE", "consistency": "STRONG"},  # Wrong
            "priority": "CRITICAL",
            "estimated_duration_ms": 60000
        },
        "context": {"current_time": current_time}
    }
    
    result := sla_enforcement.result with input as input
    result.allow == false
    
    violation := result.violations[_]
    violation.rule == "qos_mismatch_risk_band"
    violation.severity == "critical"
}
