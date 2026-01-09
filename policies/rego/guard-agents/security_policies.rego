# Guard Agents Security Policies
# OPA Rego policies for validating security requirements of ExecutionTickets
# Part of Neural Hive Mind - Guard Agents Service

package neuralhive.guard.security_policies

import future.keywords.in
import future.keywords.contains
import future.keywords.if
import future.keywords.every

# Default result structure
default allow := false

# Dangerous capabilities that should not be allowed
dangerous_capabilities := {"SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "SYS_RAWIO", "SYS_MODULE", "DAC_OVERRIDE"}

# Insecure protocols that should be flagged
insecure_protocols := {"HTTP", "FTP", "TELNET", "SMTP", "POP3", "IMAP"}

# Secret patterns to detect hardcoded secrets
secret_patterns := {"password", "secret", "api_key", "apikey", "token", "credential", "private_key"}

# Main result aggregating all evaluations
result := {
    "allow": allow,
    "violations": violations,
    "warnings": warnings,
    "security_context": security_context
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
all_violations := privileged_container_violations |
    root_user_violations |
    host_network_violations |
    host_pid_violations |
    host_ipc_violations |
    dangerous_capabilities_violations |
    missing_network_policy_violations |
    unrestricted_egress_violations |
    unrestricted_ingress_violations |
    insecure_protocol_violations |
    unsigned_image_violations |
    unscanned_image_violations |
    high_severity_vulnerabilities_violations |
    latest_tag_violations |
    hardcoded_secret_violations |
    missing_vault_integration_violations |
    secret_in_env_violations

# Warnings (non-blocking issues)
warnings contains warning if {
    some warning in all_warnings
}

all_warnings := deprecated_api_warnings | best_practice_warnings

# Security context summary
security_context := {
    "ticket_id": input.ticket.ticket_id,
    "environment": input.ticket.environment,
    "task_type": input.ticket.task_type,
    "violation_count": count(violations),
    "critical_count": count(critical_violations),
    "high_count": count(high_violations),
    "medium_count": count(medium_violations),
    "low_count": count(low_violations),
    "risk_score": calculate_risk_score
}

# Calculate risk score based on violations
calculate_risk_score := score if {
    critical_weight := count(critical_violations) * 100
    high_weight := count(high_violations) * 50
    medium_weight := count(medium_violations) * 20
    low_weight := count(low_violations) * 5
    score := critical_weight + high_weight + medium_weight + low_weight
}

# =============================================================================
# CONTAINER SECURITY VIOLATIONS
# =============================================================================

# Rule: privileged_container_violation
# Detect containers running in privileged mode
privileged_container_violations contains violation if {
    container_spec := input.ticket.parameters.container_spec
    is_privileged_container(container_spec)
    violation := {
        "rule": "privileged_container",
        "severity": "CRITICAL",
        "message": "Container is configured to run in privileged mode",
        "resource": input.ticket.ticket_id,
        "details": {
            "container_name": object.get(container_spec, "name", "unknown"),
            "privileged": true
        },
        "remediation": "Remove privileged: true from container security context"
    }
}

# Rule: root_user_violation
# Detect containers running as root user
root_user_violations contains violation if {
    container_spec := input.ticket.parameters.container_spec
    is_running_as_root(container_spec)
    violation := {
        "rule": "root_user",
        "severity": "HIGH",
        "message": "Container is configured to run as root user",
        "resource": input.ticket.ticket_id,
        "details": {
            "container_name": object.get(container_spec, "name", "unknown"),
            "run_as_user": object.get(container_spec.security_context, "runAsUser", 0)
        },
        "remediation": "Set runAsNonRoot: true and specify a non-root runAsUser"
    }
}

# Rule: host_network_violation
# Detect containers using host network namespace
host_network_violations contains violation if {
    container_spec := input.ticket.parameters.container_spec
    container_spec.host_network == true
    violation := {
        "rule": "host_network",
        "severity": "CRITICAL",
        "message": "Container is configured to use host network namespace",
        "resource": input.ticket.ticket_id,
        "details": {
            "container_name": object.get(container_spec, "name", "unknown"),
            "host_network": true
        },
        "remediation": "Remove hostNetwork: true and use proper network policies"
    }
}

# Rule: host_pid_violation
# Detect containers using host PID namespace
host_pid_violations contains violation if {
    container_spec := input.ticket.parameters.container_spec
    container_spec.host_pid == true
    violation := {
        "rule": "host_pid",
        "severity": "HIGH",
        "message": "Container is configured to use host PID namespace",
        "resource": input.ticket.ticket_id,
        "details": {
            "container_name": object.get(container_spec, "name", "unknown"),
            "host_pid": true
        },
        "remediation": "Remove hostPID: true from pod specification"
    }
}

# Rule: host_ipc_violation
# Detect containers using host IPC namespace
host_ipc_violations contains violation if {
    container_spec := input.ticket.parameters.container_spec
    container_spec.host_ipc == true
    violation := {
        "rule": "host_ipc",
        "severity": "HIGH",
        "message": "Container is configured to use host IPC namespace",
        "resource": input.ticket.ticket_id,
        "details": {
            "container_name": object.get(container_spec, "name", "unknown"),
            "host_ipc": true
        },
        "remediation": "Remove hostIPC: true from pod specification"
    }
}

# Rule: dangerous_capabilities_violation
# Detect containers with dangerous Linux capabilities
dangerous_capabilities_violations contains violation if {
    container_spec := input.ticket.parameters.container_spec
    capabilities := object.get(container_spec, "capabilities", {})
    add_caps := object.get(capabilities, "add", [])
    some cap in add_caps
    cap in dangerous_capabilities
    not cap in object.get(input.security, "allowed_capabilities", [])
    violation := {
        "rule": "dangerous_capabilities",
        "severity": "CRITICAL",
        "message": sprintf("Container has dangerous capability: %s", [cap]),
        "resource": input.ticket.ticket_id,
        "details": {
            "container_name": object.get(container_spec, "name", "unknown"),
            "capability": cap,
            "all_capabilities": add_caps
        },
        "remediation": sprintf("Remove capability %s from container security context", [cap])
    }
}

# =============================================================================
# NETWORK POLICY VIOLATIONS
# =============================================================================

# Rule: missing_network_policy_violation
# Detect missing NetworkPolicy in production environments
missing_network_policy_violations contains violation if {
    is_production_environment(input.ticket.environment)
    object.get(input.security, "require_network_policies", true)
    network_policy := object.get(input.ticket.parameters, "network_policy", {})
    count(network_policy) == 0
    violation := {
        "rule": "missing_network_policy",
        "severity": "HIGH",
        "message": "No NetworkPolicy defined for production deployment",
        "resource": input.ticket.ticket_id,
        "details": {
            "environment": input.ticket.environment
        },
        "remediation": "Define a NetworkPolicy to restrict ingress and egress traffic"
    }
}

# Rule: unrestricted_egress_violation
# Detect NetworkPolicy with unrestricted egress
unrestricted_egress_violations contains violation if {
    network_policy := input.ticket.parameters.network_policy
    egress := object.get(network_policy, "egress", [])
    some rule in egress
    is_unrestricted_egress(rule)
    violation := {
        "rule": "unrestricted_egress",
        "severity": "MEDIUM",
        "message": "NetworkPolicy allows unrestricted egress traffic",
        "resource": input.ticket.ticket_id,
        "details": {
            "egress_rule": rule
        },
        "remediation": "Restrict egress to specific destinations and ports"
    }
}

# Rule: unrestricted_ingress_violation
# Detect NetworkPolicy with unrestricted ingress
unrestricted_ingress_violations contains violation if {
    network_policy := input.ticket.parameters.network_policy
    ingress := object.get(network_policy, "ingress", [])
    some rule in ingress
    is_unrestricted_ingress(rule)
    violation := {
        "rule": "unrestricted_ingress",
        "severity": "MEDIUM",
        "message": "NetworkPolicy allows unrestricted ingress traffic",
        "resource": input.ticket.ticket_id,
        "details": {
            "ingress_rule": rule
        },
        "remediation": "Restrict ingress to specific sources and ports"
    }
}

# Rule: insecure_protocol_violation
# Detect use of insecure protocols
insecure_protocol_violations contains violation if {
    network_policy := object.get(input.ticket.parameters, "network_policy", {})
    protocols := object.get(network_policy, "protocols", [])
    some protocol in protocols
    upper(protocol) in insecure_protocols
    violation := {
        "rule": "insecure_protocol",
        "severity": "HIGH",
        "message": sprintf("Insecure protocol detected: %s", [protocol]),
        "resource": input.ticket.ticket_id,
        "details": {
            "protocol": protocol,
            "insecure_protocols": insecure_protocols
        },
        "remediation": sprintf("Replace %s with a secure alternative (e.g., HTTPS, SFTP, SSH)", [protocol])
    }
}

# =============================================================================
# IMAGE SECURITY VIOLATIONS
# =============================================================================

# Rule: unsigned_image_violation
# Detect unsigned container images
unsigned_image_violations contains violation if {
    image := input.ticket.parameters.image
    object.get(input.security, "require_signed_images", true)
    not object.get(image, "signed", false)
    violation := {
        "rule": "unsigned_image",
        "severity": "HIGH",
        "message": "Container image is not signed",
        "resource": input.ticket.ticket_id,
        "details": {
            "image_name": object.get(image, "name", "unknown"),
            "image_tag": object.get(image, "tag", "unknown")
        },
        "remediation": "Use signed container images from trusted registries"
    }
}

# Rule: unscanned_image_violation
# Detect container images without vulnerability scans
unscanned_image_violations contains violation if {
    image := input.ticket.parameters.image
    not object.get(image, "scanned", false)
    violation := {
        "rule": "unscanned_image",
        "severity": "MEDIUM",
        "message": "Container image has not been scanned for vulnerabilities",
        "resource": input.ticket.ticket_id,
        "details": {
            "image_name": object.get(image, "name", "unknown"),
            "image_tag": object.get(image, "tag", "unknown")
        },
        "remediation": "Scan container image with vulnerability scanner before deployment"
    }
}

# Rule: high_severity_vulnerabilities_violation
# Detect images with HIGH or CRITICAL vulnerabilities
high_severity_vulnerabilities_violations contains violation if {
    image := input.ticket.parameters.image
    scan_results := object.get(image, "scan_results", {})
    has_high_severity_vulnerabilities(scan_results)
    max_severity := object.get(input.security, "max_vulnerability_severity", "HIGH")
    violation := {
        "rule": "high_severity_vulnerabilities",
        "severity": "HIGH",
        "message": "Container image has HIGH or CRITICAL vulnerabilities",
        "resource": input.ticket.ticket_id,
        "details": {
            "image_name": object.get(image, "name", "unknown"),
            "critical_count": object.get(scan_results, "critical", 0),
            "high_count": object.get(scan_results, "high", 0),
            "max_allowed_severity": max_severity
        },
        "remediation": "Update base image and dependencies to fix vulnerabilities"
    }
}

# Rule: latest_tag_violation
# Detect use of :latest tag in production
latest_tag_violations contains violation if {
    is_production_environment(input.ticket.environment)
    image := input.ticket.parameters.image
    tag := object.get(image, "tag", "latest")
    tag == "latest"
    violation := {
        "rule": "latest_tag",
        "severity": "MEDIUM",
        "message": "Container image uses :latest tag in production",
        "resource": input.ticket.ticket_id,
        "details": {
            "image_name": object.get(image, "name", "unknown"),
            "tag": tag,
            "environment": input.ticket.environment
        },
        "remediation": "Use specific image tags or SHA256 digests for production deployments"
    }
}

# =============================================================================
# SECRET MANAGEMENT VIOLATIONS
# =============================================================================

# Rule: hardcoded_secret_violation
# Detect hardcoded secrets in configuration
hardcoded_secret_violations contains violation if {
    secrets := object.get(input.ticket.parameters, "secrets", {})
    some key, value in secrets
    is_hardcoded_secret(key, value)
    violation := {
        "rule": "hardcoded_secret",
        "severity": "CRITICAL",
        "message": sprintf("Hardcoded secret detected: %s", [key]),
        "resource": input.ticket.ticket_id,
        "details": {
            "secret_key": key,
            "pattern_match": true
        },
        "remediation": "Use Vault or Kubernetes Secrets for secret management"
    }
}

# Rule: missing_vault_integration_violation
# Detect missing Vault integration for sensitive secrets
missing_vault_integration_violations contains violation if {
    secrets := object.get(input.ticket.parameters, "secrets", {})
    count(secrets) > 0
    is_production_environment(input.ticket.environment)
    not object.get(input.ticket.parameters, "vault_integration", false)
    some key in object.keys(secrets)
    is_sensitive_secret_key(key)
    violation := {
        "rule": "missing_vault_integration",
        "severity": "HIGH",
        "message": "Sensitive secrets detected without Vault integration",
        "resource": input.ticket.ticket_id,
        "details": {
            "sensitive_keys": [k | some k in object.keys(secrets); is_sensitive_secret_key(k)],
            "vault_integration": false,
            "environment": input.ticket.environment
        },
        "remediation": "Enable Vault integration for secure secret management"
    }
}

# Rule: secret_in_env_violation
# Detect secrets passed via environment variables
secret_in_env_violations contains violation if {
    container_spec := input.ticket.parameters.container_spec
    env_vars := object.get(container_spec, "env", [])
    some env in env_vars
    is_secret_env_var(env)
    violation := {
        "rule": "secret_in_env",
        "severity": "MEDIUM",
        "message": sprintf("Secret detected in environment variable: %s", [env.name]),
        "resource": input.ticket.ticket_id,
        "details": {
            "env_name": env.name,
            "container_name": object.get(container_spec, "name", "unknown")
        },
        "remediation": "Use secretKeyRef or Vault injection instead of plain environment variables"
    }
}

# =============================================================================
# WARNING RULES (Non-blocking)
# =============================================================================

# Deprecated API warnings
deprecated_api_warnings contains warning if {
    api_version := object.get(input.ticket.parameters, "api_version", "")
    is_deprecated_api(api_version)
    warning := {
        "type": "deprecated_api",
        "message": sprintf("Using deprecated API version: %s", [api_version]),
        "details": {
            "api_version": api_version
        }
    }
}

# Best practice warnings
best_practice_warnings contains warning if {
    container_spec := input.ticket.parameters.container_spec
    not object.get(container_spec, "read_only_root_filesystem", false)
    warning := {
        "type": "best_practice",
        "message": "Container root filesystem is not read-only",
        "details": {
            "read_only_root_filesystem": false
        }
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Check if container is privileged
is_privileged_container(container_spec) if {
    container_spec.privileged == true
}

is_privileged_container(container_spec) if {
    security_context := object.get(container_spec, "security_context", {})
    security_context.privileged == true
}

# Check if container runs as root
is_running_as_root(container_spec) if {
    security_context := object.get(container_spec, "security_context", {})
    run_as_user := object.get(security_context, "runAsUser", -1)
    run_as_user == 0
}

is_running_as_root(container_spec) if {
    security_context := object.get(container_spec, "security_context", {})
    not object.get(security_context, "runAsNonRoot", false)
    not security_context.runAsUser
}

# Check if environment is production
is_production_environment(env) if {
    lower(env) == "production"
}

is_production_environment(env) if {
    lower(env) == "prod"
}

# Check for HIGH/CRITICAL vulnerabilities
has_high_severity_vulnerabilities(scan_results) if {
    critical := object.get(scan_results, "critical", 0)
    critical > 0
}

has_high_severity_vulnerabilities(scan_results) if {
    high := object.get(scan_results, "high", 0)
    high > 0
}

# Check for dangerous capabilities
has_dangerous_capability(capabilities) if {
    some cap in capabilities
    cap in dangerous_capabilities
}

# Check if value appears to be a hardcoded secret
is_hardcoded_secret(key, value) if {
    is_sensitive_secret_key(key)
    is_string(value)
    count(value) > 0
    not startswith(value, "${")
    not startswith(value, "vault:")
    not startswith(value, "secret:")
}

# Check if key indicates a sensitive secret
is_sensitive_secret_key(key) if {
    some pattern in secret_patterns
    contains(lower(key), pattern)
}

# Check if environment variable contains a secret
is_secret_env_var(env) if {
    is_sensitive_secret_key(env.name)
    value := object.get(env, "value", "")
    count(value) > 0
    not env.valueFrom
}

# Check for unrestricted egress
is_unrestricted_egress(rule) if {
    count(object.get(rule, "to", [])) == 0
    count(object.get(rule, "ports", [])) == 0
}

is_unrestricted_egress(rule) if {
    to := object.get(rule, "to", [])
    some dest in to
    ip_block := object.get(dest, "ipBlock", {})
    cidr := object.get(ip_block, "cidr", "")
    cidr == "0.0.0.0/0"
}

# Check for unrestricted ingress
is_unrestricted_ingress(rule) if {
    count(object.get(rule, "from", [])) == 0
    count(object.get(rule, "ports", [])) == 0
}

is_unrestricted_ingress(rule) if {
    from := object.get(rule, "from", [])
    some source in from
    ip_block := object.get(source, "ipBlock", {})
    cidr := object.get(ip_block, "cidr", "")
    cidr == "0.0.0.0/0"
}

# Check for deprecated API versions
is_deprecated_api(api_version) if {
    deprecated_apis := {"extensions/v1beta1", "apps/v1beta1", "apps/v1beta2"}
    api_version in deprecated_apis
}
