package neuralhive.orchestrator.resource_limits

# Limites de timeout por risk_band (em milissegundos)
timeout_limits := {
    "critical": 7200000,  # 2h
    "high": 3600000,      # 1h
    "medium": 1800000,    # 30min
    "low": 900000         # 15min
}

# Limites de retries por risk_band
retry_limits := {
    "critical": 5,
    "high": 3,
    "medium": 2,
    "low": 1
}

# Resultado principal
result := {
    "allow": allow,
    "violations": violations,
    "warnings": warnings
}

# Allow se não houver violações
default allow := false
allow {
    count(violations) == 0
}

# Coletar todas as violações
violations[violation] {
    violation := timeout_exceeds_maximum
}

violations[violation] {
    violation := retries_exceed_maximum
}

violations[violation] {
    violation := estimated_duration_unrealistic
}

violations[violation] {
    violation := capabilities_not_allowed[_]
}

violations[violation] {
    violation := concurrent_tickets_limit_exceeded
}

# Coletar warnings
warnings := []

# Regra 1: Timeout excede máximo
timeout_exceeds_maximum := violation {
    ticket := input.resource
    risk_band := ticket.risk_band
    timeout_ms := ticket.sla.timeout_ms
    max_timeout := timeout_limits[risk_band]

    timeout_ms > max_timeout

    violation := {
        "policy": "resource_limits",
        "rule": "timeout_exceeds_maximum",
        "severity": "high",
        "field": "sla.timeout_ms",
        "msg": sprintf("Timeout de %vms excede máximo de %vms para risk_band=%v", [timeout_ms, max_timeout, risk_band]),
        "expected": max_timeout,
        "actual": timeout_ms
    }
}

# Regra 2: Retries excedem máximo
retries_exceed_maximum := violation {
    ticket := input.resource
    risk_band := ticket.risk_band
    max_retries := ticket.sla.max_retries
    max_allowed := retry_limits[risk_band]

    max_retries > max_allowed

    violation := {
        "policy": "resource_limits",
        "rule": "retries_exceed_maximum",
        "severity": "medium",
        "field": "sla.max_retries",
        "msg": sprintf("Max_retries de %v excede máximo de %v para risk_band=%v", [max_retries, max_allowed, risk_band]),
        "expected": max_allowed,
        "actual": max_retries
    }
}

# Regra 3: Estimated duration unrealistic
estimated_duration_unrealistic := violation {
    ticket := input.resource
    estimated_ms := ticket.estimated_duration_ms
    timeout_ms := ticket.sla.timeout_ms

    # Muito curto (<1s) ou maior que timeout
    condition := estimated_ms < 1000
    condition

    violation := {
        "policy": "resource_limits",
        "rule": "estimated_duration_unrealistic",
        "severity": "low",
        "field": "estimated_duration_ms",
        "msg": sprintf("Estimated_duration de %vms é muito curto (mínimo 1000ms)", [estimated_ms]),
        "expected": ">=1000",
        "actual": estimated_ms
    }
}

estimated_duration_unrealistic := violation {
    ticket := input.resource
    estimated_ms := ticket.estimated_duration_ms
    timeout_ms := ticket.sla.timeout_ms

    estimated_ms >= timeout_ms

    violation := {
        "policy": "resource_limits",
        "rule": "estimated_duration_unrealistic",
        "severity": "medium",
        "field": "estimated_duration_ms",
        "msg": sprintf("Estimated_duration de %vms não pode ser >= timeout de %vms", [estimated_ms, timeout_ms]),
        "expected": sprintf("<%v", [timeout_ms]),
        "actual": estimated_ms
    }
}

# Regra 4: Capabilities não permitidas
capabilities_not_allowed[violation] {
    ticket := input.resource
    allowed := input.parameters.allowed_capabilities

    required_cap := ticket.required_capabilities[_]
    not is_capability_allowed(required_cap, allowed)

    violation := {
        "policy": "resource_limits",
        "rule": "capabilities_not_allowed",
        "severity": "high",
        "field": "required_capabilities",
        "msg": sprintf("Capability '%v' não está na whitelist", [required_cap]),
        "expected": allowed,
        "actual": required_cap
    }
}

# Regra 5: Limite de tickets concorrentes
concurrent_tickets_limit_exceeded := violation {
    context := input.context
    total_tickets := context.total_tickets
    max_tickets := input.parameters.max_concurrent_tickets

    total_tickets > max_tickets

    violation := {
        "policy": "resource_limits",
        "rule": "concurrent_tickets_limit",
        "severity": "high",
        "field": "total_tickets",
        "msg": sprintf("Total de %v tickets excede limite de %v tickets concorrentes", [total_tickets, max_tickets]),
        "expected": max_tickets,
        "actual": total_tickets
    }
}

# Helper: Verificar se capability está permitida
is_capability_allowed(capability, allowed_list) {
    allowed_list[_] == capability
}
