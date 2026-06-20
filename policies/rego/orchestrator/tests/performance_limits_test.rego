package neural_hive.performance.limits_test

import data.neural_hive.performance.limits

# Risco não crítico sem duração estimada → allow
test_clean_performance_allowed {
	limits.allow with input as {
		"subject": "endpoint de listagem",
		"risk_band": "medium",
	}
}

# Duração estimada dentro do limite → allow
test_duration_within_limit_allowed {
	limits.allow with input as {
		"subject": "endpoint de listagem",
		"risk_band": "low",
		"estimated_duration_ms": 1000000,
	}
}

# Risco crítico → deny (exige revisão)
test_critical_risk_denied {
	not limits.allow with input as {
		"subject": "endpoint de listagem",
		"risk_band": "critical",
	}
}

# Duração estimada acima do limite → deny
test_duration_exceeds_limit_denied {
	not limits.allow with input as {
		"subject": "endpoint de listagem",
		"risk_band": "low",
		"estimated_duration_ms": 7200000,
	}
}

# Estrutura da violação de risco crítico
test_critical_risk_violation_structure {
	violations := limits.violations with input as {
		"subject": "endpoint de listagem",
		"risk_band": "critical",
	}
	violations[_].rule_id == "critical_performance_requires_review"
	violations[_].severity == "HIGH"
}
