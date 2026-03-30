# Testes para resource-limits.rego
# Epic H - H003: Testes de OPA Policies

package resourcelimits

import future.keywords.contains
import future.keywords.if

test_resource_limits_missing_cpu_limits {
  # Container sem CPU limits deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"memory": "512Mi"},
              "requests": {"cpu": "100m", "memory": "256Mi"}
            }
          }]
        }
      }
    }
  }
}

test_resource_limits_missing_memory_limits {
  # Container sem memory limits deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "500m"},
              "requests": {"cpu": "100m", "memory": "256Mi"}
            }
          }]
        }
      }
    }
  }
}

test_resource_limits_missing_cpu_requests {
  # Container sem CPU requests deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "500m", "memory": "512Mi"},
              "requests": {"memory": "256Mi"}
            }
          }]
        }
      }
    }
  }
}

test_resource_limits_missing_memory_requests {
  # Container sem memory requests deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "500m", "memory": "512Mi"},
              "requests": {"cpu": "100m"}
            }
          }]
        }
      }
    }
  }
}

test_resource_limits_complete {
  # Container com todos os recursos deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "500m", "memory": "512Mi"},
              "requests": {"cpu": "100m", "memory": "256Mi"}
            }
          }]
        }
      }
    }
  }
}

test_resource_limits_init_container {
  # InitContainer também deve ter recursos
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "initContainers": [{
            "name": "init",
            "resources": {
              "requests": {"cpu": "50m"}
            }
          }],
          "containers": [{
            "name": "main",
            "resources": {
              "limits": {"cpu": "500m", "memory": "512Mi"},
              "requests": {"cpu": "100m", "memory": "256Mi"}
            }
          }]
        }
      }
    }
  }
}
