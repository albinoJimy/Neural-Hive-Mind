# Testes para pod-security-policy.rego
# Epic H - H003: Testes de OPA Policies

package podsecuritypolicy

import future.keywords.contains
import future.keywords.if

test_pod_security_privileged_container {
  # Container privilegiado deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {"privileged": true}
          }]
        }
      }
    },
    "parameters": {
      "allowPrivileged": false
    }
  }
}

test_pod_security_non_privileged {
  # Container não privilegiado deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {"privileged": false}
          }]
        }
      }
    },
    "parameters": {
      "allowPrivileged": false
    }
  }
}

test_pod_security_host_network {
  # Pod com hostNetwork deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "hostNetwork": true,
          "containers": [{"name": "main"}]
        }
      }
    },
    "parameters": {
      "allowHostNetwork": false
    }
  }
}

test_pod_security_host_pid {
  # Pod com hostPID deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "hostPID": true,
          "containers": [{"name": "main"}]
        }
      }
    },
    "parameters": {
      "allowHostPID": false
    }
  }
}

test_pod_security_host_ipc {
  # Pod com hostIPC deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "hostIPC": true,
          "containers": [{"name": "main"}]
        }
      }
    },
    "parameters": {
      "allowHostIPC": false
    }
  }
}

test_pod_security_root_user {
  # Container como root deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {"runAsUser": 0}
          }]
        }
      }
    },
    "parameters": {}
  }
}

test_pod_security_non_root_user {
  # Container como não-root deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "securityContext": {
              "runAsUser": 1000,
              "runAsNonRoot": true
            }
          }]
        }
      }
    },
    "parameters": {}
  }
}
