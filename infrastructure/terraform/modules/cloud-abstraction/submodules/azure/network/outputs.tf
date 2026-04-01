output "vpc_id" {
  value = azurerm_virtual_network.main.id
}

output "private_subnet_ids" {
  value = azurerm_subnet.private[*].id
}

output "public_subnet_ids" {
  value = azurerm_subnet.public[*].id
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "location" {
  value = azurerm_resource_group.main.location
}
