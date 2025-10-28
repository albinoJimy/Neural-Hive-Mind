variable "cluster_name" {
  description = "Name of the Kafka cluster"
  type        = string
  default     = "neural-hive-kafka"

  validation {
    condition     = length(var.cluster_name) <= 63 && can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.cluster_name))
    error_message = "Cluster name must be a valid Kubernetes name (lowercase, alphanumeric, hyphens, max 63 chars)."
  }
}

variable "kafka_version" {
  description = "Kafka version to deploy"
  type        = string
  default     = "3.6.1"

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.kafka_version))
    error_message = "Kafka version must be in semantic version format (e.g., 3.6.1)."
  }
}

variable "storage_size" {
  description = "Storage size for each Kafka broker"
  type        = string
  default     = "100Gi"

  validation {
    condition     = can(regex("^[0-9]+(Gi|Ti|Mi)$", var.storage_size))
    error_message = "Storage size must be in Kubernetes format (e.g., 100Gi, 1Ti)."
  }
}

variable "storage_class" {
  description = "Storage class for Kafka persistent volumes"
  type        = string
  default     = "fast-ssd"
}

variable "replicas" {
  description = "Number of Kafka broker replicas"
  type        = number
  default     = 3

  validation {
    condition     = var.replicas >= 3 && var.replicas % 2 == 1
    error_message = "Replicas must be an odd number >= 3 for proper quorum."
  }
}

variable "enable_metrics" {
  description = "Enable Prometheus metrics collection"
  type        = bool
  default     = true
}

variable "enable_cruise_control" {
  description = "Enable Cruise Control for cluster optimization"
  type        = bool
  default     = true
}

variable "log_retention_hours" {
  description = "Log retention period in hours"
  type        = number
  default     = 168 # 7 days

  validation {
    condition     = var.log_retention_hours > 0 && var.log_retention_hours <= 8760 # Max 1 year
    error_message = "Log retention hours must be between 1 and 8760 (1 year)."
  }
}

# Exactly-once delivery configurations
variable "transaction_state_log_replication_factor" {
  description = "Replication factor for transaction state log"
  type        = number
  default     = 3

  validation {
    condition     = var.transaction_state_log_replication_factor >= 3
    error_message = "Transaction state log replication factor must be >= 3 for exactly-once guarantees."
  }
}

variable "transaction_state_log_min_isr" {
  description = "Minimum in-sync replicas for transaction state log"
  type        = number
  default     = 2

  validation {
    condition     = var.transaction_state_log_min_isr >= 2
    error_message = "Transaction state log min ISR must be >= 2 for exactly-once guarantees."
  }
}

variable "default_replication_factor" {
  description = "Default replication factor for topics"
  type        = number
  default     = 3

  validation {
    condition     = var.default_replication_factor >= 2
    error_message = "Default replication factor must be >= 2 for high availability."
  }
}

# Governance and tagging
variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    "neural-hive-mind.org/component" = "kafka-cluster"
    "neural-hive-mind.org/layer"     = "infrastructure"
    "neural-hive-mind.org/managed-by" = "terraform"
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

# Security configurations
variable "enable_tls" {
  description = "Enable TLS encryption for Kafka communication"
  type        = bool
  default     = true
}

variable "enable_sasl" {
  description = "Enable SASL authentication"
  type        = bool
  default     = true
}

variable "ssl_protocol" {
  description = "SSL/TLS protocol version"
  type        = string
  default     = "TLSv1.3"

  validation {
    condition     = contains(["TLSv1.2", "TLSv1.3"], var.ssl_protocol)
    error_message = "SSL protocol must be TLSv1.2 or TLSv1.3."
  }
}

# Performance tuning
variable "num_network_threads" {
  description = "Number of network threads for Kafka"
  type        = number
  default     = 8

  validation {
    condition     = var.num_network_threads >= 1 && var.num_network_threads <= 32
    error_message = "Number of network threads must be between 1 and 32."
  }
}

variable "num_io_threads" {
  description = "Number of I/O threads for Kafka"
  type        = number
  default     = 16

  validation {
    condition     = var.num_io_threads >= 1 && var.num_io_threads <= 64
    error_message = "Number of I/O threads must be between 1 and 64."
  }
}

variable "socket_send_buffer_bytes" {
  description = "Socket send buffer size in bytes"
  type        = number
  default     = 102400

  validation {
    condition     = var.socket_send_buffer_bytes >= 1024
    error_message = "Socket send buffer must be >= 1024 bytes."
  }
}

variable "socket_receive_buffer_bytes" {
  description = "Socket receive buffer size in bytes"
  type        = number
  default     = 102400

  validation {
    condition     = var.socket_receive_buffer_bytes >= 1024
    error_message = "Socket receive buffer must be >= 1024 bytes."
  }
}

variable "num_partitions" {
  description = "Default number of partitions for auto-created topics"
  type        = number
  default     = 6

  validation {
    condition     = var.num_partitions >= 1 && var.num_partitions <= 100
    error_message = "Number of partitions must be between 1 and 100."
  }
}

# Monitoring configuration
variable "metrics_port" {
  description = "Port for JMX metrics"
  type        = number
  default     = 9999

  validation {
    condition     = var.metrics_port >= 1024 && var.metrics_port <= 65535
    error_message = "Metrics port must be between 1024 and 65535."
  }
}

variable "enable_jmx" {
  description = "Enable JMX for monitoring"
  type        = bool
  default     = true
}

# Resource limits
variable "kafka_memory_request" {
  description = "Memory request for Kafka brokers"
  type        = string
  default     = "2Gi"
}

variable "kafka_memory_limit" {
  description = "Memory limit for Kafka brokers"
  type        = string
  default     = "4Gi"
}

variable "kafka_cpu_request" {
  description = "CPU request for Kafka brokers"
  type        = string
  default     = "1000m"
}

variable "kafka_cpu_limit" {
  description = "CPU limit for Kafka brokers"
  type        = string
  default     = "2000m"
}

variable "zookeeper_memory_request" {
  description = "Memory request for Zookeeper nodes"
  type        = string
  default     = "1Gi"
}

variable "zookeeper_memory_limit" {
  description = "Memory limit for Zookeeper nodes"
  type        = string
  default     = "2Gi"
}

variable "zookeeper_cpu_request" {
  description = "CPU request for Zookeeper nodes"
  type        = string
  default     = "500m"
}

variable "zookeeper_cpu_limit" {
  description = "CPU limit for Zookeeper nodes"
  type        = string
  default     = "1000m"
}

# JVM configuration
variable "kafka_heap_size" {
  description = "JVM heap size for Kafka brokers"
  type        = string
  default     = "2g"

  validation {
    condition     = can(regex("^[0-9]+[gGmM]$", var.kafka_heap_size))
    error_message = "Heap size must be in format like '2g' or '2048m'."
  }
}

variable "zookeeper_heap_size" {
  description = "JVM heap size for Zookeeper nodes"
  type        = string
  default     = "1g"

  validation {
    condition     = can(regex("^[0-9]+[gGmM]$", var.zookeeper_heap_size))
    error_message = "Heap size must be in format like '1g' or '1024m'."
  }
}

# Compression settings
variable "compression_type" {
  description = "Default compression type for topics"
  type        = string
  default     = "snappy"

  validation {
    condition     = contains(["uncompressed", "snappy", "lz4", "gzip", "zstd"], var.compression_type)
    error_message = "Compression type must be one of: uncompressed, snappy, lz4, gzip, zstd."
  }
}