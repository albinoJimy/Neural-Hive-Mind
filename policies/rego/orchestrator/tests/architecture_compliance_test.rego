package neural_hive.architecture.compliance_test

import data.neural_hive.architecture.compliance

# Mudança não destrutiva com sujeito definido → allow
test_clean_architecture_allowed {
	compliance.allow with input as {
		"subject": "serviço de autenticação",
		"is_destructive": false,
		"security_level": "internal",
		"risk_band": "medium",
	}
}

# Mudança destrutiva sem confidential → deny
test_destructive_without_confidential_denied {
	not compliance.allow with input as {
		"subject": "serviço de autenticação",
		"is_destructive": true,
		"security_level": "internal",
		"risk_band": "high",
	}
}

# Mudança destrutiva COM confidential → allow
test_destructive_with_confidential_allowed {
	compliance.allow with input as {
		"subject": "serviço de autenticação",
		"is_destructive": true,
		"security_level": "confidential",
		"risk_band": "high",
	}
}

# Sem subject → deny (falta componente alvo)
test_missing_subject_denied {
	not compliance.allow with input as {
		"is_destructive": false,
		"security_level": "internal",
		"risk_band": "medium",
	}
}

# Estrutura da violação de subject ausente
test_missing_subject_violation_structure {
	violations := compliance.violations with input as {
		"is_destructive": false,
		"security_level": "internal",
		"risk_band": "medium",
	}
	violations[_].rule_id == "architecture_missing_subject"
	violations[_].severity == "MEDIUM"
}
