# Testes para rbac-restrictions.rego
# Epic H - H003: Testes de OPA Policies

package rbacrestrictions

import future.keywords.contains
import future.keywords.if

test_rbac_restrictions_cluster_admin_forbidden {
  # ClusterRoleBinding para cluster-admin deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "ClusterRoleBinding"},
      "object": {
        "metadata": {"name": "dangerous-binding"},
        "roleRef": {
          "kind": "ClusterRole",
          "name": "cluster-admin"
        },
        "subjects": [{
          "kind": "User",
          "name": "unauthorized-user"
        }]
      }
    },
    "parameters": {
      "forbidden_roles": ["cluster-admin", "admin", "edit"],
      "allowed_subjects": ["admin@neuralhive.io"]
    }
  }
}

test_rbac_restrictions_admin_allowed_subject {
  # RoleBinding admin para subject permitido deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "RoleBinding"},
      "object": {
        "metadata": {
          "name": "admin-binding",
          "namespace": "production"
        },
        "roleRef": {
          "kind": "ClusterRole",
          "name": "admin"
        },
        "subjects": [{
          "kind": "User",
          "name": "admin@neuralhive.io"
        }]
      }
    },
    "parameters": {
      "forbidden_roles": ["cluster-admin", "admin", "edit"],
      "allowed_subjects": ["admin@neuralhive.io"]
    }
  }
}

test_rbac_restrictions_role_edit_prod_violation {
  # RoleBinding edit em produção deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "RoleBinding"},
      "object": {
        "metadata": {
          "name": "edit-binding",
          "namespace": "production"
        },
        "roleRef": {
          "kind": "ClusterRole",
          "name": "edit"
        },
        "subjects": [{
          "kind": "User",
          "name": "developer@neuralhive.io"
        }]
      }
    },
    "parameters": {
      "forbidden_roles": ["cluster-admin", "admin", "edit"],
      "allowed_subjects": ["admin@neuralhive.io"]
    }
  }
}

test_rbac_restrictions_safe_role {
  # RoleBinding para role segura deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "RoleBinding"},
      "object": {
        "metadata": {
          "name": "viewer-binding",
          "namespace": "production"
        },
        "roleRef": {
          "kind": "ClusterRole",
          "name": "viewer"
        },
        "subjects": [{
          "kind": "User",
          "name": "viewer@neuralhive.io"
        }]
      }
    },
    "parameters": {
      "forbidden_roles": ["cluster-admin", "admin", "edit"],
      "allowed_subjects": []
    }
  }
}

test_rbac_restrictions_dev_namespace {
  # Namespace de desenvolvimento permite mais flexibilidade
  not violation with input as {
    "review": {
      "kind": {"kind": "RoleBinding"},
      "object": {
        "metadata": {
          "name": "edit-binding",
          "namespace": "development"
        },
        "roleRef": {
          "kind": "ClusterRole",
          "name": "edit"
        },
        "subjects": [{
          "kind": "User",
          "name": "developer@neuralhive.io"
        }]
      }
    },
    "parameters": {
      "forbidden_roles": ["cluster-admin", "admin", "edit"],
      "allowed_subjects": []
    }
  }
}
