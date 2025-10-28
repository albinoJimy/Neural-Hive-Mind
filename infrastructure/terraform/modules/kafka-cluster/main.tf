terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }
}

# Namespace for Kafka cluster
resource "kubernetes_namespace" "kafka" {
  metadata {
    name = var.cluster_name
    labels = {
      "app.kubernetes.io/name"       = "kafka"
      "app.kubernetes.io/instance"   = var.cluster_name
      "app.kubernetes.io/version"    = var.kafka_version
      "app.kubernetes.io/managed-by" = "terraform"
      "neural-hive-mind.org/layer"   = "infrastructure"
      "istio-injection"              = "enabled"
    }
  }
}

# Strimzi Operator deployment
resource "helm_release" "strimzi_operator" {
  name       = "strimzi-cluster-operator"
  repository = "https://strimzi.io/charts/"
  chart      = "strimzi-kafka-operator"
  version    = "0.38.0"
  namespace  = kubernetes_namespace.kafka.metadata[0].name

  values = [yamlencode({
    watchNamespaces = [kubernetes_namespace.kafka.metadata[0].name]
    image = {
      registry   = "quay.io"
      repository = "strimzi"
      tag        = "0.38.0"
    }
    resources = {
      limits = {
        memory = "512Mi"
        cpu    = "500m"
      }
      requests = {
        memory = "256Mi"
        cpu    = "200m"
      }
    }
    createGlobalResources = false
    logLevel = "INFO"
  })]

  depends_on = [kubernetes_namespace.kafka]
}

# Kafka cluster configuration
resource "kubernetes_manifest" "kafka_cluster" {
  manifest = {
    apiVersion = "kafka.strimzi.io/v1beta2"
    kind       = "Kafka"
    metadata = {
      name      = var.cluster_name
      namespace = kubernetes_namespace.kafka.metadata[0].name
      labels = {
        "app.kubernetes.io/name"       = "kafka"
        "app.kubernetes.io/instance"   = var.cluster_name
        "app.kubernetes.io/version"    = var.kafka_version
        "neural-hive-mind.org/layer"   = "infrastructure"
      }
    }
    spec = {
      kafka = {
        version  = var.kafka_version
        replicas = var.replicas
        listeners = [
          {
            name = "plain"
            port = 9092
            type = "internal"
            tls  = false
          },
          {
            name = "tls"
            port = 9093
            type = "internal"
            tls  = true
            authentication = {
              type = "tls"
            }
          }
        ]
        authorization = {
          type = "simple"
        }
        config = {
          # Exactly-once delivery configurations
          "enable.idempotence"                       = "true"
          "acks"                                     = "all"
          "retries"                                  = "2147483647"
          "max.in.flight.requests.per.connection"   = "5"
          "min.insync.replicas"                      = "2"
          "default.replication.factor"               = var.default_replication_factor
          "offsets.topic.replication.factor"        = var.default_replication_factor
          "transaction.state.log.replication.factor" = var.transaction_state_log_replication_factor
          "transaction.state.log.min.isr"           = var.transaction_state_log_min_isr

          # Performance optimizations
          "num.network.threads"                     = "8"
          "num.io.threads"                          = "16"
          "socket.send.buffer.bytes"                = "102400"
          "socket.receive.buffer.bytes"             = "102400"
          "socket.request.max.bytes"                = "104857600"
          "num.partitions"                          = "6"
          "num.recovery.threads.per.data.dir"      = "1"
          "log.retention.hours"                     = var.log_retention_hours
          "log.segment.bytes"                       = "1073741824"
          "log.retention.check.interval.ms"        = "300000"
          "log.cleanup.policy"                      = "delete"
          "compression.type"                        = "snappy"

          # Security configurations
          "ssl.client.auth"                         = "required"
          "ssl.protocol"                            = "TLSv1.3"
          "ssl.enabled.protocols"                   = "TLSv1.3"
          "ssl.cipher.suites"                       = "TLS_AES_256_GCM_SHA384,TLS_CHACHA20_POLY1305_SHA256"

          # Monitoring
          "jmx.port"                                = "9999"
        }
        storage = {
          type        = "persistent-claim"
          size        = var.storage_size
          class       = var.storage_class
          deleteClaim = false
        }
        resources = {
          requests = {
            memory = "2Gi"
            cpu    = "1000m"
          }
          limits = {
            memory = "4Gi"
            cpu    = "2000m"
          }
        }
        jvmOptions = {
          "-Xms" = "1g"
          "-Xmx" = "2g"
        }
        template = {
          pod = {
            securityContext = {
              runAsUser    = 1001
              runAsGroup   = 1001
              fsGroup      = 1001
              runAsNonRoot = true
            }
            affinity = {
              podAntiAffinity = {
                requiredDuringSchedulingIgnoredDuringExecution = [
                  {
                    labelSelector = {
                      matchExpressions = [
                        {
                          key      = "app.kubernetes.io/name"
                          operator = "In"
                          values   = ["kafka"]
                        }
                      ]
                    }
                    topologyKey = "kubernetes.io/hostname"
                  }
                ]
              }
            }
            tolerations = [
              {
                key      = "neural-hive-mind.org/kafka"
                operator = "Equal"
                value    = "true"
                effect   = "NoSchedule"
              }
            ]
          }
        }
        metricsConfig = var.enable_metrics ? {
          type = "jmxPrometheusExporter"
          valueFrom = {
            configMapKeyRef = {
              name = kubernetes_config_map.kafka_metrics[0].metadata[0].name
              key  = "kafka-metrics-config.yml"
            }
          }
        } : null
      }
      zookeeper = {
        replicas = 3
        storage = {
          type        = "persistent-claim"
          size        = "10Gi"
          class       = var.storage_class
          deleteClaim = false
        }
        resources = {
          requests = {
            memory = "1Gi"
            cpu    = "500m"
          }
          limits = {
            memory = "2Gi"
            cpu    = "1000m"
          }
        }
        jvmOptions = {
          "-Xms" = "512m"
          "-Xmx" = "1g"
        }
        template = {
          pod = {
            securityContext = {
              runAsUser    = 1001
              runAsGroup   = 1001
              fsGroup      = 1001
              runAsNonRoot = true
            }
            affinity = {
              podAntiAffinity = {
                requiredDuringSchedulingIgnoredDuringExecution = [
                  {
                    labelSelector = {
                      matchExpressions = [
                        {
                          key      = "app.kubernetes.io/name"
                          operator = "In"
                          values   = ["zookeeper"]
                        }
                      ]
                    }
                    topologyKey = "kubernetes.io/hostname"
                  }
                ]
              }
            }
          }
        }
        metricsConfig = var.enable_metrics ? {
          type = "jmxPrometheusExporter"
          valueFrom = {
            configMapKeyRef = {
              name = kubernetes_config_map.zookeeper_metrics[0].metadata[0].name
              key  = "zookeeper-metrics-config.yml"
            }
          }
        } : null
      }
      entityOperator = {
        topicOperator = {
          resources = {
            requests = {
              memory = "512Mi"
              cpu    = "200m"
            }
            limits = {
              memory = "1Gi"
              cpu    = "500m"
            }
          }
        }
        userOperator = {
          resources = {
            requests = {
              memory = "512Mi"
              cpu    = "200m"
            }
            limits = {
              memory = "1Gi"
              cpu    = "500m"
            }
          }
        }
      }
      cruiseControl = var.enable_cruise_control ? {
        metricsConfig = {
          type = "jmxPrometheusExporter"
          valueFrom = {
            configMapKeyRef = {
              name = kubernetes_config_map.cruise_control_metrics[0].metadata[0].name
              key  = "cruise-control-metrics-config.yml"
            }
          }
        }
        resources = {
          requests = {
            memory = "1Gi"
            cpu    = "500m"
          }
          limits = {
            memory = "2Gi"
            cpu    = "1000m"
          }
        }
      } : null
    }
  }

  depends_on = [
    helm_release.strimzi_operator,
    kubernetes_config_map.kafka_metrics,
    kubernetes_config_map.zookeeper_metrics,
    kubernetes_config_map.cruise_control_metrics
  ]
}

# Metrics configuration for Kafka
resource "kubernetes_config_map" "kafka_metrics" {
  count = var.enable_metrics ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-kafka-metrics"
    namespace = kubernetes_namespace.kafka.metadata[0].name
  }

  data = {
    "kafka-metrics-config.yml" = file("${path.module}/configs/kafka-metrics-config.yml")
  }

  depends_on = [kubernetes_namespace.kafka]
}

# Metrics configuration for Zookeeper
resource "kubernetes_config_map" "zookeeper_metrics" {
  count = var.enable_metrics ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-zookeeper-metrics"
    namespace = kubernetes_namespace.kafka.metadata[0].name
  }

  data = {
    "zookeeper-metrics-config.yml" = file("${path.module}/configs/zookeeper-metrics-config.yml")
  }

  depends_on = [kubernetes_namespace.kafka]
}

# Metrics configuration for Cruise Control
resource "kubernetes_config_map" "cruise_control_metrics" {
  count = var.enable_cruise_control && var.enable_metrics ? 1 : 0

  metadata {
    name      = "${var.cluster_name}-cruise-control-metrics"
    namespace = kubernetes_namespace.kafka.metadata[0].name
  }

  data = {
    "cruise-control-metrics-config.yml" = file("${path.module}/configs/cruise-control-metrics-config.yml")
  }

  depends_on = [kubernetes_namespace.kafka]
}

# Network policy for Kafka cluster
resource "kubernetes_network_policy" "kafka_network_policy" {
  metadata {
    name      = "${var.cluster_name}-network-policy"
    namespace = kubernetes_namespace.kafka.metadata[0].name
  }

  spec {
    pod_selector {
      match_labels = {
        "app.kubernetes.io/name" = "kafka"
      }
    }

    policy_types = ["Ingress", "Egress"]

    # Ingress rules
    ingress {
      from {
        namespace_selector {
          match_labels = {
            "neural-hive-mind.org/kafka-access" = "enabled"
          }
        }
      }
      ports {
        port     = "9092"
        protocol = "TCP"
      }
      ports {
        port     = "9093"
        protocol = "TCP"
      }
    }

    # Allow Kafka inter-broker communication
    ingress {
      from {
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = "kafka"
          }
        }
      }
    }

    # Allow Zookeeper communication
    ingress {
      from {
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = "zookeeper"
          }
        }
      }
    }

    # Egress rules
    egress {
      to {
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = "zookeeper"
          }
        }
      }
    }

    egress {
      to {
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = "kafka"
          }
        }
      }
    }

    # Allow DNS resolution
    egress {
      to {
        namespace_selector {
          match_labels = {
            name = "kube-system"
          }
        }
      }
      ports {
        port     = "53"
        protocol = "UDP"
      }
    }
  }

  depends_on = [kubernetes_namespace.kafka]
}

# Pod Disruption Budget for Kafka
resource "kubernetes_pod_disruption_budget_v1" "kafka_pdb" {
  metadata {
    name      = "${var.cluster_name}-kafka-pdb"
    namespace = kubernetes_namespace.kafka.metadata[0].name
  }

  spec {
    min_available = "2"
    selector {
      match_labels = {
        "app.kubernetes.io/name" = "kafka"
      }
    }
  }

  depends_on = [kubernetes_namespace.kafka]
}

# Pod Disruption Budget for Zookeeper
resource "kubernetes_pod_disruption_budget_v1" "zookeeper_pdb" {
  metadata {
    name      = "${var.cluster_name}-zookeeper-pdb"
    namespace = kubernetes_namespace.kafka.metadata[0].name
  }

  spec {
    min_available = "2"
    selector {
      match_labels = {
        "app.kubernetes.io/name" = "zookeeper"
      }
    }
  }

  depends_on = [kubernetes_namespace.kafka]
}