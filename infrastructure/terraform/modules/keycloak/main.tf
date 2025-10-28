# Keycloak OAuth2/OIDC Provider Module para Neural Hive-Mind
# Implementa Keycloak como provedor OAuth2 com integração Kubernetes

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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.4"
    }
  }
}

locals {
  keycloak_labels = merge(var.common_labels, {
    "app.kubernetes.io/name"       = "keycloak"
    "app.kubernetes.io/instance"   = var.instance_name
    "app.kubernetes.io/component"  = "auth"
    "app.kubernetes.io/part-of"    = "neural-hive-mind"
    "neural-hive.io/layer"         = "security"
    "neural-hive.io/data-classification" = "confidential"
  })
}

# Generate random passwords if not provided
resource "random_password" "keycloak_admin" {
  count   = var.admin_password == "" ? 1 : 0
  length  = 16
  special = true
}

resource "random_password" "database_password" {
  count   = var.database_password == "" ? 1 : 0
  length  = 16
  special = false
}

# Namespace para Keycloak
resource "kubernetes_namespace" "keycloak" {
  metadata {
    name = var.namespace
    labels = merge(local.keycloak_labels, {
      "istio-injection" = "enabled"
      "name"            = var.namespace
    })
  }
}

# Secret para credenciais admin
resource "kubernetes_secret" "keycloak_admin" {
  metadata {
    name      = "${var.instance_name}-admin"
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels    = local.keycloak_labels
    annotations = {
      "neural-hive.io/secret-type" = "admin-credentials"
    }
  }

  type = "Opaque"

  data = {
    username = base64encode(var.admin_username)
    password = base64encode(var.admin_password != "" ? var.admin_password : random_password.keycloak_admin[0].result)
  }
}

# Secret para database
resource "kubernetes_secret" "keycloak_database" {
  metadata {
    name      = "${var.instance_name}-database"
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels    = local.keycloak_labels
    annotations = {
      "neural-hive.io/secret-type" = "database-credentials"
    }
  }

  type = "Opaque"

  data = {
    username = base64encode(var.database_username)
    password = base64encode(var.database_password != "" ? var.database_password : random_password.database_password[0].result)
    host     = base64encode(var.database_host)
    port     = base64encode(tostring(var.database_port))
    database = base64encode(var.database_name)
    url      = base64encode("jdbc:postgresql://${var.database_host}:${var.database_port}/${var.database_name}")
  }
}

# ConfigMap para configuração Keycloak
resource "kubernetes_config_map" "keycloak_config" {
  metadata {
    name      = "${var.instance_name}-config"
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels    = local.keycloak_labels
  }

  data = {
    "keycloak.conf" = <<-EOT
      # Database
      db=postgres
      db-url-host=${var.database_host}
      db-url-port=${var.database_port}
      db-url-database=${var.database_name}
      db-username=${var.database_username}

      # HTTP/HTTPS
      http-enabled=true
      hostname-strict=false
      hostname-strict-https=false
      proxy=edge

      # Clustering
      cache=ispn
      cache-stack=kubernetes

      # Metrics
      metrics-enabled=${var.enable_metrics}

      # Health checks
      health-enabled=true

      # Theme
      spi-theme-static-max-age=-1
      spi-theme-cache-themes=false
      spi-theme-cache-templates=false
    EOT

    "realm-config.json" = jsonencode({
      realm = var.realm_name
      enabled = true
      displayName = "Neural Hive-Mind"
      displayNameHtml = "<div class=\"kc-logo-text\"><span>Neural Hive-Mind</span></div>"

      # Token settings
      accessTokenLifespan = var.token_lifespan
      accessTokenLifespanForImplicitFlow = var.token_lifespan
      ssoSessionIdleTimeout = 1800
      ssoSessionMaxLifespan = 36000

      # Password policy
      passwordPolicy = "hashIterations(27500) and specialChars(1) and upperCase(1) and digits(1) and notUsername(undefined) and length(8)"

      # Clients
      clients = [
        {
          clientId = "gateway-intencoes"
          name = "Gateway de Intenções"
          enabled = true
          protocol = "openid-connect"
          publicClient = false
          serviceAccountsEnabled = true
          authorizationServicesEnabled = false
          directAccessGrantsEnabled = true
          standardFlowEnabled = true
          implicitFlowEnabled = false

          attributes = {
            "access.token.lifespan" = tostring(var.token_lifespan)
            "client.secret.creation.time" = tostring(timestamp())
          }

          redirectUris = var.gateway_redirect_uris
          webOrigins = var.gateway_web_origins

          defaultClientScopes = [
            "web-origins", "acr", "profile", "roles", "email"
          ]
          optionalClientScopes = [
            "address", "phone", "offline_access", "microprofile-jwt"
          ]
        }
      ]

      # Default roles
      roles = {
        realm = [
          {
            name = "neural-hive-user"
            description = "Usuário padrão do Neural Hive-Mind"
            composite = false
          },
          {
            name = "neural-hive-admin"
            description = "Administrador do Neural Hive-Mind"
            composite = false
          },
          {
            name = "service-account"
            description = "Service account role"
            composite = false
          }
        ]
      }

      # Default groups
      groups = [
        {
          name = "neural-hive-users"
          path = "/neural-hive-users"
        },
        {
          name = "neural-hive-admins"
          path = "/neural-hive-admins"
        }
      ]
    })
  }
}

# Deployment do Keycloak
resource "kubernetes_deployment" "keycloak" {
  metadata {
    name      = var.instance_name
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels    = local.keycloak_labels
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = {
        app = var.instance_name
      }
    }

    template {
      metadata {
        labels = merge(local.keycloak_labels, {
          app     = var.instance_name
          version = var.keycloak_version
        })
        annotations = {
          "sidecar.istio.io/inject"                = "true"
          "neural-hive.io/monitoring"              = "enabled"
          "prometheus.io/scrape"                   = var.enable_metrics ? "true" : "false"
          "prometheus.io/port"                     = "9000"
          "prometheus.io/path"                     = "/metrics"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.keycloak.metadata[0].name

        # Init container para aguardar database
        init_container {
          name  = "wait-for-db"
          image = "busybox:1.35"
          command = [
            "sh", "-c",
            "until nc -z ${var.database_host} ${var.database_port}; do echo 'Waiting for database...'; sleep 2; done"
          ]
        }

        container {
          name  = "keycloak"
          image = "quay.io/keycloak/keycloak:${var.keycloak_version}"

          args = [
            "start",
            "--config-file=/opt/keycloak/conf/keycloak.conf",
            "--import-realm"
          ]

          port {
            name           = "http"
            container_port = 8080
            protocol       = "TCP"
          }

          port {
            name           = "https"
            container_port = 8443
            protocol       = "TCP"
          }

          port {
            name           = "management"
            container_port = 9000
            protocol       = "TCP"
          }

          env {
            name = "KEYCLOAK_ADMIN"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.keycloak_admin.metadata[0].name
                key  = "username"
              }
            }
          }

          env {
            name = "KEYCLOAK_ADMIN_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.keycloak_admin.metadata[0].name
                key  = "password"
              }
            }
          }

          env {
            name = "KC_DB_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.keycloak_database.metadata[0].name
                key  = "password"
              }
            }
          }

          env {
            name  = "KC_HEALTH_ENABLED"
            value = "true"
          }

          env {
            name  = "KC_METRICS_ENABLED"
            value = tostring(var.enable_metrics)
          }

          env {
            name  = "KC_LOG_LEVEL"
            value = var.log_level
          }

          env {
            name  = "JAVA_OPTS_APPEND"
            value = "-Djgroups.dns.query=${var.instance_name}-headless.${kubernetes_namespace.keycloak.metadata[0].name}.svc.cluster.local"
          }

          resources {
            requests = {
              cpu    = var.cpu_request
              memory = var.memory_request
            }
            limits = {
              cpu    = var.cpu_limit
              memory = var.memory_limit
            }
          }

          volume_mount {
            name       = "keycloak-config"
            mount_path = "/opt/keycloak/conf/keycloak.conf"
            sub_path   = "keycloak.conf"
            read_only  = true
          }

          volume_mount {
            name       = "realm-config"
            mount_path = "/opt/keycloak/data/import/realm.json"
            sub_path   = "realm-config.json"
            read_only  = true
          }

          liveness_probe {
            http_get {
              path   = "/health/live"
              port   = "management"
              scheme = "HTTP"
            }
            initial_delay_seconds = 300
            period_seconds        = 30
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path   = "/health/ready"
              port   = "management"
              scheme = "HTTP"
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          startup_probe {
            http_get {
              path   = "/health"
              port   = "management"
              scheme = "HTTP"
            }
            initial_delay_seconds = 30
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 30
          }
        }

        volume {
          name = "keycloak-config"
          config_map {
            name = kubernetes_config_map.keycloak_config.metadata[0].name
            items {
              key  = "keycloak.conf"
              path = "keycloak.conf"
            }
          }
        }

        volume {
          name = "realm-config"
          config_map {
            name = kubernetes_config_map.keycloak_config.metadata[0].name
            items {
              key  = "realm-config.json"
              path = "realm-config.json"
            }
          }
        }

        # Anti-affinity para HA
        affinity {
          pod_anti_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              pod_affinity_term {
                label_selector {
                  match_labels = {
                    app = var.instance_name
                  }
                }
                topology_key = "topology.kubernetes.io/zone"
              }
            }
          }
        }
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_unavailable = "25%"
        max_surge       = "25%"
      }
    }
  }
}

# ServiceAccount para Keycloak
resource "kubernetes_service_account" "keycloak" {
  metadata {
    name      = var.instance_name
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels    = local.keycloak_labels
  }
}

# Service principal
resource "kubernetes_service" "keycloak" {
  metadata {
    name      = var.instance_name
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels    = local.keycloak_labels
    annotations = {
      "service.beta.kubernetes.io/aws-load-balancer-type" = "nlb"
      "neural-hive.io/service-type"                       = "auth"
    }
  }

  spec {
    selector = {
      app = var.instance_name
    }

    port {
      name        = "http"
      port        = 8080
      target_port = "http"
      protocol    = "TCP"
    }

    port {
      name        = "https"
      port        = 8443
      target_port = "https"
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}

# Headless service para clustering
resource "kubernetes_service" "keycloak_headless" {
  metadata {
    name      = "${var.instance_name}-headless"
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels    = local.keycloak_labels
  }

  spec {
    cluster_ip = "None"
    selector = {
      app = var.instance_name
    }

    port {
      name        = "http"
      port        = 8080
      target_port = "http"
      protocol    = "TCP"
    }
  }
}

# Service para métricas
resource "kubernetes_service" "keycloak_metrics" {
  count = var.enable_metrics ? 1 : 0

  metadata {
    name      = "${var.instance_name}-metrics"
    namespace = kubernetes_namespace.keycloak.metadata[0].name
    labels = merge(local.keycloak_labels, {
      "app.kubernetes.io/component" = "metrics"
    })
  }

  spec {
    selector = {
      app = var.instance_name
    }

    port {
      name        = "metrics"
      port        = 9000
      target_port = "management"
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}