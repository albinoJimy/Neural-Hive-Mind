package neuralhive.orchestrator.security_constraints

# Resultado principal
result := {
    "allow": allow,
    "violations": violations,
    "warnings": warnings,
    "security_context": security_context
}

# Allow se não houver violações críticas/high
default allow := false
allow {
    count([v | v := violations[_]; v.severity == "critical"]) == 0
    count([v | v := violations[_]; v.severity == "high"]) == 0
}

# Coletar violações
violations[violation] {
    violation := cross_tenant_access_violation
}

violations[violation] {
    violation := missing_authentication_violation
}

violations[violation] {
    violation := invalid_jwt_violation
}

violations[violation] {
    violation := insufficient_permissions_violation
}

violations[violation] {
    violation := pii_handling_violation
}

violations[violation] {
    violation := tenant_rate_limit_exceeded_violation
}

# Regra 1: Cross-tenant access
cross_tenant_access_violation := violation {
    ticket := input.resource
    ticket_tenant := ticket.tenant_id
    allowed_tenants := input.security.allowed_tenants
    
    not tenant_is_allowed(ticket_tenant, allowed_tenants)
    
    violation := {
        "policy": "security_constraints",
        "rule": "cross_tenant_access",
        "severity": "critical",
        "field": "tenant_id",
        "msg": sprintf("Tenant %v não está na whitelist de tenants permitidos", [ticket_tenant]),
        "expected": allowed_tenants,
        "actual": ticket_tenant
    }
}

# Regra 2: Missing authentication
missing_authentication_violation := violation {
    context := input.context
    spiffe_enabled := input.security.spiffe_enabled
    
    spiffe_enabled == true
    not context.jwt_token
    
    violation := {
        "policy": "security_constraints",
        "rule": "missing_authentication",
        "severity": "critical",
        "field": "context.jwt_token",
        "msg": "SPIFFE JWT token ausente quando autenticação está habilitada",
        "expected": "JWT token válido",
        "actual": null
    }
}

# Regra 3: Invalid JWT (validação básica de estrutura)
invalid_jwt_violation := violation {
    context := input.context
    jwt_token := context.jwt_token
    
    jwt_token != null
    not is_valid_jwt_structure(jwt_token)
    
    violation := {
        "policy": "security_constraints",
        "rule": "invalid_jwt",
        "severity": "critical",
        "field": "context.jwt_token",
        "msg": "JWT token com estrutura inválida",
        "expected": "JWT com formato válido (header.payload.signature)",
        "actual": jwt_token
    }
}

# Regra 4: Insufficient permissions (RBAC)
insufficient_permissions_violation := violation {
    ticket := input.resource
    context := input.context
    rbac_roles := input.security.rbac_roles
    
    user_id := context.user_id
    user_roles := rbac_roles[user_id]
    required_capability := ticket.required_capabilities[_]
    
    not has_capability_permission(user_roles, required_capability)
    
    violation := {
        "policy": "security_constraints",
        "rule": "insufficient_permissions",
        "severity": "high",
        "field": "required_capabilities",
        "msg": sprintf("Usuário %v não tem permissão para capability %v", [user_id, required_capability]),
        "expected": sprintf("Role com permissão para %v", [required_capability]),
        "actual": user_roles
    }
}

# Regra 5: PII handling violation
pii_handling_violation := violation {
    ticket := input.resource
    contains_pii := ticket.contains_pii
    data_classification := ticket.data_classification
    
    contains_pii == true
    data_classification != "confidential"
    
    violation := {
        "policy": "security_constraints",
        "rule": "pii_handling_violation",
        "severity": "high",
        "field": "data_classification",
        "msg": "Dados com PII devem ter classificação 'confidential'",
        "expected": "confidential",
        "actual": data_classification
    }
}

# Regra 6: Tenant rate limit exceeded
tenant_rate_limit_exceeded_violation := violation {
    ticket := input.resource
    context := input.context
    tenant_id := ticket.tenant_id

    limit := tenant_limit(tenant_id)
    request_count := context.request_count_last_minute
    request_count > limit

    violation := {
        "policy": "security_constraints",
        "rule": "tenant_rate_limit_exceeded",
        "severity": "medium",
        "field": "request_count_last_minute",
        "msg": sprintf("Tenant %v excedeu rate limit de %v req/min (atual: %v)", [tenant_id, limit, request_count]),
        "expected": limit,
        "actual": request_count
    }
}

tenant_limit(tenant_id) = limit {
    limit := input.security.tenant_rate_limits[tenant_id]
} else = limit {
    limit := input.security.default_tenant_rate_limit
} else = limit {
    limit := input.security.global_rate_limit
}

# Helpers
tenant_is_allowed(tenant_id, allowed_list) {
    count(allowed_list) == 0
}

tenant_is_allowed(tenant_id, allowed_list) {
    allowed_list[_] == tenant_id
}

is_valid_jwt_structure(token) {
    # Validação básica: 3 partes separadas por '.'
    parts := split(token, ".")
    count(parts) == 3
}

has_capability_permission(roles, capability) {
    # Mapeamento simplificado: developer pode code_generation/testing, admin pode tudo
    roles[_] == "admin"
}

has_capability_permission(roles, capability) {
    roles[_] == "developer"
    capability_allowed_for_developer(capability)
}

capability_allowed_for_developer(cap) {
    cap == "code_generation"
}

capability_allowed_for_developer(cap) {
    cap == "testing"
}

# Security context para auditoria
security_context := {
    "tenant_id": input.resource.tenant_id,
    "user_id": input.context.user_id,
    "authenticated": is_authenticated,
    "authorized": is_authorized,
    "timestamp": input.context.current_time
}

is_authenticated {
    input.context.jwt_token != null
    is_valid_jwt_structure(input.context.jwt_token)
}

is_authorized {
    count([v | v := violations[_]; v.rule == "insufficient_permissions"]) == 0
}
