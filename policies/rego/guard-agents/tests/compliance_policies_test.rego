# Guard Agents Compliance Policies Tests
# Unit tests for compliance_policies.rego
# Part of Neural Hive Mind - Guard Agents Service

package neuralhive.guard.compliance_policies_test

import data.neuralhive.guard.compliance_policies
import future.keywords.in

# =============================================================================
# TEST: Valid Compliant Ticket (No Violations)
# =============================================================================

test_valid_compliant_ticket {
    input := {
        "ticket": {
            "ticket_id": "test-compliant-001",
            "task_type": "DEPLOY",
            "contains_pii": true,
            "data_classification": "CONFIDENTIAL",
            "data_residency_region": "eu-west-1",
            "target_region": "eu-west-1",
            "data_config": {
                "persists_data": true,
                "encryption_at_rest": true
            },
            "retention_policy": {
                "retention_days": 90,
                "auto_delete": true
            },
            "audit_config": {
                "enabled": true,
                "retention_days": 730,
                "include_user_identity": true
            },
            "compliance_controls": {
                "gdpr": {
                    "consent_management": true,
                    "data_subject_rights": true,
                    "lawful_basis_documented": true
                }
            }
        },
        "compliance": {
            "required_regulations": ["GDPR"],
            "max_retention_days": 365,
            "max_pii_retention_days": 180,
            "require_encryption_at_rest": true,
            "require_audit_logging": true,
            "min_audit_retention_days": 365
        }
    }

    result := compliance_policies.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# =============================================================================
# TEST: PII Without Encryption Violation
# =============================================================================

test_pii_without_encryption_violation {
    input := {
        "ticket": {
            "ticket_id": "test-pii-encrypt-001",
            "task_type": "DEPLOY",
            "contains_pii": true,
            "data_classification": "CONFIDENTIAL",
            "data_config": {
                "persists_data": true,
                "encryption_at_rest": false
            }
        },
        "compliance": {
            "required_regulations": ["GDPR"],
            "require_encryption_at_rest": true
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find PII without encryption violation
    violation := [v | v := result.violations[_]; v.rule == "pii_without_encryption"][0]
    violation.severity == "CRITICAL"
    contains(violation.message, "PII data detected without encryption")
}

# =============================================================================
# TEST: PII Cross-Region Violation
# =============================================================================

test_pii_cross_region_violation {
    input := {
        "ticket": {
            "ticket_id": "test-pii-region-001",
            "task_type": "DEPLOY",
            "contains_pii": true,
            "data_classification": "CONFIDENTIAL",
            "data_residency_region": "eu-west-1",
            "target_region": "us-east-1",
            "cross_region_transfer_approved": false,
            "data_config": {
                "encryption_at_rest": true
            }
        },
        "compliance": {
            "required_regulations": ["GDPR"],
            "require_encryption_at_rest": true
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find PII cross-region violation
    violation := [v | v := result.violations[_]; v.rule == "pii_cross_region"][0]
    violation.severity == "CRITICAL"
    violation.details.source_region == "eu-west-1"
    violation.details.target_region == "us-east-1"
}

# =============================================================================
# TEST: Missing Audit Logging Violation
# =============================================================================

test_missing_audit_logging_violation {
    input := {
        "ticket": {
            "ticket_id": "test-audit-001",
            "task_type": "DEPLOY",
            "contains_pii": false,
            "data_classification": "INTERNAL",
            "audit_config": {
                "enabled": false
            }
        },
        "compliance": {
            "required_regulations": [],
            "require_audit_logging": true
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find missing audit logging violation
    violation := [v | v := result.violations[_]; v.rule == "missing_audit_logging"][0]
    violation.severity == "HIGH"
    contains(violation.message, "Audit logging not enabled")
}

# =============================================================================
# TEST: GDPR Violation
# =============================================================================

test_gdpr_violation {
    input := {
        "ticket": {
            "ticket_id": "test-gdpr-001",
            "task_type": "DEPLOY",
            "contains_pii": true,
            "data_classification": "CONFIDENTIAL",
            "data_config": {
                "encryption_at_rest": true
            },
            "compliance_controls": {
                "gdpr": {
                    "consent_management": false,
                    "data_subject_rights": false,
                    "lawful_basis_documented": false
                }
            }
        },
        "compliance": {
            "required_regulations": ["GDPR"],
            "require_encryption_at_rest": true
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find GDPR violation
    violation := [v | v := result.violations[_]; v.rule == "gdpr_violation"][0]
    violation.severity == "CRITICAL"
    violation.details.regulation == "GDPR"
    count(violation.details.missing_controls) > 0
}

# =============================================================================
# TEST: Excessive Retention Period Violation
# =============================================================================

test_excessive_retention_period_violation {
    input := {
        "ticket": {
            "ticket_id": "test-retention-001",
            "task_type": "DEPLOY",
            "contains_pii": false,
            "data_classification": "INTERNAL",
            "data_config": {
                "persists_data": true
            },
            "retention_policy": {
                "retention_days": 3650,
                "auto_delete": true
            }
        },
        "compliance": {
            "required_regulations": [],
            "max_retention_days": 2555
        }
    }

    result := compliance_policies.result with input as input

    # Find excessive retention violation
    violation := [v | v := result.violations[_]; v.rule == "excessive_retention_period"][0]
    violation.severity == "MEDIUM"
    violation.details.retention_days == 3650
    violation.details.max_allowed_days == 2555
}

# =============================================================================
# TEST: HIPAA Violation
# =============================================================================

test_hipaa_violation {
    input := {
        "ticket": {
            "ticket_id": "test-hipaa-001",
            "task_type": "DEPLOY",
            "contains_pii": false,
            "data_classification": "RESTRICTED",
            "compliance_controls": {
                "hipaa": {
                    "access_controls": false,
                    "encryption": false,
                    "audit_controls": false,
                    "baa_signed": false
                }
            }
        },
        "compliance": {
            "required_regulations": ["HIPAA"]
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find HIPAA violation
    violation := [v | v := result.violations[_]; v.rule == "hipaa_violation"][0]
    violation.severity == "CRITICAL"
    violation.details.regulation == "HIPAA"
}

# =============================================================================
# TEST: PCI-DSS Violation
# =============================================================================

test_pci_dss_violation {
    input := {
        "ticket": {
            "ticket_id": "test-pci-001",
            "task_type": "DEPLOY",
            "handles_payment_data": true,
            "data_types": ["payment", "credit_card"],
            "compliance_controls": {
                "pci_dss": {
                    "encryption": false,
                    "network_segmentation": false,
                    "access_controls": false,
                    "vulnerability_scanning": false
                }
            }
        },
        "compliance": {
            "required_regulations": ["PCI-DSS"]
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find PCI-DSS violation
    violation := [v | v := result.violations[_]; v.rule == "pci_dss_violation"][0]
    violation.severity == "CRITICAL"
    violation.details.regulation == "PCI-DSS"
}

# =============================================================================
# TEST: SOX Violation
# =============================================================================

test_sox_violation {
    input := {
        "ticket": {
            "ticket_id": "test-sox-001",
            "task_type": "DEPLOY",
            "is_financial_system": true,
            "system_type": "financial",
            "compliance_controls": {
                "sox": {
                    "change_management": false,
                    "access_controls": false,
                    "audit_trail": false,
                    "segregation_of_duties": false
                }
            }
        },
        "compliance": {
            "required_regulations": ["SOX"]
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find SOX violation
    violation := [v | v := result.violations[_]; v.rule == "sox_violation"][0]
    violation.severity == "HIGH"
    violation.details.regulation == "SOX"
}

# =============================================================================
# TEST: PII Without Classification Violation
# =============================================================================

test_pii_without_classification_violation {
    input := {
        "ticket": {
            "ticket_id": "test-pii-class-001",
            "task_type": "DEPLOY",
            "contains_pii": true,
            "data_classification": "PUBLIC",
            "data_config": {
                "encryption_at_rest": true
            }
        },
        "compliance": {
            "required_regulations": [],
            "require_encryption_at_rest": true
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Find PII without classification violation
    violation := [v | v := result.violations[_]; v.rule == "pii_without_classification"][0]
    violation.severity == "HIGH"
    violation.details.current_classification == "PUBLIC"
}

# =============================================================================
# TEST: Insufficient Audit Retention Violation
# =============================================================================

test_insufficient_audit_retention_violation {
    input := {
        "ticket": {
            "ticket_id": "test-audit-ret-001",
            "task_type": "DEPLOY",
            "audit_config": {
                "enabled": true,
                "retention_days": 30,
                "include_user_identity": true
            }
        },
        "compliance": {
            "required_regulations": [],
            "require_audit_logging": true,
            "min_audit_retention_days": 365
        }
    }

    result := compliance_policies.result with input as input

    # Find insufficient audit retention violation
    violation := [v | v := result.violations[_]; v.rule == "insufficient_audit_retention"][0]
    violation.severity == "MEDIUM"
    violation.details.audit_retention_days == 30
    violation.details.min_required_days == 365
}

# =============================================================================
# TEST: Missing Retention Policy Violation
# =============================================================================

test_missing_retention_policy_violation {
    input := {
        "ticket": {
            "ticket_id": "test-ret-policy-001",
            "task_type": "DEPLOY",
            "data_config": {
                "persists_data": true
            }
        },
        "compliance": {
            "required_regulations": []
        }
    }

    result := compliance_policies.result with input as input

    # Find missing retention policy violation
    violation := [v | v := result.violations[_]; v.rule == "missing_retention_policy"][0]
    violation.severity == "MEDIUM"
}

# =============================================================================
# TEST: Compliance Context Summary
# =============================================================================

test_compliance_context_summary {
    input := {
        "ticket": {
            "ticket_id": "test-context-001",
            "task_type": "DEPLOY",
            "contains_pii": true,
            "data_classification": "CONFIDENTIAL",
            "data_config": {
                "encryption_at_rest": false
            }
        },
        "compliance": {
            "required_regulations": ["GDPR"],
            "require_encryption_at_rest": true
        }
    }

    result := compliance_policies.result with input as input

    # Verify compliance context is populated
    result.compliance_context.ticket_id == "test-context-001"
    result.compliance_context.contains_pii == true
    result.compliance_context.data_classification == "CONFIDENTIAL"
    result.compliance_context.violation_count > 0
    result.compliance_context.compliance_score < 100
}

# =============================================================================
# TEST: Multiple Regulatory Violations
# =============================================================================

test_multiple_regulatory_violations {
    input := {
        "ticket": {
            "ticket_id": "test-multi-reg-001",
            "task_type": "DEPLOY",
            "contains_pii": true,
            "handles_payment_data": true,
            "is_financial_system": true,
            "data_classification": "RESTRICTED",
            "data_config": {
                "encryption_at_rest": false
            },
            "compliance_controls": {}
        },
        "compliance": {
            "required_regulations": ["GDPR", "HIPAA", "PCI-DSS", "SOX"],
            "require_encryption_at_rest": true
        }
    }

    result := compliance_policies.result with input as input
    result.allow == false

    # Should have multiple regulatory violations
    count(result.violations) >= 4
    result.compliance_context.critical_count >= 2
}
