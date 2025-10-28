# Configuração de Backend S3 - Neural Hive-Mind
# Usar com: terraform init -backend-config=backend.hcl
#
# Para diferentes ambientes:
# - Dev: terraform init -backend-config=environments/dev/backend.hcl
# - Staging: terraform init -backend-config=environments/staging/backend.hcl
# - Prod: terraform init -backend-config=environments/prod/backend.hcl

# Nome do bucket S3 para armazenar estado Terraform
bucket = "neural-hive-terraform-state-dev"

# Caminho do arquivo de estado no bucket
key = "infrastructure/terraform.tfstate"

# Região AWS do bucket
region = "us-east-1"

# Habilitar criptografia do estado
encrypt = true

# Tabela DynamoDB para lock de estado (previne modificações concorrentes)
dynamodb_table = "neural-hive-terraform-locks-dev"

# KMS key para criptografia (opcional - usa default se não especificado)
# kms_key_id = "arn:aws:kms:us-east-1:xxxxxxxxxxxx:key/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Templates para outros ambientes:
#
# STAGING:
# bucket         = "neural-hive-terraform-state-staging"
# key            = "infrastructure/terraform.tfstate"
# region         = "us-east-1"
# encrypt        = true
# dynamodb_table = "neural-hive-terraform-locks-staging"
#
# PRODUCTION:
# bucket         = "neural-hive-terraform-state-prod"
# key            = "infrastructure/terraform.tfstate"
# region         = "us-east-1"
# encrypt        = true
# dynamodb_table = "neural-hive-terraform-locks-prod"
# kms_key_id     = "arn:aws:kms:us-east-1:xxxxxxxxxxxx:key/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"