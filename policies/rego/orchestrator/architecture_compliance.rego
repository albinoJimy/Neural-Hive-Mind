package neural_hive.architecture.compliance

# Política de conformidade arquitetural para tasks VALIDATE do domínio "architecture".
#
# O ValidateExecutor (worker-agents) consulta:
#   GET /v1/data/neural_hive/architecture/compliance
# com input = {target, subject, entities, security_level, is_destructive, risk_band}.
#
# Contrato esperado pelo opa_client (worker): devolve um documento com
#   { "allow": bool, "violations": [ {rule_id, message, severity}, ... ] }
#
# Postura: allow=true quando não há violações; deny (allow=false) com a lista de
# violações quando uma condição de risco arquitetural é detetada. Usa input.X
# defensivamente — Rego ignora chaves ausentes, pelo que campos opcionais não
# disparam violações quando não existem.

default allow := false

allow {
	count(violations) == 0
}

# Mudança arquitetural destrutiva exige nível de confidencialidade adequado.
violations[v] {
	input.is_destructive == true
	input.security_level != "confidential"
	v := {
		"rule_id": "architectural_change_requires_confidential",
		"message": sprintf("Mudança arquitetural destrutiva requer security_level=confidential, encontrado: %v", [input.security_level]),
		"severity": "HIGH",
	}
}

# Sem componente/sujeito alvo definido não há contexto arquitetural a validar.
violations[v] {
	not _has_subject
	v := {
		"rule_id": "architecture_missing_subject",
		"message": "Validação arquitetural requer um componente/sujeito alvo (input.subject)",
		"severity": "MEDIUM",
	}
}

# input.subject presente e não vazio.
_has_subject {
	input.subject
	input.subject != ""
}
