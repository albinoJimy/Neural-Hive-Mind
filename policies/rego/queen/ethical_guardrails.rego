package neuralhive.queen.ethical_guardrails

# Resultado principal
result := {
    "allow": allow,
    "violations": violations,
    "warnings": warnings,
    "guardrails_validated": guardrails_validated
}

# Allow se não houver violações críticas
default allow := false
allow {
    count([v | v := violations[_]; v.severity == "critical"]) == 0
}

# Coletar violações
violations[violation] {
    violation := excessive_risk_violation
}

violations[violation] {
    violation := low_confidence_critical_decision
}

violations[violation] {
    violation := bias_risk_violation
}

violations[violation] {
    violation := privacy_violation
}

violations[violation] {
    violation := resource_saturation_critical
}

violations[violation] {
    violation := exception_approval_without_justification
}

# Regra 1: Risk score excessivo (>0.9)
excessive_risk_violation := violation {
    decision := input.decision
    risk_score := decision.risk_assessment.risk_score

    risk_score > 0.9

    violation := {
        "policy": "ethical_guardrails",
        "rule": "excessive_risk",
        "severity": "critical",
        "field": "risk_assessment.risk_score",
        "msg": sprintf("Risk score %v excede threshold de 0.9", [risk_score]),
        "expected": "<=0.9",
        "actual": risk_score
    }
}

# Regra 2: Baixa confiança em decisão crítica
low_confidence_critical_decision := violation {
    decision := input.decision
    confidence := decision.confidence_score
    decision_type := decision.decision_type

    # Decisões críticas requerem alta confiança
    critical_types := ["REPLANNING", "EXCEPTION_APPROVAL", "QOS_ADJUSTMENT"]
    decision_type == critical_types[_]
    confidence < 0.7

    violation := {
        "policy": "ethical_guardrails",
        "rule": "low_confidence_critical_decision",
        "severity": "high",
        "field": "confidence_score",
        "msg": sprintf("Decisão crítica %v com confiança baixa: %v", [decision_type, confidence]),
        "expected": ">=0.7",
        "actual": confidence
    }
}

# Regra 3: Risco de bias em decisões que afetam usuários
bias_risk_violation := violation {
    decision := input.decision
    action := decision.decision.action

    # Ações que afetam usuários diretamente
    user_affecting_actions := ["pause_execution", "adjust_priorities", "reallocate_resources"]
    action == user_affecting_actions[_]

    # Verificar se há análise de bias
    not has_bias_analysis(decision)

    violation := {
        "policy": "ethical_guardrails",
        "rule": "bias_risk",
        "severity": "high",
        "field": "analysis",
        "msg": sprintf("Ação %v afeta usuários mas não tem análise de bias", [action]),
        "expected": "bias_analysis presente",
        "actual": "ausente"
    }
}

# Regra 4: Violação de privacy (dados pessoais sem consentimento)
privacy_violation := violation {
    decision := input.decision
    context := decision.context

    # Verificar se há incidentes críticos relacionados a PII
    critical_incidents := context.critical_incidents
    count(critical_incidents) > 0

    # Verificar se decisão envolve dados pessoais
    involves_personal_data(decision)

    # Verificar se há consentimento
    not has_user_consent(decision)

    violation := {
        "policy": "ethical_guardrails",
        "rule": "privacy_violation",
        "severity": "critical",
        "field": "context",
        "msg": "Decisão envolve dados pessoais sem consentimento do usuário",
        "expected": "user_consent=true",
        "actual": "ausente"
    }
}

# Regra 5: Saturação crítica de recursos (>95%)
resource_saturation_critical := violation {
    decision := input.decision
    context := decision.context
    saturation := context.resource_saturation

    saturation > 0.95

    # Decisão não é de realocação de recursos
    decision.decision.action != "reallocate_resources"

    violation := {
        "policy": "ethical_guardrails",
        "rule": "resource_saturation_critical",
        "severity": "critical",
        "field": "context.resource_saturation",
        "msg": sprintf("Saturação crítica de recursos (%v%%) sem ação de realocação", [saturation * 100]),
        "expected": "action=reallocate_resources",
        "actual": decision.decision.action
    }
}

# Regra 6: Exception approval sem justificativa
exception_approval_without_justification := violation {
    decision := input.decision
    decision_type := decision.decision_type

    decision_type == "EXCEPTION_APPROVAL"

    # Verificar se há justificativa no reasoning_summary
    reasoning := decision.reasoning_summary
    not contains(reasoning, "justificativa")
    not contains(reasoning, "justification")

    violation := {
        "policy": "ethical_guardrails",
        "rule": "exception_approval_without_justification",
        "severity": "high",
        "field": "reasoning_summary",
        "msg": "Exception approval sem justificativa clara",
        "expected": "reasoning_summary com justificativa",
        "actual": reasoning
    }
}

# Warnings
warnings[warning] {
    warning := high_risk_warning
}

warnings[warning] {
    warning := multiple_sla_violations_warning
}

# Warning 1: Risk score alto (0.7-0.9)
high_risk_warning := warning {
    decision := input.decision
    risk_score := decision.risk_assessment.risk_score

    risk_score > 0.7
    risk_score <= 0.9

    warning := {
        "policy": "ethical_guardrails",
        "rule": "high_risk_warning",
        "msg": sprintf("Risk score alto: %v (considerar revisão humana)", [risk_score])
    }
}

# Warning 2: Múltiplas violações de SLA
multiple_sla_violations_warning := warning {
    decision := input.decision
    context := decision.context
    sla_violations := context.sla_violations

    count(sla_violations) > 3

    warning := {
        "policy": "ethical_guardrails",
        "rule": "multiple_sla_violations",
        "msg": sprintf("%v serviços com violações de SLA", [count(sla_violations)])
    }
}

# Guardrails validados (para auditoria)
guardrails_validated := validated {
    allow
    validated := [
        "risk_threshold_acceptable",
        "confidence_threshold_met",
        "no_bias_risk",
        "privacy_compliant",
        "resource_saturation_acceptable",
        "exception_approval_justified"
    ]
}

guardrails_validated := [] {
    not allow
}

# Helpers
has_bias_analysis(decision) {
    decision.analysis.metrics_snapshot["bias_score"]
}

involves_personal_data(decision) {
    # Simplificado: verificar se há menção a PII no contexto
    decision.context.critical_incidents[_] == "pii_exposure"
}

has_user_consent(decision) {
    decision.decision.parameters["user_consent"] == true
}
