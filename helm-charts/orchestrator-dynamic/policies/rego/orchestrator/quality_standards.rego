package neural_hive.quality.standards

# Política de padrões de qualidade para tasks VALIDATE do domínio "quality".
#
# O ValidateExecutor (worker-agents) consulta:
#   GET /v1/data/neural_hive/quality/standards
# com input = {target, subject, entities, security_level, is_destructive, risk_band}.
#
# Contrato esperado pelo opa_client (worker): devolve um documento com
#   { "allow": bool, "violations": [ {rule_id, message, severity}, ... ] }
#
# Postura: allow=true quando não há violações; deny (allow=false) com a lista de
# violações quando um padrão de qualidade é desrespeitado. Regras condicionais a
# campos opcionais (ex: quality_score) só disparam quando o campo existe.

default allow := false

allow {
	count(violations) == 0
}

# Sem sujeito/artefacto alvo não há o que avaliar quanto a qualidade.
violations[v] {
	not _has_subject
	v := {
		"rule_id": "quality_missing_subject",
		"message": "Validação de qualidade requer um sujeito/artefacto alvo (input.subject)",
		"severity": "MEDIUM",
	}
}

# Quando quality_score é fornecido (numérico), exige um mínimo aceitável.
# O guard is_number evita falso-negativo silencioso quando o campo vem null.
violations[v] {
	is_number(input.quality_score)
	input.quality_score < 0.5
	v := {
		"rule_id": "quality_score_below_threshold",
		"message": sprintf("Quality score abaixo do mínimo (0.5): %v", [input.quality_score]),
		"severity": "HIGH",
	}
}

# input.subject presente e não vazio.
_has_subject {
	input.subject
	input.subject != ""
}
