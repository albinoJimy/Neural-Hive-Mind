package neural_hive.security.validation_test

import data.neural_hive.security.validation

# Task limpa (viability-analysis): não destrutiva, confidential, risco médio → allow
test_clean_task_allowed {
	validation.allow with input as {
		"target": "OAuth2 com MFA",
		"is_destructive": false,
		"security_level": "confidential",
		"risk_band": "medium",
	}
}

# Operação destrutiva sem confidential → deny
test_destructive_without_confidential_denied {
	not validation.allow with input as {
		"is_destructive": true,
		"security_level": "internal",
		"risk_band": "medium",
	}
}

# Operação destrutiva COM confidential → allow (a violação não dispara)
test_destructive_with_confidential_allowed {
	validation.allow with input as {
		"is_destructive": true,
		"security_level": "confidential",
		"risk_band": "high",
	}
}

# Risco crítico sem confidential → deny
test_critical_risk_without_confidential_denied {
	not validation.allow with input as {
		"is_destructive": false,
		"security_level": "internal",
		"risk_band": "critical",
	}
}

# Fail-closed: destrutiva com security_level ausente (null) → deny
test_destructive_with_null_security_level_denied {
	not validation.allow with input as {
		"is_destructive": true,
		"security_level": null,
		"risk_band": "medium",
	}
}

# Violação produz a estrutura esperada (rule_id/message/severity)
test_violation_structure {
	violations := validation.violations with input as {
		"is_destructive": true,
		"security_level": "internal",
		"risk_band": "medium",
	}
	count(violations) == 1
	violations[_].rule_id == "destructive_requires_confidential"
	violations[_].severity == "HIGH"
}
