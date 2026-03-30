# Testes para audit-logging.rego
# Epic H - H003: Testes de OPA Policies

package auditlogging

import future.keywords.contains
import future.keywords.if

test_audit_logging_prod_missing {
  # Deployment em produção sem annotation de audit deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "api-deployment",
          "namespace": "production"
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{"name": "api"}]
            }
          }
        }
      }
    },
    "parameters": {
      "require_for_namespaces": ["production", "prod"]
    }
  }
}

test_audit_logging_prod_with_annotation {
  # Deployment em produção com annotation deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "api-deployment",
          "namespace": "production",
          "annotations": {"neural-hive.io/audit-log": "enabled"}
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{"name": "api"}]
            }
          }
        }
      }
    },
    "parameters": {
      "require_for_namespaces": ["production", "prod"]
    }
  }
}

test_audit_logging_staging {
  # Deployment em staging pode não ter audit logging
  not violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "api-deployment",
          "namespace": "staging"
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{"name": "api"}]
            }
          }
        }
      }
    },
    "parameters": {
      "require_for_namespaces": ["production", "prod"]
    }
  }
}

test_audit_logging_statefulset_prod {
  # StatefulSet em produção também requer audit logging
  violation with input as {
    "review": {
      "kind": {"kind": "StatefulSet"},
      "object": {
        "metadata": {
          "name": "db-statefulset",
          "namespace": "prod"
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{"name": "db"}]
            }
          }
        }
      }
    },
    "parameters": {
      "require_for_namespaces": ["production", "prod"]
    }
  }
}

test_audit_logging_daemonset_prod {
  # DaemonSet em produção também requer audit logging
  violation with input as {
    "review": {
      "kind": {"kind": "DaemonSet"},
      "object": {
        "metadata": {
          "name": "monitor-daemonset",
          "namespace": "production"
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{"name": "monitor"}]
            }
          }
        }
      }
    },
    "parameters": {
      "require_for_namespaces": ["production", "prod"]
    }
  }
}

test_audit_logging_dev_no_requirement {
  # Namespaces não listados não requerem audit logging
  not violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "api-deployment",
          "namespace": "development"
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{"name": "api"}]
            }
          }
        }
      }
    },
    "parameters": {
      "require_for_namespaces": ["production", "prod"]
    }
  }
}
