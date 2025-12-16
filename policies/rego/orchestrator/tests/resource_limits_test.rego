package neuralhive.orchestrator.resource_limits_test

import data.neuralhive.orchestrator.resource_limits

# Test: Valid ticket within limits
test_valid_ticket_within_limits {
    input := {
        "resource": {
            "ticket_id": "test-123",
            "risk_band": "high",
            "sla": {"timeout_ms": 60000, "max_retries": 3},
            "estimated_duration_ms": 30000,
            "required_capabilities": ["code_generation"]
        },
        "parameters": {
            "allowed_capabilities": ["code_generation", "deployment"],
            "max_concurrent_tickets": 100
        },
        "context": {"total_tickets": 50}
    }
    
    result := resource_limits.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# Test: Timeout exceeds maximum
test_timeout_exceeds_maximum {
    input := {
        "resource": {
            "ticket_id": "test-456",
            "risk_band": "high",
            "sla": {"timeout_ms": 7200000, "max_retries": 3},  # 2h > 1h limit
            "estimated_duration_ms": 30000,
            "required_capabilities": ["code_generation"]
        },
        "parameters": {
            "allowed_capabilities": ["code_generation"],
            "max_concurrent_tickets": 100
        },
        "context": {"total_tickets": 50}
    }
    
    result := resource_limits.result with input as input
    result.allow == false
    count(result.violations) > 0
    
    # Verificar violação específica
    violation := result.violations[_]
    violation.rule == "timeout_exceeds_maximum"
    violation.severity == "high"
}

# Test: Capability not allowed
test_capability_not_allowed {
    input := {
        "resource": {
            "ticket_id": "test-789",
            "risk_band": "low",
            "sla": {"timeout_ms": 60000, "max_retries": 1},
            "estimated_duration_ms": 30000,
            "required_capabilities": ["malicious_capability"]
        },
        "parameters": {
            "allowed_capabilities": ["code_generation", "testing"],
            "max_concurrent_tickets": 100
        },
        "context": {"total_tickets": 50}
    }
    
    result := resource_limits.result with input as input
    result.allow == false
    
    violation := result.violations[_]
    violation.rule == "capabilities_not_allowed"
    violation.severity == "high"
}
