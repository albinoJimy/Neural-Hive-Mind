# Azure Cluster Submodule
# Implementa AKS (Azure Kubernetes Service)

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# AKS Cluster
resource "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = "${var.cluster_name}-dns"
  kubernetes_version  = var.kubernetes_version
  tags                = var.tags

  # Network Profile
  network_profile {
    network_plugin = "azure"
    network_mode   = "transparent"
    network_policy = "azure"
    dns_service_ip = "10.0.0.10"
    service_cidr   = "10.0.0.0/24"
    outbound_type  = var.environment == "prod" ? "userDefinedRouting" : "loadBalancer"
  }

  # Default Node Pool
  default_node_pool {
    name                         = "system"
    node_count                   = var.desired_nodes_per_zone
    min_count                    = var.min_nodes_per_zone
    max_count                    = var.max_nodes_per_zone
    vm_size                      = var.node_instance_types[0]
    vnet_subnet_id               = var.private_subnet_ids[0]
    enable_auto_scaling          = true
    enable_host_encryption       = true
    enable_node_public_ip        = false
    only_critical_addons_enabled = true
    orchestrator_version         = var.kubernetes_version
    os_disk_size_gb              = 30
    os_disk_type                 = "Premium_LRS"
    scale_down_mode              = "Delete"
    zones                        = var.availability_zones
  }

  # User Node Pools
  dynamic "node_pool" {
    for_each = var.availability_zones
    content {
      name                   = "user-${node_pool.value}"
      node_count             = var.desired_nodes_per_zone
      min_count              = var.min_nodes_per_zone
      max_count              = var.max_nodes_per_zone
      vm_size                = var.node_instance_types[0]
      vnet_subnet_id         = var.private_subnet_ids[node_pool.index]
      enable_auto_scaling    = true
      enable_host_encryption = true
      enable_node_public_ip  = false
      orchestrator_version   = var.kubernetes_version
      os_disk_size_gb        = 30
      os_disk_type           = "Premium_LRS"
      scale_down_mode        = "Delete"
      zones                  = [node_pool.value]
      os_type                = "Linux"
    }
  }

  # Identity (SystemAssigned Managed Identity)
  identity {
    type = "SystemAssigned"
  }

  # Private Cluster
  private_cluster_enabled             = var.enable_private_endpoint
  private_cluster_public_fqdn_enabled = !var.enable_private_endpoint
  private_dns_zone_id                 = var.enable_private_endpoint ? azurerm_private_dns_zone.main[0].id : null

  # Azure AD Integration
  azure_active_directory_role_based_access_control {
    managed            = true
    azure_rbac_enabled = true
  }

  # Add-ons
  oms_agent {
    log_analytics_workspace_id = var.log_analytics_workspace_id
  }

  azure_policy_enabled = true

  http_application_routing_enabled = false

  # Monitor Configuration
  monitor_metrics {
    annotations_allowed = null
    labels_allowed      = null
  }

  # Kubernetes Network Configuration
  kubernetes_network_config {
    network_plugin_mode = "transparent"
    dns_service_ip      = "10.0.0.10"
    service_cidr        = "10.0.0.0/24"
    pod_cidrs           = ["10.244.0.0/16"]
  }
}

# Private DNS Zone para Private Cluster
resource "azurerm_private_dns_zone" "main" {
  count = var.enable_private_endpoint ? 1 : 0

  name                = "privatelink.${var.location}.azmk8s.io"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "main" {
  count = var.enable_private_endpoint ? 1 : 0

  name                  = "${var.cluster_name}-dns-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.main[0].name
  virtual_network_id    = var.vpc_id
  registration_enabled  = true
}
