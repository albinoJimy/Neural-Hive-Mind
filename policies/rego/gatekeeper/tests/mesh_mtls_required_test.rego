# Testes para mesh-mtls-required.rego
# Epic H - H003: Testes de OPA Policies

package meshmtlsrequired

import future.keywords.contains
import future.keywords.if

test_mesh_mtls_required_deployment_excluded {
  # Deployment em namespace excluído deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "test-deployment",
          "namespace": "kube-system"
        }
      }
    }
  }
}

test_mesh_mtls_required_deployment_neural_hive {
  # Deployment em namespace neural-hive deve passar (assumido mTLS configurado)
  not violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "service-deployment",
          "namespace": "neural-hive-services"
        }
      }
    }
  }
}

test_mesh_mtls_required_deployment_violation {
  # Deployment em namespace não configurado deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "app-deployment",
          "namespace": "default"
        }
      }
    }
  }
}

test_mesh_mtls_required_statefulset_violation {
  # StatefulSet em namespace não configurado deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "StatefulSet"},
      "object": {
        "metadata": {
          "name": "db-statefulset",
          "namespace": "applications"
        }
      }
    }
  }
}
