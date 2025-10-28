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
      "app.kubernetes.io/name"      = "clickhouse"
      "app.kubernetes.io/instance"  = var.cluster_name
      "app.kubernetes.io/component" = "analytics"
      "app.kubernetes.io/part-of"   = "neural-hive-mind"
      "neural-hive.io/layer"        = "memory"
      "neural-hive.io/component"    = "historical-analytics"
      "neural-hive.io/environment"  = var.environment
    }
  )
}

# Namespace
resource "kubernetes_namespace" "clickhouse" {
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
resource "kubernetes_secret" "clickhouse_auth" {
  metadata {
    name      = "${var.cluster_name}-auth"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    admin_password    = base64encode(var.admin_password)
    readonly_password = base64encode(var.readonly_password)
    writer_password   = base64encode(var.writer_password)
  }

  type = "Opaque"
}

# Helm release do ClickHouse Operator
resource "helm_release" "clickhouse_operator" {
  name             = "clickhouse-operator"
  repository       = "https://docs.altinity.com/clickhouse-operator/"
  chart            = "altinity-clickhouse-operator"
  version          = "0.21.0"
  namespace        = kubernetes_namespace.clickhouse.metadata[0].name
  create_namespace = false

  set {
    name  = "operator.image"
    value = "altinity/clickhouse-operator:0.21.0"
  }
}

# ConfigMap com configurações e scripts
resource "kubernetes_config_map" "clickhouse_config" {
  metadata {
    name      = "${var.cluster_name}-config"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    "init-databases.sql" = <<-EOF
      CREATE DATABASE IF NOT EXISTS neural_hive;
      CREATE DATABASE IF NOT EXISTS telemetry;
      CREATE DATABASE IF NOT EXISTS events;
    EOF

    "init-tables.sql" = <<-EOF
      -- Tabela de telemetria
      CREATE TABLE IF NOT EXISTS telemetry.metrics (
        timestamp DateTime,
        agent_id String,
        metric_name String,
        metric_value Float64,
        tags Map(String, String),
        date Date DEFAULT toDate(timestamp)
      ) ENGINE = MergeTree()
      PARTITION BY toYYYYMM(date)
      ORDER BY (date, agent_id, metric_name, timestamp)
      TTL date + INTERVAL ${var.ttl_days} DAY
      SETTINGS index_granularity = 8192;

      -- Tabela de eventos
      CREATE TABLE IF NOT EXISTS events.event_log (
        timestamp DateTime64(3),
        event_id String,
        event_type String,
        agent_id String,
        payload String,
        metadata Map(String, String),
        date Date DEFAULT toDate(timestamp)
      ) ENGINE = MergeTree()
      PARTITION BY toYYYYMM(date)
      ORDER BY (date, event_type, agent_id, timestamp)
      TTL date + INTERVAL ${var.ttl_days} DAY
      SETTINGS index_granularity = 8192;
    EOF

    "optimize.sh" = <<-EOF
      #!/bin/bash
      echo "Optimizing tables..."
      clickhouse-client --query "OPTIMIZE TABLE telemetry.metrics FINAL;"
      clickhouse-client --query "OPTIMIZE TABLE events.event_log FINAL;"
      echo "Optimization completed"
    EOF

    "backup.sh" = <<-EOF
      #!/bin/bash
      BACKUP_DIR="/backup/$(date +%Y%m%d-%H%M%S)"
      mkdir -p $BACKUP_DIR
      clickhouse-backup create $BACKUP_DIR
      echo "Backup completed: $BACKUP_DIR"
    EOF

    "health-check.sh" = <<-EOF
      #!/bin/bash
      clickhouse-client --query "SELECT 1;" > /dev/null 2>&1
      echo $?
    EOF
  }
}

# ClickHouseInstallation Custom Resource
resource "kubernetes_manifest" "clickhouse_installation" {
  manifest = {
    apiVersion = "clickhouse.altinity.com/v1"
    kind       = "ClickHouseInstallation"

    metadata = {
      name      = var.cluster_name
      namespace = kubernetes_namespace.clickhouse.metadata[0].name
      labels    = local.common_labels
    }

    spec = {
      configuration = {
        zookeeper = {
          nodes = [
            for i in range(var.zookeeper_nodes) : {
              host = "zookeeper-${i}.zookeeper-headless.${kubernetes_namespace.clickhouse.metadata[0].name}.svc.cluster.local"
              port = 2181
            }
          ]
        }

        users = {
          admin = {
            password     = var.admin_password
            networks     = { ip = ["::/0"] }
            profile      = "default"
            quota        = "default"
            access_management = 1
          }
          readonly = {
            password = var.readonly_password
            networks = { ip = ["::/0"] }
            profile  = "readonly"
            quota    = "default"
          }
          writer = {
            password = var.writer_password
            networks = { ip = ["::/0"] }
            profile  = "default"
            quota    = "default"
          }
        }

        profiles = {
          default = {
            max_memory_usage               = var.max_memory_usage
            max_threads                    = var.max_threads
            load_balancing                 = "random"
            log_queries                    = 1
            log_query_threads              = 1
          }
          readonly = {
            readonly = 1
          }
        }

        quotas = {
          default = {
            interval = {
              duration      = 3600
              queries       = 0
              errors        = 0
              result_rows   = 0
              read_rows     = 0
              execution_time = 0
            }
          }
        }

        settings = {
          compression = {
            case = {
              method = var.compression_codec
            }
          }
        }

        clusters = [
          {
            name = var.cluster_name
            layout = {
              shardsCount   = var.shards
              replicasCount = var.replicas
            }
          }
        ]
      }

      templates = {
        podTemplates = [
          {
            name = "clickhouse-pod"
            spec = {
              containers = [
                {
                  name  = "clickhouse"
                  image = "clickhouse/clickhouse-server:${var.clickhouse_version}"
                  resources = {
                    requests = {
                      cpu    = var.cpu_request
                      memory = var.memory_request
                    }
                    limits = {
                      cpu    = var.cpu_limit
                      memory = var.memory_limit
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
                              values   = ["clickhouse"]
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
        ]

        volumeClaimTemplates = [
          {
            name = "data-volume"
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

        serviceTemplates = [
          {
            name = "service-template"
            spec = {
              type = "ClusterIP"
              ports = [
                {
                  name       = "http"
                  port       = 8123
                  targetPort = 8123
                },
                {
                  name       = "native"
                  port       = 9000
                  targetPort = 9000
                },
                {
                  name       = "metrics"
                  port       = 9363
                  targetPort = 9363
                }
              ]
            }
          }
        ]
      }

      defaults = {
        templates = {
          podTemplate              = "clickhouse-pod"
          dataVolumeClaimTemplate  = "data-volume"
          serviceTemplate          = "service-template"
        }
      }
    }
  }

  depends_on = [helm_release.clickhouse_operator]
}

# Deploy ZooKeeper StatefulSet
resource "kubernetes_stateful_set" "zookeeper" {
  metadata {
    name      = "zookeeper"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
    labels    = merge(local.common_labels, { "app" = "zookeeper" })
  }

  spec {
    service_name = "zookeeper-headless"
    replicas     = var.zookeeper_nodes

    selector {
      match_labels = {
        app = "zookeeper"
      }
    }

    template {
      metadata {
        labels = merge(local.common_labels, { "app" = "zookeeper" })
      }

      spec {
        init_container {
          name  = "init-zookeeper-id"
          image = "busybox:1.36"
          command = [
            "sh",
            "-c",
            "POD_NAME=$(cat /etc/podinfo/pod_name) && POD_ORDINAL=$${POD_NAME##*-} && echo $((POD_ORDINAL + 1)) > /data/myid"
          ]

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }

          volume_mount {
            name       = "podinfo"
            mount_path = "/etc/podinfo"
          }
        }

        container {
          name  = "zookeeper"
          image = "zookeeper:3.8"

          port {
            name           = "client"
            container_port = 2181
          }

          port {
            name           = "follower"
            container_port = 2888
          }

          port {
            name           = "election"
            container_port = 3888
          }

          env {
            name  = "ZOO_SERVERS"
            value = join(" ", [for i in range(var.zookeeper_nodes) : "server.${i + 1}=zookeeper-${i}.zookeeper-headless:2888:3888;2181"])
          }

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }

          resources {
            requests = {
              cpu    = "200m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "1Gi"
            }
          }
        }

        volume {
          name = "podinfo"
          downward_api {
            items {
              path = "pod_name"
              field_ref {
                field_path = "metadata.name"
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
            storage = var.zk_storage_size
          }
        }
      }
    }
  }
}

# Headless service for ZooKeeper
resource "kubernetes_service" "zookeeper_headless" {
  metadata {
    name      = "zookeeper-headless"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
    labels    = merge(local.common_labels, { "app" = "zookeeper" })
  }

  spec {
    cluster_ip = "None"

    port {
      name = "client"
      port = 2181
    }

    port {
      name = "follower"
      port = 2888
    }

    port {
      name = "election"
      port = 3888
    }

    selector = {
      app = "zookeeper"
    }
  }
}

# Service ClusterIP para ClickHouse
resource "kubernetes_service" "clickhouse" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
    labels    = local.common_labels
    annotations = {
      "neural-hive.io/service-type" = "analytics"
    }
  }

  spec {
    type = "ClusterIP"

    port {
      name        = "http"
      port        = 8123
      target_port = 8123
      protocol    = "TCP"
    }

    port {
      name        = "native"
      port        = 9000
      target_port = 9000
      protocol    = "TCP"
    }

    dynamic "port" {
      for_each = var.enable_metrics ? [1] : []
      content {
        name        = "metrics"
        port        = 9363
        target_port = 9363
        protocol    = "TCP"
      }
    }

    selector = {
      "app.kubernetes.io/name"     = "clickhouse"
      "app.kubernetes.io/instance" = var.cluster_name
    }
  }

  depends_on = [kubernetes_manifest.clickhouse_installation]
}

# PodDisruptionBudget
resource "kubernetes_pod_disruption_budget_v1" "clickhouse" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    min_available = var.shards > 1 ? var.shards : 1

    selector {
      match_labels = {
        "app.kubernetes.io/name"     = "clickhouse"
        "app.kubernetes.io/instance" = var.cluster_name
      }
    }
  }

  depends_on = [kubernetes_manifest.clickhouse_installation]
}
