# Testes para secret-encryption.rego
# Epic H - H003: Testes de OPA Policies

package secretencryption

import future.keywords.contains

test_secret_encryption_prod_opaque_missing {
  # Secret Opaque em produção sem criptografia deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Secret"},
      "object": {
        "metadata": {
          "name": "api-secret",
          "namespace": "production"
        },
        "type": "Opaque",
        "data": {"password": "cGFzc3dvcmQxMjM="}
      }
    }
  }
}

test_secret_encryption_prod_with_annotation {
  # Secret em produção com annotation deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Secret"},
      "object": {
        "metadata": {
          "name": "api-secret",
          "namespace": "production",
          "annotations": {"neural-hive.io/encrypted": "true"}
        },
        "type": "Opaque",
        "data": {"password": "cGFzc3dvcmQxMjM="}
      }
    }
  }
}

test_secret_encryption_prod_external_secret {
  # ExternalSecret em produção deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Secret"},
      "object": {
        "metadata": {
          "name": "external-secret",
          "namespace": "production"
        },
        "type": "external-secret-operator.io/external-secret"
      }
    }
  }
}

test_secret_encryption_staging {
  # Secret em staging não requer criptografia
  not violation with input as {
    "review": {
      "kind": {"kind": "Secret"},
      "object": {
        "metadata": {
          "name": "api-secret",
          "namespace": "staging"
        },
        "type": "Opaque",
        "data": {"password": "cGFzc3dvcmQxMjM="}
      }
    }
  }
}

test_secret_encryption_docker_registry {
  # Secret docker-registry pode não ter annotation (uso específico)
  not violation with input as {
    "review": {
      "kind": {"kind": "Secret"},
      "object": {
        "metadata": {
          "name": "registry-secret",
          "namespace": "production"
        },
        "type": "kubernetes.io/dockerconfigjson",
        "data": {".dockerconfigjson": "eyJhdXRocyI6eyJ..."}
      }
    }
  }
}
