# Módulo Terraform para PostgreSQL como state store do Temporal Server

terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.20"
    }
  }
}

# Namespace
resource "kubernetes_namespace" "postgres_temporal" {
  metadata {
    name = var.namespace
    labels = merge(
      var.common_labels,
      {
        "app.kubernetes.io/name"      = "postgres-temporal"
        "app.kubernetes.io/component" = "database"
        "neural-hive.io/layer"        = "infrastructure"
        "environment"                  = var.environment
      }
    )
  }
}

# ConfigMap com configurações PostgreSQL
resource "kubernetes_config_map" "postgres_config" {
  metadata {
    name      = "${var.cluster_name}-config"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name })
  }

  data = {
    "postgresql.conf" = <<-EOT
      max_connections = 300
      shared_buffers = 512MB
      effective_cache_size = 2GB
      maintenance_work_mem = 64MB
      checkpoint_completion_target = 0.9
      wal_buffers = 16MB
      default_statistics_target = 100
      random_page_cost = 1.1
      effective_io_concurrency = 200
      work_mem = 4MB
      min_wal_size = 1GB
      max_wal_size = 4GB
      max_worker_processes = 4
      max_parallel_workers_per_gather = 2
      max_parallel_workers = 4
      max_parallel_maintenance_workers = 2
      wal_level = replica
      archive_mode = on
      archive_command = 'aws s3 cp %p s3://neural-hive-backups-prod/temporal/wal/%f'
      archive_timeout = 300  # 5 minutes
    EOT

    "pg_hba.conf" = <<-EOT
      # TYPE  DATABASE        USER            ADDRESS                 METHOD
      local   all             all                                     trust
      host    all             all             127.0.0.1/32            md5
      host    all             all             ::1/128                 md5
      host    all             all             0.0.0.0/0               md5
      host    replication     all             0.0.0.0/0               md5
    EOT
  }
}

# Secret com credenciais
resource "kubernetes_secret" "postgres_credentials" {
  metadata {
    name      = "${var.cluster_name}-credentials"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name })
  }

  data = {
    "postgres-password"    = base64encode(var.postgres_password)
    "temporal-password"    = base64encode(var.temporal_password)
    "replication-password" = base64encode(var.replication_password)
  }

  type = "Opaque"
}

# StatefulSet PostgreSQL
resource "kubernetes_stateful_set" "postgres" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name })
  }

  spec {
    service_name = "${var.cluster_name}-headless"
    replicas     = var.replica_count

    selector {
      match_labels = {
        "app" = var.cluster_name
      }
    }

    template {
      metadata {
        labels = {
          "app" = var.cluster_name
        }
      }

      spec {
        security_context {
          run_as_user  = 999
          run_as_group = 999
          fs_group     = 999
        }

        init_container {
          name  = "init-postgres"
          image = "postgres:${var.postgres_version}"
          command = [
            "sh", "-c",
            "mkdir -p /var/lib/postgresql/data && chown -R 999:999 /var/lib/postgresql/data"
          ]
          volume_mount {
            name       = "data"
            mount_path = "/var/lib/postgresql/data"
          }
        }

        container {
          name  = "postgres"
          image = "postgres:${var.postgres_version}"

          port {
            name           = "postgresql"
            container_port = 5432
            protocol       = "TCP"
          }

          env {
            name  = "POSTGRES_DB"
            value = "temporal"
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.postgres_credentials.metadata[0].name
                key  = "postgres-password"
              }
            }
          }

          env {
            name  = "PGDATA"
            value = "/var/lib/postgresql/data/pgdata"
          }

          volume_mount {
            name       = "data"
            mount_path = "/var/lib/postgresql/data"
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/postgresql"
          }

          liveness_probe {
            exec {
              command = ["pg_isready", "-U", "postgres"]
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            exec {
              command = ["pg_isready", "-U", "postgres"]
            }
            initial_delay_seconds = 5
            period_seconds        = 5
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = "500m"
              memory = "1Gi"
            }
            limits = {
              cpu    = "2000m"
              memory = "4Gi"
            }
          }
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.postgres_config.metadata[0].name
          }
        }

        affinity {
          pod_anti_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              pod_affinity_term {
                label_selector {
                  match_expressions {
                    key      = "app"
                    operator = "In"
                    values   = [var.cluster_name]
                  }
                }
                topology_key = "kubernetes.io/hostname"
              }
            }
          }
        }
      }
    }

    volume_claim_template {
      metadata {
        name = "data"
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
  }
}

# Service Headless para descoberta
resource "kubernetes_service" "postgres_headless" {
  metadata {
    name      = "${var.cluster_name}-headless"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name })
  }

  spec {
    type       = "ClusterIP"
    cluster_ip = "None"

    port {
      name        = "postgresql"
      port        = 5432
      target_port = "postgresql"
      protocol    = "TCP"
    }

    selector = {
      "app" = var.cluster_name
    }
  }
}

# Service LoadBalancer (opcional, para acesso externo)
resource "kubernetes_service" "postgres_lb" {
  count = var.enable_external_access ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-lb"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name })
  }

  spec {
    type = "LoadBalancer"

    port {
      name        = "postgresql"
      port        = 5432
      target_port = "postgresql"
      protocol    = "TCP"
    }

    selector = {
      "app" = var.cluster_name
    }
  }
}

# Job de inicialização do schema Temporal
resource "kubernetes_job" "temporal_schema_init" {
  depends_on = [kubernetes_stateful_set.postgres]

  metadata {
    name      = "temporal-schema-init"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = "temporal-schema-init" })
  }

  spec {
    template {
      metadata {
        labels = { "app" = "temporal-schema-init" }
      }

      spec {
        restart_policy = "OnFailure"

        container {
          name  = "schema-init"
          image = "temporalio/admin-tools:latest"

          env {
            name  = "POSTGRES_HOST"
            value = "${var.cluster_name}-headless"
          }

          env {
            name  = "POSTGRES_PORT"
            value = "5432"
          }

          env {
            name  = "POSTGRES_USER"
            value = "temporal"
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.postgres_credentials.metadata[0].name
                key  = "temporal-password"
              }
            }
          }

          command = [
            "sh", "-c",
            <<-EOT
              temporal-sql-tool \
                --plugin postgres \
                --ep $POSTGRES_HOST:$POSTGRES_PORT \
                -u $POSTGRES_USER \
                -p $POSTGRES_PASSWORD \
                --db temporal \
                setup-schema -v 0.0

              temporal-sql-tool \
                --plugin postgres \
                --ep $POSTGRES_HOST:$POSTGRES_PORT \
                -u $POSTGRES_USER \
                -p $POSTGRES_PASSWORD \
                --db temporal \
                update-schema -d /etc/temporal/schema/postgresql/v96/temporal/versioned
            EOT
          ]
        }
      }
    }

    backoff_limit = 3
  }

  wait_for_completion = false
}
