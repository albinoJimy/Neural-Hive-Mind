# Testes para redis-security-required.rego
# Epic H - H003: Testes de OPA Policies

package redissecurityrequired

import future.keywords.contains

test_redis_security_auth_required {
  # Service Redis porta 6379 sem annotation auth deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "redis-service",
          "namespace": "redis-cluster"
        },
        "spec": {
          "ports": [{"port": 6379}]
        }
      }
    }
  }
}

test_redis_security_with_auth_annotation {
  # Service Redis com annotation auth deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "redis-service",
          "namespace": "redis-cluster",
          "annotations": {"redis.security/auth": "required"}
        },
        "spec": {
          "ports": [{"port": 6379}]
        }
      }
    }
  }
}

test_redis_security_prod_tls_required {
  # Service Redis em produção sem TLS deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "redis-prod",
          "namespace": "production",
          "labels": {"neural-hive.io/environment": "prod"},
          "annotations": {"redis.security/auth": "required"}
        },
        "spec": {
          "ports": [{"port": 6379}]
        }
      }
    }
  }
}

test_redis_security_prod_with_tls {
  # Service Redis em produção com TLS deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "redis-prod",
          "namespace": "production",
          "labels": {"neural-hive.io/environment": "prod"},
          "annotations": {
            "redis.security/auth": "required",
            "redis.security/tls": "required"
          }
        },
        "spec": {
          "ports": [{"port": 6379}]
        }
      }
    }
  }
}

test_redis_security_non_redis_service {
  # Service não-Redis não deve violar
  not violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "web-service",
          "namespace": "production"
        },
        "spec": {
          "ports": [{"port": 8080}]
        }
      }
    }
  }
}
