#!/bin/bash

# Script para configurar backend S3 e DynamoDB para Terraform
# Cria recursos AWS necessários para armazenamento remoto de estado

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações padrão
ENVIRONMENT=${1:-dev}
AWS_REGION=${AWS_REGION:-us-east-1}
PROJECT_NAME="neural-hive"
BUCKET_PREFIX="${PROJECT_NAME}-terraform-state"
TABLE_PREFIX="${PROJECT_NAME}-terraform-locks"

echo -e "${BLUE}===== Configuração de Backend Terraform S3/DynamoDB =====${NC}"
echo "Ambiente: $ENVIRONMENT"
echo "Região: $AWS_REGION"
echo ""

# Verificar pré-requisitos
check_prerequisites() {
    echo -e "${YELLOW}Verificando pré-requisitos...${NC}"

    # Verificar AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}AWS CLI não encontrado. Por favor instale o AWS CLI.${NC}"
        exit 1
    fi

    # Verificar credenciais AWS
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}Credenciais AWS não configuradas ou inválidas.${NC}"
        exit 1
    fi

    # Obter ID da conta AWS
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
    echo "Conta AWS: $AWS_ACCOUNT_ID"

    # Verificar terraform
    if ! command -v terraform &> /dev/null; then
        echo -e "${YELLOW}Terraform não encontrado. Por favor instale o Terraform.${NC}"
    fi

    echo -e "${GREEN}Pré-requisitos verificados!${NC}"
}

# Criar bucket S3
create_s3_bucket() {
    BUCKET_NAME="${BUCKET_PREFIX}-${ENVIRONMENT}"

    echo -e "${YELLOW}Criando bucket S3: $BUCKET_NAME${NC}"

    # Verificar se bucket já existe
    if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
        echo -e "${GREEN}Bucket $BUCKET_NAME já existe.${NC}"
    else
        # Criar bucket
        if [[ "$AWS_REGION" == "us-east-1" ]]; then
            aws s3api create-bucket \
                --bucket "$BUCKET_NAME" \
                --region "$AWS_REGION"
        else
            aws s3api create-bucket \
                --bucket "$BUCKET_NAME" \
                --region "$AWS_REGION" \
                --create-bucket-configuration LocationConstraint="$AWS_REGION"
        fi

        # Habilitar versionamento
        aws s3api put-bucket-versioning \
            --bucket "$BUCKET_NAME" \
            --versioning-configuration Status=Enabled

        # Habilitar criptografia padrão
        aws s3api put-bucket-encryption \
            --bucket "$BUCKET_NAME" \
            --server-side-encryption-configuration '{
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        },
                        "BucketKeyEnabled": true
                    }
                ]
            }'

        # Bloquear acesso público
        aws s3api put-public-access-block \
            --bucket "$BUCKET_NAME" \
            --public-access-block-configuration \
                BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

        # Adicionar tags
        aws s3api put-bucket-tagging \
            --bucket "$BUCKET_NAME" \
            --tagging '{
                "TagSet": [
                    {"Key": "Environment", "Value": "'$ENVIRONMENT'"},
                    {"Key": "Project", "Value": "'$PROJECT_NAME'"},
                    {"Key": "ManagedBy", "Value": "terraform"},
                    {"Key": "Purpose", "Value": "terraform-state"}
                ]
            }'

        # Configurar lifecycle para limpeza de versões antigas
        aws s3api put-bucket-lifecycle-configuration \
            --bucket "$BUCKET_NAME" \
            --lifecycle-configuration '{
                "Rules": [
                    {
                        "ID": "delete-old-versions",
                        "Status": "Enabled",
                        "NoncurrentVersionExpiration": {
                            "NoncurrentDays": 90
                        },
                        "AbortIncompleteMultipartUpload": {
                            "DaysAfterInitiation": 7
                        }
                    }
                ]
            }'

        echo -e "${GREEN}Bucket S3 $BUCKET_NAME criado com sucesso!${NC}"
    fi
}

# Criar tabela DynamoDB
create_dynamodb_table() {
    TABLE_NAME="${TABLE_PREFIX}-${ENVIRONMENT}"

    echo -e "${YELLOW}Criando tabela DynamoDB: $TABLE_NAME${NC}"

    # Verificar se tabela já existe
    if aws dynamodb describe-table --table-name "$TABLE_NAME" --region "$AWS_REGION" &> /dev/null; then
        echo -e "${GREEN}Tabela $TABLE_NAME já existe.${NC}"
    else
        # Criar tabela
        aws dynamodb create-table \
            --table-name "$TABLE_NAME" \
            --attribute-definitions AttributeName=LockID,AttributeType=S \
            --key-schema AttributeName=LockID,KeyType=HASH \
            --billing-mode PAY_PER_REQUEST \
            --region "$AWS_REGION" \
            --tags \
                Key=Environment,Value="$ENVIRONMENT" \
                Key=Project,Value="$PROJECT_NAME" \
                Key=ManagedBy,Value=terraform \
                Key=Purpose,Value=terraform-lock

        # Aguardar tabela ficar ativa
        echo "Aguardando tabela ficar ativa..."
        aws dynamodb wait table-exists --table-name "$TABLE_NAME" --region "$AWS_REGION"

        # Habilitar point-in-time recovery
        aws dynamodb update-continuous-backups \
            --table-name "$TABLE_NAME" \
            --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
            --region "$AWS_REGION"

        echo -e "${GREEN}Tabela DynamoDB $TABLE_NAME criada com sucesso!${NC}"
    fi
}

# Criar arquivo de configuração backend
create_backend_config() {
    CONFIG_DIR="environments/${ENVIRONMENT}"
    CONFIG_FILE="${CONFIG_DIR}/backend.hcl"

    echo -e "${YELLOW}Criando arquivo de configuração backend: $CONFIG_FILE${NC}"

    # Criar diretório se não existir
    mkdir -p "$CONFIG_DIR"

    # Criar arquivo de configuração
    cat > "$CONFIG_FILE" << EOF
# Backend S3 Configuration - ${ENVIRONMENT} environment
# Generated by setup-backend.sh on $(date)

bucket         = "${BUCKET_PREFIX}-${ENVIRONMENT}"
key            = "infrastructure/terraform.tfstate"
region         = "${AWS_REGION}"
encrypt        = true
dynamodb_table = "${TABLE_PREFIX}-${ENVIRONMENT}"

# Para usar KMS customizado, descomente e configure:
# kms_key_id = "arn:aws:kms:${AWS_REGION}:${AWS_ACCOUNT_ID}:key/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
EOF

    echo -e "${GREEN}Arquivo de configuração criado: $CONFIG_FILE${NC}"
}

# Criar política IAM para acesso ao backend
create_iam_policy() {
    POLICY_NAME="${PROJECT_NAME}-terraform-backend-${ENVIRONMENT}"

    echo -e "${YELLOW}Criando política IAM: $POLICY_NAME${NC}"

    # Criar documento de política
    POLICY_DOC=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation",
                "s3:GetBucketVersioning"
            ],
            "Resource": "arn:aws:s3:::${BUCKET_PREFIX}-${ENVIRONMENT}"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::${BUCKET_PREFIX}-${ENVIRONMENT}/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:DescribeTable",
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:DeleteItem"
            ],
            "Resource": "arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT_ID}:table/${TABLE_PREFIX}-${ENVIRONMENT}"
        }
    ]
}
EOF
)

    # Verificar se política já existe
    if aws iam get-policy --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}" &> /dev/null; then
        echo -e "${GREEN}Política IAM $POLICY_NAME já existe.${NC}"
    else
        # Criar política
        aws iam create-policy \
            --policy-name "$POLICY_NAME" \
            --policy-document "$POLICY_DOC" \
            --description "Política para acesso ao backend Terraform do ambiente $ENVIRONMENT" \
            --tags \
                Key=Environment,Value="$ENVIRONMENT" \
                Key=Project,Value="$PROJECT_NAME" \
                Key=ManagedBy,Value=terraform

        echo -e "${GREEN}Política IAM $POLICY_NAME criada com sucesso!${NC}"
    fi

    echo ""
    echo "ARN da política: arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}"
}

# Instruções de uso
print_usage_instructions() {
    echo ""
    echo -e "${BLUE}===== Configuração Concluída =====${NC}"
    echo ""
    echo "Recursos criados:"
    echo "  • Bucket S3: ${BUCKET_PREFIX}-${ENVIRONMENT}"
    echo "  • Tabela DynamoDB: ${TABLE_PREFIX}-${ENVIRONMENT}"
    echo "  • Arquivo de configuração: environments/${ENVIRONMENT}/backend.hcl"
    echo "  • Política IAM: ${PROJECT_NAME}-terraform-backend-${ENVIRONMENT}"
    echo ""
    echo -e "${GREEN}Para usar este backend, execute:${NC}"
    echo ""
    echo "  cd infrastructure/terraform"
    echo "  terraform init -backend-config=../../environments/${ENVIRONMENT}/backend.hcl"
    echo ""
    echo "Para migrar estado existente:"
    echo "  terraform init -migrate-state -backend-config=../../environments/${ENVIRONMENT}/backend.hcl"
    echo ""
}

# Função para destruir backend (cleanup)
destroy_backend() {
    echo -e "${RED}===== ATENÇÃO: Destruindo Backend Terraform =====${NC}"
    echo "Esta ação irá DELETAR permanentemente:"
    echo "  • Bucket S3: ${BUCKET_PREFIX}-${ENVIRONMENT}"
    echo "  • Tabela DynamoDB: ${TABLE_PREFIX}-${ENVIRONMENT}"
    echo ""
    read -p "Tem certeza que deseja continuar? (digite 'DESTRUIR' para confirmar): " CONFIRM

    if [[ "$CONFIRM" != "DESTRUIR" ]]; then
        echo "Operação cancelada."
        exit 0
    fi

    # Deletar bucket S3
    BUCKET_NAME="${BUCKET_PREFIX}-${ENVIRONMENT}"
    if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
        echo "Removendo todos os objetos do bucket..."
        aws s3 rm "s3://$BUCKET_NAME" --recursive
        echo "Removendo versões de objetos..."
        aws s3api list-object-versions --bucket "$BUCKET_NAME" --query 'Versions[].{Key:Key,VersionId:VersionId}' --output json | \
            jq -r '.[] | "--key '\''\(.Key)'\'' --version-id \(.VersionId)"' | \
            xargs -I {} aws s3api delete-object --bucket "$BUCKET_NAME" {}
        echo "Deletando bucket..."
        aws s3api delete-bucket --bucket "$BUCKET_NAME"
        echo -e "${GREEN}Bucket deletado.${NC}"
    fi

    # Deletar tabela DynamoDB
    TABLE_NAME="${TABLE_PREFIX}-${ENVIRONMENT}"
    if aws dynamodb describe-table --table-name "$TABLE_NAME" &> /dev/null; then
        echo "Deletando tabela DynamoDB..."
        aws dynamodb delete-table --table-name "$TABLE_NAME" --region "$AWS_REGION"
        echo -e "${GREEN}Tabela deletada.${NC}"
    fi

    echo -e "${GREEN}Backend destruído com sucesso.${NC}"
}

# Main
main() {
    # Verificar se é para destruir
    if [[ "${2}" == "destroy" ]]; then
        check_prerequisites
        destroy_backend
    else
        check_prerequisites
        create_s3_bucket
        create_dynamodb_table
        create_iam_policy
        create_backend_config
        print_usage_instructions
    fi
}

# Executar
main "$@"