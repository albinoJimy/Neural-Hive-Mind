# Guard Agents Resource Policies
# OPA Rego policies for validating resource limits and quotas of ExecutionTickets
# Part of Neural Hive Mind - Guard Agents Service

package neuralhive.guard.resource_policies

import future.keywords.in
import future.keywords.contains
import future.keywords.if
import future.keywords.every

# Default result structure
default allow := false

# CPU unit conversions (to millicores)
cpu_unit_multipliers := {
    "m": 1,
    "": 1000,
    "k": 1000000
}

# Memory unit conversions (to bytes)
memory_unit_multipliers := {
    "": 1,
    "Ki": 1024,
    "Mi": 1048576,
    "Gi": 1073741824,
    "Ti": 1099511627776,
    "K": 1000,
    "M": 1000000,
    "G": 1000000000,
    "T": 1000000000000
}

# Main result aggregating all evaluations
result := {
    "allow": allow,
    "violations": violations,
    "warnings": warnings,
    "resource_context": resource_context
}

# Allow if no critical or high severity violations exist
allow if {
    count(critical_violations) == 0
    count(high_violations) == 0
}

# Collect all violations
violations := critical_violations | high_violations | medium_violations | low_violations

# Categorize violations by severity
critical_violations contains violation if {
    some violation in all_violations
    violation.severity == "CRITICAL"
}

high_violations contains violation if {
    some violation in all_violations
    violation.severity == "HIGH"
}

medium_violations contains violation if {
    some violation in all_violations
    violation.severity == "MEDIUM"
}

low_violations contains violation if {
    some violation in all_violations
    violation.severity == "LOW"
}

# Aggregate all violation rules
all_violations := missing_cpu_limits_violations |
    missing_memory_limits_violations |
    excessive_cpu_request_violations |
    excessive_memory_request_violations |
    cpu_limit_exceeds_quota_violations |
    memory_limit_exceeds_quota_violations |
    namespace_quota_exceeded_violations |
    pod_count_quota_exceeded_violations |
    storage_quota_exceeded_violations |
    service_quota_exceeded_violations |
    low_cpu_utilization_violations |
    low_memory_utilization_violations |
    oversized_request_violations |
    missing_hpa_violations |
    insufficient_replicas_violations |
    excessive_replicas_violations

# Warnings (non-blocking issues)
warnings contains warning if {
    some warning in all_warnings
}

all_warnings := resource_recommendation_warnings

# Resource context summary
resource_context := {
    "ticket_id": input.ticket.ticket_id,
    "environment": input.ticket.environment,
    "requested_cpu": get_cpu_request,
    "requested_memory": get_memory_request,
    "cpu_limit": get_cpu_limit,
    "memory_limit": get_memory_limit,
    "replicas": object.get(input.ticket, "replicas", 1),
    "violation_count": count(violations),
    "critical_count": count(critical_violations),
    "high_count": count(high_violations),
    "medium_count": count(medium_violations),
    "low_count": count(low_violations),
    "efficiency_score": calculate_efficiency_score
}

# Get CPU request value
get_cpu_request := cpu if {
    resources := object.get(input.ticket, "resources", {})
    requests := object.get(resources, "requests", {})
    cpu := object.get(requests, "cpu", "0m")
}

# Get memory request value
get_memory_request := memory if {
    resources := object.get(input.ticket, "resources", {})
    requests := object.get(resources, "requests", {})
    memory := object.get(requests, "memory", "0Mi")
}

# Get CPU limit value
get_cpu_limit := cpu if {
    resources := object.get(input.ticket, "resources", {})
    limits := object.get(resources, "limits", {})
    cpu := object.get(limits, "cpu", "0m")
}

# Get memory limit value
get_memory_limit := memory if {
    resources := object.get(input.ticket, "resources", {})
    limits := object.get(resources, "limits", {})
    memory := object.get(limits, "memory", "0Mi")
}

# Calculate efficiency score based on resource utilization
calculate_efficiency_score := score if {
    violation_penalty := count(violations) * 10
    base_score := 100 - violation_penalty
    score := max([0, base_score])
}

# =============================================================================
# CPU/MEMORY LIMIT VIOLATIONS
# =============================================================================

# Rule: missing_cpu_limits_violation
# Detect containers without CPU limits defined
missing_cpu_limits_violations contains violation if {
    resources := object.get(input.ticket, "resources", {})
    limits := object.get(resources, "limits", {})
    not limits.cpu
    violation := {
        "rule": "missing_cpu_limits",
        "severity": "MEDIUM",
        "message": "No CPU limits defined for container",
        "resource": input.ticket.ticket_id,
        "details": {
            "current_limits": limits,
            "has_cpu_limit": false
        },
        "remediation": "Define CPU limits to prevent resource exhaustion"
    }
}

# Rule: missing_memory_limits_violation
# Detect containers without memory limits defined
missing_memory_limits_violations contains violation if {
    resources := object.get(input.ticket, "resources", {})
    limits := object.get(resources, "limits", {})
    not limits.memory
    violation := {
        "rule": "missing_memory_limits",
        "severity": "MEDIUM",
        "message": "No memory limits defined for container",
        "resource": input.ticket.ticket_id,
        "details": {
            "current_limits": limits,
            "has_memory_limit": false
        },
        "remediation": "Define memory limits to prevent OOM conditions"
    }
}

# Rule: excessive_cpu_request_violation
# Detect CPU requests that exceed per-container maximum
excessive_cpu_request_violations contains violation if {
    resources := object.get(input.ticket, "resources", {})
    requests := object.get(resources, "requests", {})
    cpu_request := object.get(requests, "cpu", "0m")
    max_cpu := object.get(input.thresholds, "max_cpu_per_container", "4000m")
    parse_cpu_value(cpu_request) > parse_cpu_value(max_cpu)
    violation := {
        "rule": "excessive_cpu_request",
        "severity": "HIGH",
        "message": sprintf("CPU request (%s) exceeds maximum allowed (%s)", [cpu_request, max_cpu]),
        "resource": input.ticket.ticket_id,
        "details": {
            "cpu_request": cpu_request,
            "max_allowed": max_cpu,
            "request_millicores": parse_cpu_value(cpu_request),
            "max_millicores": parse_cpu_value(max_cpu)
        },
        "remediation": "Reduce CPU request to comply with resource limits"
    }
}

# Rule: excessive_memory_request_violation
# Detect memory requests that exceed per-container maximum
excessive_memory_request_violations contains violation if {
    resources := object.get(input.ticket, "resources", {})
    requests := object.get(resources, "requests", {})
    memory_request := object.get(requests, "memory", "0Mi")
    max_memory := object.get(input.thresholds, "max_memory_per_container", "8Gi")
    parse_memory_value(memory_request) > parse_memory_value(max_memory)
    violation := {
        "rule": "excessive_memory_request",
        "severity": "HIGH",
        "message": sprintf("Memory request (%s) exceeds maximum allowed (%s)", [memory_request, max_memory]),
        "resource": input.ticket.ticket_id,
        "details": {
            "memory_request": memory_request,
            "max_allowed": max_memory,
            "request_bytes": parse_memory_value(memory_request),
            "max_bytes": parse_memory_value(max_memory)
        },
        "remediation": "Reduce memory request to comply with resource limits"
    }
}

# Rule: cpu_limit_exceeds_quota_violation
# Detect CPU limits that exceed namespace quota
cpu_limit_exceeds_quota_violations contains violation if {
    resources := object.get(input.ticket, "resources", {})
    limits := object.get(resources, "limits", {})
    cpu_limit := object.get(limits, "cpu", "0m")
    namespace_quota := object.get(input.quotas, "namespace_cpu_quota", "")
    namespace_quota != ""
    parse_cpu_value(cpu_limit) > parse_cpu_value(namespace_quota)
    violation := {
        "rule": "cpu_limit_exceeds_quota",
        "severity": "HIGH",
        "message": sprintf("CPU limit (%s) exceeds namespace quota (%s)", [cpu_limit, namespace_quota]),
        "resource": input.ticket.ticket_id,
        "details": {
            "cpu_limit": cpu_limit,
            "namespace_quota": namespace_quota
        },
        "remediation": "Reduce CPU limit or request quota increase"
    }
}

# Rule: memory_limit_exceeds_quota_violation
# Detect memory limits that exceed namespace quota
memory_limit_exceeds_quota_violations contains violation if {
    resources := object.get(input.ticket, "resources", {})
    limits := object.get(resources, "limits", {})
    memory_limit := object.get(limits, "memory", "0Mi")
    namespace_quota := object.get(input.quotas, "namespace_memory_quota", "")
    namespace_quota != ""
    parse_memory_value(memory_limit) > parse_memory_value(namespace_quota)
    violation := {
        "rule": "memory_limit_exceeds_quota",
        "severity": "HIGH",
        "message": sprintf("Memory limit (%s) exceeds namespace quota (%s)", [memory_limit, namespace_quota]),
        "resource": input.ticket.ticket_id,
        "details": {
            "memory_limit": memory_limit,
            "namespace_quota": namespace_quota
        },
        "remediation": "Reduce memory limit or request quota increase"
    }
}

# =============================================================================
# RESOURCE QUOTA VIOLATIONS
# =============================================================================

# Rule: namespace_quota_exceeded_violation
# Detect when deployment would exceed namespace resource quota
namespace_quota_exceeded_violations contains violation if {
    resources := object.get(input.ticket, "resources", {})
    requests := object.get(resources, "requests", {})
    replicas := object.get(input.ticket, "replicas", 1)

    cpu_request := object.get(requests, "cpu", "0m")
    total_cpu := parse_cpu_value(cpu_request) * replicas

    current_usage := object.get(input.quotas, "current_cpu_usage", "0m")
    namespace_quota := object.get(input.quotas, "namespace_cpu_quota", "")
    namespace_quota != ""

    projected_usage := parse_cpu_value(current_usage) + total_cpu
    projected_usage > parse_cpu_value(namespace_quota)

    violation := {
        "rule": "namespace_quota_exceeded",
        "severity": "CRITICAL",
        "message": "Deployment would exceed namespace CPU quota",
        "resource": input.ticket.ticket_id,
        "details": {
            "current_usage": current_usage,
            "additional_request": sprintf("%dm", [total_cpu]),
            "projected_total": sprintf("%dm", [projected_usage]),
            "namespace_quota": namespace_quota,
            "replicas": replicas
        },
        "remediation": "Reduce resource requests or request quota increase"
    }
}

# Rule: pod_count_quota_exceeded_violation
# Detect when deployment would exceed pod count quota
pod_count_quota_exceeded_violations contains violation if {
    replicas := object.get(input.ticket, "replicas", 1)
    current_pods := object.get(input.quotas, "current_pod_count", 0)
    max_pods := object.get(input.quotas, "max_pods", 0)
    max_pods > 0
    current_pods + replicas > max_pods
    violation := {
        "rule": "pod_count_quota_exceeded",
        "severity": "HIGH",
        "message": sprintf("Deployment would exceed pod count quota (%d + %d > %d)", [current_pods, replicas, max_pods]),
        "resource": input.ticket.ticket_id,
        "details": {
            "current_pods": current_pods,
            "requested_replicas": replicas,
            "max_pods": max_pods
        },
        "remediation": "Reduce replica count or request quota increase"
    }
}

# Rule: storage_quota_exceeded_violation
# Detect when deployment would exceed storage quota
storage_quota_exceeded_violations contains violation if {
    storage := object.get(input.ticket, "storage", {})
    storage_request := object.get(storage, "size", "0Gi")
    current_storage := object.get(input.quotas, "current_storage_usage", "0Gi")
    max_storage := object.get(input.quotas, "max_storage", "")
    max_storage != ""

    projected := parse_memory_value(current_storage) + parse_memory_value(storage_request)
    projected > parse_memory_value(max_storage)

    violation := {
        "rule": "storage_quota_exceeded",
        "severity": "HIGH",
        "message": "Deployment would exceed storage quota",
        "resource": input.ticket.ticket_id,
        "details": {
            "storage_request": storage_request,
            "current_usage": current_storage,
            "max_storage": max_storage
        },
        "remediation": "Reduce storage request or request quota increase"
    }
}

# Rule: service_quota_exceeded_violation
# Detect when deployment would exceed service quota
service_quota_exceeded_violations contains violation if {
    services := object.get(input.ticket, "services", [])
    current_services := object.get(input.quotas, "current_service_count", 0)
    max_services := object.get(input.quotas, "max_services", 0)
    max_services > 0
    current_services + count(services) > max_services
    violation := {
        "rule": "service_quota_exceeded",
        "severity": "MEDIUM",
        "message": sprintf("Deployment would exceed service quota (%d + %d > %d)", [current_services, count(services), max_services]),
        "resource": input.ticket.ticket_id,
        "details": {
            "current_services": current_services,
            "requested_services": count(services),
            "max_services": max_services
        },
        "remediation": "Reduce number of services or consolidate"
    }
}

# =============================================================================
# RESOURCE EFFICIENCY VIOLATIONS
# =============================================================================

# Rule: low_cpu_utilization_violation
# Detect consistently low CPU utilization
low_cpu_utilization_violations contains violation if {
    metrics := object.get(input.ticket, "metrics", {})
    cpu_utilization := object.get(metrics, "avg_cpu_utilization_percent", 100)
    min_utilization := object.get(input.thresholds, "min_cpu_utilization_percent", 20)
    cpu_utilization < min_utilization
    cpu_utilization > 0
    violation := {
        "rule": "low_cpu_utilization",
        "severity": "LOW",
        "message": sprintf("Low CPU utilization detected: %d%% (threshold: %d%%)", [cpu_utilization, min_utilization]),
        "resource": input.ticket.ticket_id,
        "details": {
            "avg_cpu_utilization": cpu_utilization,
            "threshold": min_utilization
        },
        "remediation": "Consider reducing CPU requests to improve resource efficiency"
    }
}

# Rule: low_memory_utilization_violation
# Detect consistently low memory utilization
low_memory_utilization_violations contains violation if {
    metrics := object.get(input.ticket, "metrics", {})
    memory_utilization := object.get(metrics, "avg_memory_utilization_percent", 100)
    min_utilization := object.get(input.thresholds, "min_memory_utilization_percent", 20)
    memory_utilization < min_utilization
    memory_utilization > 0
    violation := {
        "rule": "low_memory_utilization",
        "severity": "LOW",
        "message": sprintf("Low memory utilization detected: %d%% (threshold: %d%%)", [memory_utilization, min_utilization]),
        "resource": input.ticket.ticket_id,
        "details": {
            "avg_memory_utilization": memory_utilization,
            "threshold": min_utilization
        },
        "remediation": "Consider reducing memory requests to improve resource efficiency"
    }
}

# Rule: oversized_request_violation
# Detect requests significantly larger than actual utilization
oversized_request_violations contains violation if {
    metrics := object.get(input.ticket, "metrics", {})
    resources := object.get(input.ticket, "resources", {})
    requests := object.get(resources, "requests", {})

    cpu_request := object.get(requests, "cpu", "0m")
    actual_cpu_usage := object.get(metrics, "peak_cpu_millicores", 0)
    request_millicores := parse_cpu_value(cpu_request)

    request_millicores > 0
    actual_cpu_usage > 0
    utilization_ratio := (actual_cpu_usage / request_millicores) * 100
    utilization_ratio < 30

    violation := {
        "rule": "oversized_request",
        "severity": "MEDIUM",
        "message": sprintf("CPU request is oversized: only using %d%% of requested resources", [round(utilization_ratio)]),
        "resource": input.ticket.ticket_id,
        "details": {
            "cpu_request": cpu_request,
            "peak_usage_millicores": actual_cpu_usage,
            "utilization_percent": round(utilization_ratio)
        },
        "remediation": "Right-size CPU requests based on actual usage patterns"
    }
}

# =============================================================================
# SCALING VIOLATIONS
# =============================================================================

# Rule: missing_hpa_violation
# Detect missing HPA in production
missing_hpa_violations contains violation if {
    is_production_environment(input.ticket.environment)
    object.get(input.thresholds, "require_hpa_production", true)
    not object.get(input.ticket, "hpa_enabled", false)
    violation := {
        "rule": "missing_hpa",
        "severity": "MEDIUM",
        "message": "No Horizontal Pod Autoscaler configured for production deployment",
        "resource": input.ticket.ticket_id,
        "details": {
            "environment": input.ticket.environment,
            "hpa_enabled": false
        },
        "remediation": "Configure HPA for automatic scaling based on resource utilization"
    }
}

# Rule: insufficient_replicas_violation
# Detect insufficient replicas for production
insufficient_replicas_violations contains violation if {
    is_production_environment(input.ticket.environment)
    replicas := object.get(input.ticket, "replicas", 1)
    min_replicas := object.get(input.thresholds, "min_replicas_production", 2)
    replicas < min_replicas
    violation := {
        "rule": "insufficient_replicas",
        "severity": "HIGH",
        "message": sprintf("Insufficient replicas for production: %d (minimum: %d)", [replicas, min_replicas]),
        "resource": input.ticket.ticket_id,
        "details": {
            "current_replicas": replicas,
            "min_required": min_replicas,
            "environment": input.ticket.environment
        },
        "remediation": sprintf("Increase replica count to at least %d for high availability", [min_replicas])
    }
}

# Rule: excessive_replicas_violation
# Detect excessive replicas that may waste resources
excessive_replicas_violations contains violation if {
    replicas := object.get(input.ticket, "replicas", 1)
    max_replicas := object.get(input.thresholds, "max_replicas", 100)
    replicas > max_replicas
    violation := {
        "rule": "excessive_replicas",
        "severity": "MEDIUM",
        "message": sprintf("Excessive replicas configured: %d (maximum: %d)", [replicas, max_replicas]),
        "resource": input.ticket.ticket_id,
        "details": {
            "current_replicas": replicas,
            "max_allowed": max_replicas
        },
        "remediation": "Review replica count and consider using HPA for dynamic scaling"
    }
}

# =============================================================================
# WARNING RULES (Non-blocking)
# =============================================================================

# Resource recommendation warnings
resource_recommendation_warnings contains warning if {
    resources := object.get(input.ticket, "resources", {})
    requests := object.get(resources, "requests", {})
    limits := object.get(resources, "limits", {})

    cpu_request := object.get(requests, "cpu", "0m")
    cpu_limit := object.get(limits, "cpu", "0m")

    parse_cpu_value(cpu_request) > 0
    parse_cpu_value(cpu_limit) > 0

    ratio := parse_cpu_value(cpu_limit) / parse_cpu_value(cpu_request)
    ratio > 10

    warning := {
        "type": "resource_recommendation",
        "message": sprintf("Large gap between CPU request and limit (ratio: %.1f)", [ratio]),
        "details": {
            "cpu_request": cpu_request,
            "cpu_limit": cpu_limit,
            "ratio": ratio
        }
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Parse CPU value to millicores
parse_cpu_value(cpu_string) := millicores if {
    is_string(cpu_string)
    regex.match(`^[0-9]+m$`, cpu_string)
    millicores := to_number(trim_suffix(cpu_string, "m"))
}

parse_cpu_value(cpu_string) := millicores if {
    is_string(cpu_string)
    regex.match(`^[0-9]+(\.[0-9]+)?$`, cpu_string)
    millicores := to_number(cpu_string) * 1000
}

parse_cpu_value(cpu_string) := 0 if {
    is_string(cpu_string)
    cpu_string == ""
}

parse_cpu_value(cpu_string) := 0 if {
    is_string(cpu_string)
    cpu_string == "0"
}

parse_cpu_value(cpu_value) := millicores if {
    is_number(cpu_value)
    millicores := cpu_value * 1000
}

# Parse memory value to bytes
parse_memory_value(memory_string) := bytes if {
    is_string(memory_string)
    regex.match(`^[0-9]+Ki$`, memory_string)
    bytes := to_number(trim_suffix(memory_string, "Ki")) * 1024
}

parse_memory_value(memory_string) := bytes if {
    is_string(memory_string)
    regex.match(`^[0-9]+Mi$`, memory_string)
    bytes := to_number(trim_suffix(memory_string, "Mi")) * 1048576
}

parse_memory_value(memory_string) := bytes if {
    is_string(memory_string)
    regex.match(`^[0-9]+Gi$`, memory_string)
    bytes := to_number(trim_suffix(memory_string, "Gi")) * 1073741824
}

parse_memory_value(memory_string) := bytes if {
    is_string(memory_string)
    regex.match(`^[0-9]+Ti$`, memory_string)
    bytes := to_number(trim_suffix(memory_string, "Ti")) * 1099511627776
}

parse_memory_value(memory_string) := bytes if {
    is_string(memory_string)
    regex.match(`^[0-9]+$`, memory_string)
    bytes := to_number(memory_string)
}

parse_memory_value(memory_string) := 0 if {
    is_string(memory_string)
    memory_string == ""
}

parse_memory_value(memory_string) := 0 if {
    is_string(memory_string)
    memory_string == "0"
}

parse_memory_value(memory_value) := bytes if {
    is_number(memory_value)
    bytes := memory_value
}

# Check if environment is production
is_production_environment(env) if {
    lower(env) == "production"
}

is_production_environment(env) if {
    lower(env) == "prod"
}

# Check if value is within quota
is_within_quota(value, quota) if {
    value <= quota
}

# Calculate utilization percentage
calculate_utilization(request, limit) := percentage if {
    request > 0
    limit > 0
    percentage := (request / limit) * 100
}

# Round helper
round(x) := y if {
    y := floor(x + 0.5)
}

# Max helper
max(values) := result if {
    result := [v | v := values[_]; v >= values[_]][0]
}

# Floor helper for rounding
floor(x) := y if {
    y := x - (x % 1)
}
