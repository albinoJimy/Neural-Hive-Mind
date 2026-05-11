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
    violation := jwt_expired_violation
}

violations[violation] {
    violation := jwt_invalid_issuer_violation
}

violations[violation] {
    violation := jwt_invalid_audience_violation
}

violations[violation] {
    violation := jwt_invalid_spiffe_id_violation
}

violations[violation] {
    violation := jwt_missing_required_claims_violation
}

violations[violation] {
    violation := jwt_jwks_unavailable_violation
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

# Regra 3: Invalid JWT (validação completa com io.jwt.decode_verify)
invalid_jwt_violation := violation {
    context := input.context
    jwt_token := context.jwt_token

    jwt_token != null
    not is_valid_jwt_with_verification(jwt_token)

    violation := {
        "policy": "security_constraints",
        "rule": "invalid_jwt",
        "severity": "critical",
        "field": "context.jwt_token",
        "msg": "JWT token inválido: assinatura não verificada ou claims obrigatórios ausentes",
        "expected": "JWT válido com assinatura verificada e claims obrigatórios (sub, exp, iat, tenant_id, roles)",
        "actual": "JWT inválido"
    }
}

# Regra 3.1: JWT expirado
jwt_expired_violation := violation {
    context := input.context
    jwt_token := context.jwt_token

    jwt_token != null
    is_valid_jwt_structure(jwt_token)

    # Decodificar payload para verificar exp
    [header, payload, signature] := io.jwt.decode(jwt_token)
    exp := payload.exp
    current_time := time.now_ns() / 1000000000  # Converter para segundos

    exp < current_time

    violation := {
        "policy": "security_constraints",
        "rule": "jwt_expired",
        "severity": "critical",
        "field": "context.jwt_token",
        "msg": sprintf("JWT expirado (exp: %v, current: %v)", [exp, current_time]),
        "expected": "JWT não expirado",
        "actual": exp
    }
}

# Regra 3.2: JWT issuer inválido
jwt_invalid_issuer_violation := violation {
    context := input.context
    jwt_token := context.jwt_token
    expected_issuer := input.security.jwt_issuer

    jwt_token != null
    expected_issuer != null

    [header, payload, signature] := io.jwt.decode(jwt_token)
    iss := payload.iss

    iss != expected_issuer

    violation := {
        "policy": "security_constraints",
        "rule": "jwt_invalid_issuer",
        "severity": "high",
        "field": "context.jwt_token",
        "msg": sprintf("JWT issuer inválido (esperado: %v, atual: %v)", [expected_issuer, iss]),
        "expected": expected_issuer,
        "actual": iss
    }
}

# Regra 3.3: JWT audience inválido
jwt_invalid_audience_violation := violation {
    context := input.context
    jwt_token := context.jwt_token
    expected_audience := input.security.jwt_audience

    jwt_token != null
    expected_audience != null

    [header, payload, signature] := io.jwt.decode(jwt_token)
    aud := payload.aud

    # aud pode ser string ou array
    not audience_matches(aud, expected_audience)

    violation := {
        "policy": "security_constraints",
        "rule": "jwt_invalid_audience",
        "severity": "high",
        "field": "context.jwt_token",
        "msg": sprintf("JWT audience inválido (esperado: %v, atual: %v)", [expected_audience, aud]),
        "expected": expected_audience,
        "actual": aud
    }
}

# Regra 3.4: SPIFFE ID inválido no subject
jwt_invalid_spiffe_id_violation := violation {
    context := input.context
    jwt_token := context.jwt_token
    trust_domain := input.security.spiffe_trust_domain

    jwt_token != null
    trust_domain != null

    [header, payload, signature] := io.jwt.decode(jwt_token)
    sub := payload.sub

    # Subject deve ser um SPIFFE ID válido
    not startswith(sub, sprintf("spiffe://%v/", [trust_domain]))

    violation := {
        "policy": "security_constraints",
        "rule": "jwt_invalid_spiffe_id",
        "severity": "critical",
        "field": "context.jwt_token",
        "msg": sprintf("SPIFFE ID inválido no JWT subject (esperado trust domain: %v, atual: %v)", [trust_domain, sub]),
        "expected": sprintf("spiffe://%v/...", [trust_domain]),
        "actual": sub
    }
}

# Regra 3.5: Claims obrigatórios ausentes (tenant_id, roles)
jwt_missing_required_claims_violation := violation {
    context := input.context
    jwt_token := context.jwt_token

    jwt_token != null
    is_valid_jwt_structure(jwt_token)

    [header, payload, signature] := io.jwt.decode(jwt_token)

    # Verificar claims obrigatórios
    required_claims := ["sub", "exp", "iat", "tenant_id", "roles"]
    missing_claim := required_claims[_]
    not payload[missing_claim]

    violation := {
        "policy": "security_constraints",
        "rule": "jwt_missing_required_claims",
        "severity": "critical",
        "field": "context.jwt_token",
        "msg": sprintf("JWT ausente claim obrigatório: %v", [missing_claim]),
        "expected": required_claims,
        "actual": missing_claim
    }
}

# Regra 3.6: JWKS indisponível (fail-closed)
# Esta violação é gerada quando:
# 1. JWT token está presente
# 2. JWKS não está disponível (nem via data nem via http.send)
# 3. Fallback sem assinatura NÃO está habilitado (jwt_allow_unsigned_fallback != true)
jwt_jwks_unavailable_violation := violation {
    context := input.context
    jwt_token := context.jwt_token

    jwt_token != null
    is_valid_jwt_structure(jwt_token)

    # JWKS não disponível
    not get_spire_jwks

    # Fallback não permitido (comportamento seguro padrão)
    not input.security.jwt_allow_unsigned_fallback == true

    violation := {
        "policy": "security_constraints",
        "rule": "jwt_jwks_unavailable",
        "severity": "critical",
        "field": "context.jwt_token",
        "msg": "JWKS indisponível para verificação de assinatura JWT. Configurar jwks_url ou data.spire_jwks",
        "expected": "JWKS disponível via data.spire_jwks ou input.security.jwks_url",
        "actual": "JWKS não encontrado"
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

# Helper: Obter JWKS do SPIRE Server via HTTP
# Usa cache interno do OPA para evitar requests excessivos
# Retorna JWKS JSON ou undefined se indisponível
get_spire_jwks := jwks {
    # Verificar se JWKS foi fornecido via data (testes ou bundle)
    jwks := data.spire_jwks
} else := jwks {
    # Buscar JWKS via HTTP do SPIRE Server
    jwks_url := input.security.jwks_url
    jwks_url != null

    response := http.send({
        "method": "GET",
        "url": jwks_url,
        "cache": true,
        "force_cache": true,
        "force_cache_duration_seconds": 300,  # Cache de 5 minutos
        "timeout": "5s",
        "raise_error": false
    })

    response.status_code == 200
    jwks := response.body
}

# Helper: Validar JWT com verificação de assinatura usando JWKS do SPIRE
# Modos de operação:
# 1. Produção: JWKS carregado via http.send do SPIRE Server ou via data.spire_jwks
# 2. Dev explícito: Fallback sem assinatura APENAS se input.security.jwt_allow_unsigned_fallback == true
# 3. Fail-closed: Retorna false se JWKS indisponível e fallback não permitido
is_valid_jwt_with_verification(token) {
    # Validação básica de estrutura
    is_valid_jwt_structure(token)

    # Obter configuração de segurança do input
    issuer := input.security.jwt_issuer
    audience := input.security.jwt_audience

    # Obter JWKS (via data ou http.send)
    jwks := get_spire_jwks

    # Verificar assinatura com JWKS
    # io.jwt.decode_verify retorna [valid, header, payload]
    # IMPORTANTE: time deve estar em segundos (Unix timestamp), não nanosegundos
    [valid, header, payload] := io.jwt.decode_verify(
        token,
        {
            "cert": jwks,
            "iss": issuer,
            "aud": audience,
            "time": time.now_ns() / 1000000000  # Converter nanosegundos para segundos
        }
    )

    # Validação bem-sucedida se valid == true
    valid == true

    # Verificar claims obrigatórios (incluindo novos: tenant_id, roles)
    payload.sub
    payload.exp
    payload.iat
    payload.tenant_id  # Claim obrigatório para multi-tenancy
    payload.roles      # Claim obrigatório para RBAC
}

# Fallback EXPLÍCITO: Validar JWT sem verificação de assinatura
# ATENÇÃO SEGURANÇA: Este fallback só é ativado quando:
# 1. JWKS não está disponível (nem via data nem via http.send)
# 2. input.security.jwt_allow_unsigned_fallback == true (opt-in explícito)
# Em produção, jwt_allow_unsigned_fallback DEVE ser false (default)
is_valid_jwt_with_verification(token) {
    # Validação básica de estrutura
    is_valid_jwt_structure(token)

    # CRÍTICO: Fallback só permitido se explicitamente habilitado
    input.security.jwt_allow_unsigned_fallback == true

    # Verificar que JWKS realmente não está disponível
    not get_spire_jwks

    # Decodificar sem verificar assinatura
    [header, payload, signature] := io.jwt.decode(token)

    # Verificar campos obrigatórios mínimos (estrutura + expiração)
    payload.sub
    payload.exp
    payload.iat
    payload.tenant_id  # Também exigir claims de multi-tenancy
    payload.roles      # Também exigir claims de RBAC

    # Validar expiração manualmente
    current_time := time.now_ns() / 1000000000
    payload.exp > current_time
}

# Helper: Verificar se audience corresponde
audience_matches(aud, expected) {
    # aud é string
    is_string(aud)
    aud == expected
}

audience_matches(aud, expected) {
    # aud é array
    is_array(aud)
    aud[_] == expected
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
