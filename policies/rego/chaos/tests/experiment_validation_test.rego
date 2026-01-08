# Testes para Chaos Engineering Experiment Validation Policy

package neuralhive.chaos.experiment_validation_test

import future.keywords.if
import data.neuralhive.chaos.experiment_validation

# =============================================================================
# Test: Experimento válido em staging deve ser permitido
# =============================================================================
test_allow_valid_staging_experiment if {
    experiment_validation.allow with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 3,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-execution",
                    "service_name": "worker-agents"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {}
    }
}

# =============================================================================
# Test: Namespace protegido deve ser negado
# =============================================================================
test_deny_protected_namespace if {
    not experiment_validation.allow with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 3,
            "fault_injections": [{
                "target": {
                    "namespace": "kube-system",
                    "service_name": "coredns"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {}
    }
}

# =============================================================================
# Test: Produção sem aprovação deve ser negada
# =============================================================================
test_deny_production_without_approval if {
    not experiment_validation.allow with input as {
        "experiment": {
            "environment": "production",
            "blast_radius_limit": 1,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-execution",
                    "service_name": "worker-agents"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {
            "opa_approved": false
        }
    }
}

# =============================================================================
# Test: Produção com aprovação deve ser permitida
# =============================================================================
test_allow_production_with_approval if {
    experiment_validation.allow with input as {
        "experiment": {
            "environment": "production",
            "blast_radius_limit": 1,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-execution",
                    "service_name": "worker-agents"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {
            "opa_approved": true,
            "approved_by": "platform-admin"
        }
    }
}

# =============================================================================
# Test: Blast radius excedido deve ser negado
# =============================================================================
test_deny_exceeded_blast_radius if {
    not experiment_validation.allow with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 10,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-execution",
                    "service_name": "worker-agents"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {}
    }
}

# =============================================================================
# Test: Executor não autorizado deve ser negado
# =============================================================================
test_deny_unauthorized_executor if {
    not experiment_validation.allow with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 3,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-execution",
                    "service_name": "worker-agents"
                }
            }]
        },
        "executor": {
            "name": "random-user",
            "role": "developer",
            "groups": []
        },
        "approval": {}
    }
}

# =============================================================================
# Test: Executor autorizado por grupo
# =============================================================================
test_allow_authorized_by_group if {
    experiment_validation.allow with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 3,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-execution",
                    "service_name": "worker-agents"
                }
            }]
        },
        "executor": {
            "name": "dev-user",
            "role": "developer",
            "groups": ["chaos-engineering"]
        },
        "approval": {}
    }
}

# =============================================================================
# Test: Serviço crítico sem aprovação deve ser negado
# =============================================================================
test_deny_critical_service_without_approval if {
    not experiment_validation.allow with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 3,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-orchestration",
                    "service_name": "consensus-engine"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {
            "opa_approved": false
        }
    }
}

# =============================================================================
# Test: Serviço crítico com aprovação deve ser permitido
# =============================================================================
test_allow_critical_service_with_approval if {
    experiment_validation.allow with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 3,
            "fault_injections": [{
                "target": {
                    "namespace": "neural-hive-orchestration",
                    "service_name": "consensus-engine"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {
            "opa_approved": true
        }
    }
}

# =============================================================================
# Test: Violations são reportadas corretamente
# =============================================================================
test_violations_protected_namespace if {
    violations := experiment_validation.violations with input as {
        "experiment": {
            "environment": "staging",
            "blast_radius_limit": 3,
            "fault_injections": [{
                "target": {
                    "namespace": "kube-system",
                    "service_name": "coredns"
                }
            }]
        },
        "executor": {
            "name": "test-sre",
            "role": "sre",
            "groups": []
        },
        "approval": {}
    }
    count(violations) > 0
    some violation in violations
    violation.rule == "protected_namespace"
}
