output "cluster_endpoint" {
  value = var.enable_private_endpoint ? azurerm_kubernetes_cluster.main.private_fqdn : azurerm_kubernetes_cluster.main.fqdn
}

output "cluster_ca_certificate" {
  value     = azurerm_kubernetes_cluster.main.kube_config[0].cluster_certificate
  sensitive = true
}

output "cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "cluster_id" {
  value = azurerm_kubernetes_cluster.main.id
}

output "node_security_group_id" {
  value = azurerm_kubernetes_cluster.main.network_profile[0].network_plugin == "kubenet" ? azurerm_kubernetes_cluster.main.node_resource_group : azurerm_kubernetes_cluster.main.default_node_pool[0].vnet_subnet_id
}

output "oidc_provider_arn" {
  value = "arn:azure:${var.region}:${var.resource_group_name}:oidc:${azurerm_kubernetes_cluster.main.identity[0].principal_id}"
}

output "oidc_provider_url" {
  value = "https://eastus.oic.prod-aks.azure.com/${azurerm_kubernetes_cluster.main.identity[0].principal_id}"
}
