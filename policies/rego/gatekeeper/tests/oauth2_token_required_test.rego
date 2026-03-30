# Testes para oauth2-token-required.rego
# Epic H - H003: Testes de OPA Policies
#
# Execute com: opa test policies/rego/gatekeeper/tests/ -v

package oauth2tokenrequired

import future.keywords.contains
import future.keywords.if

test_oauth2_token_required_service_critical {
  # Service crítico sem annotation deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "gateway-intencoes",
          "namespace": "production"
        }
      }
    },
    "parameters": {
      "oauth2_required_services": ["gateway-intencoes", "neural-hive-api"]
    }
  }
}

test_oauth2_token_required_service_with_annotation {
  # Service com annotation deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "gateway-intencoes",
          "namespace": "production",
          "annotations": {"auth.neural-hive/required": "true"}
        }
      }
    },
    "parameters": {
      "oauth2_required_services": ["gateway-intencoes", "neural-hive-api"]
    }
  }
}

test_oauth2_token_required_non_critical_service {
  # Service não crítico não precisa de OAuth2
  not violation with input as {
    "review": {
      "kind": {"kind": "Service"},
      "object": {
        "metadata": {
          "name": "cache-service",
          "namespace": "production"
        }
      }
    },
    "parameters": {
      "oauth2_required_services": ["gateway-intencoes", "neural-hive-api"]
    }
  }
}

test_oauth2_token_required_deployment_env_check {
  # Deployment sem variáveis OAuth2 deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Deployment"},
      "object": {
        "metadata": {
          "name": "gateway-deployment",
          "labels": {"app": "gateway-intencoes"}
        },
        "spec": {
          "template": {
            "spec": {
              "containers": [{
                "name": "gateway",
                "env": [
                  {"name": "PORT", "value": "8000"}
                ],
                "resources": {}
              }]
            }
          }
        }
      }
    },
    "parameters": {
      "oauth2_required_services": ["gateway-intencoes"]
    }
  }
}
