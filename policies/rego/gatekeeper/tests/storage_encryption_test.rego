# Testes para storage-encryption.rego
# Epic H - H003: Testes de OPA Policies

package storageencryption

import future.keywords.contains

test_storage_encryption_prod_missing {
  # PVC em produção sem criptografia deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "PersistentVolumeClaim"},
      "object": {
        "metadata": {
          "name": "data-pvc",
          "namespace": "production"
        },
        "spec": {
          "accessModes": ["ReadWriteOnce"],
          "resources": {
            "requests": {"storage": "10Gi"}
          }
        }
      }
    }
  }
}

test_storage_encryption_prod_with_annotation {
  # PVC em produção com annotation de criptografia deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "PersistentVolumeClaim"},
      "object": {
        "metadata": {
          "name": "data-pvc",
          "namespace": "production",
          "annotations": {"pv.kubernetes.io/encryption": "true"}
        },
        "spec": {
          "accessModes": ["ReadWriteOnce"],
          "resources": {
            "requests": {"storage": "10Gi"}
          }
        }
      }
    }
  }
}

test_storage_encryption_staging {
  # PVC em staging não requer criptografia
  not violation with input as {
    "review": {
      "kind": {"kind": "PersistentVolumeClaim"},
      "object": {
        "metadata": {
          "name": "data-pvc",
          "namespace": "staging"
        },
        "spec": {
          "accessModes": ["ReadWriteOnce"],
          "resources": {
            "requests": {"storage": "10Gi"}
          }
        }
      }
    }
  }
}

test_storage_encryption_dev {
  # PVC em development não requer criptografia
  not violation with input as {
    "review": {
      "kind": {"kind": "PersistentVolumeClaim"},
      "object": {
        "metadata": {
          "name": "data-pvc",
          "namespace": "development"
        },
        "spec": {
          "accessModes": ["ReadWriteOnce"],
          "resources": {
            "requests": {"storage": "10Gi"}
          }
        }
      }
    }
  }
}
