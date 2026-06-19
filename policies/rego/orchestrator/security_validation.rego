package neural_hive.security.validation

# Política de validação de segurança para tasks VALIDATE do pipeline cognitivo.
#
# O ValidateExecutor (worker-agents) consulta:
#   GET /v1/data/neural_hive/security/validation
# com input = {target, subject, entities, security_level, is_destructive, risk_band}.
#
# Contrato esperado pelo opa_client (worker): devolve um documento com
#   { "allow": bool, "violations": [ {rule_id, message, severity}, ... ] }
#
# Postura: allow=true quando não há violações (task limpa); deny (allow=false)
# com a lista de violações quando uma condição de risco é detetada. Quando o OPA
# está indisponível, o executor aplica fallback conservador (fail-closed).

default allow := false

allow {
	count(violations) == 0
}

# Operação destrutiva sem nível de confidencialidade adequado.
violations[v] {
	input.is_destructive == true
	input.security_level != "confidential"
	v := {
		"rule_id": "destructive_requires_confidential",
		"message": sprintf("Operação destrutiva requer security_level=confidential, encontrado: %v", [input.security_level]),
		"severity": "HIGH",
	}
}

# Risco crítico sem nível de confidencialidade adequado.
violations[v] {
	input.risk_band == "critical"
	input.security_level != "confidential"
	v := {
		"rule_id": "critical_risk_requires_confidential",
		"message": "Risco crítico (risk_band=critical) requer security_level=confidential",
		"severity": "MEDIUM",
	}
}
