terraform {
  required_version = ">= 1.0"
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

# Namespace para stack de observabilidade
resource "kubernetes_namespace" "observability" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name"       = "observability"
      "app.kubernetes.io/component"  = "monitoring"
      "neural.hive/layer"           = "observabilidade"
      "istio-injection"             = "enabled"
    }
  }
}

# Prometheus Operator com CRDs
resource "helm_release" "prometheus_operator" {
  name       = "prometheus-operator"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  namespace  = kubernetes_namespace.observability.metadata[0].name
  version    = var.prometheus_operator_version

  values = [
    templatefile("${path.module}/templates/prometheus-values.yaml.tpl", {
      retention_days          = var.prometheus_retention_days
      storage_class          = var.storage_class
      storage_size           = var.prometheus_storage_size
      grafana_admin_password = var.grafana_admin_password
      enable_thanos          = var.enable_thanos
      alertmanager_config    = var.alertmanager_config
    })
  ]

  depends_on = [kubernetes_namespace.observability]
}

# OpenTelemetry Collector - Enhanced with correlation processing
resource "helm_release" "opentelemetry_collector" {
  name       = "opentelemetry-collector"
  repository = "https://open-telemetry.github.io/opentelemetry-helm-charts"
  chart      = "opentelemetry-collector"
  namespace  = kubernetes_namespace.observability.metadata[0].name
  version    = var.otel_collector_version

  values = [
    templatefile("${path.module}/templates/otel-collector-values.yaml.tpl", {
      sampling_rate           = var.otel_sampling_rate
      prometheus_url          = "prometheus-kube-prometheus-prometheus:9090"
      jaeger_endpoint         = "jaeger-collector:14250"
      loki_endpoint          = var.enable_loki ? "loki-gateway:80" : ""
      resources              = var.otel_collector_resources
      enable_correlation     = var.enable_correlation_processing
      correlation_headers    = var.correlation_headers
      enable_exemplars       = var.enable_exemplars
      tail_sampling_policies = var.tail_sampling_policies
    })
  ]

  depends_on = [
    kubernetes_namespace.observability,
    helm_release.prometheus_operator,
    helm_release.jaeger
  ]
}

# Jaeger Tracing - Updated to use new upstream chart version
resource "helm_release" "jaeger" {
  name       = "jaeger"
  repository = "https://jaegertracing.github.io/helm-charts"
  chart      = "jaeger"
  namespace  = kubernetes_namespace.observability.metadata[0].name
  version    = var.jaeger_version

  values = [
    templatefile("${path.module}/templates/jaeger-values.yaml.tpl", {
      deployment_strategy = var.jaeger_deployment_strategy
      storage_type       = var.jaeger_storage_type
      storage_class      = var.storage_class
      retention_days     = var.jaeger_retention_days
      resources          = var.jaeger_resources
      enable_otlp        = var.jaeger_enable_otlp
      sampling_strategies = var.jaeger_sampling_strategies
    })
  ]

  depends_on = [kubernetes_namespace.observability]
}

# Grafana Dashboard - Separate Helm release for better control
resource "helm_release" "grafana" {
  name       = "grafana"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "grafana"
  namespace  = kubernetes_namespace.observability.metadata[0].name
  version    = var.grafana_version

  values = [
    templatefile("${path.module}/templates/grafana-values.yaml.tpl", {
      admin_password      = var.grafana_admin_password
      domain             = var.grafana_domain
      environment        = var.environment
      storage_class      = var.storage_class
      storage_size       = var.grafana_storage_size
      replicas           = var.high_availability.grafana_replicas
      enable_ingress     = var.enable_grafana_ingress
      enable_loki        = var.enable_loki
      enable_tempo       = var.enable_tempo
      resources          = var.grafana_resources
      security_enabled   = var.security_config.enable_pod_security
    })
  ]

  depends_on = [
    kubernetes_namespace.observability,
    helm_release.prometheus_operator
  ]
}

# Loki Logging (Optional)
resource "helm_release" "loki" {
  count      = var.enable_loki ? 1 : 0
  name       = "loki"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "loki-stack"
  namespace  = kubernetes_namespace.observability.metadata[0].name
  version    = var.loki_version

  values = [
    templatefile("${path.module}/templates/loki-values.yaml.tpl", {
      storage_class      = var.storage_class
      storage_size       = var.loki_storage_size
      retention_days     = var.loki_retention_days
      resources          = var.loki_resources
      enable_promtail    = var.loki_enable_promtail
      enable_fluent_bit  = var.loki_enable_fluent_bit
    })
  ]

  depends_on = [kubernetes_namespace.observability]
}

# ServiceMonitor para métricas customizadas do Neural Hive-Mind
resource "kubernetes_manifest" "neural_hive_service_monitor" {
  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "ServiceMonitor"
    metadata = {
      name      = "neural-hive-metrics"
      namespace = kubernetes_namespace.observability.metadata[0].name
      labels = {
        "app.kubernetes.io/name" = "neural-hive-metrics"
        "neural.hive/component"  = "monitoring"
      }
    }
    spec = {
      selector = {
        matchLabels = {
          "neural.hive/metrics" = "enabled"
        }
      }
      namespaceSelector = {
        any = true
      }
      endpoints = [
        {
          port     = "metrics"
          interval = "30s"
          path     = "/metrics"
          honorLabels = true
        }
      ]
    }
  }

  depends_on = [helm_release.prometheus_operator]
}

# SLO rules are managed via file-based approach in monitoring/alerts/slo-alerts.yaml
# Applied by deploy-observability.sh script to avoid duplication

# Storage Classes para componentes que precisam de storage persistente
resource "kubernetes_storage_class" "observability_ssd" {
  count = var.create_storage_class ? 1 : 0

  metadata {
    name = "${var.namespace}-ssd"
    labels = {
      "app.kubernetes.io/name"     = "observability-storage"
      "neural.hive/component"      = "storage"
    }
  }

  storage_provisioner    = var.storage_provisioner
  reclaim_policy        = "Retain"
  volume_binding_mode   = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    type = "gp3"
    iops = "3000"
    throughput = "125"
    encrypted  = "true"
  }
}

# ConfigMap para configurações customizadas do Neural Hive-Mind
resource "kubernetes_config_map" "neural_hive_configs" {
  metadata {
    name      = "neural-hive-observability-config"
    namespace = kubernetes_namespace.observability.metadata[0].name
    labels = {
      "app.kubernetes.io/name"     = "neural-hive-config"
      "neural.hive/component"      = "configuration"
    }
  }

  data = {
    "correlation.yaml" = yamlencode({
      correlation = {
        intent_id_header = "X-Neural-Hive-Intent-ID"
        plan_id_header   = "X-Neural-Hive-Plan-ID"
        domain_header    = "X-Neural-Hive-Domain"
        user_id_header   = "X-Neural-Hive-User-ID"
      }
      sampling = {
        default_rate     = var.otel_sampling_rate
        high_value_rate  = 1.0
        error_rate       = 1.0
      }
      slos = {
        barramento_latency_ms = 150
        availability_percent  = 99.9
        plan_generation_ms    = 120
        capture_latency_ms    = 200
      }
    })
  }
}

# PodMonitor para monitoramento de pods com instrumentação OpenTelemetry
resource "kubernetes_manifest" "neural_hive_pod_monitor" {
  manifest = {
    apiVersion = "monitoring.coreos.com/v1"
    kind       = "PodMonitor"
    metadata = {
      name      = "neural-hive-pods"
      namespace = kubernetes_namespace.observability.metadata[0].name
      labels = {
        "app.kubernetes.io/name" = "neural-hive-pod-monitor"
        "neural.hive/component"  = "monitoring"
      }
    }
    spec = {
      selector = {
        matchLabels = {
          "neural.hive/instrumented" = "true"
        }
      }
      namespaceSelector = {
        any = true
      }
      podMetricsEndpoints = [
        {
          port     = "metrics"
          interval = "15s"
          path     = "/metrics"
          honorLabels = true
        }
      ]
    }
  }

  depends_on = [helm_release.prometheus_operator]
}