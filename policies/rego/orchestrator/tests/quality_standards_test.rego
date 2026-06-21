package neural_hive.quality.standards_test

import data.neural_hive.quality.standards

# Sujeito presente e sem quality_score → allow (score opcional não dispara)
test_clean_quality_allowed {
	standards.allow with input as {
		"subject": "módulo de pagamentos",
		"is_destructive": false,
		"security_level": "internal",
		"risk_band": "medium",
	}
}

# Sujeito presente com quality_score aceitável → allow
test_quality_score_above_threshold_allowed {
	standards.allow with input as {
		"subject": "módulo de pagamentos",
		"quality_score": 0.8,
	}
}

# Sem subject → deny
test_missing_subject_denied {
	not standards.allow with input as {
		"is_destructive": false,
		"risk_band": "medium",
	}
}

# quality_score abaixo do mínimo → deny
test_quality_score_below_threshold_denied {
	not standards.allow with input as {
		"subject": "módulo de pagamentos",
		"quality_score": 0.3,
	}
}

# Estrutura da violação de score baixo
test_quality_score_violation_structure {
	violations := standards.violations with input as {
		"subject": "módulo de pagamentos",
		"quality_score": 0.3,
	}
	violations[_].rule_id == "quality_score_below_threshold"
	violations[_].severity == "HIGH"
}
