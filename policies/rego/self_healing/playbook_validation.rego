# Self-Healing Engine Playbook Validation Policy
#
# This policy validates self-healing actions before execution to prevent:
# - Repeated reallocations (rate limiting)
# - Invalid workflow restarts (terminal state protection)
# - Unauthorized ticket modifications
#
# Package: neuralhive.self_healing.playbook_validation

package neuralhive.self_healing.playbook_validation

import future.keywords.if
import future.keywords.in

# Default deny
default allow = false

# Constants
reallocation_cooldown_ns := 300000000000  # 5 minutes in nanoseconds
terminal_workflow_states := ["COMPLETED", "FAILED", "CANCELLED"]

# =============================================================================
# Allow Rules - Define when actions are permitted
# =============================================================================

# Allow reallocate_ticket if conditions are met
allow if {
    input.resource.action == "reallocate_ticket"
    allow_reallocate_ticket
}

# Allow restart_workflow if conditions are met
allow if {
    input.resource.action == "restart_workflow"
    allow_restart_workflow
}

# Allow update_ticket_status if conditions are met
allow if {
    input.resource.action == "update_ticket_status"
    allow_update_ticket_status
}

# Allow trigger_replanning if conditions are met
allow if {
    input.resource.action == "trigger_replanning"
    allow_trigger_replanning
}

# Allow any action not explicitly validated
allow if {
    not input.resource.action in ["reallocate_ticket", "restart_workflow", "update_ticket_status", "trigger_replanning"]
}

# =============================================================================
# Reallocate Ticket Validation
# =============================================================================

# Conditions for allowing ticket reallocation
allow_reallocate_ticket if {
    # Ticket ID must be provided (can be resolved from affected_tickets)
    has_ticket_id_or_affected_tickets

    # Reason must be provided
    input.resource.reason != ""

    # Not recently reallocated (rate limiting)
    not recently_reallocated
}

# Check if ticket_id is present directly
has_ticket_id_or_affected_tickets if {
    input.resource.ticket_id != ""
}

# Check if affected_tickets array is non-empty (batch reallocation)
has_ticket_id_or_affected_tickets if {
    count(input.resource.affected_tickets) > 0
}

# Check if ticket was recently reallocated (within cooldown period)
recently_reallocated if {
    input.context.last_reallocation_timestamp > 0
    time.now_ns() - input.context.last_reallocation_timestamp < reallocation_cooldown_ns
}

# =============================================================================
# Restart Workflow Validation
# =============================================================================

# Conditions for allowing workflow restart
allow_restart_workflow if {
    # Workflow ID must be provided
    input.resource.workflow_id != ""

    # Workflow must not be in terminal state
    not workflow_in_terminal_state
}

# Check if workflow is in a terminal state
workflow_in_terminal_state if {
    input.context.workflow_state in terminal_workflow_states
}

# =============================================================================
# Update Ticket Status Validation
# =============================================================================

# Conditions for allowing ticket status update
allow_update_ticket_status if {
    # Ticket ID must be provided
    input.resource.ticket_id != ""
}

# =============================================================================
# Trigger Replanning Validation
# =============================================================================

# Conditions for allowing replanning
allow_trigger_replanning if {
    # Plan ID or workflow ID must be provided
    has_plan_or_workflow_id

    # Workflow must not be in terminal state
    not workflow_in_terminal_state
}

has_plan_or_workflow_id if {
    input.resource.plan_id != ""
}

has_plan_or_workflow_id if {
    input.resource.workflow_id != ""
}

# =============================================================================
# Violations - Collect policy violations for reporting
# =============================================================================

violations[violation] if {
    input.resource.action == "reallocate_ticket"
    not has_ticket_id_or_affected_tickets
    violation := {
        "policy": "playbook_validation",
        "rule": "reallocate_ticket_missing_ticket_id",
        "msg": "Ticket reallocation requires ticket_id or non-empty affected_tickets",
        "severity": "high"
    }
}

violations[violation] if {
    input.resource.action == "reallocate_ticket"
    input.resource.reason == ""
    violation := {
        "policy": "playbook_validation",
        "rule": "reallocate_ticket_missing_reason",
        "msg": "Ticket reallocation requires reason",
        "severity": "medium"
    }
}

violations[violation] if {
    input.resource.action == "reallocate_ticket"
    recently_reallocated
    violation := {
        "policy": "playbook_validation",
        "rule": "reallocate_ticket_rate_limited",
        "msg": "Ticket was recently reallocated (within 5 minutes cooldown)",
        "severity": "high"
    }
}

violations[violation] if {
    input.resource.action == "restart_workflow"
    input.resource.workflow_id == ""
    violation := {
        "policy": "playbook_validation",
        "rule": "restart_workflow_missing_workflow_id",
        "msg": "Workflow restart requires workflow_id",
        "severity": "high"
    }
}

violations[violation] if {
    input.resource.action == "restart_workflow"
    workflow_in_terminal_state
    violation := {
        "policy": "playbook_validation",
        "rule": "restart_workflow_terminal_state",
        "msg": sprintf("Cannot restart workflow in terminal state: %s", [input.context.workflow_state]),
        "severity": "high"
    }
}

violations[violation] if {
    input.resource.action == "update_ticket_status"
    input.resource.ticket_id == ""
    violation := {
        "policy": "playbook_validation",
        "rule": "update_ticket_status_missing_ticket_id",
        "msg": "Ticket status update requires ticket_id",
        "severity": "high"
    }
}

violations[violation] if {
    input.resource.action == "trigger_replanning"
    not has_plan_or_workflow_id
    violation := {
        "policy": "playbook_validation",
        "rule": "trigger_replanning_missing_id",
        "msg": "Replanning requires plan_id or workflow_id",
        "severity": "high"
    }
}

violations[violation] if {
    input.resource.action == "trigger_replanning"
    workflow_in_terminal_state
    violation := {
        "policy": "playbook_validation",
        "rule": "trigger_replanning_terminal_state",
        "msg": sprintf("Cannot trigger replanning for workflow in terminal state: %s", [input.context.workflow_state]),
        "severity": "high"
    }
}

# =============================================================================
# Metadata - Policy information
# =============================================================================

metadata := {
    "policy_name": "playbook_validation",
    "version": "1.0.0",
    "description": "Validates self-healing playbook actions",
    "owner": "self-healing-engine",
    "actions_validated": [
        "reallocate_ticket",
        "restart_workflow",
        "update_ticket_status",
        "trigger_replanning"
    ]
}
