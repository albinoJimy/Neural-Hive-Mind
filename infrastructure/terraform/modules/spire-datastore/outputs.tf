# Outputs for SPIRE Datastore Module

output "rds_endpoint" {
  description = "Endpoint completo do RDS (host:port)"
  value       = "${aws_db_instance.spire.address}:${aws_db_instance.spire.port}"
}

output "rds_address" {
  description = "Endereço DNS do RDS PostgreSQL"
  value       = aws_db_instance.spire.address
}

output "rds_port" {
  description = "Porta do RDS PostgreSQL"
  value       = aws_db_instance.spire.port
}

output "database_name" {
  description = "Nome do banco de dados SPIRE"
  value       = aws_db_instance.spire.db_name
}

output "database_username" {
  description = "Nome de usuário do banco de dados SPIRE"
  value       = aws_db_instance.spire.username
  sensitive   = true
}

output "secret_arn" {
  description = "ARN do AWS Secrets Manager secret contendo credenciais do banco de dados"
  value       = aws_secretsmanager_secret.spire_db.arn
}

output "secret_name" {
  description = "Nome do AWS Secrets Manager secret"
  value       = aws_secretsmanager_secret.spire_db.name
}

output "security_group_id" {
  description = "ID do security group do RDS"
  value       = aws_security_group.spire_rds.id
}

output "connection_string" {
  description = "Connection string PostgreSQL completa (sensível - usar em Kubernetes Secret)"
  value       = "postgresql://${aws_db_instance.spire.username}:${random_password.spire_db_password.result}@${aws_db_instance.spire.address}:${aws_db_instance.spire.port}/${aws_db_instance.spire.db_name}?sslmode=require"
  sensitive   = true
}

output "rds_instance_id" {
  description = "ID da instância RDS"
  value       = aws_db_instance.spire.id
}

output "rds_resource_id" {
  description = "Resource ID da instância RDS (para CloudWatch Logs)"
  value       = aws_db_instance.spire.resource_id
}
