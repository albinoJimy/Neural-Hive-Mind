package neural_hive.operational.procedures_test

import data.neural_hive.operational.procedures

# Operação não destrutiva, risco médio → allow
test_clean_operational_allowed {
	procedures.allow with input as {
		"subject": "rotina de backup",
		"is_destructive": false,
		"security_level": "internal",
		"risk_band": "medium",
	}
}

# Operação destrutiva sem confidential → deny
test_destructive_without_confidential_denied {
	not procedures.allow with input as {
		"subject": "rotina de backup",
		"is_destructive": true,
		"security_level": "internal",
		"risk_band": "medium",
	}
}

# Operação destrutiva COM confidential → allow
test_destructive_with_confidential_allowed {
	procedures.allow with input as {
		"subject": "rotina de backup",
		"is_destructive": true,
		"security_level": "confidential",
		"risk_band": "high",
	}
}

# Risco crítico → deny
test_critical_risk_denied {
	not procedures.allow with input as {
		"subject": "rotina de backup",
		"is_destructive": false,
		"security_level": "internal",
		"risk_band": "critical",
	}
}

# Estrutura da violação destrutiva
test_destructive_violation_structure {
	violations := procedures.violations with input as {
		"subject": "rotina de backup",
		"is_destructive": true,
		"security_level": "internal",
		"risk_band": "medium",
	}
	violations[_].rule_id == "destructive_operation_requires_confidential"
	violations[_].severity == "HIGH"
}
