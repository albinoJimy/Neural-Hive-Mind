# Guard Agents Security Policies Tests
# Unit tests for security_policies.rego
# Part of Neural Hive Mind - Guard Agents Service

package neuralhive.guard.security_policies_test

import data.neuralhive.guard.security_policies
import future.keywords.in

# =============================================================================
# TEST: Valid Secure Container (No Violations)
# =============================================================================

test_valid_secure_container {
    input := {
        "ticket": {
            "ticket_id": "test-secure-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "secure-app",
                    "privileged": false,
                    "host_network": false,
                    "host_pid": false,
                    "host_ipc": false,
                    "security_context": {
                        "runAsNonRoot": true,
                        "runAsUser": 1000,
                        "readOnlyRootFilesystem": true
                    },
                    "capabilities": {
                        "drop": ["ALL"],
                        "add": ["NET_BIND_SERVICE"]
                    },
                    "env": []
                },
                "network_policy": {
                    "ingress": [{"from": [{"podSelector": {"matchLabels": {"app": "frontend"}}}]}],
                    "egress": [{"to": [{"podSelector": {"matchLabels": {"app": "database"}}}]}],
                    "protocols": ["HTTPS"]
                },
                "image": {
                    "name": "myregistry.io/secure-app",
                    "tag": "v1.2.3",
                    "signed": true,
                    "scanned": true,
                    "scan_results": {
                        "critical": 0,
                        "high": 0,
                        "medium": 2,
                        "low": 5
                    }
                },
                "vault_integration": true
            }
        },
        "security": {
            "allowed_capabilities": ["NET_BIND_SERVICE"],
            "require_signed_images": true,
            "require_network_policies": true,
            "max_vulnerability_severity": "HIGH"
        }
    }

    result := security_policies.result with input as input
    result.allow == true
    count(result.violations) == 0
}

# =============================================================================
# TEST: Privileged Container Violation
# =============================================================================

test_privileged_container_violation {
    input := {
        "ticket": {
            "ticket_id": "test-privileged-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "privileged-app",
                    "privileged": true
                }
            }
        },
        "security": {
            "allowed_capabilities": []
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find the privileged container violation
    violation := [v | v := result.violations[_]; v.rule == "privileged_container"][0]
    violation.severity == "CRITICAL"
    violation.message == "Container is configured to run in privileged mode"
}

# =============================================================================
# TEST: Root User Violation
# =============================================================================

test_root_user_violation {
    input := {
        "ticket": {
            "ticket_id": "test-root-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "root-app",
                    "privileged": false,
                    "security_context": {
                        "runAsUser": 0
                    }
                }
            }
        },
        "security": {
            "allowed_capabilities": []
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find the root user violation
    violation := [v | v := result.violations[_]; v.rule == "root_user"][0]
    violation.severity == "HIGH"
}

# =============================================================================
# TEST: Dangerous Capabilities Violation
# =============================================================================

test_dangerous_capabilities_violation {
    input := {
        "ticket": {
            "ticket_id": "test-caps-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "dangerous-caps-app",
                    "privileged": false,
                    "capabilities": {
                        "add": ["SYS_ADMIN", "NET_ADMIN"]
                    }
                }
            }
        },
        "security": {
            "allowed_capabilities": []
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find dangerous capabilities violations
    cap_violations := [v | v := result.violations[_]; v.rule == "dangerous_capabilities"]
    count(cap_violations) >= 1
    cap_violations[0].severity == "CRITICAL"
}

# =============================================================================
# TEST: Unsigned Image Violation
# =============================================================================

test_unsigned_image_violation {
    input := {
        "ticket": {
            "ticket_id": "test-unsigned-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "unsigned-app",
                    "privileged": false
                },
                "image": {
                    "name": "myregistry.io/unsigned-app",
                    "tag": "v1.0.0",
                    "signed": false,
                    "scanned": true
                }
            }
        },
        "security": {
            "allowed_capabilities": [],
            "require_signed_images": true
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find unsigned image violation
    violation := [v | v := result.violations[_]; v.rule == "unsigned_image"][0]
    violation.severity == "HIGH"
}

# =============================================================================
# TEST: Hardcoded Secret Violation
# =============================================================================

test_hardcoded_secret_violation {
    input := {
        "ticket": {
            "ticket_id": "test-secret-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "secret-app",
                    "privileged": false
                },
                "secrets": {
                    "database_password": "my-hardcoded-secret-123",
                    "api_key": "sk-12345abcdef"
                }
            }
        },
        "security": {
            "allowed_capabilities": []
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find hardcoded secret violations
    secret_violations := [v | v := result.violations[_]; v.rule == "hardcoded_secret"]
    count(secret_violations) >= 1
    secret_violations[0].severity == "CRITICAL"
}

# =============================================================================
# TEST: Insecure Protocol Violation
# =============================================================================

test_insecure_protocol_violation {
    input := {
        "ticket": {
            "ticket_id": "test-protocol-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "insecure-protocol-app",
                    "privileged": false
                },
                "network_policy": {
                    "protocols": ["HTTP", "FTP"]
                }
            }
        },
        "security": {
            "allowed_capabilities": []
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find insecure protocol violations
    protocol_violations := [v | v := result.violations[_]; v.rule == "insecure_protocol"]
    count(protocol_violations) >= 1
    protocol_violations[0].severity == "HIGH"
}

# =============================================================================
# TEST: Multiple Violations
# =============================================================================

test_multiple_violations {
    input := {
        "ticket": {
            "ticket_id": "test-multi-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "insecure-app",
                    "privileged": true,
                    "host_network": true,
                    "security_context": {
                        "runAsUser": 0
                    },
                    "capabilities": {
                        "add": ["SYS_ADMIN"]
                    },
                    "env": [
                        {"name": "DB_PASSWORD", "value": "secret123"}
                    ]
                },
                "network_policy": {},
                "image": {
                    "name": "myregistry.io/insecure-app",
                    "tag": "latest",
                    "signed": false,
                    "scanned": false
                },
                "secrets": {
                    "api_token": "hardcoded-token-value"
                }
            }
        },
        "security": {
            "allowed_capabilities": [],
            "require_signed_images": true,
            "require_network_policies": true
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Should have multiple violations
    count(result.violations) >= 5

    # Verify critical violations exist
    result.security_context.critical_count > 0
}

# =============================================================================
# TEST: Host Network Violation
# =============================================================================

test_host_network_violation {
    input := {
        "ticket": {
            "ticket_id": "test-hostnet-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "hostnet-app",
                    "privileged": false,
                    "host_network": true
                }
            }
        },
        "security": {
            "allowed_capabilities": []
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find host network violation
    violation := [v | v := result.violations[_]; v.rule == "host_network"][0]
    violation.severity == "CRITICAL"
}

# =============================================================================
# TEST: Latest Tag Violation in Production
# =============================================================================

test_latest_tag_violation {
    input := {
        "ticket": {
            "ticket_id": "test-latest-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "latest-tag-app",
                    "privileged": false
                },
                "image": {
                    "name": "myregistry.io/app",
                    "tag": "latest",
                    "signed": true,
                    "scanned": true,
                    "scan_results": {
                        "critical": 0,
                        "high": 0
                    }
                }
            }
        },
        "security": {
            "allowed_capabilities": [],
            "require_signed_images": true
        }
    }

    result := security_policies.result with input as input

    # Find latest tag violation
    violation := [v | v := result.violations[_]; v.rule == "latest_tag"][0]
    violation.severity == "MEDIUM"
}

# =============================================================================
# TEST: Missing Network Policy in Production
# =============================================================================

test_missing_network_policy_violation {
    input := {
        "ticket": {
            "ticket_id": "test-netpol-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "no-netpol-app",
                    "privileged": false
                }
            }
        },
        "security": {
            "allowed_capabilities": [],
            "require_network_policies": true
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find missing network policy violation
    violation := [v | v := result.violations[_]; v.rule == "missing_network_policy"][0]
    violation.severity == "HIGH"
}

# =============================================================================
# TEST: High Severity Vulnerabilities
# =============================================================================

test_high_severity_vulnerabilities_violation {
    input := {
        "ticket": {
            "ticket_id": "test-vuln-001",
            "task_type": "DEPLOY",
            "environment": "production",
            "parameters": {
                "container_spec": {
                    "name": "vulnerable-app",
                    "privileged": false
                },
                "image": {
                    "name": "myregistry.io/vulnerable-app",
                    "tag": "v1.0.0",
                    "signed": true,
                    "scanned": true,
                    "scan_results": {
                        "critical": 2,
                        "high": 5,
                        "medium": 10,
                        "low": 20
                    }
                }
            }
        },
        "security": {
            "allowed_capabilities": [],
            "require_signed_images": true,
            "max_vulnerability_severity": "HIGH"
        }
    }

    result := security_policies.result with input as input
    result.allow == false

    # Find high severity vulnerabilities violation
    violation := [v | v := result.violations[_]; v.rule == "high_severity_vulnerabilities"][0]
    violation.severity == "HIGH"
}

# =============================================================================
# TEST: Security Context Summary
# =============================================================================

test_security_context_summary {
    input := {
        "ticket": {
            "ticket_id": "test-context-001",
            "task_type": "DEPLOY",
            "environment": "staging",
            "parameters": {
                "container_spec": {
                    "name": "test-app",
                    "privileged": true
                }
            }
        },
        "security": {
            "allowed_capabilities": []
        }
    }

    result := security_policies.result with input as input

    # Verify security context is populated
    result.security_context.ticket_id == "test-context-001"
    result.security_context.environment == "staging"
    result.security_context.task_type == "DEPLOY"
    result.security_context.violation_count > 0
    result.security_context.risk_score > 0
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
            "parameters": {
                "container_spec": {
                    "name": "dev-app",
                    "privileged": false
                },
                "image": {
                    "name": "myregistry.io/dev-app",
                    "tag": "latest",
                    "signed": true,
                    "scanned": true,
                    "scan_results": {
                        "critical": 0,
                        "high": 0
                    }
                }
            }
        },
        "security": {
            "allowed_capabilities": [],
            "require_signed_images": true,
            "require_network_policies": true
        }
    }

    result := security_policies.result with input as input

    # In development, latest tag should not cause violation
    latest_violations := [v | v := result.violations[_]; v.rule == "latest_tag"]
    count(latest_violations) == 0
}
