package neuralhive.orchestrator.sla_enforcement

# Mapeamento de QoS por risk_band
qos_requirements := {
    "critical": {
        "delivery_mode": "EXACTLY_ONCE",
        "consistency": "STRONG"
    },
    "high": {
        "delivery_mode": "EXACTLY_ONCE",
        "consistency": "STRONG"
    },
    "medium": {
        "delivery_mode": "AT_LEAST_ONCE",
        "consistency": ["STRONG", "EVENTUAL"]
    },
    "low": {
        "delivery_mode": ["AT_LEAST_ONCE", "AT_MOST_ONCE"],
        "consistency": ["STRONG", "EVENTUAL", "WEAK"]
    }
}

# Mapeamento de priority por risk_band
priority_requirements := {
    "critical": ["CRITICAL"],
    "high": ["CRITICAL", "HIGH"],
    "medium": ["CRITICAL", "HIGH", "NORMAL"],
    "low": ["CRITICAL", "HIGH", "NORMAL", "LOW"]
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
    violation := deadline_in_past
}

violations[violation] {
    violation := deadline_too_far
}

violations[violation] {
    violation := qos_mismatch_risk_band
}

violations[violation] {
    violation := priority_mismatch_risk_band
}

violations[violation] {
    violation := timeout_insufficient
}

# Coletar warnings
warnings[warning] {
    warning := deadline_approaching_threshold
}

# Regra 1: Deadline no passado
deadline_in_past := violation {
    ticket := input.resource
    deadline := ticket.sla.deadline
    current_time := input.context.current_time

    deadline < current_time

    violation := {
        "policy": "sla_enforcement",
        "rule": "deadline_in_past",
        "severity": "critical",
        "field": "sla.deadline",
        "msg": sprintf("Deadline %v está no passado (current_time=%v)", [deadline, current_time]),
        "expected": sprintf(">%v", [current_time]),
        "actual": deadline
    }
}

# Regra 2: Deadline muito distante (>7 dias)
deadline_too_far := violation {
    ticket := input.resource
    deadline := ticket.sla.deadline
    current_time := input.context.current_time

    # 7 dias em milissegundos
    seven_days_ms := 7 * 24 * 60 * 60 * 1000
    max_deadline := current_time + seven_days_ms

    deadline > max_deadline

    violation := {
        "policy": "sla_enforcement",
        "rule": "deadline_too_far",
        "severity": "medium",
        "field": "sla.deadline",
        "msg": sprintf("Deadline está muito distante (>7 dias): %v", [deadline]),
        "expected": sprintf("<=%v", [max_deadline]),
        "actual": deadline
    }
}

# Regra 3: QoS não alinhado com risk_band
qos_mismatch_risk_band := violation {
    ticket := input.resource
    risk_band := ticket.risk_band
    qos := ticket.qos

    # Para critical e high, validar delivery_mode exato
    risk_band == "critical"
    required_delivery := qos_requirements[risk_band].delivery_mode
    qos.delivery_mode != required_delivery

    violation := {
        "policy": "sla_enforcement",
        "rule": "qos_mismatch_risk_band",
        "severity": "critical",
        "field": "qos.delivery_mode",
        "msg": sprintf("Risk_band=%v requer delivery_mode=%v, encontrado %v", [risk_band, required_delivery, qos.delivery_mode]),
        "expected": required_delivery,
        "actual": qos.delivery_mode
    }
}

qos_mismatch_risk_band := violation {
    ticket := input.resource
    risk_band := ticket.risk_band
    qos := ticket.qos

    risk_band == "high"
    required_delivery := qos_requirements[risk_band].delivery_mode
    qos.delivery_mode != required_delivery

    violation := {
        "policy": "sla_enforcement",
        "rule": "qos_mismatch_risk_band",
        "severity": "high",
        "field": "qos.delivery_mode",
        "msg": sprintf("Risk_band=%v requer delivery_mode=%v, encontrado %v", [risk_band, required_delivery, qos.delivery_mode]),
        "expected": required_delivery,
        "actual": qos.delivery_mode
    }
}

qos_mismatch_risk_band := violation {
    ticket := input.resource
    risk_band := ticket.risk_band
    qos := ticket.qos

    # Para critical e high, validar consistency
    risk_band == "critical"
    required_consistency := qos_requirements[risk_band].consistency
    qos.consistency != required_consistency

    violation := {
        "policy": "sla_enforcement",
        "rule": "qos_mismatch_risk_band",
        "severity": "critical",
        "field": "qos.consistency",
        "msg": sprintf("Risk_band=%v requer consistency=%v, encontrado %v", [risk_band, required_consistency, qos.consistency]),
        "expected": required_consistency,
        "actual": qos.consistency
    }
}

qos_mismatch_risk_band := violation {
    ticket := input.resource
    risk_band := ticket.risk_band
    qos := ticket.qos

    risk_band == "high"
    required_consistency := qos_requirements[risk_band].consistency
    qos.consistency != required_consistency

    violation := {
        "policy": "sla_enforcement",
        "rule": "qos_mismatch_risk_band",
        "severity": "high",
        "field": "qos.consistency",
        "msg": sprintf("Risk_band=%v requer consistency=%v, encontrado %v", [risk_band, required_consistency, qos.consistency]),
        "expected": required_consistency,
        "actual": qos.consistency
    }
}

# Regra 4: Priority não alinhada com risk_band
priority_mismatch_risk_band := violation {
    ticket := input.resource
    risk_band := ticket.risk_band
    priority := ticket.priority

    allowed_priorities := priority_requirements[risk_band]
    not priority_is_allowed(priority, allowed_priorities)

    violation := {
        "policy": "sla_enforcement",
        "rule": "priority_mismatch_risk_band",
        "severity": "medium",
        "field": "priority",
        "msg": sprintf("Priority=%v não permitida para risk_band=%v (permitidas: %v)", [priority, risk_band, allowed_priorities]),
        "expected": allowed_priorities,
        "actual": priority
    }
}

# Regra 5: Timeout insuficiente
timeout_insufficient := violation {
    ticket := input.resource
    timeout_ms := ticket.sla.timeout_ms
    estimated_ms := ticket.estimated_duration_ms

    # Timeout deve ser >= estimated_duration * 1.5
    min_timeout := estimated_ms * 1.5
    timeout_ms < min_timeout

    violation := {
        "policy": "sla_enforcement",
        "rule": "timeout_insufficient",
        "severity": "high",
        "field": "sla.timeout_ms",
        "msg": sprintf("Timeout de %vms insuficiente para estimated_duration de %vms (requer >=1.5x = %vms)", [timeout_ms, estimated_ms, min_timeout]),
        "expected": sprintf(">=%v", [min_timeout]),
        "actual": timeout_ms
    }
}

# Warning: Deadline se aproximando
deadline_approaching_threshold := warning {
    ticket := input.resource
    deadline := ticket.sla.deadline
    current_time := input.context.current_time

    time_remaining := deadline - current_time
    timeout_ms := ticket.sla.timeout_ms

    # Warning se <20% do tempo restante
    threshold := timeout_ms * 0.2
    time_remaining < threshold
    time_remaining > 0  # Não duplicar com deadline_in_past

    warning := {
        "policy": "sla_enforcement",
        "rule": "deadline_approaching_threshold",
        "msg": sprintf("Deadline se aproximando: restam apenas %vms (<20%% do timeout)", [time_remaining])
    }
}

# Helper: Verificar se priority está permitida
priority_is_allowed(priority, allowed_list) {
    allowed_list[_] == priority
}
