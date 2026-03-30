# Testes para ingress-tls.rego
# Epic H - H003: Testes de OPA Policies

package ingresstls

import future.keywords.contains
import future.keywords.if

test_ingress_tls_prod_missing {
  # Ingress em produção sem TLS deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Ingress"},
      "object": {
        "metadata": {
          "name": "api-ingress",
          "namespace": "production"
        },
        "spec": {}
      }
    },
    "parameters": {
      "require_in_prod": true,
      "excluded_namespaces": ["kube-system", "gatekeeper-system"]
    }
  }
}

test_ingress_tls_prod_with_tls {
  # Ingress em produção com TLS deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Ingress"},
      "object": {
        "metadata": {
          "name": "api-ingress",
          "namespace": "production"
        },
        "spec": {
          "tls": [{
            "hosts": ["api.example.com"],
            "secretName": "api-tls"
          }]
        }
      }
    },
    "parameters": {
      "require_in_prod": true,
      "excluded_namespaces": ["kube-system", "gatekeeper-system"]
    }
  }
}

test_ingress_tls_staging_no_tls {
  # Ingress em staging pode não ter TLS
  not violation with input as {
    "review": {
      "kind": {"kind": "Ingress"},
      "object": {
        "metadata": {
          "name": "api-ingress",
          "namespace": "staging"
        },
        "spec": {}
      }
    },
    "parameters": {
      "require_in_prod": true,
      "excluded_namespaces": ["kube-system", "gatekeeper-system"]
    }
  }
}

test_ingress_tls_excluded_namespace {
  # Namespace excluído não requer TLS
  not violation with input as {
    "review": {
      "kind": {"kind": "Ingress"},
      "object": {
        "metadata": {
          "name": "system-ingress",
          "namespace": "kube-system"
        },
        "spec": {}
      }
    },
    "parameters": {
      "require_in_prod": true,
      "excluded_namespaces": ["kube-system", "gatekeeper-system"]
    }
  }
}
