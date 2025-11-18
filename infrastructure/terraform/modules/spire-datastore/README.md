# Módulo Terraform: spire-datastore

Provisiona RDS PostgreSQL para SPIRE Server e armazena credenciais no AWS Secrets Manager.

## Recursos Provisionados

- **RDS PostgreSQL**: Banco de dados para armazenamento de entradas SPIRE
- **AWS Secrets Manager Secret**: Credenciais do banco de dados
- **Security Group**: Controle de acesso ao RDS
- **Subnet Group**: Configuração de rede

## Outputs

| Output | Descrição | Uso |
|--------|-----------|-----|
| `connection_string` | String de conexão PostgreSQL completa | Criar Kubernetes Secret |
| `secret_arn` | ARN do AWS Secrets Manager secret | External Secrets Operator |
| `secret_name` | Nome do secret no Secrets Manager | External Secrets Operator |
| `rds_endpoint` | Endpoint do RDS (host:port) | Configuração manual |
| `database_name` | Nome do banco de dados | Verificação |

## Criação do Kubernetes Secret

Após `terraform apply`, o Secret do Kubernetes **deve ser criado manualmente** ou via External Secrets Operator.

### Opção 1: Criação Manual (kubectl)

```bash
# Capturar connection string do Terraform
terraform output -raw connection_string > /tmp/conn_string.txt

# Criar Secret no namespace spire-system
kubectl create secret generic spire-database-secret \
  --from-literal=connection-string=$(cat /tmp/conn_string.txt) \
  -n spire-system

# Limpar arquivo temporário
rm /tmp/conn_string.txt

# Verificar Secret
kubectl get secret spire-database-secret -n spire-system -o yaml
```

**Formato esperado**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: spire-database-secret
  namespace: spire-system
type: Opaque
data:
  connection-string: <base64-encoded-connection-string>
```

### Opção 2: External Secrets Operator (Recomendado para Produção)

#### Passo 1: Instalar External Secrets Operator

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace
```

#### Passo 2: Configurar IRSA para External Secrets

O Service Account do External Secrets precisa de permissões para ler do Secrets Manager:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:neural-hive-spire-db-*"
    }
  ]
}
```

Anexar policy à role IRSA:
```bash
ROLE_NAME=$(kubectl get sa external-secrets -n external-secrets -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}' | awk -F'/' '{print $NF}')

aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name SecretsManagerReadAccess \
  --policy-document file://policy.json
```

#### Passo 3: Criar ClusterSecretStore

```yaml
# cluster-secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secrets-manager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

Aplicar:
```bash
kubectl apply -f cluster-secret-store.yaml
```

#### Passo 4: Criar ExternalSecret

```yaml
# spire-db-external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: spire-db-secret
  namespace: spire-system
spec:
  refreshInterval: 1h  # Sincronizar a cada hora
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: spire-database-secret  # Nome do Secret K8s
    creationPolicy: Owner
  data:
    - secretKey: connection-string  # Key no Secret K8s
      remoteRef:
        key: neural-hive-spire-db-production  # Nome do secret no Secrets Manager (varia por ambiente)
```

**Importante**: Substituir `neural-hive-spire-db-production` pelo valor de `terraform output -raw secret_name`.

Aplicar:
```bash
kubectl apply -f spire-db-external-secret.yaml

# Verificar sincronização
kubectl get externalsecret -n spire-system
# Output esperado: STATUS=SecretSynced

kubectl get secret spire-database-secret -n spire-system
```

#### Passo 5 (Opcional): Usar dataFrom para múltiplos campos

Se o secret no Secrets Manager contiver JSON com múltiplos campos:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: spire-db-secret
  namespace: spire-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: spire-database-secret
  dataFrom:
    - extract:
        key: neural-hive-spire-db-production
```

Isso cria um Secret com todas as chaves do JSON:
```yaml
data:
  connection_string: <base64>
  username: <base64>
  password: <base64>
  endpoint: <base64>
  port: <base64>
```

## Integração com Helm Chart SPIRE

No `helm-charts/spire/values.yaml`, configure:

```yaml
server:
  datastore:
    sql:
      databaseType: "postgres"
      connectionStringSecret:
        enabled: true
        name: "spire-database-secret"  # Nome do Secret criado acima
        key: "connection-string"       # Key dentro do Secret
```

Deploy:
```bash
helm install spire ./helm-charts/spire \
  --namespace spire-system \
  --set server.datastore.sql.connectionStringSecret.enabled=true \
  --set server.datastore.sql.connectionStringSecret.name=spire-database-secret
```

## Rotação de Credenciais

### Com External Secrets (Automático)

1. **Atualizar senha no RDS**:
```bash
aws rds modify-db-instance \
  --db-instance-identifier neural-hive-spire-db \
  --master-user-password NEW_PASSWORD \
  --apply-immediately
```

2. **Atualizar Secrets Manager**:
```bash
NEW_CONN_STRING="postgresql://spire_server:NEW_PASSWORD@ENDPOINT:5432/spire?sslmode=require"

aws secretsmanager update-secret \
  --secret-id neural-hive-spire-db-production \
  --secret-string "{\"connection_string\": \"$NEW_CONN_STRING\"}"
```

3. **External Secrets sincroniza automaticamente** (em até 1h ou forçar):
```bash
kubectl annotate externalsecret spire-db-secret -n spire-system \
  force-sync=$(date +%s) --overwrite
```

4. **Restart SPIRE Server** para aplicar nova credencial:
```bash
kubectl rollout restart statefulset/spire-server -n spire-system
```

### Sem External Secrets (Manual)

```bash
# Atualizar Secret manualmente
kubectl create secret generic spire-database-secret \
  --from-literal=connection-string="$NEW_CONN_STRING" \
  -n spire-system --dry-run=client -o yaml | kubectl apply -f -

# Restart SPIRE
kubectl rollout restart statefulset/spire-server -n spire-system
```

## Backup e Recovery

### Backup Automático (RDS)

Configurado no módulo Terraform:
```hcl
backup_retention_period = 7  # 7 dias de snapshots
backup_window           = "03:00-04:00"  # 3h-4h UTC
```

Verificar snapshots:
```bash
aws rds describe-db-snapshots \
  --db-instance-identifier neural-hive-spire-db \
  --snapshot-type automated
```

### Restore de Snapshot

```bash
# Listar snapshots disponíveis
aws rds describe-db-snapshots \
  --db-instance-identifier neural-hive-spire-db

# Restore para nova instância
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier neural-hive-spire-db-restored \
  --db-snapshot-identifier rds:neural-hive-spire-db-2025-11-17-03-00

# Aguardar disponibilidade
aws rds wait db-instance-available \
  --db-instance-identifier neural-hive-spire-db-restored

# Obter novo endpoint
NEW_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier neural-hive-spire-db-restored \
  --query 'DBInstances[0].Endpoint.Address' --output text)

# Atualizar connection string no Secret
NEW_CONN="postgresql://spire_server:PASSWORD@$NEW_ENDPOINT:5432/spire?sslmode=require"

kubectl create secret generic spire-database-secret \
  --from-literal=connection-string="$NEW_CONN" \
  -n spire-system --dry-run=client -o yaml | kubectl apply -f -

# Restart SPIRE
kubectl rollout restart statefulset/spire-server -n spire-system
```

## Troubleshooting

### Secret não encontrado

```bash
# Verificar se Secret existe
kubectl get secret spire-database-secret -n spire-system

# Se não existe, criar manualmente (ver Opção 1)

# Se usando External Secrets, verificar status
kubectl describe externalsecret spire-db-secret -n spire-system
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets
```

### SPIRE não conecta ao RDS

```bash
# Verificar connection string no Secret
kubectl get secret spire-database-secret -n spire-system -o jsonpath='{.data.connection-string}' | base64 -d

# Testar conectividade do pod SPIRE
kubectl run -it --rm debug --image=postgres:14 --restart=Never -- \
  psql "$(kubectl get secret spire-database-secret -n spire-system -o jsonpath='{.data.connection-string}' | base64 -d)"

# Verificar logs do SPIRE Server
kubectl logs -n spire-system spire-server-0 | grep -i "database\|postgres\|sql"
```

### External Secrets não sincroniza

```bash
# Verificar ClusterSecretStore
kubectl get clustersecretstore aws-secrets-manager -o yaml

# Verificar ExternalSecret
kubectl describe externalsecret spire-db-secret -n spire-system

# Verificar permissões IRSA
aws iam get-role-policy --role-name <IRSA_ROLE> --policy-name SecretsManagerReadAccess

# Forçar sincronização
kubectl annotate externalsecret spire-db-secret -n spire-system \
  force-sync=$(date +%s) --overwrite
```

## Variáveis do Módulo

Veja `variables.tf` para lista completa. Principais:

- `environment`: Ambiente (development, staging, production)
- `vpc_id`: VPC ID para RDS
- `private_subnet_ids`: Subnets para RDS (privadas recomendadas)
- `instance_class`: Tipo de instância RDS (default: db.t3.micro)
- `allocated_storage`: Tamanho do disco em GB (default: 20)
- `backup_retention_period`: Dias de retenção de backup (default: 7)

## Segurança

- **Senha gerada aleatoriamente** via `random_password` (32 caracteres)
- **Armazenamento criptografado** no Secrets Manager
- **SSL obrigatório** na connection string (`sslmode=require`)
- **Security Group** permite apenas tráfego do cluster EKS
- **RDS em subnets privadas** (sem acesso público)

## Referências

- [External Secrets Operator Documentation](https://external-secrets.io/)
- [SPIRE PostgreSQL Datastore](https://spiffe.io/docs/latest/deploying/spire_server/#postgresql)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
