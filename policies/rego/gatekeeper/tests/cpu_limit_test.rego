# Testes para cpu-limit.rego
# Epic H - H003: Testes de OPA Policies

package cpulimit

import future.keywords.contains

test_cpu_limit_exceeded {
  # Container que excede CPU limit deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "8", "memory": "8Gi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_cpu": "4"
    }
  }
}

test_cpu_limit_within_bounds {
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
      "max_cpu": "4"
    }
  }
}

test_cpu_limit_exactly_max {
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
              "limits": {"cpu": "4", "memory": "8Gi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_cpu": "4"
    }
  }
}

test_cpu_limit_millicores {
  # Valores em millicores devem funcionar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "5000m", "memory": "8Gi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_cpu": "4"
    }
  }
}

test_cpu_limit_millicores_within_bounds {
  # Millicores dentro do limite devem passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "3000m", "memory": "4Gi"}
            }
          }]
        }
      }
    },
    "parameters": {
      "max_cpu": "4"
    }
  }
}
