package neuralhive.orchestrator.http_authz_test

import data.neuralhive.orchestrator.authz

# =============================================================================
# Test: Public Paths - Sem autenticação
# =============================================================================

test_public_path_health_allowed {
    input := {
        "request": {
            "path": "/health",
            "method": "GET"
        },
        "user": {}
    }
    allow := authz.allow with input as input
    allow == true
}

test_public_path_metrics_allowed {
    input := {
        "request": {
            "path": "/metrics",
            "method": "GET"
        },
        "user": {}
    }
    allow := authz.allow with input as input
    allow == true
}

test_public_path_docs_allowed {
    input := {
        "request": {
            "path": "/docs",
            "method": "GET"
        },
        "user": {}
    }
    allow := authz.allow with input as input
    allow == true
}

# =============================================================================
# Test: Admin Role - Acesso total
# =============================================================================

test_admin_can_access_everything {
    input := {
        "request": {
            "path": "/api/v1/delete-everything",
            "method": "DELETE"
        },
        "user": {
            "id": "admin-1",
            "tenant_id": "system",
            "role": "admin"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

test_admin_can_post_workflows {
    input := {
        "request": {
            "path": "/api/v1/workflows/start",
            "method": "POST"
        },
        "user": {
            "id": "admin-1",
            "tenant_id": "system",
            "role": "admin"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

# =============================================================================
# Test: Developer Role - Acesso leitura
# =============================================================================

test_developer_can_get_api {
    input := {
        "request": {
            "path": "/api/v1/workflows",
            "method": "GET"
        },
        "user": {
            "id": "dev-1",
            "tenant_id": "tenant-a",
            "role": "developer"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

test_developer_cannot_post_api {
    input := {
        "request": {
            "path": "/api/v1/workflows/start",
            "method": "POST"
        },
        "user": {
            "id": "dev-1",
            "tenant_id": "tenant-a",
            "role": "developer"
        }
    }
    allow := authz.allow with input as input
    allow == false
}

# =============================================================================
# Test: Tenant Isolation
# =============================================================================

test_tenant_can_access_own_resources {
    input := {
        "request": {
            "path": "/api/v1/tenant-a/workflows",
            "method": "GET"
        },
        "user": {
            "id": "user-a",
            "tenant_id": "tenant-a",
            "role": "developer"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

test_tenant_cannot_access_other_tenant_resources {
    input := {
        "request": {
            "path": "/api/v1/tenant-b/workflows",
            "method": "GET"
        },
        "user": {
            "id": "user-a",
            "tenant_id": "tenant-a",
            "role": "developer"
        }
    }
    allow := authz.allow with input as input
    allow == false
}

test_authenticated_user_can_access_api_v1 {
    input := {
        "request": {
            "path": "/api/v1/workflows",
            "method": "GET"
        },
        "user": {
            "id": "user-123",
            "tenant_id": "tenant-abc",
            "role": "viewer"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

# =============================================================================
# Test: Worker Role
# =============================================================================

test_worker_can_access_workers_endpoints {
    input := {
        "request": {
            "path": "/api/v1/workers/status",
            "method": "GET"
        },
        "user": {
            "id": "worker-1",
            "tenant_id": "system",
            "role": "worker"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

test_worker_can_post_worker_registration {
    input := {
        "request": {
            "path": "/api/v1/workers/register",
            "method": "POST"
        },
        "user": {
            "id": "worker-1",
            "tenant_id": "system",
            "role": "worker"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

test_worker_cannot_access_other_endpoints {
    input := {
        "request": {
            "path": "/api/v1/admin/delete",
            "method": "DELETE"
        },
        "user": {
            "id": "worker-1",
            "tenant_id": "system",
            "role": "worker"
        }
    }
    allow := authz.allow with input as input
    allow == false
}

# =============================================================================
# Test: Service Registry Role
# =============================================================================

test_service_registry_can_register_workers {
    input := {
        "request": {
            "path": "/api/v1/workers/register",
            "method": "POST"
        },
        "user": {
            "id": "service-registry",
            "tenant_id": "system",
            "role": "service-registry"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

test_service_registry_can_unregister_workers {
    input := {
        "request": {
            "path": "/api/v1/workers/register",
            "method": "DELETE"
        },
        "user": {
            "id": "service-registry",
            "tenant_id": "system",
            "role": "service-registry"
        }
    }
    allow := authz.allow with input as input
    allow == true
}

# =============================================================================
# Test: Sem Autenticação - Deve negar
# =============================================================================

test_unauthenticated_request_denied {
    input := {
        "request": {
            "path": "/api/v1/workflows",
            "method": "GET"
        },
        "user": {
            "id": "anonymous",
            "tenant_id": "",
            "role": "guest"
        }
    }
    allow := authz.allow with input as input
    allow == false
}

test_empty_user_denied {
    input := {
        "request": {
            "path": "/api/v1/workflows/start",
            "method": "POST"
        },
        "user": {}
    }
    allow := authz.allow with input as input
    allow == false
}
