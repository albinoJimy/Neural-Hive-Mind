package neuralhive.orchestrator.security_constraints_test

import data.neuralhive.orchestrator.security_constraints

# Helper: Create a valid JWT structure for testing
# JWT format: base64(header).base64(payload).signature
# header: {"alg":"RS256","typ":"JWT"}
# Note: For OPA io.jwt.decode, we only need valid base64-encoded JSON

# Base64 encoded header: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9
# Valid test JWT with proper claims:
# - sub: spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents
# - iss: https://spire-server.spire-system.svc.cluster.local
# - aud: orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local
# - exp: 9999999999 (far future)
# - iat: 1700000000
#
# Payload JSON: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000}
# Base64 payload: eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMH0

valid_test_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMH0.test_signature"

# Expired JWT (exp: 1600000000 - past date)
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":1600000000,"iat":1500000000}
expired_test_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjE2MDAwMDAwMDAsImlhdCI6MTUwMDAwMDAwMH0.test_signature"

# JWT with wrong issuer
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://malicious-issuer.example.com","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000}
wrong_issuer_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vbWFsaWNpb3VzLWlzc3Vlci5leGFtcGxlLmNvbSIsImF1ZCI6Im9yY2hlc3RyYXRvci1keW5hbWljLm5ldXJhbC1oaXZlLW9yY2hlc3RyYXRpb24uc3ZjLmNsdXN0ZXIubG9jYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMH0.test_signature"

# JWT with wrong audience
# Payload: {"sub":"spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"wrong-audience.example.com","exp":9999999999,"iat":1700000000}
wrong_audience_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1leGVjdXRpb24vc2Evd29ya2VyLWFnZW50cyIsImlzcyI6Imh0dHBzOi8vc3BpcmUtc2VydmVyLnNwaXJlLXN5c3RlbS5zdmMuY2x1c3Rlci5sb2NhbCIsImF1ZCI6Indyb25nLWF1ZGllbmNlLmV4YW1wbGUuY29tIiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDB9.test_signature"

# JWT with invalid SPIFFE ID (wrong trust domain)
# Payload: {"sub":"spiffe://wrong-domain.local/ns/neural-hive-execution/sa/worker-agents","iss":"https://spire-server.spire-system.svc.cluster.local","aud":"orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local","exp":9999999999,"iat":1700000000}
wrong_spiffe_id_jwt := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly93cm9uZy1kb21haW4ubG9jYWwvbnMvbmV1cmFsLWhpdmUtZXhlY3V0aW9uL3NhL3dvcmtlci1hZ2VudHMiLCJpc3MiOiJodHRwczovL3NwaXJlLXNlcnZlci5zcGlyZS1zeXN0ZW0uc3ZjLmNsdXN0ZXIubG9jYWwiLCJhdWQiOiJvcmNoZXN0cmF0b3ItZHluYW1pYy5uZXVyYWwtaGl2ZS1vcmNoZXN0cmF0aW9uLnN2Yy5jbHVzdGVyLmxvY2FsIiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDB9.test_signature"

# Common security config for tests
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
    "default_tenant_rate_limit": 100
}

# Test: Valid security context with proper JWT
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
            "jwt_token": valid_test_jwt,
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 45
        },
        "security": base_security_config
    }

    result := security_constraints.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# Test: Cross-tenant access violation
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
            "jwt_token": valid_test_jwt,
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

# Test: Missing authentication
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

# Test: JWT with expired token
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
            "jwt_token": expired_test_jwt,
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

# Test: JWT with invalid issuer
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

# Test: JWT with invalid audience
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

# Test: JWT with invalid SPIFFE ID (wrong trust domain)
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

# Test: Insufficient permissions
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
            "jwt_token": valid_test_jwt,
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

# Test: PII handling violation
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
            "jwt_token": valid_test_jwt,
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

# Test: Tenant rate limit exceeded
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
            "jwt_token": valid_test_jwt,
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

# Test: SPIFFE disabled should not require JWT validation
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
    # Should not trigger missing_authentication since spiffe is disabled
    missing_auth_violations := [v | v := result.violations[_]; v.rule == "missing_authentication"]
    count(missing_auth_violations) == 0
}
