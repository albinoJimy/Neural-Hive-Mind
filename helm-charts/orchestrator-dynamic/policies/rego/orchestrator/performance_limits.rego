package neural_hive.performance.limits

# Política de limites de performance para tasks VALIDATE do domínio "performance".
#
# O ValidateExecutor (worker-agents) consulta:
#   GET /v1/data/neural_hive/performance/limits
# com input = {target, subject, entities, security_level, is_destructive, risk_band}.
#
# Contrato esperado pelo opa_client (worker): devolve um documento com
#   { "allow": bool, "violations": [ {rule_id, message, severity}, ... ] }
#
# Postura: allow=true quando não há violações; deny (allow=false) com a lista de
# violações quando um limite de performance é excedido. Regras condicionais a
# campos opcionais (ex: estimated_duration_ms) só disparam quando o campo existe.

default allow := false

allow {
	count(violations) == 0
}

# Performance crítica (risk_band=critical) exige revisão explícita.
violations[v] {
	input.risk_band == "critical"
	v := {
		"rule_id": "critical_performance_requires_review",
		"message": "Performance crítica (risk_band=critical) requer revisão antes de prosseguir",
		"severity": "HIGH",
	}
}

# Quando a duração estimada é fornecida (numérica), exige que não exceda 1 hora.
# O guard is_number evita falso-negativo silencioso quando o campo vem null.
violations[v] {
	is_number(input.estimated_duration_ms)
	input.estimated_duration_ms > 3600000
	v := {
		"rule_id": "estimated_duration_exceeds_limit",
		"message": sprintf("Duração estimada excede o limite de 3600000ms: %v", [input.estimated_duration_ms]),
		"severity": "MEDIUM",
	}
}
