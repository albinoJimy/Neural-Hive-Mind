# Backend S3 Configuration - DEV Environment
# Neural Hive-Mind Development Infrastructure

# Bucket S3 para armazenar estado Terraform (ambiente de desenvolvimento)
bucket = "neural-hive-terraform-state-dev"

# Caminho do arquivo de estado dentro do bucket
key = "infrastructure/terraform.tfstate"

# Região AWS do bucket
region = "us-east-1"

# Habilitar criptografia do estado
encrypt = true

# Tabela DynamoDB para lock de estado (previne modificações concorrentes)
dynamodb_table = "neural-hive-terraform-locks-dev"

# Configurações opcionais para desenvolvimento:
# - Não usar KMS customizado para reduzir custos
# - Usar configurações básicas de criptografia AES256

# Para configurar este backend:
# 1. Execute: scripts/setup/setup-backend.sh dev
# 2. Execute: terraform init -backend-config=environments/dev/backend.hcl
#
# Para migrar estado existente:
# terraform init -migrate-state -backend-config=environments/dev/backend.hcl
#
# Para destruir backend quando não precisar mais:
# scripts/setup/setup-backend.sh dev destroy