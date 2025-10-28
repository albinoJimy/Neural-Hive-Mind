output "cluster_name" {
  description = "Nome do cluster Kafka"
  value       = var.cluster_name
}

output "namespace" {
  description = "Namespace do cluster Kafka"
  value       = kubernetes_namespace.kafka.metadata[0].name
}

output "bootstrap_servers" {
  description = "Endereços dos bootstrap servers Kafka"
  value       = "${var.cluster_name}-kafka-bootstrap.${kubernetes_namespace.kafka.metadata[0].name}.svc.cluster.local:9092"
}

output "bootstrap_servers_tls" {
  description = "Endereços dos bootstrap servers Kafka com TLS"
  value       = "${var.cluster_name}-kafka-bootstrap.${kubernetes_namespace.kafka.metadata[0].name}.svc.cluster.local:9093"
}

output "cluster_ca_cert_secret" {
  description = "Nome do secret contendo certificado CA do cluster"
  value       = "${var.cluster_name}-cluster-ca-cert"
}

output "admin_credentials_secret" {
  description = "Nome do secret contendo credenciais de admin"
  value       = "${var.cluster_name}-admin-credentials"
}

output "zookeeper_connect" {
  description = "String de conexão do Zookeeper"
  value       = "${var.cluster_name}-zookeeper-client.${kubernetes_namespace.kafka.metadata[0].name}.svc.cluster.local:2181"
}

output "metrics_endpoints" {
  description = "Endpoints de métricas Prometheus"
  value = var.enable_metrics ? {
    kafka      = "${var.cluster_name}-kafka-brokers.${kubernetes_namespace.kafka.metadata[0].name}.svc.cluster.local:9308"
    zookeeper  = "${var.cluster_name}-zookeeper-nodes.${kubernetes_namespace.kafka.metadata[0].name}.svc.cluster.local:9308"
    cruise_control = var.enable_cruise_control ? "${var.cluster_name}-cruise-control.${kubernetes_namespace.kafka.metadata[0].name}.svc.cluster.local:9308" : null
  } : null
}

output "schema_registry_url" {
  description = "URL do Schema Registry (se habilitado)"
  value       = var.enable_schema_registry ? "http://${var.cluster_name}-schema-registry.${kubernetes_namespace.kafka.metadata[0].name}.svc.cluster.local:8081" : null
}

output "kafka_version" {
  description = "Versão do Kafka deployada"
  value       = var.kafka_version
}

output "replicas" {
  description = "Número de réplicas Kafka"
  value       = var.replicas
}

output "storage_size" {
  description = "Tamanho do storage por broker"
  value       = var.storage_size
}

output "environment" {
  description = "Ambiente do deployment"
  value       = var.environment
}

output "exactly_once_config" {
  description = "Configurações de exactly-once delivery"
  value = {
    enable_idempotence                       = "true"
    acks                                     = "all"
    min_insync_replicas                      = "2"
    transaction_state_log_replication_factor = var.transaction_state_log_replication_factor
    transaction_state_log_min_isr           = var.transaction_state_log_min_isr
  }
}

output "security_config" {
  description = "Configurações de segurança"
  value = {
    tls_enabled         = var.enable_tls
    sasl_enabled        = var.enable_sasl
    ssl_protocol        = var.ssl_protocol
    client_auth_required = "true"
  }
}

output "performance_config" {
  description = "Configurações de performance"
  value = {
    num_network_threads        = var.num_network_threads
    num_io_threads            = var.num_io_threads
    socket_send_buffer_bytes   = var.socket_send_buffer_bytes
    socket_receive_buffer_bytes = var.socket_receive_buffer_bytes
    num_partitions            = var.num_partitions
    compression_type          = var.compression_type
  }
}

output "monitoring_config" {
  description = "Configurações de monitoramento"
  value = var.enable_metrics ? {
    metrics_enabled = true
    jmx_port        = var.metrics_port
    jmx_enabled     = var.enable_jmx
    cruise_control_enabled = var.enable_cruise_control
  } : {
    metrics_enabled = false
  }
}

output "resource_limits" {
  description = "Limites de recursos configurados"
  value = {
    kafka = {
      memory_request = var.kafka_memory_request
      memory_limit   = var.kafka_memory_limit
      cpu_request    = var.kafka_cpu_request
      cpu_limit      = var.kafka_cpu_limit
      heap_size      = var.kafka_heap_size
    }
    zookeeper = {
      memory_request = var.zookeeper_memory_request
      memory_limit   = var.zookeeper_memory_limit
      cpu_request    = var.zookeeper_cpu_request
      cpu_limit      = var.zookeeper_cpu_limit
      heap_size      = var.zookeeper_heap_size
    }
  }
}

output "network_policy_name" {
  description = "Nome da NetworkPolicy criada"
  value       = kubernetes_network_policy.kafka_network_policy.metadata[0].name
}

output "pod_disruption_budgets" {
  description = "Pod Disruption Budgets criados"
  value = {
    kafka     = kubernetes_pod_disruption_budget_v1.kafka_pdb.metadata[0].name
    zookeeper = kubernetes_pod_disruption_budget_v1.zookeeper_pdb.metadata[0].name
  }
}

output "strimzi_operator_version" {
  description = "Versão do Strimzi Operator deployada"
  value       = "0.38.0"
}

output "tags" {
  description = "Tags aplicadas aos recursos"
  value       = var.tags
}