# Outputs para Keycloak Module

output "instance_name" {
  description = "Nome da instância Keycloak"
  value       = var.instance_name
}

output "namespace" {
  description = "Namespace do Keycloak"
  value       = kubernetes_namespace.keycloak.metadata[0].name
}

output "keycloak_url" {
  description = "URL do Keycloak"
  value       = "${var.external_url}"
}

output "internal_url" {
  description = "URL interno do Keycloak no cluster"
  value       = "http://${var.instance_name}.${kubernetes_namespace.keycloak.metadata[0].name}.svc.cluster.local:8080"
}

output "service_name" {
  description = "Nome do service Kubernetes"
  value       = kubernetes_service.keycloak.metadata[0].name
}

output "service_port" {
  description = "Porta do service HTTP"
  value       = 8080
}

output "service_port_https" {
  description = "Porta do service HTTPS"
  value       = 8443
}

# Admin Credentials
output "admin_secret_name" {
  description = "Nome do secret com credenciais admin"
  value       = kubernetes_secret.keycloak_admin.metadata[0].name
}

output "admin_username" {
  description = "Username do administrador"
  value       = var.admin_username
  sensitive   = false
}

# Realm Information
output "realm_name" {
  description = "Nome do realm principal"
  value       = var.realm_name
}

output "realm_url" {
  description = "URL do realm"
  value       = "${var.external_url}/auth/realms/${var.realm_name}"
}

# OAuth2/OIDC Endpoints
output "auth_url" {
  description = "URL de autenticação OAuth2"
  value       = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/auth"
}

output "token_url" {
  description = "URL para obter tokens OAuth2"
  value       = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/token"
}

output "userinfo_url" {
  description = "URL de informações do usuário"
  value       = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/userinfo"
}

output "jwks_uri" {
  description = "URI do JWKS para validação JWT"
  value       = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/certs"
}

output "issuer" {
  description = "Issuer JWT"
  value       = "${var.external_url}/auth/realms/${var.realm_name}"
}

output "logout_url" {
  description = "URL de logout"
  value       = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/logout"
}

# Client Configuration
output "gateway_client_config" {
  description = "Configuração OAuth2 para Gateway de Intenções"
  value = {
    client_id     = "gateway-intencoes"
    realm         = var.realm_name
    auth_url      = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/auth"
    token_url     = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/token"
    userinfo_url  = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/userinfo"
    jwks_uri      = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/certs"
    issuer        = "${var.external_url}/auth/realms/${var.realm_name}"
    scopes        = ["openid", "profile", "email", "roles"]
  }
  sensitive = false
}

# Istio Integration
output "istio_jwt_config" {
  description = "Configuração JWT para Istio RequestAuthentication"
  value = {
    issuer  = "${var.external_url}/auth/realms/${var.realm_name}"
    jwks_uri = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/certs"
    audiences = [
      "gateway-intencoes",
      "neural-hive-services"
    ]
  }
}

# Database Information
output "database_config" {
  description = "Configuração do banco de dados"
  value = {
    host      = var.database_host
    port      = var.database_port
    database  = var.database_name
    username  = var.database_username
    secret    = kubernetes_secret.keycloak_database.metadata[0].name
  }
  sensitive = false
}

# Metrics and Monitoring
output "metrics_endpoint" {
  description = "Endpoint de métricas Prometheus"
  value       = var.enable_metrics ? "${var.instance_name}-metrics.${kubernetes_namespace.keycloak.metadata[0].name}.svc.cluster.local:9000" : null
}

output "metrics_path" {
  description = "Path das métricas"
  value       = "/metrics"
}

output "health_check_url" {
  description = "URL para health checks"
  value       = "http://${var.instance_name}.${kubernetes_namespace.keycloak.metadata[0].name}.svc.cluster.local:9000/health"
}

# Configuration for Applications
output "application_config" {
  description = "Configuração para integração com aplicações"
  value = {
    # Environment variables para aplicações
    KEYCLOAK_URL              = var.external_url
    KEYCLOAK_REALM           = var.realm_name
    KEYCLOAK_CLIENT_ID       = "gateway-intencoes"
    KEYCLOAK_AUTH_URL        = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/auth"
    KEYCLOAK_TOKEN_URL       = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/token"
    KEYCLOAK_USERINFO_URL    = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/userinfo"
    KEYCLOAK_JWKS_URI        = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/certs"
    KEYCLOAK_ISSUER          = "${var.external_url}/auth/realms/${var.realm_name}"
    KEYCLOAK_LOGOUT_URL      = "${var.external_url}/auth/realms/${var.realm_name}/protocol/openid-connect/logout"
  }
  sensitive = false
}

# Backup Configuration
output "backup_config" {
  description = "Configuração de backup"
  value = var.backup_enabled ? {
    enabled           = true
    schedule          = var.backup_schedule
    retention_days    = var.backup_retention_days
    config_map       = kubernetes_config_map.keycloak_config.metadata[0].name
  } : null
}

# Secrets Management
output "secrets" {
  description = "Lista de secrets criados"
  value = {
    admin_credentials    = kubernetes_secret.keycloak_admin.metadata[0].name
    database_credentials = kubernetes_secret.keycloak_database.metadata[0].name
  }
}

# Service Account
output "service_account" {
  description = "Nome da service account"
  value       = kubernetes_service_account.keycloak.metadata[0].name
}

# ConfigMap
output "config_map" {
  description = "Nome do ConfigMap com configurações"
  value       = kubernetes_config_map.keycloak_config.metadata[0].name
}

# Deployment Status
output "deployment_info" {
  description = "Informações do deployment"
  value = {
    name      = kubernetes_deployment.keycloak.metadata[0].name
    namespace = kubernetes_deployment.keycloak.metadata[0].namespace
    replicas  = var.replicas
    version   = var.keycloak_version
    strategy  = "RollingUpdate"
  }
}

# Integration URLs for External Systems
output "integration_urls" {
  description = "URLs para integração com sistemas externos"
  value = {
    admin_console = "${var.external_url}/auth/admin/master/console/"
    realm_console = "${var.external_url}/auth/admin/${var.realm_name}/console/"
    account_mgmt  = "${var.external_url}/auth/realms/${var.realm_name}/account/"
    well_known    = "${var.external_url}/auth/realms/${var.realm_name}/.well-known/openid_configuration"
  }
}