package neuralhive.orchestrator.feature_flags_test

import data.neuralhive.orchestrator.feature_flags

# Test: Enable intelligent scheduler for critical
test_enable_intelligent_scheduler_critical {
    input := {
        "resource": {"ticket_id": "ff-123", "risk_band": "critical"},
        "flags": {
            "intelligent_scheduler_enabled": true,
            "scheduler_namespaces": ["production", "staging"],
            "burst_capacity_enabled": false,
            "predictive_allocation_enabled": false,
            "auto_scaling_enabled": false
        },
        "context": {
            "namespace": "production",
            "current_load": 0.5,
            "tenant_id": "tenant-1",
            "queue_depth": 50,
            "current_time": 1700000000000,
            "model_accuracy": 0.9
        }
    }
    
    result := feature_flags.result with input as input
    result.enable_intelligent_scheduler == true
}

# Test: Burst capacity for premium tenant
test_burst_capacity_premium_tenant {
    input := {
        "resource": {"ticket_id": "ff-456", "risk_band": "high"},
        "flags": {
            "intelligent_scheduler_enabled": false,
            "burst_capacity_enabled": true,
            "burst_threshold": 0.8,
            "premium_tenants": ["tenant-premium"],
            "predictive_allocation_enabled": false,
            "auto_scaling_enabled": false
        },
        "context": {
            "namespace": "production",
            "current_load": 0.6,
            "tenant_id": "tenant-premium",
            "queue_depth": 50,
            "current_time": 1700000000000
        }
    }
    
    result := feature_flags.result with input as input
    result.enable_burst_capacity == true
}

# Test: Experimental features in dev namespace
test_experimental_features_dev {
    input := {
        "resource": {"ticket_id": "ff-789", "risk_band": "low"},
        "flags": {
            "intelligent_scheduler_enabled": false,
            "burst_capacity_enabled": false,
            "predictive_allocation_enabled": false,
            "auto_scaling_enabled": false
        },
        "context": {
            "namespace": "development",
            "current_load": 0.5,
            "tenant_id": "tenant-1",
            "queue_depth": 50,
            "current_time": 1700000000000
        }
    }
    
    result := feature_flags.result with input as input
    result.enable_experimental_features == true
}
