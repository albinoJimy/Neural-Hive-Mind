# Testes para memory-limit.rego
# Epic H - H003: Testes de OPA Policies

package memorylimit

import future.keywords.contains

test_memory_limit_exceeded_gib {
  # Container que excede memory limit em Gi deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "2", "memory": "16Gi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_memory": "8Gi"
    }
  }
}

test_memory_limit_within_bounds {
  # Container dentro dos limites deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "2", "memory": "4Gi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_memory": "8Gi"
    }
  }
}

test_memory_limit_exactly_max {
  # Container no limite exato deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "2", "memory": "8Gi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_memory": "8Gi"
    }
  }
}

test_memory_limit_mib_exceeded {
  # Valores em Mi também devem ser verificados
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "2", "memory": "10240Mi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_memory": "8Gi"
    }
  }
}

test_memory_limit_mib_within_bounds {
  # Mi dentro do limite devem passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "2", "memory": "4096Mi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_memory": "8Gi"
    }
  }
}

test_memory_limit_mixed_units {
  # Mistura de containers com diferentes unidades
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [
            {
              "name": "main",
              "resources": {
                "limits": {"cpu": "2", "memory": "4Gi"}
              }
            },
            {
              "name": "sidecar",
              "resources": {
                "limits": {"cpu": "500m", "memory": "8Gi"}
              }
            }
          ]
        }
      }
    },
    "parameters": {
      "max_memory": "8Gi"
    }
  }
}
