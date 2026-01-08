# Testes para Chaos Engineering Blast Radius Limits Policy

package neuralhive.chaos.blast_radius_limits_test

import future.keywords.if
import data.neuralhive.chaos.blast_radius_limits

# =============================================================================
# Test: POD_KILL dentro dos limites em staging
# =============================================================================
test_allow_pod_kill_within_staging_limits if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [{
                "fault_type": "pod_kill",
                "target": {
                    "percentage": 50
                }
            }]
        }
    }
}

# =============================================================================
# Test: POD_KILL excedendo limites em production
# =============================================================================
test_deny_pod_kill_exceeding_production_limits if {
    not blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "production",
            "fault_injections": [{
                "fault_type": "pod_kill",
                "target": {
                    "percentage": 50
                }
            }]
        }
    }
}

# =============================================================================
# Test: NETWORK_LATENCY dentro dos limites
# =============================================================================
test_allow_network_latency_within_limits if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [{
                "fault_type": "network_latency",
                "parameters": {
                    "latency_ms": 1000
                },
                "target": {
                    "percentage": 30
                }
            }]
        }
    }
}

# =============================================================================
# Test: NETWORK_LATENCY excedendo limites em production
# =============================================================================
test_deny_network_latency_exceeding_production_limits if {
    not blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "production",
            "fault_injections": [{
                "fault_type": "network_latency",
                "parameters": {
                    "latency_ms": 500
                },
                "target": {
                    "percentage": 20
                }
            }]
        }
    }
}

# =============================================================================
# Test: CPU_STRESS dentro dos limites
# =============================================================================
test_allow_cpu_stress_within_limits if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "development",
            "fault_injections": [{
                "fault_type": "cpu_stress",
                "parameters": {
                    "cpu_cores": 4,
                    "cpu_load_percent": 80
                }
            }]
        }
    }
}

# =============================================================================
# Test: CPU_STRESS excedendo cores em staging
# =============================================================================
test_deny_cpu_stress_exceeding_cores if {
    not blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [{
                "fault_type": "cpu_stress",
                "parameters": {
                    "cpu_cores": 10,
                    "cpu_load_percent": 80
                }
            }]
        }
    }
}

# =============================================================================
# Test: MEMORY_STRESS dentro dos limites
# =============================================================================
test_allow_memory_stress_within_limits if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [{
                "fault_type": "memory_stress",
                "parameters": {
                    "memory_bytes": 536870912
                }
            }]
        }
    }
}

# =============================================================================
# Test: MEMORY_STRESS excedendo limite em production
# =============================================================================
test_deny_memory_stress_exceeding_production if {
    not blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "production",
            "fault_injections": [{
                "fault_type": "memory_stress",
                "parameters": {
                    "memory_bytes": 536870912
                }
            }]
        }
    }
}

# =============================================================================
# Test: HTTP_ERROR dentro dos limites
# =============================================================================
test_allow_http_error_within_limits if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [{
                "fault_type": "http_error",
                "target": {
                    "percentage": 20
                },
                "duration_seconds": 120
            }]
        }
    }
}

# =============================================================================
# Test: HTTP_DELAY dentro dos limites
# =============================================================================
test_allow_http_delay_within_limits if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "development",
            "fault_injections": [{
                "fault_type": "http_delay",
                "parameters": {
                    "http_delay_ms": 5000
                },
                "target": {
                    "percentage": 50
                }
            }]
        }
    }
}

# =============================================================================
# Test: NETWORK_PARTITION dentro dos limites de duração
# =============================================================================
test_allow_network_partition_within_duration if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [{
                "fault_type": "network_partition",
                "duration_seconds": 180
            }]
        }
    }
}

# =============================================================================
# Test: NETWORK_PARTITION excedendo duração em production
# =============================================================================
test_deny_network_partition_exceeding_duration if {
    not blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "production",
            "fault_injections": [{
                "fault_type": "network_partition",
                "duration_seconds": 120
            }]
        }
    }
}

# =============================================================================
# Test: Múltiplas injeções todas dentro dos limites
# =============================================================================
test_allow_multiple_injections_within_limits if {
    blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [
                {
                    "fault_type": "pod_kill",
                    "target": {"percentage": 30}
                },
                {
                    "fault_type": "network_latency",
                    "parameters": {"latency_ms": 500},
                    "target": {"percentage": 25}
                }
            ]
        }
    }
}

# =============================================================================
# Test: Múltiplas injeções com uma excedendo
# =============================================================================
test_deny_multiple_injections_one_exceeding if {
    not blast_radius_limits.allow with input as {
        "experiment": {
            "environment": "production",
            "fault_injections": [
                {
                    "fault_type": "pod_kill",
                    "target": {"percentage": 5}
                },
                {
                    "fault_type": "network_latency",
                    "parameters": {"latency_ms": 500},
                    "target": {"percentage": 50}
                }
            ]
        }
    }
}

# =============================================================================
# Test: Violations para POD_KILL
# =============================================================================
test_violations_pod_kill if {
    violations := blast_radius_limits.violations with input as {
        "experiment": {
            "environment": "production",
            "fault_injections": [{
                "fault_type": "pod_kill",
                "target": {"percentage": 50}
            }]
        }
    }
    count(violations) > 0
    some violation in violations
    violation.rule == "pod_kill_percentage_exceeded"
}

# =============================================================================
# Test: Violations para CPU_STRESS
# =============================================================================
test_violations_cpu_stress if {
    violations := blast_radius_limits.violations with input as {
        "experiment": {
            "environment": "staging",
            "fault_injections": [{
                "fault_type": "cpu_stress",
                "parameters": {
                    "cpu_cores": 10,
                    "cpu_load_percent": 80
                }
            }]
        }
    }
    count(violations) > 0
    some violation in violations
    violation.rule == "cpu_stress_cores_exceeded"
}
