# Guard Agents Resource Policies Tests
# Unit tests for resource_policies.rego
# Part of Neural Hive Mind - Guard Agents Service

package neuralhive.guard.resource_policies_test

import data.neuralhive.guard.resource_policies
import future.keywords.in

# =============================================================================
# TEST: Valid Resource Limits (No Violations)
# =============================================================================

test_valid_resource_limits {
    input := {
        "ticket": {
            "ticket_id": "test-resources-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 3,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {
            "namespace_cpu_quota": "8000m",
            "namespace_memory_quota": "16Gi",
            "max_pods": 50,
            "current_pod_count": 10
        },
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2,
            "require_hpa_production": true
        }
    }

    result := resource_policies.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# =============================================================================
# TEST: Missing CPU Limits Violation
# =============================================================================

test_missing_cpu_limits_violation {
    input := {
        "ticket": {
            "ticket_id": "test-cpu-limit-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 2,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "min_replicas_production": 2
        }
    }

    result := resource_policies.result with input as input

    # Find missing CPU limits violation
    violation := [v | v := result.violations[_]; v.rule == "missing_cpu_limits"][0]
    violation.severity == "MEDIUM"
    contains(violation.message, "No CPU limits defined")
}

# =============================================================================
# TEST: Excessive CPU Request Violation
# =============================================================================

test_excessive_cpu_request_violation {
    input := {
        "ticket": {
            "ticket_id": "test-cpu-excess-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 2,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "8000m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "10000m",
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2
        }
    }

    result := resource_policies.result with input as input
    result.allow == false

    # Find excessive CPU request violation
    violation := [v | v := result.violations[_]; v.rule == "excessive_cpu_request"][0]
    violation.severity == "HIGH"
    violation.details.cpu_request == "8000m"
    violation.details.max_allowed == "4000m"
}

# =============================================================================
# TEST: Namespace Quota Exceeded Violation
# =============================================================================

test_namespace_quota_exceeded_violation {
    input := {
        "ticket": {
            "ticket_id": "test-quota-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 5,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "2000m",
                    "memory": "2Gi"
                },
                "limits": {
                    "cpu": "4000m",
                    "memory": "4Gi"
                }
            }
        },
        "quotas": {
            "namespace_cpu_quota": "8000m",
            "current_cpu_usage": "6000m",
            "max_pods": 50,
            "current_pod_count": 10
        },
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2
        }
    }

    result := resource_policies.result with input as input
    result.allow == false

    # Find namespace quota exceeded violation
    violation := [v | v := result.violations[_]; v.rule == "namespace_quota_exceeded"][0]
    violation.severity == "CRITICAL"
    contains(violation.message, "exceed namespace CPU quota")
}

# =============================================================================
# TEST: Insufficient Replicas Violation
# =============================================================================

test_insufficient_replicas_violation {
    input := {
        "ticket": {
            "ticket_id": "test-replicas-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 1,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2,
            "require_hpa_production": true
        }
    }

    result := resource_policies.result with input as input
    result.allow == false

    # Find insufficient replicas violation
    violation := [v | v := result.violations[_]; v.rule == "insufficient_replicas"][0]
    violation.severity == "HIGH"
    violation.details.current_replicas == 1
    violation.details.min_required == 2
}

# =============================================================================
# TEST: Low CPU Utilization Violation
# =============================================================================

test_low_cpu_utilization_violation {
    input := {
        "ticket": {
            "ticket_id": "test-util-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 2,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                },
                "limits": {
                    "cpu": "2000m",
                    "memory": "2Gi"
                }
            },
            "metrics": {
                "avg_cpu_utilization_percent": 10,
                "avg_memory_utilization_percent": 15
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2,
            "min_cpu_utilization_percent": 20,
            "min_memory_utilization_percent": 20
        }
    }

    result := resource_policies.result with input as input

    # Find low CPU utilization violation
    cpu_violation := [v | v := result.violations[_]; v.rule == "low_cpu_utilization"][0]
    cpu_violation.severity == "LOW"
    cpu_violation.details.avg_cpu_utilization == 10

    # Find low memory utilization violation
    memory_violation := [v | v := result.violations[_]; v.rule == "low_memory_utilization"][0]
    memory_violation.severity == "LOW"
    memory_violation.details.avg_memory_utilization == 15
}

# =============================================================================
# TEST: Missing HPA Violation
# =============================================================================

test_missing_hpa_violation {
    input := {
        "ticket": {
            "ticket_id": "test-hpa-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 3,
            "hpa_enabled": false,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2,
            "require_hpa_production": true
        }
    }

    result := resource_policies.result with input as input

    # Find missing HPA violation
    violation := [v | v := result.violations[_]; v.rule == "missing_hpa"][0]
    violation.severity == "MEDIUM"
    violation.details.hpa_enabled == false
}

# =============================================================================
# TEST: Pod Count Quota Exceeded Violation
# =============================================================================

test_pod_count_quota_exceeded_violation {
    input := {
        "ticket": {
            "ticket_id": "test-pods-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 10,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {
            "max_pods": 50,
            "current_pod_count": 45
        },
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2
        }
    }

    result := resource_policies.result with input as input
    result.allow == false

    # Find pod count quota exceeded violation
    violation := [v | v := result.violations[_]; v.rule == "pod_count_quota_exceeded"][0]
    violation.severity == "HIGH"
    violation.details.current_pods == 45
    violation.details.requested_replicas == 10
    violation.details.max_pods == 50
}

# =============================================================================
# TEST: Excessive Memory Request Violation
# =============================================================================

test_excessive_memory_request_violation {
    input := {
        "ticket": {
            "ticket_id": "test-mem-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 2,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "1000m",
                    "memory": "16Gi"
                },
                "limits": {
                    "cpu": "2000m",
                    "memory": "32Gi"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2
        }
    }

    result := resource_policies.result with input as input
    result.allow == false

    # Find excessive memory request violation
    violation := [v | v := result.violations[_]; v.rule == "excessive_memory_request"][0]
    violation.severity == "HIGH"
    violation.details.memory_request == "16Gi"
    violation.details.max_allowed == "8Gi"
}

# =============================================================================
# TEST: Resource Context Summary
# =============================================================================

test_resource_context_summary {
    input := {
        "ticket": {
            "ticket_id": "test-context-001",
            "task_type": "DEPLOY",
            "environment": "staging",
            "replicas": 2,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {},
        "thresholds": {}
    }

    result := resource_policies.result with input as input

    # Verify resource context is populated
    result.resource_context.ticket_id == "test-context-001"
    result.resource_context.environment == "staging"
    result.resource_context.requested_cpu == "500m"
    result.resource_context.requested_memory == "512Mi"
    result.resource_context.replicas == 2
}

# =============================================================================
# TEST: Development Environment (Less Strict)
# =============================================================================

test_development_environment_less_strict {
    input := {
        "ticket": {
            "ticket_id": "test-dev-001",
            "task_type": "DEPLOY",
            "environment": "development",
            "replicas": 1,
            "hpa_enabled": false,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2,
            "require_hpa_production": true
        }
    }

    result := resource_policies.result with input as input
    result.allow == true

    # In development, no replica or HPA violations
    replica_violations := [v | v := result.violations[_]; v.rule == "insufficient_replicas"]
    count(replica_violations) == 0

    hpa_violations := [v | v := result.violations[_]; v.rule == "missing_hpa"]
    count(hpa_violations) == 0
}

# =============================================================================
# TEST: Storage Quota Exceeded Violation
# =============================================================================

test_storage_quota_exceeded_violation {
    input := {
        "ticket": {
            "ticket_id": "test-storage-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 2,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m",
                    "memory": "1Gi"
                }
            },
            "storage": {
                "size": "50Gi"
            }
        },
        "quotas": {
            "current_storage_usage": "80Gi",
            "max_storage": "100Gi"
        },
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2
        }
    }

    result := resource_policies.result with input as input
    result.allow == false

    # Find storage quota exceeded violation
    violation := [v | v := result.violations[_]; v.rule == "storage_quota_exceeded"][0]
    violation.severity == "HIGH"
    violation.details.storage_request == "50Gi"
    violation.details.max_storage == "100Gi"
}

# =============================================================================
# TEST: Excessive Replicas Violation
# =============================================================================

test_excessive_replicas_violation {
    input := {
        "ticket": {
            "ticket_id": "test-excess-rep-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 150,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "100m",
                    "memory": "128Mi"
                },
                "limits": {
                    "cpu": "200m",
                    "memory": "256Mi"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2,
            "max_replicas": 100
        }
    }

    result := resource_policies.result with input as input

    # Find excessive replicas violation
    violation := [v | v := result.violations[_]; v.rule == "excessive_replicas"][0]
    violation.severity == "MEDIUM"
    violation.details.current_replicas == 150
    violation.details.max_allowed == 100
}

# =============================================================================
# TEST: Missing Memory Limits Violation
# =============================================================================

test_missing_memory_limits_violation {
    input := {
        "ticket": {
            "ticket_id": "test-mem-limit-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 2,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "500m",
                    "memory": "512Mi"
                },
                "limits": {
                    "cpu": "1000m"
                }
            }
        },
        "quotas": {},
        "thresholds": {
            "min_replicas_production": 2
        }
    }

    result := resource_policies.result with input as input

    # Find missing memory limits violation
    violation := [v | v := result.violations[_]; v.rule == "missing_memory_limits"][0]
    violation.severity == "MEDIUM"
    contains(violation.message, "No memory limits defined")
}

# =============================================================================
# TEST: Oversized Request Violation
# =============================================================================

test_oversized_request_violation {
    input := {
        "ticket": {
            "ticket_id": "test-oversized-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "replicas": 2,
            "hpa_enabled": true,
            "resources": {
                "requests": {
                    "cpu": "4000m",
                    "memory": "8Gi"
                },
                "limits": {
                    "cpu": "4000m",
                    "memory": "8Gi"
                }
            },
            "metrics": {
                "peak_cpu_millicores": 400,
                "avg_cpu_utilization_percent": 10
            }
        },
        "quotas": {},
        "thresholds": {
            "max_cpu_per_container": "4000m",
            "max_memory_per_container": "8Gi",
            "min_replicas_production": 2,
            "min_cpu_utilization_percent": 20
        }
    }

    result := resource_policies.result with input as input

    # Find oversized request violation
    violation := [v | v := result.violations[_]; v.rule == "oversized_request"][0]
    violation.severity == "MEDIUM"
    violation.details.peak_usage_millicores == 400
}
