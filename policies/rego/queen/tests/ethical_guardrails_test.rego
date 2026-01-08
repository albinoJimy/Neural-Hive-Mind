package neuralhive.queen.ethical_guardrails

# Test 1: Excessive risk violation
test_excessive_risk_violation {
    decision := {
        "decision_type": "REPLANNING",
        "confidence_score": 0.8,
        "risk_assessment": {"risk_score": 0.95},
        "decision": {"action": "trigger_replanning"},
        "context": {"resource_saturation": 0.5, "critical_incidents": [], "sla_violations": []},
        "analysis": {"metrics_snapshot": {}},
        "reasoning_summary": "Test"
    }

    res := result with input as {"decision": decision}

    res.allow == false
    count(res.violations) > 0
    some v
    v := res.violations[_]
    v.rule == "excessive_risk"
}

# Test 2: Low confidence critical decision
test_low_confidence_critical_decision {
    decision := {
        "decision_type": "REPLANNING",
        "confidence_score": 0.6,
        "risk_assessment": {"risk_score": 0.5},
        "decision": {"action": "trigger_replanning"},
        "context": {"resource_saturation": 0.5, "critical_incidents": [], "sla_violations": []},
        "analysis": {"metrics_snapshot": {}},
        "reasoning_summary": "Test"
    }

    res := result with input as {"decision": decision}

    some v
    v := res.violations[_]
    v.rule == "low_confidence_critical_decision"
}

# Test 3: Allow safe decision
test_allow_safe_decision {
    decision := {
        "decision_type": "PRIORITIZATION",
        "confidence_score": 0.85,
        "risk_assessment": {"risk_score": 0.3},
        "decision": {"action": "adjust_priorities", "parameters": {}},
        "context": {"resource_saturation": 0.5, "critical_incidents": [], "sla_violations": []},
        "analysis": {"metrics_snapshot": {"bias_score": 0.1}},
        "reasoning_summary": "Ajuste de prioridades baseado em contexto"
    }

    res := result with input as {"decision": decision}

    res.allow == true
    count(res.violations) == 0
}

# Test 4: High risk warning
test_high_risk_warning {
    decision := {
        "decision_type": "PRIORITIZATION",
        "confidence_score": 0.85,
        "risk_assessment": {"risk_score": 0.75},
        "decision": {"action": "adjust_priorities", "parameters": {}},
        "context": {"resource_saturation": 0.5, "critical_incidents": [], "sla_violations": []},
        "analysis": {"metrics_snapshot": {"bias_score": 0.1}},
        "reasoning_summary": "Ajuste"
    }

    res := result with input as {"decision": decision}

    res.allow == true
    some w
    w := res.warnings[_]
    w.rule == "high_risk_warning"
}

# Test 5: Resource saturation critical
test_resource_saturation_critical {
    decision := {
        "decision_type": "PRIORITIZATION",
        "confidence_score": 0.85,
        "risk_assessment": {"risk_score": 0.3},
        "decision": {"action": "adjust_priorities", "parameters": {}},
        "context": {"resource_saturation": 0.97, "critical_incidents": [], "sla_violations": []},
        "analysis": {"metrics_snapshot": {}},
        "reasoning_summary": "Test"
    }

    res := result with input as {"decision": decision}

    res.allow == false
    some v
    v := res.violations[_]
    v.rule == "resource_saturation_critical"
}

# Test 6: Resource saturation ok with reallocate action
test_resource_saturation_ok_with_reallocation {
    decision := {
        "decision_type": "RESOURCE_REALLOCATION",
        "confidence_score": 0.85,
        "risk_assessment": {"risk_score": 0.3},
        "decision": {"action": "reallocate_resources", "parameters": {}},
        "context": {"resource_saturation": 0.97, "critical_incidents": [], "sla_violations": []},
        "analysis": {"metrics_snapshot": {"bias_score": 0.1}},
        "reasoning_summary": "Realocação necessária"
    }

    res := result with input as {"decision": decision}

    # Não deve ter violação de resource_saturation_critical pois ação é reallocate_resources
    not_resource_violation := [v | v := res.violations[_]; v.rule == "resource_saturation_critical"]
    count(not_resource_violation) == 0
}
