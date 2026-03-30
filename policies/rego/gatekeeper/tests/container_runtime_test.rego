# Testes para container-runtime.rego
# Epic H - H003: Testes de OPA Policies

package containerruntime

import future.keywords.contains
import future.keywords.if

test_container_runtime_dangerous_capability {
  # Container com capability perigosa deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {
              "capabilities": {
                "add": ["NET_ADMIN", "SYS_ADMIN"]
              }
            }
          }]
        }
      }
    },
    "parameters": {
      "allow_capabilities_add": ["NET_BIND_SERVICE"],
      "require_read_only_root": false,
      "require_drop_all": false
    }
  }
}

test_container_runtime_allowed_capability {
  # Container com capability permitida deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {
              "capabilities": {
                "add": ["NET_BIND_SERVICE"]
              }
            }
          }]
        }
      }
    },
    "parameters": {
      "allow_capabilities_add": ["NET_BIND_SERVICE"],
      "require_read_only_root": false,
      "require_drop_all": false
    }
  }
}

test_container_runtime_read_only_root_required {
  # Container sem root read-only deve violar (se requerido)
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {}
          }]
        }
      }
    },
    "parameters": {
      "allow_capabilities_add": [],
      "require_read_only_root": true,
      "require_drop_all": false
    }
  }
}

test_container_runtime_read_only_root_set {
  # Container com root read-only deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {
              "readOnlyRootFilesystem": true
            }
          }]
        }
      }
    },
    "parameters": {
      "allow_capabilities_add": [],
      "require_read_only_root": true,
      "require_drop_all": false
    }
  }
}

test_container_runtime_drop_all_required {
  # Container sem drop ALL deve violar (se requerido)
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {
              "capabilities": {
                "drop": ["NET_RAW"]
              }
            }
          }]
        }
      }
    },
    "parameters": {
      "allow_capabilities_add": [],
      "require_read_only_root": false,
      "require_drop_all": true
    }
  }
}

test_container_runtime_drop_all_set {
  # Container com drop ALL deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {
              "capabilities": {
                "drop": ["ALL"]
              }
            }
          }]
        }
      }
    },
    "parameters": {
      "allow_capabilities_add": [],
      "require_read_only_root": false,
      "require_drop_all": true
    }
  }
}
