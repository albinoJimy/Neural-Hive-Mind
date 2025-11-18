# SPIRE Datastore Module
# Provisiona PostgreSQL RDS para armazenamento persistente do SPIRE Server

# Security Group para RDS PostgreSQL
resource "aws_security_group" "spire_rds" {
  name_prefix = "${var.cluster_name}-spire-rds-"
  description = "Security group para SPIRE PostgreSQL RDS"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from EKS cluster"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_security_group_id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-spire-rds-sg"
      Environment = var.environment
      Component   = "spire-datastore"
    }
  )

  lifecycle {
    create_before_destroy = true
  }
}

# DB Subnet Group
resource "aws_db_subnet_group" "spire" {
  name_prefix = "${var.cluster_name}-spire-"
  description = "Subnet group para SPIRE RDS"
  subnet_ids  = var.private_subnet_ids

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-spire-db-subnet-group"
      Environment = var.environment
      Component   = "spire-datastore"
    }
  )
}

# Gerar senha aleatória para usuário spire_server
resource "random_password" "spire_db_password" {
  length  = 32
  special = true
  # Evitar caracteres que podem causar problemas em connection strings
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "spire" {
  identifier_prefix = "${var.cluster_name}-spire-"

  # Engine configuration
  engine               = "postgres"
  engine_version       = "15.4"
  instance_class       = var.instance_class

  # Storage configuration
  allocated_storage     = var.allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  # Database configuration
  db_name  = "spire"
  username = "spire_server"
  password = random_password.spire_db_password.result
  port     = 5432

  # Network configuration
  db_subnet_group_name   = aws_db_subnet_group.spire.name
  vpc_security_group_ids = [aws_security_group.spire_rds.id]
  publicly_accessible    = false

  # High availability
  multi_az = var.multi_az

  # Backup configuration
  backup_retention_period = var.backup_retention_days
  backup_window          = "03:00-04:00"  # UTC
  maintenance_window     = "mon:04:00-mon:05:00"  # UTC

  # Performance Insights
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  # Deletion protection
  deletion_protection = var.environment == "prod" ? true : false
  skip_final_snapshot = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${var.cluster_name}-spire-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}" : null

  # Auto minor version upgrade
  auto_minor_version_upgrade = true

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-spire-db"
      Environment = var.environment
      Component   = "spire-datastore"
      ManagedBy   = "terraform"
    }
  )

  lifecycle {
    ignore_changes = [
      # Ignorar mudanças no snapshot identifier timestamp
      final_snapshot_identifier
    ]
  }
}

# AWS Secrets Manager Secret para credenciais
resource "aws_secretsmanager_secret" "spire_db" {
  name_prefix = "${var.cluster_name}/spire/database-"
  description = "Credenciais do banco de dados SPIRE PostgreSQL"

  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-spire-db-credentials"
      Environment = var.environment
      Component   = "spire-datastore"
    }
  )
}

# Secret Version com credenciais
resource "aws_secretsmanager_secret_version" "spire_db" {
  secret_id = aws_secretsmanager_secret.spire_db.id
  secret_string = jsonencode({
    username = aws_db_instance.spire.username
    password = random_password.spire_db_password.result
    host     = aws_db_instance.spire.address
    port     = aws_db_instance.spire.port
    database = aws_db_instance.spire.db_name
    connection_string = "postgresql://${aws_db_instance.spire.username}:${random_password.spire_db_password.result}@${aws_db_instance.spire.address}:${aws_db_instance.spire.port}/${aws_db_instance.spire.db_name}?sslmode=require"
  })
}

# IAM Policy para SPIRE Server Service Account acessar Secret
data "aws_iam_policy_document" "spire_server_secrets_access" {
  statement {
    sid    = "AllowGetSecretValue"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [aws_secretsmanager_secret.spire_db.arn]
  }
}

resource "aws_iam_policy" "spire_server_secrets_access" {
  name_prefix = "${var.cluster_name}-spire-server-secrets-"
  description = "Permite SPIRE Server acessar credenciais do banco de dados"
  policy      = data.aws_iam_policy_document.spire_server_secrets_access.json

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-spire-server-secrets-policy"
      Environment = var.environment
      Component   = "spire-datastore"
    }
  )
}

# Output do ARN da policy para attachment no IRSA role do SPIRE Server
output "secrets_access_policy_arn" {
  description = "ARN da IAM policy para acessar secret do banco de dados SPIRE"
  value       = aws_iam_policy.spire_server_secrets_access.arn
}
