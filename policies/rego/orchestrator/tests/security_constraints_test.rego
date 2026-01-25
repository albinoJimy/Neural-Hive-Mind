package neuralhive.orchestrator.security_constraints_test

import data.neuralhive.orchestrator.security_constraints

# ==============================================================================
# JWT Fixtures para Testes
# ==============================================================================

# Base64 encoded header: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9
# header: {"alg":"RS256","typ":"JWT"}

# JWT válido COM todos os claims obrigatórios (tenant_id, roles)
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000,"tenant_id":"tenant-123","roles":["developer"]}
valid_jwt_with_all_claims := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMCwidGVuYW50X2lkIjoidGVuYW50LTEyMyIsInJvbGVzIjpbImRldmVsb3BlciJdfQ.test_signature"

# JWT válido COM claims para tenant diferente (para teste cross-tenant)
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000,"tenant_id":"tenant-456","roles":["developer"]}
valid_jwt_tenant_456 := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMCwidGVuYW50X2lkIjoidGVuYW50LTQ1NiIsInJvbGVzIjpbImRldmVsb3BlciJdfQ.test_signature"

# JWT LEGADO sem tenant_id/roles (para teste de claims ausentes)
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000}
legacy_jwt_without_new_claims := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMH0.test_signature"

# JWT expirado (exp: 1600000000 - data passada)
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":1600000000,"iat":1500000000,"tenant_id":"tenant-123","roles":["developer"]}
expired_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjE2MDAwMDAwMDAsImlhdCI6MTUwMDAwMDAwMCwidGVuYW50X2lkIjoidGVuYW50LTEyMyIsInJvbGVzIjpbImRldmVsb3BlciJdfQ.test_signature"

# JWT com issuer errado
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://malicious-issuer.example.com","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000,"tenant_id":"tenant-123","roles":["developer"]}
wrong_issuer_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vbWFsaWNpb3VzLWlzc3Vlci5leGFtcGxlLmNvbSIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMCwidGVuYW50X2lkIjoidGVuYW50LTEyMyIsInJvbGVzIjpbImRldmVsb3BlciJdfQ.test_signature"

# JWT com audience errado
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"wrong-audience.example.com","exp":9999999999,"iat":1700000000,"tenant_id":"tenant-123","roles":["developer"]}
wrong_audience_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Indyb25nLWF1ZGllbmNlLmV4YW1wbGUuY29tIiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDAsInRlbmFudF9pZCI6InRlbmFudC0xMjMiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXX0.test_signature"

# JWT com SPIFFE ID inválido (trust domain errado)
# Payload: {"sub":"spiffe://wrong-domain.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000,"tenant_id":"tenant-123","roles":["developer"]}
wrong_spiffe_id_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly93cm9uZy1kb21haW4ubG9jYWwvbnMvbmV1cmFsLWhpdmUtZXhlY3V0aW9uL3NhL3dvcmtlci1hZ2VudHMiLCJpc3MiOiJodHRwczovL3NwaXJlLXNlcnZlci5zcGlyZS1zeXN0ZW0uc3ZjLmNsdXN0ZXIubG9jYWwiLCJhdWQiOiJvcmNoZXN0cmF0b3ItZHluYW1pYy5uZXVyYWwtaGl2ZS1vcmNoZXN0cmF0aW9uLnN2Yy5jbHVzdGVyLmxvY2FsIiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDAsInRlbmFudF9pZCI6InRlbmFudC0xMjMiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXX0.test_signature"

# JWT sem tenant_id
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000,"roles":["developer"]}
jwt_missing_tenant_id := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMCwicm9sZXMiOlsiZGV2ZWxvcGVyIl19.test_signature"

# JWT sem roles
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000,"tenant_id":"tenant-123"}
jwt_missing_roles := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMCwidGVuYW50X2lkIjoidGVuYW50LTEyMyJ9.test_signature"

# ==============================================================================
# Mock JWKS para Testes de Verificação de Assinatura
# ==============================================================================

# JWKS mock com chave RSA pública de teste
# Nota: Em testes reais de assinatura, usar chave real gerada para o JWT
mock_spire_jwks := {
    "keys": [{
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "test-key-1",
        "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
        "e": "AQAB"
    }]
}

# ==============================================================================
# Configuração Base de Segurança
# ==============================================================================

base_security_config := {
    "spiffe_enabled": true,
    "spiffe_trust_domain": "neural-hive.local",
    "jwt_issuer": "https://spire-server.spire-system.svc.cluster.local",
    "jwt_audience": "orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local",
    "trust_domain": "neural-hive.local",
    "allowed_tenants": ["tenant-123", "tenant-456"],
    "rbac_roles": {"user@example.com": ["developer"]},
    "data_residency_regions": ["us-east-1"],
    "tenant_rate_limits": {"tenant-123": 100},
    "global_rate_limit": 1000,
    "default_tenant_rate_limit": 100,
    # Habilitar fallback sem assinatura para testes sem JWKS
    "jwt_allow_unsigned_fallback": true
}

# Configuração com fallback desabilitado (fail-closed)
security_config_fail_closed := object.union(base_security_config, {
    "jwt_allow_unsigned_fallback": false
})

# ==============================================================================
# TESTES: Contexto de Segurança Válido
# ==============================================================================

# Teste: Contexto de segurança válido com JWT completo (com fallback habilitado)
test_valid_security_context {
    input := {
        "resource": {
            "ticket_id": "sec-123",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "confidential",
            "contains_pii": true
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 45
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# Teste: JWT válido com todos os claims obrigatórios (sem violações de claims)
test_valid_jwt_with_all_required_claims {
    input := {
        "resource": {
            "ticket_id": "sec-valid-all-claims",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "confidential",
            "contains_pii": true
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 45
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    # Não deve haver violações de claims ausentes
    missing_claims_violations := [v | v := result.violations[_]; v.rule == "jwt_missing_required_claims"]
    count(missing_claims_violations) == 0
}

# ==============================================================================
# TESTES: Violações de Cross-Tenant Access
# ==============================================================================

# Teste: Violação de acesso cross-tenant
test_cross_tenant_access_violation {
    input := {
        "resource": {
            "ticket_id": "sec-456",
            "tenant_id": "tenant-unauthorized",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": object.union(base_security_config, {
            "allowed_tenants": ["tenant-123", "tenant-456"],
            "tenant_rate_limits": {"tenant-unauthorized": 100}
        })
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "cross_tenant_access"
    violation.severity == "critical"
}

# ==============================================================================
# TESTES: Autenticação Ausente
# ==============================================================================

# Teste: Autenticação ausente quando SPIFFE habilitado
test_missing_authentication {
    input := {
        "resource": {
            "ticket_id": "sec-789",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "missing_authentication"
    violation.severity == "critical"
}

# Teste: SPIFFE desabilitado não requer JWT
test_spiffe_disabled_no_jwt_required {
    input := {
        "resource": {
            "ticket_id": "sec-no-spiffe",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "confidential",
            "contains_pii": true
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": object.union(base_security_config, {
            "spiffe_enabled": false
        })
    }

    result := security_constraints.result with input as input
    # Não deve disparar missing_authentication já que spiffe está desabilitado
    missing_auth_violations := [v | v := result.violations[_]; v.rule == "missing_authentication"]
    count(missing_auth_violations) == 0
}

# ==============================================================================
# TESTES: Validação de JWT - Expiração
# ==============================================================================

# Teste: JWT expirado
test_jwt_expired {
    input := {
        "resource": {
            "ticket_id": "sec-exp-001",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": expired_jwt,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "jwt_expired"
    violation.severity == "critical"
}

# ==============================================================================
# TESTES: Validação de JWT - Issuer
# ==============================================================================

# Teste: JWT com issuer inválido
test_jwt_invalid_issuer {
    input := {
        "resource": {
            "ticket_id": "sec-iss-001",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": wrong_issuer_jwt,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "jwt_invalid_issuer"
    violation.severity == "high"
}

# ==============================================================================
# TESTES: Validação de JWT - Audience
# ==============================================================================

# Teste: JWT com audience inválido
test_jwt_invalid_audience {
    input := {
        "resource": {
            "ticket_id": "sec-aud-001",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": wrong_audience_jwt,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "jwt_invalid_audience"
    violation.severity == "high"
}

# ==============================================================================
# TESTES: Validação de JWT - SPIFFE ID
# ==============================================================================

# Teste: JWT com SPIFFE ID inválido (trust domain errado)
test_jwt_invalid_spiffe_id {
    input := {
        "resource": {
            "ticket_id": "sec-spiffe-001",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": wrong_spiffe_id_jwt,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "jwt_invalid_spiffe_id"
    violation.severity == "critical"
}

# ==============================================================================
# TESTES: Validação de JWT - Claims Obrigatórios
# ==============================================================================

# Teste: JWT sem claim tenant_id
test_jwt_missing_tenant_id {
    input := {
        "resource": {
            "ticket_id": "sec-missing-tenant",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": jwt_missing_tenant_id,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "jwt_missing_required_claims"
    violation.severity == "critical"
}

# Teste: JWT sem claim roles
test_jwt_missing_roles {
    input := {
        "resource": {
            "ticket_id": "sec-missing-roles",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": jwt_missing_roles,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "jwt_missing_required_claims"
    violation.severity == "critical"
}

# ==============================================================================
# TESTES: Verificação de Assinatura JWT com JWKS
# ==============================================================================

# Teste: JWT válido com JWKS fornecido via data (mock)
# Nota: Este teste valida que a política aceita JWT quando JWKS está disponível
# Em ambiente real, a assinatura seria verificada criptograficamente
test_jwt_with_jwks_available {
    input := {
        "resource": {
            "ticket_id": "sec-jwks-001",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "confidential",
            "contains_pii": true
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 45
        },
        "security": object.union(base_security_config, {
            "jwt_allow_unsigned_fallback": false
        })
    }

    # Teste com JWKS mock fornecido via data
    # Nota: io.jwt.decode_verify falhará com assinatura inválida, então usamos fallback
    result := security_constraints.result with input as input with data.spire_jwks as mock_spire_jwks

    # Com JWKS mock inválido para a assinatura de teste, espera-se invalid_jwt
    # Este comportamento é correto: fail-closed quando assinatura não verifica
    invalid_jwt_violations := [v | v := result.violations[_]; v.rule == "invalid_jwt"]
    count(invalid_jwt_violations) > 0
}

# Teste: Comportamento fail-closed quando JWKS indisponível e fallback desabilitado
test_jwt_jwks_unavailable_fail_closed {
    input := {
        "resource": {
            "ticket_id": "sec-jwks-unavailable",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": security_config_fail_closed
    }

    # Sem JWKS e sem fallback permitido -> violação jwt_jwks_unavailable
    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "jwt_jwks_unavailable"
    violation.severity == "critical"
}

# Teste: Fallback sem assinatura quando explicitamente habilitado
test_jwt_fallback_with_explicit_flag {
    input := {
        "resource": {
            "ticket_id": "sec-fallback",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "confidential",
            "contains_pii": true
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 45
        },
        "security": object.union(base_security_config, {
            "jwt_allow_unsigned_fallback": true
        })
    }

    # Com fallback habilitado e sem JWKS, deve validar estrutura apenas
    result := security_constraints.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# ==============================================================================
# TESTES: Permissões Insuficientes (RBAC)
# ==============================================================================

# Teste: Permissões insuficientes
test_insufficient_permissions {
    input := {
        "resource": {
            "ticket_id": "sec-999",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["deployment"],  # Viewer não tem permissão
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "viewer@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": object.union(base_security_config, {
            "rbac_roles": {"viewer@example.com": ["viewer"]}
        })
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "insufficient_permissions"
    violation.severity == "high"
}

# ==============================================================================
# TESTES: Violações de PII
# ==============================================================================

# Teste: Violação de tratamento de PII
test_pii_handling_violation {
    input := {
        "resource": {
            "ticket_id": "sec-111",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",  # Deveria ser confidential
            "contains_pii": true
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "pii_handling_violation"
    violation.severity == "high"
}

# ==============================================================================
# TESTES: Rate Limiting
# ==============================================================================

# Teste: Limite de taxa do tenant excedido
test_tenant_rate_limit_exceeded {
    input := {
        "resource": {
            "ticket_id": "sec-222",
            "tenant_id": "tenant-123",
            "namespace": "production",
            "required_capabilities": ["code_generation"],
            "data_classification": "public",
            "contains_pii": false
        },
        "context": {
            "current_time": 1700000000000,
            "user_id": "user@example.com",
            "jwt_token": valid_jwt_with_all_claims,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 150  # Excede limite de 100
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == false

    violation := result.violations[_]
    violation.rule == "tenant_rate_limit_exceeded"
    violation.severity == "medium"
}
