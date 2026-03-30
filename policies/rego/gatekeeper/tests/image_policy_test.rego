# Testes para image-policy.rego
# Epic H - H003: Testes de OPA Policies

package imagepolicy

import future.keywords.contains
import future.keywords.if

test_image_policy_unauthorized_registry {
  # Imagem de registry não autorizado deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "image": "unauthorized registry/image:tag"
          }]
        }
      }
    },
    "parameters": {
      "allowed_registries": ["ghcr.io/albinojimy/", "docker.io/neuralhive/"]
    }
  }
}

test_image_policy_authorized_registry {
  # Imagem de registry autorizado deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "image": "ghcr.io/albinojimy/service:v1.0.0"
          }]
        }
      }
    },
    "parameters": {
      "allowed_registries": ["ghcr.io/albinojimy/", "docker.io/neuralhive/"]
    }
  }
}

test_image_policy_latest_tag {
  # Tag :latest não permitida deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "image": "ghcr.io/albinojimy/service:latest"
          }]
        }
      }
    },
    "parameters": {
      "allowed_registries": ["ghcr.io/albinojimy/"],
      "allow_latest_tag": false
    }
  }
}

test_image_policy_no_tag {
  # Imagem sem tag não permitida deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "image": "ghcr.io/albinojimy/service"
          }]
        }
      }
    },
    "parameters": {
      "allowed_registries": ["ghcr.io/albinojimy/"],
      "allow_latest_tag": false
    }
  }
}

test_image_policy_specific_tag {
  # Tag específica deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "image": "ghcr.io/albinojimy/service:v1.2.3"
          }]
        }
      }
    },
    "parameters": {
      "allowed_registries": ["ghcr.io/albinojimy/"],
      "allow_latest_tag": false
    }
  }
}

test_image_policy_unsigned_required {
  # Imagem não assinada com require_signature=true deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "image": "ghcr.io/albinojimy/service:v1.0.0"
          }]
        }
      }
    },
    "parameters": {
      "allowed_registries": ["ghcr.io/albinojimy/"],
      "require_signature": true
    }
  }
}

test_image_policy_signed_image {
  # Imagem assinada (com digest SHA256) deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Pod"},
      "object": {
        "metadata": {"name": "test-pod"},
        "spec": {
          "containers": [{
            "name": "main",
            "image": "ghcr.io/albinojimy/service@sha256:abc123..."
          }]
        }
      }
    },
    "parameters": {
      "allowed_registries": ["ghcr.io/albinojimy/"],
      "require_signature": true
    }
  }
}
