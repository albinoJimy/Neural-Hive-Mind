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
      "app.kubernetes.io/name"      = "mongodb"
      "app.kubernetes.io/instance"  = var.cluster_name
      "app.kubernetes.io/component" = "database"
      "app.kubernetes.io/part-of"   = "neural-hive-mind"
      "neural-hive.io/layer"        = "memory"
      "neural-hive.io/component"    = "operational-context"
      "neural-hive.io/environment"  = var.environment
    }
  )
}

# Namespace
resource "kubernetes_namespace" "mongodb" {
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
resource "kubernetes_secret" "mongodb_auth" {
  metadata {
    name      = "${var.cluster_name}-auth"
    namespace = kubernetes_namespace.mongodb.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    password = base64encode(var.root_password)
  }

  type = "Opaque"
}

# Helm release do MongoDB Operator
resource "helm_release" "mongodb_operator" {
  name             = "mongodb-operator"
  repository       = "https://mongodb.github.io/helm-charts"
  chart            = "community-operator"
  version          = "0.8.3"
  namespace        = kubernetes_namespace.mongodb.metadata[0].name
  create_namespace = false

  set {
    name  = "operator.watchNamespace"
    value = kubernetes_namespace.mongodb.metadata[0].name
  }
}

# ConfigMap com scripts de manutenção
resource "kubernetes_config_map" "mongodb_scripts" {
  metadata {
    name      = "${var.cluster_name}-scripts"
    namespace = kubernetes_namespace.mongodb.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    "health-check.sh" = <<-EOF
      #!/bin/bash
      mongosh --quiet --eval "db.adminCommand('ping')"
    EOF

    "backup-manual.sh" = <<-EOF
      #!/bin/bash
      BACKUP_DIR="/backup/$(date +%Y%m%d-%H%M%S)"
      mkdir -p $BACKUP_DIR
      mongodump --out=$BACKUP_DIR
      echo "Backup completed: $BACKUP_DIR"
    EOF

    "restore.sh" = <<-EOF
      #!/bin/bash
      if [ -z "$1" ]; then
        echo "Usage: $0 <backup-directory>"
        exit 1
      fi
      mongorestore $1
    EOF
  }
}

# MongoDB ReplicaSet Custom Resource
resource "kubernetes_manifest" "mongodb_replicaset" {
  manifest = {
    apiVersion = "mongodbcommunity.mongodb.com/v1"
    kind       = "MongoDBCommunity"

    metadata = {
      name      = var.cluster_name
      namespace = kubernetes_namespace.mongodb.metadata[0].name
      labels    = local.common_labels
      annotations = {
        "neural-hive.io/backup-enabled" = tostring(var.backup_enabled)
      }
    }

    spec = {
      members = var.replica_count
      type    = "ReplicaSet"
      version = var.mongodb_version

      security = {
        authentication = {
          modes = ["SCRAM"]
        }
        tls = (var.tls_enabled && var.tls_secret_name != "") ? {
          enabled = true
          certificateKeySecret = {
            name = var.tls_secret_name
          }
        } : {}
      }

      users = [
        {
          name = "admin"
          db   = "admin"
          passwordSecretRef = {
            name = kubernetes_secret.mongodb_auth.metadata[0].name
            key  = "password"
          }
          roles = [
            {
              name = "root"
              db   = "admin"
            }
          ]
          scramCredentialsSecretName = "${var.cluster_name}-admin-scram"
        }
      ]

      statefulSet = {
        spec = {
          volumeClaimTemplates = [
            {
              metadata = {
                name = "data-volume"
              }
              spec = {
                accessModes = ["ReadWriteOnce"]
                storageClassName = var.storage_class
                resources = {
                  requests = {
                    storage = var.storage_size
                  }
                }
              }
            }
          ]

          template = {
            spec = {
              containers = [
                {
                  name = "mongod"
                  resources = {
                    requests = {
                      cpu    = var.mongodb_cpu_request
                      memory = var.mongodb_memory_request
                    }
                    limits = {
                      cpu    = var.mongodb_cpu_limit
                      memory = var.mongodb_memory_limit
                    }
                  }
                }
              ]

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
                              values   = ["mongodb"]
                            }
                          ]
                        }
                        topologyKey = "topology.kubernetes.io/zone"
                      }
                    }
                  ]
                }
              }
            }
          }
        }
      }

      additionalMongodConfig = {
        "storage.wiredTiger.engineConfig.journalCompressor" = "zstd"
        "net.tls.mode" = (var.tls_enabled && var.tls_secret_name != "") ? "requireTLS" : "disabled"
      }

      prometheus = var.enable_metrics ? {
        enabled = true
        port    = 9216
      } : {}
    }
  }

  depends_on = [helm_release.mongodb_operator]
}

# Service
resource "kubernetes_service" "mongodb" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.mongodb.metadata[0].name
    labels    = local.common_labels
    annotations = {
      "neural-hive.io/service-type" = "database"
    }
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "mongodb"
      port        = 27017
      target_port = 27017
      protocol    = "TCP"
    }

    dynamic "port" {
      for_each = var.enable_metrics ? [1] : []
      content {
        name        = "metrics"
        port        = 9216
        target_port = 9216
        protocol    = "TCP"
      }
    }

    selector = {
      "app.kubernetes.io/name"     = "mongodb"
      "app.kubernetes.io/instance" = var.cluster_name
    }
  }
}

# PodDisruptionBudget
resource "kubernetes_pod_disruption_budget_v1" "mongodb" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.mongodb.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    min_available = var.replica_count > 2 ? 2 : 1

    selector {
      match_labels = {
        "app.kubernetes.io/name"     = "mongodb"
        "app.kubernetes.io/instance" = var.cluster_name
      }
    }
  }
}

# Backup CronJob (se habilitado)
resource "kubernetes_cron_job_v1" "mongodb_backup" {
  count = var.backup_enabled ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-backup"
    namespace = kubernetes_namespace.mongodb.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    schedule                      = var.backup_schedule
    successful_jobs_history_limit = var.backup_retention_days
    failed_jobs_history_limit     = 3

    job_template {
      metadata {
        labels = local.common_labels
      }

      spec {
        template {
          metadata {
            labels = local.common_labels
          }

          spec {
            restart_policy = "OnFailure"

            container {
              name  = "backup"
              image = "mongo:${var.mongodb_version}"

              command = [
                "/bin/bash",
                "-c",
                "mongodump --host=${var.cluster_name}.${var.namespace}.svc.cluster.local --archive=/backup/mongodb-$(date +%Y%m%d-%H%M%S).archive --gzip"
              ]

              volume_mount {
                name       = "backup-storage"
                mount_path = "/backup"
              }
            }

            volume {
              name = "backup-storage"
              persistent_volume_claim {
                claim_name = "${var.cluster_name}-backup"
              }
            }
          }
        }
      }
    }
  }
}

# PVC para backup (se habilitado)
resource "kubernetes_persistent_volume_claim" "backup" {
  count = var.backup_enabled ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-backup"
    namespace = kubernetes_namespace.mongodb.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class

    resources {
      requests = {
        storage = var.storage_size
      }
    }
  }
}
