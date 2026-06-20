package neural_hive.operational.procedures

# Política de procedimentos operacionais para tasks VALIDATE do domínio "operational".
#
# O ValidateExecutor (worker-agents) consulta:
#   GET /v1/data/neural_hive/operational/procedures
# com input = {target, subject, entities, security_level, is_destructive, risk_band}.
#
# Contrato esperado pelo opa_client (worker): devolve um documento com
#   { "allow": bool, "violations": [ {rule_id, message, severity}, ... ] }
#
# Postura: allow=true quando não há violações; deny (allow=false) com a lista de
# violações quando um procedimento operacional de risco é detetado. Usa input.X
# defensivamente — Rego ignora chaves ausentes.

default allow := false

allow {
	count(violations) == 0
}

# Operação destrutiva exige nível de confidencialidade adequado.
violations[v] {
	input.is_destructive == true
	input.security_level != "confidential"
	v := {
		"rule_id": "destructive_operation_requires_confidential",
		"message": sprintf("Operação operacional destrutiva requer security_level=confidential, encontrado: %v", [input.security_level]),
		"severity": "HIGH",
	}
}

# Risco crítico operacional exige revisão explícita.
violations[v] {
	input.risk_band == "critical"
	v := {
		"rule_id": "critical_risk_requires_review",
		"message": "Risco operacional crítico (risk_band=critical) requer revisão antes de prosseguir",
		"severity": "MEDIUM",
	}
}
