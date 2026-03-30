# Testes para network-policy.rego
# Epic H - H003: Testes de OPA Policies

package networkpolicy

import future.keywords.contains
import future.keywords.if

test_network_policy_prod_deployment_violation {
  # Deployment em namespace prod deve ter NetworkPolicy
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
      "require_for_namespaces": ["production", "prod", "staging"],
      "excluded_workloads": []
    }
  }
}

test_network_policy_staging_statefulset_violation {
  # StatefulSet em staging deve ter NetworkPolicy
  violation with input as {
    "review": {
      "kind": {"kind": "StatefulSet"},
      "object": {
        "metadata": {
          "name": "db-statefulset",
          "namespace": "staging"
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
      "require_for_namespaces": ["production", "prod", "staging"],
      "excluded_workloads": []
    }
  }
}

test_network_policy_development {
  # Deployment em development não requer NetworkPolicy
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
      "require_for_namespaces": ["production", "prod", "staging"],
      "excluded_workloads": []
    }
  }
}

test_network_policy_excluded_workload {
  # Workloads excluídos não requerem NetworkPolicy
  not violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "vault",
          "namespace": "production"
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{"name": "vault"}]
            }
          }
        }
      }
    },
    "parameters": {
      "require_for_namespaces": ["production", "prod", "staging"],
      "excluded_workloads": ["vault", "vault-injector"]
    }
  }
}
