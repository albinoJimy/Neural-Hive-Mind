# Guard Agents Compliance Policies
# OPA Rego policies for validating compliance requirements of ExecutionTickets
# Part of Neural Hive Mind - Guard Agents Service

package neuralhive.guard.compliance_policies

import future.keywords.in
import future.keywords.contains
import future.keywords.if
import future.keywords.every

# Default result structure
default allow := false

# Data classification levels (ordered by sensitivity)
data_classifications := ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]

# Classifications that require encryption
encryption_required_classifications := {"CONFIDENTIAL", "RESTRICTED"}

# Task types that require audit trails
audit_required_task_types := {"DEPLOY", "DELETE", "MODIFY", "EXECUTE"}

# Regulatory frameworks
regulatory_frameworks := {"GDPR", "HIPAA", "PCI-DSS", "SOX", "CCPA", "ISO27001"}

# Main result aggregating all evaluations
result := {
    "allow": allow,
    "violations": violations,
    "warnings": warnings,
    "compliance_context": compliance_context
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
all_violations := pii_without_encryption_violations |
    pii_without_classification_violations |
    pii_cross_region_violations |
    pii_retention_violations |
    missing_retention_policy_violations |
    excessive_retention_period_violations |
    missing_deletion_mechanism_violations |
    missing_audit_logging_violations |
    insufficient_audit_retention_violations |
    missing_audit_trail_violations |
    gdpr_violations |
    hipaa_violations |
    pci_dss_violations |
    sox_violations

# Warnings (non-blocking issues)
warnings contains warning if {
    some warning in all_warnings
}

all_warnings := compliance_recommendation_warnings

# Compliance context summary
compliance_context := {
    "ticket_id": input.ticket.ticket_id,
    "contains_pii": object.get(input.ticket, "contains_pii", false),
    "data_classification": object.get(input.ticket, "data_classification", "INTERNAL"),
    "required_regulations": object.get(input.compliance, "required_regulations", []),
    "violation_count": count(violations),
    "critical_count": count(critical_violations),
    "high_count": count(high_violations),
    "medium_count": count(medium_violations),
    "low_count": count(low_violations),
    "compliance_score": calculate_compliance_score
}

# Calculate compliance score (100 = fully compliant)
calculate_compliance_score := score if {
    base_score := 100
    critical_penalty := count(critical_violations) * 30
    high_penalty := count(high_violations) * 20
    medium_penalty := count(medium_violations) * 10
    low_penalty := count(low_violations) * 5
    total_penalty := critical_penalty + high_penalty + medium_penalty + low_penalty
    raw_score := base_score - total_penalty
    score := max([0, raw_score])
}

# =============================================================================
# PII HANDLING VIOLATIONS
# =============================================================================

# Rule: pii_without_encryption_violation
# Detect PII data without encryption at rest
pii_without_encryption_violations contains violation if {
    input.ticket.contains_pii == true
    object.get(input.compliance, "require_encryption_at_rest", true)
    data_config := object.get(input.ticket, "data_config", {})
    not object.get(data_config, "encryption_at_rest", false)
    violation := {
        "rule": "pii_without_encryption",
        "severity": "CRITICAL",
        "message": "PII data detected without encryption at rest",
        "resource": input.ticket.ticket_id,
        "details": {
            "contains_pii": true,
            "encryption_at_rest": false,
            "data_classification": object.get(input.ticket, "data_classification", "unknown")
        },
        "remediation": "Enable encryption at rest for all PII data storage",
        "regulation": "GDPR Article 32, HIPAA Security Rule"
    }
}

# Rule: pii_without_classification_violation
# Detect PII data without proper data classification
pii_without_classification_violations contains violation if {
    input.ticket.contains_pii == true
    classification := object.get(input.ticket, "data_classification", "")
    not classification in encryption_required_classifications
    violation := {
        "rule": "pii_without_classification",
        "severity": "HIGH",
        "message": "PII data detected with insufficient data classification",
        "resource": input.ticket.ticket_id,
        "details": {
            "contains_pii": true,
            "current_classification": classification,
            "required_classifications": encryption_required_classifications
        },
        "remediation": "Classify PII data as CONFIDENTIAL or RESTRICTED",
        "regulation": "GDPR Article 5, ISO 27001"
    }
}

# Rule: pii_cross_region_violation
# Detect PII data transfer between regions without approval
pii_cross_region_violations contains violation if {
    input.ticket.contains_pii == true
    source_region := object.get(input.ticket, "data_residency_region", "")
    target_region := object.get(input.ticket, "target_region", source_region)
    is_cross_region_transfer(source_region, target_region)
    not object.get(input.ticket, "cross_region_transfer_approved", false)
    violation := {
        "rule": "pii_cross_region",
        "severity": "CRITICAL",
        "message": "PII cross-region transfer detected without approval",
        "resource": input.ticket.ticket_id,
        "details": {
            "source_region": source_region,
            "target_region": target_region,
            "transfer_approved": false
        },
        "remediation": "Obtain approval for cross-region PII transfer or use region-local processing",
        "regulation": "GDPR Chapter V, CCPA 1798.140"
    }
}

# Rule: pii_retention_violation
# Detect PII retention beyond allowed period
pii_retention_violations contains violation if {
    input.ticket.contains_pii == true
    retention_policy := object.get(input.ticket, "retention_policy", {})
    retention_days := object.get(retention_policy, "retention_days", 0)
    max_retention := object.get(input.compliance, "max_pii_retention_days", 365)
    retention_days > max_retention
    violation := {
        "rule": "pii_retention",
        "severity": "HIGH",
        "message": sprintf("PII retention period (%d days) exceeds maximum allowed (%d days)", [retention_days, max_retention]),
        "resource": input.ticket.ticket_id,
        "details": {
            "retention_days": retention_days,
            "max_allowed_days": max_retention,
            "contains_pii": true
        },
        "remediation": "Reduce PII retention period to comply with data minimization principles",
        "regulation": "GDPR Article 5(1)(e), CCPA 1798.105"
    }
}

# =============================================================================
# DATA RETENTION VIOLATIONS
# =============================================================================

# Rule: missing_retention_policy_violation
# Detect missing data retention policy
missing_retention_policy_violations contains violation if {
    data_config := object.get(input.ticket, "data_config", {})
    object.get(data_config, "persists_data", true)
    retention_policy := object.get(input.ticket, "retention_policy", {})
    count(retention_policy) == 0
    violation := {
        "rule": "missing_retention_policy",
        "severity": "MEDIUM",
        "message": "No data retention policy defined for persistent data",
        "resource": input.ticket.ticket_id,
        "details": {
            "persists_data": true,
            "retention_policy": null
        },
        "remediation": "Define a retention policy specifying retention period and deletion mechanism",
        "regulation": "GDPR Article 5(1)(e), SOX Section 802"
    }
}

# Rule: excessive_retention_period_violation
# Detect data retention period exceeding limits
excessive_retention_period_violations contains violation if {
    retention_policy := object.get(input.ticket, "retention_policy", {})
    retention_days := object.get(retention_policy, "retention_days", 0)
    max_retention := object.get(input.compliance, "max_retention_days", 2555)
    retention_days > max_retention
    not input.ticket.contains_pii
    violation := {
        "rule": "excessive_retention_period",
        "severity": "MEDIUM",
        "message": sprintf("Data retention period (%d days) exceeds maximum allowed (%d days)", [retention_days, max_retention]),
        "resource": input.ticket.ticket_id,
        "details": {
            "retention_days": retention_days,
            "max_allowed_days": max_retention
        },
        "remediation": "Reduce data retention period to comply with organizational policy",
        "regulation": "General data governance"
    }
}

# Rule: missing_deletion_mechanism_violation
# Detect missing automatic deletion mechanism
missing_deletion_mechanism_violations contains violation if {
    retention_policy := object.get(input.ticket, "retention_policy", {})
    retention_days := object.get(retention_policy, "retention_days", 0)
    retention_days > 0
    not object.get(retention_policy, "auto_delete", false)
    violation := {
        "rule": "missing_deletion_mechanism",
        "severity": "LOW",
        "message": "No automatic data deletion mechanism configured",
        "resource": input.ticket.ticket_id,
        "details": {
            "retention_days": retention_days,
            "auto_delete": false
        },
        "remediation": "Enable automatic data deletion after retention period expires",
        "regulation": "GDPR Article 17, Right to Erasure"
    }
}

# =============================================================================
# AUDIT VIOLATIONS
# =============================================================================

# Rule: missing_audit_logging_violation
# Detect missing audit logging for critical operations
missing_audit_logging_violations contains violation if {
    object.get(input.compliance, "require_audit_logging", true)
    task_type := input.ticket.task_type
    requires_audit_trail(task_type)
    audit_config := object.get(input.ticket, "audit_config", {})
    not object.get(audit_config, "enabled", false)
    violation := {
        "rule": "missing_audit_logging",
        "severity": "HIGH",
        "message": sprintf("Audit logging not enabled for %s operation", [task_type]),
        "resource": input.ticket.ticket_id,
        "details": {
            "task_type": task_type,
            "audit_enabled": false,
            "requires_audit": true
        },
        "remediation": "Enable audit logging for all critical operations",
        "regulation": "SOX Section 404, PCI-DSS 10.2"
    }
}

# Rule: insufficient_audit_retention_violation
# Detect audit log retention below required minimum
insufficient_audit_retention_violations contains violation if {
    audit_config := object.get(input.ticket, "audit_config", {})
    object.get(audit_config, "enabled", false)
    audit_retention := object.get(audit_config, "retention_days", 0)
    min_audit_retention := object.get(input.compliance, "min_audit_retention_days", 365)
    audit_retention < min_audit_retention
    audit_retention > 0
    violation := {
        "rule": "insufficient_audit_retention",
        "severity": "MEDIUM",
        "message": sprintf("Audit log retention (%d days) below minimum required (%d days)", [audit_retention, min_audit_retention]),
        "resource": input.ticket.ticket_id,
        "details": {
            "audit_retention_days": audit_retention,
            "min_required_days": min_audit_retention
        },
        "remediation": "Increase audit log retention to meet compliance requirements",
        "regulation": "SOX Section 802, PCI-DSS 10.7"
    }
}

# Rule: missing_audit_trail_violation
# Detect missing audit trail for critical actions
missing_audit_trail_violations contains violation if {
    task_type := input.ticket.task_type
    requires_audit_trail(task_type)
    audit_config := object.get(input.ticket, "audit_config", {})
    object.get(audit_config, "enabled", false)
    not object.get(audit_config, "include_user_identity", false)
    violation := {
        "rule": "missing_audit_trail",
        "severity": "HIGH",
        "message": "Audit trail missing user identity for critical action",
        "resource": input.ticket.ticket_id,
        "details": {
            "task_type": task_type,
            "include_user_identity": false
        },
        "remediation": "Configure audit logging to capture user identity for all critical actions",
        "regulation": "SOX Section 404, HIPAA 164.312(b)"
    }
}

# =============================================================================
# REGULATORY COMPLIANCE VIOLATIONS
# =============================================================================

# Rule: gdpr_violation
# Detect GDPR compliance violations
gdpr_violations contains violation if {
    required_regulations := object.get(input.compliance, "required_regulations", [])
    "GDPR" in required_regulations
    input.ticket.contains_pii == true
    not has_gdpr_compliance_controls(input.ticket)
    violation := {
        "rule": "gdpr_violation",
        "severity": "CRITICAL",
        "message": "GDPR compliance requirements not met for PII processing",
        "resource": input.ticket.ticket_id,
        "details": {
            "regulation": "GDPR",
            "contains_pii": true,
            "missing_controls": get_missing_gdpr_controls(input.ticket)
        },
        "remediation": "Implement required GDPR controls: consent management, data subject rights, lawful basis",
        "regulation": "GDPR Articles 6, 7, 12-22"
    }
}

# Rule: hipaa_violation
# Detect HIPAA compliance violations
hipaa_violations contains violation if {
    required_regulations := object.get(input.compliance, "required_regulations", [])
    "HIPAA" in required_regulations
    data_classification := object.get(input.ticket, "data_classification", "")
    data_classification in {"CONFIDENTIAL", "RESTRICTED"}
    not has_hipaa_compliance_controls(input.ticket)
    violation := {
        "rule": "hipaa_violation",
        "severity": "CRITICAL",
        "message": "HIPAA compliance requirements not met for PHI processing",
        "resource": input.ticket.ticket_id,
        "details": {
            "regulation": "HIPAA",
            "data_classification": data_classification,
            "missing_controls": get_missing_hipaa_controls(input.ticket)
        },
        "remediation": "Implement required HIPAA controls: access controls, encryption, audit logs, BAA",
        "regulation": "HIPAA Security Rule 164.312"
    }
}

# Rule: pci_dss_violation
# Detect PCI-DSS compliance violations
pci_dss_violations contains violation if {
    required_regulations := object.get(input.compliance, "required_regulations", [])
    "PCI-DSS" in required_regulations
    handles_payment_data(input.ticket)
    not has_pci_dss_compliance_controls(input.ticket)
    violation := {
        "rule": "pci_dss_violation",
        "severity": "CRITICAL",
        "message": "PCI-DSS compliance requirements not met for payment data processing",
        "resource": input.ticket.ticket_id,
        "details": {
            "regulation": "PCI-DSS",
            "handles_payment_data": true,
            "missing_controls": get_missing_pci_dss_controls(input.ticket)
        },
        "remediation": "Implement required PCI-DSS controls: encryption, network segmentation, access controls",
        "regulation": "PCI-DSS Requirements 3, 4, 7, 10"
    }
}

# Rule: sox_violation
# Detect SOX compliance violations
sox_violations contains violation if {
    required_regulations := object.get(input.compliance, "required_regulations", [])
    "SOX" in required_regulations
    is_financial_system(input.ticket)
    not has_sox_compliance_controls(input.ticket)
    violation := {
        "rule": "sox_violation",
        "severity": "HIGH",
        "message": "SOX compliance requirements not met for financial system",
        "resource": input.ticket.ticket_id,
        "details": {
            "regulation": "SOX",
            "is_financial_system": true,
            "missing_controls": get_missing_sox_controls(input.ticket)
        },
        "remediation": "Implement required SOX controls: change management, access controls, audit trails",
        "regulation": "SOX Sections 302, 404, 802"
    }
}

# =============================================================================
# WARNING RULES (Non-blocking)
# =============================================================================

# Compliance recommendation warnings
compliance_recommendation_warnings contains warning if {
    data_classification := object.get(input.ticket, "data_classification", "")
    data_classification == "INTERNAL"
    input.ticket.contains_pii == true
    warning := {
        "type": "compliance_recommendation",
        "message": "Consider upgrading data classification to CONFIDENTIAL for PII data",
        "details": {
            "current_classification": data_classification,
            "recommended_classification": "CONFIDENTIAL"
        }
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Check if data classification requires encryption
requires_encryption(classification) if {
    classification in encryption_required_classifications
}

# Check for cross-region transfer
is_cross_region_transfer(source, target) if {
    source != target
    source != ""
    target != ""
}

# Check if retention exceeds maximum
is_retention_excessive(retention_days, max_days) if {
    retention_days > max_days
}

# Check if task type requires audit trail
requires_audit_trail(task_type) if {
    upper(task_type) in audit_required_task_types
}

# Check if ticket handles payment data
handles_payment_data(ticket) if {
    data_types := object.get(ticket, "data_types", [])
    some data_type in data_types
    lower(data_type) in {"payment", "credit_card", "card_number", "cvv", "pan"}
}

handles_payment_data(ticket) if {
    object.get(ticket, "handles_payment_data", false)
}

# Check if ticket is for financial system
is_financial_system(ticket) if {
    system_type := object.get(ticket, "system_type", "")
    lower(system_type) in {"financial", "accounting", "billing", "payment"}
}

is_financial_system(ticket) if {
    object.get(ticket, "is_financial_system", false)
}

# GDPR compliance check
has_gdpr_compliance_controls(ticket) if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    gdpr_controls := object.get(compliance_controls, "gdpr", {})
    object.get(gdpr_controls, "consent_management", false)
    object.get(gdpr_controls, "data_subject_rights", false)
    object.get(gdpr_controls, "lawful_basis_documented", false)
}

get_missing_gdpr_controls(ticket) := missing if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    gdpr_controls := object.get(compliance_controls, "gdpr", {})
    missing := [control |
        control := ["consent_management", "data_subject_rights", "lawful_basis_documented"][_]
        not object.get(gdpr_controls, control, false)
    ]
}

# HIPAA compliance check
has_hipaa_compliance_controls(ticket) if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    hipaa_controls := object.get(compliance_controls, "hipaa", {})
    object.get(hipaa_controls, "access_controls", false)
    object.get(hipaa_controls, "encryption", false)
    object.get(hipaa_controls, "audit_controls", false)
    object.get(hipaa_controls, "baa_signed", false)
}

get_missing_hipaa_controls(ticket) := missing if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    hipaa_controls := object.get(compliance_controls, "hipaa", {})
    missing := [control |
        control := ["access_controls", "encryption", "audit_controls", "baa_signed"][_]
        not object.get(hipaa_controls, control, false)
    ]
}

# PCI-DSS compliance check
has_pci_dss_compliance_controls(ticket) if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    pci_controls := object.get(compliance_controls, "pci_dss", {})
    object.get(pci_controls, "encryption", false)
    object.get(pci_controls, "network_segmentation", false)
    object.get(pci_controls, "access_controls", false)
    object.get(pci_controls, "vulnerability_scanning", false)
}

get_missing_pci_dss_controls(ticket) := missing if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    pci_controls := object.get(compliance_controls, "pci_dss", {})
    missing := [control |
        control := ["encryption", "network_segmentation", "access_controls", "vulnerability_scanning"][_]
        not object.get(pci_controls, control, false)
    ]
}

# SOX compliance check
has_sox_compliance_controls(ticket) if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    sox_controls := object.get(compliance_controls, "sox", {})
    object.get(sox_controls, "change_management", false)
    object.get(sox_controls, "access_controls", false)
    object.get(sox_controls, "audit_trail", false)
    object.get(sox_controls, "segregation_of_duties", false)
}

get_missing_sox_controls(ticket) := missing if {
    compliance_controls := object.get(ticket, "compliance_controls", {})
    sox_controls := object.get(compliance_controls, "sox", {})
    missing := [control |
        control := ["change_management", "access_controls", "audit_trail", "segregation_of_duties"][_]
        not object.get(sox_controls, control, false)
    ]
}

# Max function helper
max(values) := result if {
    result := [v | v := values[_]; v >= values[_]][0]
}
