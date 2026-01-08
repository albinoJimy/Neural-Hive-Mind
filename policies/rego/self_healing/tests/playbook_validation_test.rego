# Self-Healing Playbook Validation Policy Tests
#
# Run with: opa test policies/rego/self_healing/ -v

package neuralhive.self_healing.playbook_validation

import future.keywords.if

# =============================================================================
# Reallocate Ticket Tests
# =============================================================================

# Test: Allow valid ticket reallocation
test_allow_reallocate_ticket_valid if {
    allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "ticket-123",
            "workflow_id": "workflow-456",
            "reason": "worker_failure"
        },
        "context": {
            "last_reallocation_timestamp": 0,
            "workflow_state": "RUNNING",
            "incident_id": "inc-789"
        }
    }
}

# Test: Deny ticket reallocation without ticket_id
test_deny_reallocate_ticket_missing_ticket_id if {
    not allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "",
            "reason": "worker_failure"
        },
        "context": {
            "last_reallocation_timestamp": 0
        }
    }
}

# Test: Deny ticket reallocation without reason
test_deny_reallocate_ticket_missing_reason if {
    not allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "ticket-123",
            "reason": ""
        },
        "context": {
            "last_reallocation_timestamp": 0
        }
    }
}

# Test: Deny ticket reallocation if recently reallocated (rate limiting)
test_deny_reallocate_ticket_rate_limited if {
    # Set timestamp to 1 minute ago (well within 5 min cooldown)
    recent_ts := time.now_ns() - 60000000000
    not allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "ticket-123",
            "reason": "worker_failure"
        },
        "context": {
            "last_reallocation_timestamp": recent_ts
        }
    }
}

# Test: Allow ticket reallocation after cooldown
test_allow_reallocate_ticket_after_cooldown if {
    # Set timestamp to 10 minutes ago (past 5 min cooldown)
    old_ts := time.now_ns() - 600000000000
    allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "ticket-123",
            "reason": "timeout_recovery",
            "affected_tickets": []
        },
        "context": {
            "last_reallocation_timestamp": old_ts
        }
    }
}

# Test: Allow batch reallocation with affected_tickets (worker failure scenario)
test_allow_reallocate_ticket_batch_with_affected_tickets if {
    allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "",
            "reason": "worker_failure",
            "affected_tickets": ["ticket-001", "ticket-002", "ticket-003"]
        },
        "context": {
            "last_reallocation_timestamp": 0,
            "workflow_state": "RUNNING",
            "incident_id": "inc-worker-crash"
        }
    }
}

# Test: Allow batch reallocation with resolved ticket_id from affected_tickets
test_allow_reallocate_ticket_batch_first_ticket_as_representative if {
    allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "ticket-001",
            "reason": "worker_failure",
            "affected_tickets": ["ticket-001", "ticket-002"]
        },
        "context": {
            "last_reallocation_timestamp": 0
        }
    }
}

# Test: Deny batch reallocation with empty affected_tickets and no ticket_id
test_deny_reallocate_ticket_empty_affected_tickets_no_ticket_id if {
    not allow with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "",
            "reason": "worker_failure",
            "affected_tickets": []
        },
        "context": {
            "last_reallocation_timestamp": 0
        }
    }
}

# Test: Violation for missing ticket_id
test_violation_reallocate_missing_ticket_id if {
    v := violations with input as {
        "resource": {
            "action": "reallocate_ticket",
            "ticket_id": "",
            "reason": "test"
        },
        "context": {}
    }
    count(v) > 0
    some violation in v
    violation.rule == "reallocate_ticket_missing_ticket_id"
}

# =============================================================================
# Restart Workflow Tests
# =============================================================================

# Test: Allow valid workflow restart
test_allow_restart_workflow_valid if {
    allow with input as {
        "resource": {
            "action": "restart_workflow",
            "workflow_id": "workflow-123",
            "reason": "self_healing_restart"
        },
        "context": {
            "workflow_state": "PAUSED"
        }
    }
}

# Test: Allow restart for RUNNING workflow
test_allow_restart_workflow_running if {
    allow with input as {
        "resource": {
            "action": "restart_workflow",
            "workflow_id": "workflow-123",
            "reason": "recovery"
        },
        "context": {
            "workflow_state": "RUNNING"
        }
    }
}

# Test: Deny restart for COMPLETED workflow
test_deny_restart_workflow_completed if {
    not allow with input as {
        "resource": {
            "action": "restart_workflow",
            "workflow_id": "workflow-123",
            "reason": "recovery"
        },
        "context": {
            "workflow_state": "COMPLETED"
        }
    }
}

# Test: Deny restart for FAILED workflow
test_deny_restart_workflow_failed if {
    not allow with input as {
        "resource": {
            "action": "restart_workflow",
            "workflow_id": "workflow-123",
            "reason": "recovery"
        },
        "context": {
            "workflow_state": "FAILED"
        }
    }
}

# Test: Deny restart for CANCELLED workflow
test_deny_restart_workflow_cancelled if {
    not allow with input as {
        "resource": {
            "action": "restart_workflow",
            "workflow_id": "workflow-123",
            "reason": "recovery"
        },
        "context": {
            "workflow_state": "CANCELLED"
        }
    }
}

# Test: Deny restart without workflow_id
test_deny_restart_workflow_missing_id if {
    not allow with input as {
        "resource": {
            "action": "restart_workflow",
            "workflow_id": "",
            "reason": "recovery"
        },
        "context": {
            "workflow_state": "PAUSED"
        }
    }
}

# Test: Violation for terminal state restart
test_violation_restart_terminal_state if {
    v := violations with input as {
        "resource": {
            "action": "restart_workflow",
            "workflow_id": "workflow-123",
            "reason": "test"
        },
        "context": {
            "workflow_state": "COMPLETED"
        }
    }
    count(v) > 0
    some violation in v
    violation.rule == "restart_workflow_terminal_state"
}

# =============================================================================
# Update Ticket Status Tests
# =============================================================================

# Test: Allow valid ticket status update
test_allow_update_ticket_status_valid if {
    allow with input as {
        "resource": {
            "action": "update_ticket_status",
            "ticket_id": "ticket-123",
            "status": "pending"
        },
        "context": {}
    }
}

# Test: Deny update without ticket_id
test_deny_update_ticket_status_missing_id if {
    not allow with input as {
        "resource": {
            "action": "update_ticket_status",
            "ticket_id": "",
            "status": "pending"
        },
        "context": {}
    }
}

# =============================================================================
# Trigger Replanning Tests
# =============================================================================

# Test: Allow replanning with plan_id
test_allow_trigger_replanning_with_plan_id if {
    allow with input as {
        "resource": {
            "action": "trigger_replanning",
            "plan_id": "plan-123",
            "workflow_id": "",
            "reason": "failure_recovery"
        },
        "context": {
            "workflow_state": "RUNNING"
        }
    }
}

# Test: Allow replanning with workflow_id
test_allow_trigger_replanning_with_workflow_id if {
    allow with input as {
        "resource": {
            "action": "trigger_replanning",
            "plan_id": "",
            "workflow_id": "workflow-123",
            "reason": "failure_recovery"
        },
        "context": {
            "workflow_state": "RUNNING"
        }
    }
}

# Test: Deny replanning without any ID
test_deny_trigger_replanning_missing_ids if {
    not allow with input as {
        "resource": {
            "action": "trigger_replanning",
            "plan_id": "",
            "workflow_id": "",
            "reason": "failure_recovery"
        },
        "context": {
            "workflow_state": "RUNNING"
        }
    }
}

# Test: Deny replanning for terminal state
test_deny_trigger_replanning_terminal_state if {
    not allow with input as {
        "resource": {
            "action": "trigger_replanning",
            "plan_id": "plan-123",
            "workflow_id": "",
            "reason": "recovery"
        },
        "context": {
            "workflow_state": "FAILED"
        }
    }
}

# Test: Allow replanning with only plan_id (no workflow_id, non-terminal state)
test_allow_trigger_replanning_only_plan_id if {
    allow with input as {
        "resource": {
            "action": "trigger_replanning",
            "plan_id": "plan-456",
            "workflow_id": "",
            "reason": "self_healing_replanning"
        },
        "context": {
            "workflow_state": "",
            "incident_id": "inc-123"
        }
    }
}

# Test: Allow replanning with only plan_id when workflow_state is RUNNING
test_allow_trigger_replanning_only_plan_id_running_state if {
    allow with input as {
        "resource": {
            "action": "trigger_replanning",
            "plan_id": "plan-789",
            "workflow_id": "",
            "reason": "failure_recovery"
        },
        "context": {
            "workflow_state": "RUNNING"
        }
    }
}

# Test: Allow replanning with only plan_id when workflow_state is PAUSED
test_allow_trigger_replanning_only_plan_id_paused_state if {
    allow with input as {
        "resource": {
            "action": "trigger_replanning",
            "plan_id": "plan-abc",
            "workflow_id": "",
            "reason": "manual_recovery"
        },
        "context": {
            "workflow_state": "PAUSED"
        }
    }
}

# =============================================================================
# General Tests
# =============================================================================

# Test: Allow unknown actions (not validated)
test_allow_unknown_action if {
    allow with input as {
        "resource": {
            "action": "restart_pod",
            "pod_name": "test-pod"
        },
        "context": {}
    }
}

# Test: Metadata is correct
test_metadata_correct if {
    metadata.policy_name == "playbook_validation"
    metadata.version == "1.0.0"
    "reallocate_ticket" in metadata.actions_validated
    "restart_workflow" in metadata.actions_validated
}
