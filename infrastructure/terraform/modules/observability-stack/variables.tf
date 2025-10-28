variable "namespace" {
  description = "Namespace para componentes de observabilidade"
  type        = string
  default     = "observability"
}

variable "prometheus_retention_days" {
  description = "Dias de retenção de dados do Prometheus"
  type        = number
  default     = 30
}

variable "prometheus_storage_size" {
  description = "Tamanho do storage para Prometheus"
  type        = string
  default     = "100Gi"
}

variable "grafana_admin_password" {
  description = "Senha do admin do Grafana"
  type        = string
  sensitive   = true
}

variable "jaeger_storage_type" {
  description = "Tipo de storage para Jaeger (memory, badger, elasticsearch, cassandra)"
  type        = string
  default     = "badger"

  validation {
    condition     = contains(["memory", "badger", "elasticsearch", "cassandra"], var.jaeger_storage_type)
    error_message = "Jaeger storage type deve ser: memory, badger, elasticsearch, ou cassandra."
  }
}

variable "jaeger_retention_days" {
  description = "Dias de retenção de traces no Jaeger"
  type        = number
  default     = 7
}

variable "otel_sampling_rate" {
  description = "Taxa de sampling do OpenTelemetry (0.0 a 1.0) - DEPRECATED: use environment_config.otel_collector.sampling_percentage"
  type        = number
  default     = 0.1

  validation {
    condition     = var.otel_sampling_rate >= 0.0 && var.otel_sampling_rate <= 1.0
    error_message = "Sampling rate deve estar entre 0.0 e 1.0."
  }
}

# External integrations
variable "slack_webhook_urls" {
  description = "URLs de webhooks do Slack por severidade"
  type = object({
    critical = string
    warning  = string
    info     = string
  })
  default = {
    critical = ""
    warning  = ""
    info     = ""
  }
  sensitive = true
}

variable "pagerduty_service_key" {
  description = "Chave de serviço do PagerDuty"
  type        = string
  default     = ""
  sensitive   = true
}

variable "servicenow_webhook_url" {
  description = "URL do webhook do ServiceNow"
  type        = string
  default     = ""
  sensitive   = true
}

variable "servicenow_api_token" {
  description = "Token de API do ServiceNow"
  type        = string
  default     = ""
  sensitive   = true
}

variable "thanos_remote_write_url" {
  description = "URL para remote write do Thanos"
  type        = string
  default     = ""
}

variable "elasticsearch_url" {
  description = "URL do Elasticsearch para Jaeger"
  type        = string
  default     = "http://elasticsearch.observability.svc.cluster.local:9200"
}

variable "postgresql_host" {
  description = "Host do PostgreSQL para Grafana"
  type        = string
  default     = "postgresql.observability.svc.cluster.local:5432"
}

variable "enable_thanos" {
  description = "Habilitar Thanos para long-term storage"
  type        = bool
  default     = false
}

variable "storage_class" {
  description = "Storage class para volumes persistentes"
  type        = string
  default     = "gp2"
}

variable "create_storage_class" {
  description = "Criar storage class customizada para observabilidade"
  type        = bool
  default     = false
}

variable "storage_provisioner" {
  description = "Provisioner para storage class customizada"
  type        = string
  default     = "ebs.csi.aws.com"
}

variable "backup_schedule" {
  description = "Schedule para backup de configurações (formato cron)"
  type        = string
  default     = "0 2 * * *"
}

variable "prometheus_operator_version" {
  description = "Versão do Prometheus Operator Helm chart"
  type        = string
  default     = "51.7.0"
}

variable "otel_collector_version" {
  description = "Versão do OpenTelemetry Collector Helm chart"
  type        = string
  default     = "0.66.0"
}

variable "jaeger_version" {
  description = "Versão do Jaeger Helm chart"
  type        = string
  default     = "3.0.10"
}

variable "grafana_version" {
  description = "Versão do Grafana Helm chart"
  type        = string
  default     = "7.0.0"
}

variable "loki_version" {
  description = "Versão do Loki Helm chart"
  type        = string
  default     = "2.16.0"
}

variable "grafana_domain" {
  description = "Domínio para acesso ao Grafana"
  type        = string
  default     = "neural-hive.local"
}

variable "environment" {
  description = "Ambiente (development, staging, production)"
  type        = string
  default     = "production"
}

variable "grafana_storage_size" {
  description = "Tamanho do storage para Grafana"
  type        = string
  default     = "10Gi"
}

variable "enable_loki" {
  description = "Habilitar Loki para logging"
  type        = bool
  default     = false
}

variable "enable_tempo" {
  description = "Habilitar Tempo para tracing"
  type        = bool
  default     = false
}

variable "loki_storage_size" {
  description = "Tamanho do storage para Loki"
  type        = string
  default     = "20Gi"
}

variable "loki_retention_days" {
  description = "Dias de retenção de logs no Loki"
  type        = number
  default     = 14
}

variable "loki_enable_promtail" {
  description = "Habilitar Promtail para coleta de logs"
  type        = bool
  default     = true
}

variable "loki_enable_fluent_bit" {
  description = "Habilitar Fluent Bit como alternativa ao Promtail"
  type        = bool
  default     = false
}

variable "enable_correlation_processing" {
  description = "Habilitar processamento de correlação no OTEL Collector"
  type        = bool
  default     = true
}

variable "correlation_headers" {
  description = "Headers para correlação de traces/métricas"
  type        = list(string)
  default = [
    "neural.hive.intent.id",
    "neural.hive.plan.id",
    "neural.hive.domain",
    "neural.hive.user.id"
  ]
}

variable "enable_exemplars" {
  description = "Habilitar exemplars nas métricas do Prometheus"
  type        = bool
  default     = true
}

variable "jaeger_deployment_strategy" {
  description = "Estratégia de deployment do Jaeger (allinone, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["allinone", "production"], var.jaeger_deployment_strategy)
    error_message = "Jaeger deployment strategy deve ser 'allinone' ou 'production'."
  }
}

variable "jaeger_enable_otlp" {
  description = "Habilitar receptor OTLP no Jaeger"
  type        = bool
  default     = true
}

variable "jaeger_sampling_strategies" {
  description = "Estratégias de sampling do Jaeger"
  type = object({
    default_strategy = object({
      type  = string
      param = number
    })
    per_service_strategies = list(object({
      service   = string
      type      = string
      param     = number
    }))
  })
  default = {
    default_strategy = {
      type  = "probabilistic"
      param = 0.1
    }
    per_service_strategies = [
      {
        service = "neural-hive-gateway"
        type    = "probabilistic"
        param   = 1.0
      }
    ]
  }
}

variable "tail_sampling_policies" {
  description = "Políticas de tail sampling para OTEL Collector"
  type = list(object({
    name = string
    type = string
    config = any
  }))
  default = [
    {
      name = "neural_hive_errors"
      type = "status_code"
      config = {
        status_codes = ["ERROR"]
      }
    },
    {
      name = "neural_hive_high_latency"
      type = "latency"
      config = {
        threshold_ms = 1000
      }
    },
    {
      name = "neural_hive_intent_sampling"
      type = "probabilistic"
      config = {
        sampling_percentage = 25
      }
    }
  ]
}

variable "otel_collector_resources" {
  description = "Recursos para OpenTelemetry Collector"
  type = object({
    limits = object({
      cpu    = string
      memory = string
    })
    requests = object({
      cpu    = string
      memory = string
    })
  })
  default = {
    limits = {
      cpu    = "1000m"
      memory = "2Gi"
    }
    requests = {
      cpu    = "500m"
      memory = "1Gi"
    }
  }
}

variable "jaeger_resources" {
  description = "Recursos para componentes do Jaeger"
  type = object({
    collector = object({
      limits = object({
        cpu    = string
        memory = string
      })
      requests = object({
        cpu    = string
        memory = string
      })
    })
    query = object({
      limits = object({
        cpu    = string
        memory = string
      })
      requests = object({
        cpu    = string
        memory = string
      })
    })
  })
  default = {
    collector = {
      limits = {
        cpu    = "500m"
        memory = "1Gi"
      }
      requests = {
        cpu    = "250m"
        memory = "512Mi"
      }
    }
    query = {
      limits = {
        cpu    = "500m"
        memory = "1Gi"
      }
      requests = {
        cpu    = "250m"
        memory = "512Mi"
      }
    }
  }
}

variable "grafana_resources" {
  description = "Recursos para Grafana"
  type = object({
    limits = object({
      cpu    = string
      memory = string
    })
    requests = object({
      cpu    = string
      memory = string
    })
  })
  default = {
    limits = {
      cpu    = "1000m"
      memory = "2Gi"
    }
    requests = {
      cpu    = "500m"
      memory = "1Gi"
    }
  }
}

variable "loki_resources" {
  description = "Recursos para componentes do Loki"
  type = object({
    loki = object({
      limits = object({
        cpu    = string
        memory = string
      })
      requests = object({
        cpu    = string
        memory = string
      })
    })
    promtail = object({
      limits = object({
        cpu    = string
        memory = string
      })
      requests = object({
        cpu    = string
        memory = string
      })
    })
  })
  default = {
    loki = {
      limits = {
        cpu    = "1000m"
        memory = "2Gi"
      }
      requests = {
        cpu    = "500m"
        memory = "1Gi"
      }
    }
    promtail = {
      limits = {
        cpu    = "200m"
        memory = "256Mi"
      }
      requests = {
        cpu    = "100m"
        memory = "128Mi"
      }
    }
  }
}

variable "high_availability" {
  description = "Configurações para alta disponibilidade"
  type = object({
    enabled           = bool
    prometheus_replicas = number
    grafana_replicas   = number
    alertmanager_replicas = number
  })
  default = {
    enabled           = true
    prometheus_replicas = 2
    grafana_replicas   = 2
    alertmanager_replicas = 3
  }
}

variable "branding_config" {
  description = "Configuração de branding para Neural Hive-Mind"
  type = object({
    company_name = string
    logo_url     = string
    theme_color  = string
  })
  default = {
    company_name = "Neural Hive-Mind"
    logo_url     = ""
    theme_color  = "#3f51b5"
  }
}

variable "security_config" {
  description = "Configurações de segurança"
  type = object({
    enable_rbac           = bool
    enable_network_policy = bool
    enable_pod_security   = bool
    tls_enabled          = bool
  })
  default = {
    enable_rbac           = true
    enable_network_policy = true
    enable_pod_security   = true
    tls_enabled          = true
  }
}

variable "backup_config" {
  description = "Configurações de backup"
  type = object({
    enabled           = bool
    storage_class     = string
    retention_days    = number
    backup_location   = string
  })
  default = {
    enabled         = true
    storage_class   = "gp2"
    retention_days  = 90
    backup_location = "s3://neural-hive-backups/observability"
  }
}

# Validation configuration
variable "validation_config" {
  description = "Configuração para validação da stack"
  type = object({
    health_check_interval = string
    slo_validation_enabled = bool
    correlation_tests_enabled = bool
    dashboard_tests_enabled = bool
  })
  default = {
    health_check_interval = "30s"
    slo_validation_enabled = true
    correlation_tests_enabled = true
    dashboard_tests_enabled = true
  }
}

variable "enable_grafana_ingress" {
  description = "Habilitar Ingress para Grafana"
  type        = bool
  default     = false
}

variable "enable_jaeger_ingress" {
  description = "Habilitar Ingress para Jaeger"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags para recursos"
  type        = map(string)
  default = {
    Environment = "production"
    Project     = "neural-hive-mind"
    Component   = "observability"
    ManagedBy   = "terraform"
    CostCenter  = "infrastructure"
    Owner       = "platform-team"
  }
}