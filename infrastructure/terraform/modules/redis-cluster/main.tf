# Redis Cluster Module para Neural Hive-Mind
# Implementa Redis Cluster usando Redis Operator para memória de curto prazo

terraform {
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
  redis_labels = merge(var.common_labels, {
    "app.kubernetes.io/name"       = "redis-cluster"
    "app.kubernetes.io/instance"   = var.cluster_name
    "app.kubernetes.io/component"  = "cache"
    "app.kubernetes.io/part-of"    = "neural-hive-mind"
    "neural-hive.io/layer"         = "memory"
    "neural-hive.io/data-classification" = "internal"
  })
}

# Redis Operator Namespace
resource "kubernetes_namespace" "redis_operator" {
  metadata {
    name = "redis-operator"
    labels = {
      "istio-injection" = "enabled"
      "name"            = "redis-operator"
    }
  }
}

# Redis Operator Helm Release
resource "helm_release" "redis_operator" {
  name       = "redis-operator"
  repository = "https://ot-redis-operator.github.io/helm-charts/"
  chart      = "redis-operator"
  version    = "0.15.1"
  namespace  = kubernetes_namespace.redis_operator.metadata[0].name

  values = [yamlencode({
    image = {
      tag = "v0.15.1"
    }
    resources = {
      requests = {
        cpu    = "100m"
        memory = "128Mi"
      }
      limits = {
        cpu    = "500m"
        memory = "256Mi"
      }
    }
    serviceAccount = {
      create = true
    }
    rbac = {
      create = true
    }
    # Integração com service mesh
    podAnnotations = {
      "sidecar.istio.io/inject" = "true"
    }
  })]

  depends_on = [kubernetes_namespace.redis_operator]
}

# Namespace para Redis Cluster
resource "kubernetes_namespace" "redis_cluster" {
  metadata {
    name = var.namespace
    labels = merge(local.redis_labels, {
      "istio-injection" = "enabled"
      "name"            = var.namespace
    })
  }
}

# Secret para autenticação Redis
resource "kubernetes_secret" "redis_auth" {
  metadata {
    name      = "${var.cluster_name}-auth"
    namespace = kubernetes_namespace.redis_cluster.metadata[0].name
    labels    = local.redis_labels
  }

  type = "Opaque"

  data = {
    password = base64encode(var.redis_password)
  }
}

# CA Certificate Secret para TLS
resource "kubernetes_secret" "redis_ca_cert" {
  count = var.tls_enabled ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-ca-cert"
    namespace = kubernetes_namespace.redis_cluster.metadata[0].name
    labels    = local.redis_labels
  }

  type = "kubernetes.io/tls"

  data = {
    "tls.crt" = base64encode(var.ca_cert)
    "tls.key" = base64encode(var.ca_key)
  }
}

# Redis Cluster CRD
resource "kubernetes_manifest" "redis_cluster" {
  manifest = {
    apiVersion = "redis.redis.opstreelabs.in/v1beta1"
    kind       = "RedisCluster"
    metadata = {
      name      = var.cluster_name
      namespace = kubernetes_namespace.redis_cluster.metadata[0].name
      labels    = local.redis_labels
    }
    spec = {
      clusterSize = var.cluster_size
      redisExporter = {
        enabled = var.enable_metrics
        image   = "quay.io/opstree/redis-exporter:1.44.0"
      }
      kubernetesConfig = {
        image           = "quay.io/opstree/redis:${var.redis_version}"
        imagePullPolicy = "IfNotPresent"
        resources = {
          requests = {
            cpu    = var.redis_cpu_request
            memory = var.redis_memory_request
          }
          limits = {
            cpu    = var.redis_cpu_limit
            memory = var.redis_memory_limit
          }
        }
        redisSecret = {
          name = kubernetes_secret.redis_auth.metadata[0].name
          key  = "password"
        }
        serviceAccountName = var.service_account_name
      }
      storage = {
        volumeClaimTemplate = {
          spec = {
            accessModes = ["ReadWriteOnce"]
            resources = {
              requests = {
                storage = var.storage_size
              }
            }
            storageClassName = var.storage_class
          }
        }
      }
      redisConfig = {
        # Configurações de TTL e memória
        "maxmemory-policy"     = var.memory_policy
        "timeout"              = "300"
        "tcp-keepalive"        = "60"
        "save"                 = var.enable_persistence ? "900 1 300 10 60 10000" : ""
        "appendonly"           = var.enable_persistence ? "yes" : "no"
        "appendfsync"          = "everysec"
        "auto-aof-rewrite-percentage" = "100"
        "auto-aof-rewrite-min-size"   = "64mb"
        # TTL padrão configurável via aplicação
        "notify-keyspace-events" = "Ex"
      }
      # TLS Configuration
      dynamic "TLS" {
        for_each = var.tls_enabled ? [1] : []
        content {
          enabled = true
          secret = {
            name = kubernetes_secret.redis_ca_cert[0].metadata[0].name
          }
        }
      }
      # Anti-affinity para distribuição multi-zona
      podAnnotations = merge(var.pod_annotations, {
        "sidecar.istio.io/inject" = "false"  # Redis não precisa de sidecar
      })
      affinity = {
        podAntiAffinity = {
          preferredDuringSchedulingIgnoredDuringExecution = [
            {
              weight = 100
              podAffinityTerm = {
                labelSelector = {
                  matchLabels = {
                    "app" = var.cluster_name
                  }
                }
                topologyKey = "topology.kubernetes.io/zone"
              }
            }
          ]
        }
      }
    }
  }

  depends_on = [
    helm_release.redis_operator,
    kubernetes_secret.redis_auth
  ]
}

# Service para acesso ao cluster
resource "kubernetes_service" "redis_cluster" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.redis_cluster.metadata[0].name
    labels    = local.redis_labels
    annotations = {
      "service.beta.kubernetes.io/aws-load-balancer-type" = "nlb"
      "neural-hive.io/service-type"                       = "cache"
      "redis.security/auth"                               = "required"
    }
  }

  spec {
    selector = {
      app = var.cluster_name
    }
    port {
      name        = "redis"
      port        = 6379
      target_port = 6379
      protocol    = "TCP"
    }
    type = "ClusterIP"
  }
}

# ConfigMap para scripts de manutenção
resource "kubernetes_config_map" "redis_maintenance" {
  metadata {
    name      = "${var.cluster_name}-maintenance"
    namespace = kubernetes_namespace.redis_cluster.metadata[0].name
    labels    = local.redis_labels
  }

  data = {
    "health-check.sh" = <<-EOT
      #!/bin/bash
      redis-cli -h ${var.cluster_name} -p 6379 -a $REDIS_PASSWORD ping
    EOT

    "cluster-info.sh" = <<-EOT
      #!/bin/bash
      redis-cli -h ${var.cluster_name} -p 6379 -a $REDIS_PASSWORD cluster info
    EOT

    "memory-usage.sh" = <<-EOT
      #!/bin/bash
      redis-cli -h ${var.cluster_name} -p 6379 -a $REDIS_PASSWORD info memory
    EOT
  }
}

# CronJob para backup automático se habilitado
resource "kubernetes_cron_job_v1" "redis_backup" {
  count = var.backup_enabled ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-backup"
    namespace = kubernetes_namespace.redis_cluster.metadata[0].name
    labels    = local.redis_labels
  }

  spec {
    schedule = var.backup_schedule
    job_template {
      metadata {
        labels = local.redis_labels
      }
      spec {
        template {
          metadata {
            labels = local.redis_labels
          }
          spec {
            container {
              name  = "redis-backup"
              image = "quay.io/opstree/redis:${var.redis_version}"
              command = [
                "/bin/bash",
                "-c",
                "redis-cli -h ${var.cluster_name} -p 6379 -a $REDIS_PASSWORD --rdb /backup/dump-$(date +%Y%m%d-%H%M%S).rdb"
              ]
              env {
                name = "REDIS_PASSWORD"
                value_from {
                  secret_key_ref {
                    name = kubernetes_secret.redis_auth.metadata[0].name
                    key  = "password"
                  }
                }
              }
              volume_mount {
                name       = "backup-storage"
                mount_path = "/backup"
              }
            }
            volume {
              name = "backup-storage"
              persistent_volume_claim {
                claim_name = "${var.cluster_name}-backup-pvc"
              }
            }
            restart_policy = "OnFailure"
          }
        }
      }
    }
  }
}

# PVC para backups
resource "kubernetes_persistent_volume_claim" "backup_pvc" {
  count = var.backup_enabled ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-backup-pvc"
    namespace = kubernetes_namespace.redis_cluster.metadata[0].name
    labels    = local.redis_labels
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class
    resources {
      requests = {
        storage = var.backup_storage_size
      }
    }
  }
}