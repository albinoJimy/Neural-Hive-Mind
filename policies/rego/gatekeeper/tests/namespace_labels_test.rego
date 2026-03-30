# Testes para namespace-labels.rego
# Epic H - H003: Testes de OPA Policies

package namespacelabels

import future.keywords.contains

test_namespace_labels_missing_environment {
  # Namespace sem label environment deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Namespace"},
      "object": {
        "metadata": {
          "name": "test-namespace",
          "labels": {
            "neural-hive.io/team": "team-platform"
          }
        }
      }
    },
    "parameters": {
      "required_labels": {
        "neural-hive.io/environment": "production|staging|development",
        "neural-hive.io/team": "team-owner"
      }
    }
  }
}

test_namespace_labels_missing_team {
  # Namespace sem label team deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "Namespace"},
      "object": {
        "metadata": {
          "name": "test-namespace",
          "labels": {
            "neural-hive.io/environment": "production"
          }
        }
      }
    },
    "parameters": {
      "required_labels": {
        "neural-hive.io/environment": "production|staging|development",
        "neural-hive.io/team": "team-owner"
      }
    }
  }
}

test_namespace_labels_complete {
  # Namespace com todos os labels deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Namespace"},
      "object": {
        "metadata": {
          "name": "test-namespace",
          "labels": {
            "neural-hive.io/environment": "production",
            "neural-hive.io/team": "team-platform"
          }
        }
      }
    },
    "parameters": {
      "required_labels": {
        "neural-hive.io/environment": "production|staging|development",
        "neural-hive.io/team": "team-owner"
      }
    }
  }
}

test_namespace_labels_development_value {
  # Namespace com environment development deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "Namespace"},
      "object": {
        "metadata": {
          "name": "dev-namespace",
          "labels": {
            "neural-hive.io/environment": "development",
            "neural-hive.io/team": "team-dev"
          }
        }
      }
    },
    "parameters": {
      "required_labels": {
        "neural-hive.io/environment": "production|staging|development",
        "neural-hive.io/team": "team-owner"
      }
    }
  }
}
