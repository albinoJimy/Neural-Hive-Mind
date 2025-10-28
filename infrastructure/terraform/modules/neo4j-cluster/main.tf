terraform {
  required_version = ">= 1.5.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }
}

locals {
  common_labels = merge(
    var.common_labels,
    {
      "app.kubernetes.io/name"      = "neo4j"
      "app.kubernetes.io/instance"  = var.cluster_name
      "app.kubernetes.io/component" = "graph-database"
      "app.kubernetes.io/part-of"   = "neural-hive-mind"
      "neural-hive.io/layer"        = "knowledge"
      "neural-hive.io/component"    = "semantic-graph"
      "neural-hive.io/environment"  = var.environment
    }
  )

  plugins_list = join(",", var.plugins_enabled)
}

# Namespace
resource "kubernetes_namespace" "neo4j" {
  metadata {
    name = var.namespace
    labels = merge(
      local.common_labels,
      {
        "istio-injection" = "enabled"
      }
    )
  }
}

# Secret para credenciais
resource "kubernetes_secret" "neo4j_auth" {
  metadata {
    name      = "${var.cluster_name}-auth"
    namespace = kubernetes_namespace.neo4j.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    "NEO4J_AUTH" = base64encode("neo4j/${var.neo4j_password}")
    password     = base64encode(var.neo4j_password)
  }

  type = "Opaque"
}

# ConfigMap com scripts de inicialização e manutenção
resource "kubernetes_config_map" "neo4j_scripts" {
  metadata {
    name      = "${var.cluster_name}-scripts"
    namespace = kubernetes_namespace.neo4j.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    "init-constraints.cypher" = <<-EOF
      // Constraints e índices iniciais
      CREATE CONSTRAINT concept_id IF NOT EXISTS
      FOR (c:Concept) REQUIRE c.id IS UNIQUE;

      CREATE CONSTRAINT entity_id IF NOT EXISTS
      FOR (e:Entity) REQUIRE e.id IS UNIQUE;

      CREATE INDEX concept_name IF NOT EXISTS
      FOR (c:Concept) ON (c.name);

      CREATE INDEX entity_type IF NOT EXISTS
      FOR (e:Entity) ON (e.type);
    EOF

    "init-ontology.cypher" = <<-EOF
      // Seed de ontologias base (exemplo)
      MERGE (root:Concept {id: 'root', name: 'Root Concept'})
      MERGE (thing:Concept {id: 'thing', name: 'Thing'})
      MERGE (root)-[:SUBSUMES]->(thing);
    EOF

    "health-check.sh" = <<-EOF
      #!/bin/bash
      cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1 as health;" > /dev/null 2>&1
      echo $?
    EOF

    "backup.sh" = <<-EOF
      #!/bin/bash
      BACKUP_DIR="/backup/$(date +%Y%m%d-%H%M%S)"
      neo4j-admin database dump neo4j --to-path=$BACKUP_DIR
      echo "Backup completed: $BACKUP_DIR"
    EOF

    "restore.sh" = <<-EOF
      #!/bin/bash
      if [ -z "$1" ]; then
        echo "Usage: $0 <backup-file>"
        exit 1
      fi
      neo4j-admin database load neo4j --from-path=$1
    EOF
  }
}

# Helm release do Neo4j
resource "helm_release" "neo4j" {
  name             = var.cluster_name
  repository       = "https://helm.neo4j.com/neo4j"
  chart            = "neo4j"
  version          = "5.15.0"
  namespace        = kubernetes_namespace.neo4j.metadata[0].name
  create_namespace = false
  timeout          = 900

  values = [
    yamlencode({
      neo4j = {
        name    = var.cluster_name
        edition = var.edition
        acceptLicenseAgreement = var.edition == "enterprise" ? "yes" : "no"

        password = var.neo4j_password

        resources = {
          cpu    = var.cpu_request
          memory = var.memory_request
        }

        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
      }

      volumes = {
        data = {
          mode = "defaultStorageClass"
          defaultStorageClass = {
            storageClassName = var.storage_class
            requests = {
              storage = var.core_storage_size
            }
          }
        }
      }

      config = {
        "server.default_listen_address"           = "0.0.0.0"
        "server.bolt.enabled"                     = "true"
        "server.http.enabled"                     = "true"
        "dbms.security.auth_enabled"              = "true"
        "server.memory.heap.initial_size"         = var.heap_initial_size
        "server.memory.heap.max_size"             = var.heap_max_size
        "server.memory.pagecache.size"            = var.pagecache_size
        "dbms.logs.query.enabled"                 = "true"
        "server.metrics.enabled"                  = var.enable_metrics ? "true" : "false"
        "server.metrics.prometheus.enabled"       = var.enable_metrics ? "true" : "false"
        "server.metrics.prometheus.endpoint"      = "0.0.0.0:2004"
        "dbms.security.procedures.unrestricted"   = local.plugins_list
        "dbms.security.procedures.allowlist"      = "${local.plugins_list},gds.*"
      }

      services = {
        neo4j = {
          enabled = true
          type    = "ClusterIP"
          ports = {
            bolt = {
              enabled = true
              port    = 7687
            }
            http = {
              enabled = true
              port    = 7474
            }
          }
        }
      }

      podAnnotations = merge(
        {
          "neural-hive.io/service-type" = "graph-database"
          "prometheus.io/scrape"        = var.enable_metrics ? "true" : "false"
          "prometheus.io/port"          = "2004"
          "prometheus.io/path"          = "/metrics"
        },
        var.common_labels
      )

      podLabels = local.common_labels

      affinity = {
        podAntiAffinity = {
          preferredDuringSchedulingIgnoredDuringExecution = [
            {
              weight = 100
              podAffinityTerm = {
                labelSelector = {
                  matchExpressions = [
                    {
                      key      = "app.kubernetes.io/name"
                      operator = "In"
                      values   = ["neo4j"]
                    }
                  ]
                }
                topologyKey = "topology.kubernetes.io/zone"
              }
            }
          ]
        }
      }

      # Plugins
      plugins = var.plugins_enabled
    })
  ]
}

# Service para Bolt
resource "kubernetes_service" "neo4j_bolt" {
  metadata {
    name      = "${var.cluster_name}-bolt"
    namespace = kubernetes_namespace.neo4j.metadata[0].name
    labels    = local.common_labels
    annotations = {
      "neural-hive.io/service-type" = "graph-database"
      "neural-hive.io/protocol"     = "bolt"
    }
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "bolt"
      port        = 7687
      target_port = 7687
      protocol    = "TCP"
    }

    selector = {
      "app.kubernetes.io/name"     = "neo4j"
      "app.kubernetes.io/instance" = var.cluster_name
    }
  }

  depends_on = [helm_release.neo4j]
}

# Service para HTTP
resource "kubernetes_service" "neo4j_http" {
  metadata {
    name      = "${var.cluster_name}-http"
    namespace = kubernetes_namespace.neo4j.metadata[0].name
    labels    = local.common_labels
    annotations = {
      "neural-hive.io/service-type" = "graph-database"
      "neural-hive.io/protocol"     = "http"
    }
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "http"
      port        = 7474
      target_port = 7474
      protocol    = "TCP"
    }

    selector = {
      "app.kubernetes.io/name"     = "neo4j"
      "app.kubernetes.io/instance" = var.cluster_name
    }
  }

  depends_on = [helm_release.neo4j]
}

# Service para Metrics (se habilitado)
resource "kubernetes_service" "neo4j_metrics" {
  count = var.enable_metrics ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-metrics"
    namespace = kubernetes_namespace.neo4j.metadata[0].name
    labels = merge(
      local.common_labels,
      {
        "neural-hive.io/monitoring" = "prometheus"
      }
    )
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "metrics"
      port        = 2004
      target_port = 2004
      protocol    = "TCP"
    }

    selector = {
      "app.kubernetes.io/name"     = "neo4j"
      "app.kubernetes.io/instance" = var.cluster_name
    }
  }

  depends_on = [helm_release.neo4j]
}

# PodDisruptionBudget
resource "kubernetes_pod_disruption_budget_v1" "neo4j" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.neo4j.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    min_available = var.core_servers > 2 ? 2 : 1

    selector {
      match_labels = {
        "app.kubernetes.io/name"     = "neo4j"
        "app.kubernetes.io/instance" = var.cluster_name
      }
    }
  }

  depends_on = [helm_release.neo4j]
}
