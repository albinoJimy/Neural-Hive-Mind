output "namespace" {
  description = "Namespace onde a stack de observabilidade foi instalada"
  value       = kubernetes_namespace.observability.metadata[0].name
}

output "prometheus_url" {
  description = "URL interna do Prometheus"
  value       = "http://prometheus-stack-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090"
}

output "grafana_url" {
  description = "URL interna do Grafana"
  value       = "http://grafana.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:3000"
}

output "grafana_external_url" {
  description = "URL externa do Grafana (via LoadBalancer/Ingress)"
  value       = var.enable_grafana_ingress ? "https://grafana.neural-hive.local" : "Port-forward para http://localhost:3000"
}

output "jaeger_url" {
  description = "URL interna do Jaeger Query"
  value       = "http://jaeger-query.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:16686"
}

output "jaeger_external_url" {
  description = "URL externa do Jaeger (via LoadBalancer/Ingress)"
  value       = var.enable_jaeger_ingress ? "https://jaeger.neural-hive.local" : "Port-forward para http://localhost:16686"
}

output "alertmanager_url" {
  description = "URL interna do AlertManager"
  value       = "http://prometheus-stack-alertmanager.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9093"
}

output "otel_collector_endpoint" {
  description = "Endpoint OTLP do OpenTelemetry Collector"
  value = {
    grpc = "opentelemetry-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:4317"
    http = "opentelemetry-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:4318"
  }
}

output "otel_collector_metrics_endpoint" {
  description = "Endpoint de métricas do OpenTelemetry Collector"
  value       = "http://opentelemetry-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:8888/metrics"
}

output "admin_credentials" {
  description = "Credenciais administrativas"
  value = {
    grafana_admin_user     = "admin"
    grafana_admin_password = var.grafana_admin_password
  }
  sensitive = true
}

output "service_endpoints" {
  description = "Endpoints de serviços para configuração de aplicações"
  value = {
    prometheus = {
      service = "prometheus-kube-prometheus-prometheus"
      port    = 9090
    }
    grafana = {
      service = "prometheus-grafana"
      port    = 80
    }
    jaeger_collector = {
      service = "jaeger-collector"
      grpc_port = 14250
      http_port = 14268
    }
    jaeger_query = {
      service = "jaeger-query"
      port    = 16686
    }
    otel_collector = {
      service = "opentelemetry-collector"
      otlp_grpc_port = 4317
      otlp_http_port = 4318
      metrics_port   = 8888
      health_port    = 13133
    }
  }
}

output "monitoring_labels" {
  description = "Labels para identificar serviços monitorados"
  value = {
    service_monitor = {
      "neural.hive/metrics" = "enabled"
    }
    pod_monitor = {
      "neural.hive/instrumented" = "true"
    }
    slo_monitoring = {
      "neural.hive/slo" = "enabled"
    }
  }
}

output "correlation_config" {
  description = "Configuração para correlação distribuída"
  value = {
    intent_id_header = "X-Neural-Hive-Intent-ID"
    plan_id_header   = "X-Neural-Hive-Plan-ID"
    domain_header    = "X-Neural-Hive-Domain"
    user_id_header   = "X-Neural-Hive-User-ID"
    baggage_keys = {
      intent_id = "neural.hive.intent.id"
      plan_id   = "neural.hive.plan.id"
      domain    = "neural.hive.domain"
      user_id   = "neural.hive.user.id"
    }
  }
}

output "slo_config" {
  description = "Configuração de SLOs do Neural Hive-Mind"
  value = {
    barramento_latency_ms = 150
    availability_percent  = 99.9
    plan_generation_ms    = 120
    capture_latency_ms    = 200
    error_budget_burn_rate = {
      fast   = 14.4  # 1 hour
      slow   = 1.0   # 6 hours
    }
  }
}

output "api_keys" {
  description = "API keys para integração externa"
  value = {
    prometheus_api = "http://prometheus-kube-prometheus-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090/api/v1/"
    grafana_api    = "http://prometheus-grafana.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local/api/"
  }
}

output "dashboard_urls" {
  description = "URLs dos dashboards principais"
  value = {
    neural_hive_overview      = "/d/neural-hive-overview/neural-hive-overview"
    fluxo_a_captura          = "/d/fluxo-a-captura/fluxo-a-captura-intencoes"
    fluxo_b_geracao          = "/d/fluxo-b-geracao/fluxo-b-geracao-planos"
    fluxo_c_orquestracao     = "/d/fluxo-c-orq/fluxo-c-orquestracao"
    fluxo_d_observabilidade  = "/d/fluxo-d-obs/fluxo-d-observabilidade"
    fluxo_e_autocura         = "/d/fluxo-e-autocura/fluxo-e-autocura"
    fluxo_f_experimentos     = "/d/fluxo-f-exp/fluxo-f-experimentos"
    slos_error_budgets       = "/d/slos-eb/slos-error-budgets"
    kubernetes_infra         = "/d/k8s-infra/kubernetes-infrastructure"
    istio_mesh              = "/d/istio-mesh/istio-service-mesh"
  }
}

output "health_check_endpoints" {
  description = "Endpoints de health check para validação"
  value = {
    prometheus     = "http://prometheus-kube-prometheus-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090/-/healthy"
    grafana        = "http://prometheus-grafana.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local/api/health"
    jaeger_query   = "http://jaeger-query.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:16687/"
    otel_collector = "http://opentelemetry-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:13133/"
    alertmanager   = "http://prometheus-kube-prometheus-alertmanager.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9093/-/healthy"
  }
}

# Outputs condicionais baseados em configuração
output "thanos_config" {
  description = "Configuração do Thanos (se habilitado)"
  value = var.enable_thanos ? {
    query_url      = "http://thanos-query.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090"
    store_gateway  = "thanos-store-gateway.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:10901"
    compactor_url  = "thanos-compactor.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:10902"
  } : null
}

output "backup_config" {
  description = "Configuração de backup"
  value = var.backup_config.enabled ? {
    schedule        = var.backup_schedule
    retention_days  = var.backup_config.retention_days
    storage_class   = var.backup_config.storage_class
    backup_location = var.backup_config.backup_location
  } : null
}

# Outputs adicionais para integração completa com scripts
output "deployment_info" {
  description = "Informações do deployment para scripts"
  value = {
    namespace           = kubernetes_namespace.observability.metadata[0].name
    environment         = var.environment
    cluster_name        = var.cluster_name
    helm_releases = {
      prometheus_stack        = helm_release.prometheus_stack.name
      grafana               = helm_release.grafana.name
      jaeger                = helm_release.jaeger.name
      opentelemetry_collector = helm_release.opentelemetry_collector.name
      loki                  = var.enable_loki ? helm_release.loki[0].name : null
      tempo                 = var.enable_tempo ? helm_release.tempo[0].name : null
    }
    storage_class         = var.storage_class
    created_at           = timestamp()
  }
}

output "grafana_config" {
  description = "Configuração específica do Grafana para scripts"
  value = {
    admin_user           = "admin"
    admin_password       = var.grafana_admin_password
    internal_url         = "http://grafana.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local"
    api_url              = "http://grafana.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local/api"
    external_url         = var.enable_grafana_ingress ? "https://grafana.${var.grafana_domain}" : null
    datasources = {
      prometheus = "http://prometheus-stack-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090"
      jaeger     = "http://jaeger-query.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:16686"
      loki       = var.enable_loki ? "http://loki-gateway.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local" : null
      tempo      = var.enable_tempo ? "http://tempo-query-frontend.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:3200" : null
    }
    features_enabled = {
      loki                = var.enable_loki
      tempo               = var.enable_tempo
      alerting           = true
      public_dashboards  = true
      library_panels     = true
    }
  }
  sensitive = true
}

output "prometheus_config" {
  description = "Configuração específica do Prometheus para validação"
  value = {
    internal_url        = "http://prometheus-stack-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090"
    api_url            = "http://prometheus-stack-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090/api/v1"
    pushgateway_url    = "http://prometheus-prometheus-pushgateway.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9091"
    node_exporter_url  = "http://prometheus-prometheus-node-exporter.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9100"
    kube_state_metrics = "http://prometheus-kube-state-metrics.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:8080"
    service_monitors = {
      neural_hive_services = "neural.hive/metrics=enabled"
      neural_hive_pods    = "neural.hive/instrumented=true"
    }
    retention = {
      days = var.prometheus_retention_days
      size = var.prometheus_storage_size
    }
    exemplars_enabled = var.enable_exemplars
  }
}

output "jaeger_config" {
  description = "Configuração específica do Jaeger para validação"
  value = {
    query_url           = "http://jaeger-query.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:16686"
    collector_grpc      = "jaeger-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:14250"
    collector_http      = "jaeger-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:14268"
    agent_port          = 6831
    external_url        = var.enable_jaeger_ingress ? "https://jaeger.${var.jaeger_domain}" : null
    sampling_endpoint   = "http://jaeger-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:14268/api/sampling"
    storage_type        = var.jaeger_storage_type
    retention_days      = var.jaeger_retention_days
    deployment_strategy = var.jaeger_deployment_strategy
    otlp_enabled       = var.jaeger_enable_otlp
  }
}

output "alertmanager_config" {
  description = "Configuração específica do AlertManager"
  value = {
    internal_url    = "http://prometheus-stack-alertmanager.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9093"
    api_url         = "http://prometheus-stack-alertmanager.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9093/api/v1"
    cluster_url     = "http://prometheus-stack-alertmanager.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9094"
    webhook_configs = var.alertmanager_config
    receivers = [
      "neural-hive-critical",
      "neural-hive-slo",
      "neural-hive-experiencia",
      "neural-hive-cognicao",
      "neural-hive-orquestracao",
      "neural-hive-execucao",
      "neural-hive-resiliencia"
    ]
  }
}

output "validation_endpoints" {
  description = "Endpoints para validação da stack completa"
  value = {
    health_checks = {
      prometheus     = "http://prometheus-stack-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090/-/healthy"
      grafana        = "http://grafana.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local/api/health"
      jaeger_query   = "http://jaeger-query.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:16687/"
      jaeger_collector = "http://jaeger-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:14269/"
      otel_collector = "http://opentelemetry-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:13133/"
      alertmanager   = "http://prometheus-stack-alertmanager.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9093/-/healthy"
    }
    test_endpoints = {
      prometheus_targets = "http://prometheus-stack-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090/api/v1/targets"
      prometheus_rules   = "http://prometheus-stack-prometheus.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9090/api/v1/rules"
      grafana_datasources = "http://grafana.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local/api/datasources"
      jaeger_services    = "http://jaeger-query.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:16686/api/services"
      otel_metrics       = "http://opentelemetry-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:8888/metrics"
    }
  }
}

output "integration_config" {
  description = "Configuração para integração com aplicações Neural Hive-Mind"
  value = {
    instrumentation = {
      otel_exporter_otlp_endpoint = "http://opentelemetry-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:4317"
      otel_exporter_jaeger_endpoint = "http://jaeger-collector.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:14250"
      prometheus_pushgateway = "http://prometheus-prometheus-pushgateway.${kubernetes_namespace.observability.metadata[0].name}.svc.cluster.local:9091"
    }
    labels_required = {
      service_monitor = "neural.hive/metrics=enabled"
      pod_monitor     = "neural.hive/instrumented=true"
      neural_component = "neural.hive/component"
      neural_layer     = "neural.hive/layer"
      neural_domain    = "neural.hive/domain"
    }
    correlation_headers = {
      intent_id = "X-Neural-Hive-Intent-ID"
      plan_id   = "X-Neural-Hive-Plan-ID"
      domain    = "X-Neural-Hive-Domain"
      user_id   = "X-Neural-Hive-User-ID"
    }
    baggage_propagation = {
      intent_id = "neural.hive.intent.id"
      plan_id   = "neural.hive.plan.id"
      domain    = "neural.hive.domain"
      user_id   = "neural.hive.user.id"
    }
  }
}