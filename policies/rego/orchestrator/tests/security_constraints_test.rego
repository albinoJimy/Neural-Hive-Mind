package neuralhive.orchestrator.security_constraints_test

import data.neuralhive.orchestrator.security_constraints

# Test: Valid security context
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
            "jwt_token": "eyJhbGc.eyJzdWI.signature",
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 45
        },
        "security": {
            "spiffe_enabled": true,
            "trust_domain": "neural-hive.local",
            "allowed_tenants": ["tenant-123", "tenant-456"],
            "rbac_roles": {"user@example.com": ["developer"]},
            "data_residency_regions": ["us-east-1"],
            "tenant_rate_limits": {"tenant-123": 100},
            "global_rate_limit": 1000
        }
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
            "jwt_token": "eyJhbGc.eyJzdWI.signature",
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": {
            "spiffe_enabled": true,
            "allowed_tenants": ["tenant-123", "tenant-456"],
            "rbac_roles": {"user@example.com": ["developer"]},
            "tenant_rate_limits": {"tenant-unauthorized": 100}
        }
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
        "security": {
            "spiffe_enabled": true,
            "allowed_tenants": ["tenant-123"],
            "rbac_roles": {"user@example.com": ["developer"]},
            "tenant_rate_limits": {"tenant-123": 100}
        }
    }
    
    result := security_constraints.result with input as input
    result.allow == false
    
    violation := result.violations[_]
    violation.rule == "missing_authentication"
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
            "jwt_token": "eyJhbGc.eyJzdWI.signature",
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": {
            "spiffe_enabled": true,
            "allowed_tenants": ["tenant-123"],
            "rbac_roles": {"viewer@example.com": ["viewer"]},
            "tenant_rate_limits": {"tenant-123": 100}
        }
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
            "jwt_token": "eyJhbGc.eyJzdWI.signature",
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 10
        },
        "security": {
            "spiffe_enabled": true,
            "allowed_tenants": ["tenant-123"],
            "rbac_roles": {"user@example.com": ["developer"]},
            "tenant_rate_limits": {"tenant-123": 100}
        }
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
            "jwt_token": "eyJhbGc.eyJzdWI.signature",
            "source_ip": "10.0.0.1",
            "request_count_last_minute": 150  # Excede limite de 100
        },
        "security": {
            "spiffe_enabled": true,
            "allowed_tenants": ["tenant-123"],
            "rbac_roles": {"user@example.com": ["developer"]},
            "tenant_rate_limits": {"tenant-123": 100}
        }
    }
    
    result := security_constraints.result with input as input
    result.allow == false
    
    violation := result.violations[_]
    violation.rule == "tenant_rate_limit_exceeded"
    violation.severity == "medium"
}
