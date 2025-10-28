# Outputs do Módulo de Rede - Neural Hive-Mind

output "vpc_id" {
  description = "ID da VPC criada"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block da VPC"
  value       = aws_vpc.main.cidr_block
}

output "private_subnet_ids" {
  description = "Lista de IDs das subnets privadas"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "Lista de IDs das subnets públicas"
  value       = aws_subnet.public[*].id
}

output "availability_zones" {
  description = "Zonas de disponibilidade utilizadas"
  value       = var.availability_zones
}

output "nat_gateway_ips" {
  description = "IPs elásticos dos NAT Gateways"
  value       = aws_eip.nat[*].public_ip
}

output "cluster_internal_security_group_id" {
  description = "ID do Security Group para comunicação interna do cluster"
  value       = aws_security_group.cluster_internal.id
}

output "vpc_endpoints_security_group_id" {
  description = "ID do Security Group para VPC endpoints"
  value       = var.enable_vpc_endpoints ? aws_security_group.vpc_endpoints[0].id : null
}

output "private_route_table_ids" {
  description = "IDs das route tables privadas"
  value       = aws_route_table.private[*].id
}

output "public_route_table_id" {
  description = "ID da route table pública"
  value       = aws_route_table.public.id
}