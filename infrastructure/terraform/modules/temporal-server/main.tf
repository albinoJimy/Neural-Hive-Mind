# Módulo Terraform para Temporal Server (frontend, history, matching, worker)

terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.20"
    }
  }
}

# Namespace
resource "kubernetes_namespace" "temporal" {
  metadata {
    name = var.namespace
    labels = merge(
      var.common_labels,
      {
        "app.kubernetes.io/name"      = "temporal"
        "app.kubernetes.io/component" = "workflow-engine"
        "neural-hive.io/layer"        = "infrastructure"
        "environment"                  = var.environment
      }
    )
  }
}

# ConfigMap com configurações do Temporal
resource "kubernetes_config_map" "temporal_config" {
  metadata {
    name      = "${var.cluster_name}-config"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name })
  }

  data = {
    "development.yaml" = <<-EOT
      global:
        membership:
          maxJoinDuration: 30s
        pprof:
          port: 7936
        metrics:
          prometheus:
            timerType: histogram
            listenAddress: 0.0.0.0:9090

      persistence:
        defaultStore: default
        visibilityStore: visibility
        numHistoryShards: ${var.num_history_shards}
        datastores:
          default:
            sql:
              pluginName: postgres
              databaseName: ${var.postgres_database}
              connectAddr: ${var.postgres_host}:${var.postgres_port}
              connectProtocol: tcp
              user: ${var.postgres_user}
              maxConns: 20
              maxIdleConns: 20
              maxConnLifetime: 1h
          visibility:
            sql:
              pluginName: postgres
              databaseName: ${var.postgres_database}
              connectAddr: ${var.postgres_host}:${var.postgres_port}
              connectProtocol: tcp
              user: ${var.postgres_user}
              maxConns: 10
              maxIdleConns: 10
              maxConnLifetime: 1h

      services:
        frontend:
          rpc:
            grpcPort: 7233
            membershipPort: 6933
            bindOnLocalHost: false

        matching:
          rpc:
            grpcPort: 7235
            membershipPort: 6935
            bindOnLocalHost: false

        history:
          rpc:
            grpcPort: 7234
            membershipPort: 6934
            bindOnLocalHost: false

        worker:
          rpc:
            grpcPort: 7239
            membershipPort: 6939
            bindOnLocalHost: false
    EOT
  }
}

# Secret com credenciais PostgreSQL
resource "kubernetes_secret" "temporal_postgres" {
  metadata {
    name      = "${var.cluster_name}-postgres-credentials"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name })
  }

  data = {
    "password" = base64encode(var.postgres_password)
  }

  type = "Opaque"
}

# Deployment - Frontend
resource "kubernetes_deployment" "temporal_frontend" {
  metadata {
    name      = "${var.cluster_name}-frontend"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels = merge(
      var.common_labels,
      {
        "app"       = var.cluster_name
        "component" = "frontend"
      }
    )
  }

  spec {
    replicas = var.frontend_replicas

    selector {
      match_labels = {
        "app"       = var.cluster_name
        "component" = "frontend"
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = "1"
        max_unavailable = "0"
      }
    }

    template {
      metadata {
        labels = {
          "app"       = var.cluster_name
          "component" = "frontend"
        }
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = "9090"
          "prometheus.io/path"   = "/metrics"
        }
      }

      spec {
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
          fs_group        = 1000
        }

        container {
          name  = "temporal-frontend"
          image = "temporalio/server:${var.temporal_version}"
          args  = ["start", "--service", "frontend"]

          port {
            name           = "rpc"
            container_port = 7233
            protocol       = "TCP"
          }

          port {
            name           = "metrics"
            container_port = 9090
            protocol       = "TCP"
          }

          env {
            name  = "SERVICES"
            value = "frontend"
          }

          env {
            name  = "LOG_LEVEL"
            value = var.log_level
          }

          env {
            name  = "DYNAMIC_CONFIG_FILE_PATH"
            value = "/etc/temporal/config/development.yaml"
          }

          env {
            name  = "POSTGRES_SEEDS"
            value = "${var.postgres_host}:${var.postgres_port}"
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.temporal_postgres.metadata[0].name
                key  = "password"
              }
            }
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/temporal/config"
          }

          liveness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 10
            period_seconds        = 5
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = var.frontend_resources.requests.cpu
              memory = var.frontend_resources.requests.memory
            }
            limits = {
              cpu    = var.frontend_resources.limits.cpu
              memory = var.frontend_resources.limits.memory
            }
          }
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.temporal_config.metadata[0].name
          }
        }

        affinity {
          pod_anti_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              pod_affinity_term {
                label_selector {
                  match_expressions {
                    key      = "component"
                    operator = "In"
                    values   = ["frontend"]
                  }
                }
                topology_key = "kubernetes.io/hostname"
              }
            }
          }
        }
      }
    }
  }
}

# Deployment - History
resource "kubernetes_deployment" "temporal_history" {
  metadata {
    name      = "${var.cluster_name}-history"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels = merge(
      var.common_labels,
      {
        "app"       = var.cluster_name
        "component" = "history"
      }
    )
  }

  spec {
    replicas = var.history_replicas

    selector {
      match_labels = {
        "app"       = var.cluster_name
        "component" = "history"
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = "1"
        max_unavailable = "0"
      }
    }

    template {
      metadata {
        labels = {
          "app"       = var.cluster_name
          "component" = "history"
        }
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = "9090"
          "prometheus.io/path"   = "/metrics"
        }
      }

      spec {
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
          fs_group        = 1000
        }

        container {
          name  = "temporal-history"
          image = "temporalio/server:${var.temporal_version}"
          args  = ["start", "--service", "history"]

          port {
            name           = "rpc"
            container_port = 7234
            protocol       = "TCP"
          }

          port {
            name           = "metrics"
            container_port = 9090
            protocol       = "TCP"
          }

          env {
            name  = "SERVICES"
            value = "history"
          }

          env {
            name  = "LOG_LEVEL"
            value = var.log_level
          }

          env {
            name  = "DYNAMIC_CONFIG_FILE_PATH"
            value = "/etc/temporal/config/development.yaml"
          }

          env {
            name  = "POSTGRES_SEEDS"
            value = "${var.postgres_host}:${var.postgres_port}"
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.temporal_postgres.metadata[0].name
                key  = "password"
              }
            }
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/temporal/config"
          }

          liveness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 10
            period_seconds        = 5
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = var.history_resources.requests.cpu
              memory = var.history_resources.requests.memory
            }
            limits = {
              cpu    = var.history_resources.limits.cpu
              memory = var.history_resources.limits.memory
            }
          }
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.temporal_config.metadata[0].name
          }
        }

        affinity {
          pod_anti_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              pod_affinity_term {
                label_selector {
                  match_expressions {
                    key      = "component"
                    operator = "In"
                    values   = ["history"]
                  }
                }
                topology_key = "kubernetes.io/hostname"
              }
            }
          }
        }
      }
    }
  }
}

# Deployment - Matching
resource "kubernetes_deployment" "temporal_matching" {
  metadata {
    name      = "${var.cluster_name}-matching"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels = merge(
      var.common_labels,
      {
        "app"       = var.cluster_name
        "component" = "matching"
      }
    )
  }

  spec {
    replicas = var.matching_replicas

    selector {
      match_labels = {
        "app"       = var.cluster_name
        "component" = "matching"
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = "1"
        max_unavailable = "0"
      }
    }

    template {
      metadata {
        labels = {
          "app"       = var.cluster_name
          "component" = "matching"
        }
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = "9090"
          "prometheus.io/path"   = "/metrics"
        }
      }

      spec {
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
          fs_group        = 1000
        }

        container {
          name  = "temporal-matching"
          image = "temporalio/server:${var.temporal_version}"
          args  = ["start", "--service", "matching"]

          port {
            name           = "rpc"
            container_port = 7235
            protocol       = "TCP"
          }

          port {
            name           = "metrics"
            container_port = 9090
            protocol       = "TCP"
          }

          env {
            name  = "SERVICES"
            value = "matching"
          }

          env {
            name  = "LOG_LEVEL"
            value = var.log_level
          }

          env {
            name  = "DYNAMIC_CONFIG_FILE_PATH"
            value = "/etc/temporal/config/development.yaml"
          }

          env {
            name  = "POSTGRES_SEEDS"
            value = "${var.postgres_host}:${var.postgres_port}"
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.temporal_postgres.metadata[0].name
                key  = "password"
              }
            }
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/temporal/config"
          }

          liveness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 10
            period_seconds        = 5
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = var.matching_resources.requests.cpu
              memory = var.matching_resources.requests.memory
            }
            limits = {
              cpu    = var.matching_resources.limits.cpu
              memory = var.matching_resources.limits.memory
            }
          }
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.temporal_config.metadata[0].name
          }
        }

        affinity {
          pod_anti_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              pod_affinity_term {
                label_selector {
                  match_expressions {
                    key      = "component"
                    operator = "In"
                    values   = ["matching"]
                  }
                }
                topology_key = "kubernetes.io/hostname"
              }
            }
          }
        }
      }
    }
  }
}

# Deployment - Worker
resource "kubernetes_deployment" "temporal_worker" {
  metadata {
    name      = "${var.cluster_name}-worker"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels = merge(
      var.common_labels,
      {
        "app"       = var.cluster_name
        "component" = "worker"
      }
    )
  }

  spec {
    replicas = var.worker_replicas

    selector {
      match_labels = {
        "app"       = var.cluster_name
        "component" = "worker"
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = "1"
        max_unavailable = "0"
      }
    }

    template {
      metadata {
        labels = {
          "app"       = var.cluster_name
          "component" = "worker"
        }
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = "9090"
          "prometheus.io/path"   = "/metrics"
        }
      }

      spec {
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
          fs_group        = 1000
        }

        container {
          name  = "temporal-worker"
          image = "temporalio/server:${var.temporal_version}"
          args  = ["start", "--service", "worker"]

          port {
            name           = "rpc"
            container_port = 7239
            protocol       = "TCP"
          }

          port {
            name           = "metrics"
            container_port = 9090
            protocol       = "TCP"
          }

          env {
            name  = "SERVICES"
            value = "worker"
          }

          env {
            name  = "LOG_LEVEL"
            value = var.log_level
          }

          env {
            name  = "DYNAMIC_CONFIG_FILE_PATH"
            value = "/etc/temporal/config/development.yaml"
          }

          env {
            name  = "POSTGRES_SEEDS"
            value = "${var.postgres_host}:${var.postgres_port}"
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.temporal_postgres.metadata[0].name
                key  = "password"
              }
            }
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/temporal/config"
          }

          liveness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            tcp_socket {
              port = "rpc"
            }
            initial_delay_seconds = 10
            period_seconds        = 5
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = var.worker_resources.requests.cpu
              memory = var.worker_resources.requests.memory
            }
            limits = {
              cpu    = var.worker_resources.limits.cpu
              memory = var.worker_resources.limits.memory
            }
          }
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.temporal_config.metadata[0].name
          }
        }

        affinity {
          pod_anti_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              pod_affinity_term {
                label_selector {
                  match_expressions {
                    key      = "component"
                    operator = "In"
                    values   = ["worker"]
                  }
                }
                topology_key = "kubernetes.io/hostname"
              }
            }
          }
        }
      }
    }
  }
}

# Service - Frontend
resource "kubernetes_service" "temporal_frontend" {
  metadata {
    name      = "${var.cluster_name}-frontend"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "frontend" })
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "rpc"
      port        = 7233
      target_port = "rpc"
      protocol    = "TCP"
    }

    port {
      name        = "metrics"
      port        = 9090
      target_port = "metrics"
      protocol    = "TCP"
    }

    selector = {
      "app"       = var.cluster_name
      "component" = "frontend"
    }
  }
}

# Service - History
resource "kubernetes_service" "temporal_history" {
  metadata {
    name      = "${var.cluster_name}-history"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "history" })
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "rpc"
      port        = 7234
      target_port = "rpc"
      protocol    = "TCP"
    }

    port {
      name        = "metrics"
      port        = 9090
      target_port = "metrics"
      protocol    = "TCP"
    }

    selector = {
      "app"       = var.cluster_name
      "component" = "history"
    }
  }
}

# Service - Matching
resource "kubernetes_service" "temporal_matching" {
  metadata {
    name      = "${var.cluster_name}-matching"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "matching" })
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "rpc"
      port        = 7235
      target_port = "rpc"
      protocol    = "TCP"
    }

    port {
      name        = "metrics"
      port        = 9090
      target_port = "metrics"
      protocol    = "TCP"
    }

    selector = {
      "app"       = var.cluster_name
      "component" = "matching"
    }
  }
}

# Service - Worker
resource "kubernetes_service" "temporal_worker" {
  metadata {
    name      = "${var.cluster_name}-worker"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "worker" })
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "rpc"
      port        = 7239
      target_port = "rpc"
      protocol    = "TCP"
    }

    port {
      name        = "metrics"
      port        = 9090
      target_port = "metrics"
      protocol    = "TCP"
    }

    selector = {
      "app"       = var.cluster_name
      "component" = "worker"
    }
  }
}

# Deployment - Web UI (opcional)
resource "kubernetes_deployment" "temporal_web" {
  count = var.enable_web_ui ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-web"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels = merge(
      var.common_labels,
      {
        "app"       = var.cluster_name
        "component" = "web"
      }
    )
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        "app"       = var.cluster_name
        "component" = "web"
      }
    }

    template {
      metadata {
        labels = {
          "app"       = var.cluster_name
          "component" = "web"
        }
      }

      spec {
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
          fs_group        = 1000
        }

        container {
          name  = "temporal-web"
          image = "temporalio/ui:${var.temporal_ui_version}"

          port {
            name           = "http"
            container_port = 8080
            protocol       = "TCP"
          }

          env {
            name  = "TEMPORAL_ADDRESS"
            value = "${var.cluster_name}-frontend.${kubernetes_namespace.temporal.metadata[0].name}.svc.cluster.local:7233"
          }

          env {
            name  = "TEMPORAL_CORS_ORIGINS"
            value = "http://localhost:3000"
          }

          liveness_probe {
            http_get {
              path = "/"
              port = "http"
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/"
              port = "http"
            }
            initial_delay_seconds = 10
            period_seconds        = 5
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }
}

# Service - Web UI (opcional)
resource "kubernetes_service" "temporal_web" {
  count = var.enable_web_ui ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-web"
    namespace = kubernetes_namespace.temporal.metadata[0].name
    labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "web" })
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "http"
      port        = 8080
      target_port = "http"
      protocol    = "TCP"
    }

    selector = {
      "app"       = var.cluster_name
      "component" = "web"
    }
  }
}

# ServiceMonitor para Prometheus (Frontend)
resource "kubernetes_manifest" "servicemonitor_frontend" {
  count = var.enable_prometheus_monitoring ? 1 : 0

  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "${var.cluster_name}-frontend"
      namespace = kubernetes_namespace.temporal.metadata[0].name
      labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "frontend" })
    }
    spec = {
      selector = {
        matchLabels = {
          "app"       = var.cluster_name
          "component" = "frontend"
        }
      }
      endpoints = [
        {
          port     = "metrics"
          interval = "30s"
          path     = "/metrics"
        }
      ]
    }
  }
}

# ServiceMonitor para Prometheus (History)
resource "kubernetes_manifest" "servicemonitor_history" {
  count = var.enable_prometheus_monitoring ? 1 : 0

  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "${var.cluster_name}-history"
      namespace = kubernetes_namespace.temporal.metadata[0].name
      labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "history" })
    }
    spec = {
      selector = {
        matchLabels = {
          "app"       = var.cluster_name
          "component" = "history"
        }
      }
      endpoints = [
        {
          port     = "metrics"
          interval = "30s"
          path     = "/metrics"
        }
      ]
    }
  }
}

# ServiceMonitor para Prometheus (Matching)
resource "kubernetes_manifest" "servicemonitor_matching" {
  count = var.enable_prometheus_monitoring ? 1 : 0

  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "${var.cluster_name}-matching"
      namespace = kubernetes_namespace.temporal.metadata[0].name
      labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "matching" })
    }
    spec = {
      selector = {
        matchLabels = {
          "app"       = var.cluster_name
          "component" = "matching"
        }
      }
      endpoints = [
        {
          port     = "metrics"
          interval = "30s"
          path     = "/metrics"
        }
      ]
    }
  }
}

# ServiceMonitor para Prometheus (Worker)
resource "kubernetes_manifest" "servicemonitor_worker" {
  count = var.enable_prometheus_monitoring ? 1 : 0

  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "${var.cluster_name}-worker"
      namespace = kubernetes_namespace.temporal.metadata[0].name
      labels    = merge(var.common_labels, { "app" = var.cluster_name, "component" = "worker" })
    }
    spec = {
      selector = {
        matchLabels = {
          "app"       = var.cluster_name
          "component" = "worker"
        }
      }
      endpoints = [
        {
          port     = "metrics"
          interval = "30s"
          path     = "/metrics"
        }
      ]
    }
  }
}
