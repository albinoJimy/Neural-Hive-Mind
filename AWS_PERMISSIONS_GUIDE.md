# Guia de Permissões AWS para Neural Hive-Mind

## 🔐 Permissões Necessárias

Para fazer o deployment completo do Neural Hive-Mind no EKS, o usuário IAM precisa das seguintes permissões:

### Opção A: Policy Administrativa (Recomendado para Desenvolvimento)

A forma mais simples é anexar a policy `AdministratorAccess`:

1. Acesse: https://console.aws.amazon.com/iam/
2. Clique em **Users** → `jimy`
3. Aba **Permissions**
4. Clique em **Add permissions** → **Attach policies directly**
5. Busque e selecione: `AdministratorAccess`
6. Clique em **Add permissions**

⚠️ **Nota**: Esta policy dá acesso total à conta AWS. Use apenas em ambientes de desenvolvimento/teste.

### Opção B: Policies Específicas (Recomendado para Produção)

Para um controle mais granular, anexe estas policies managed da AWS:

1. **EKS e EC2**:
   - `AmazonEKSClusterPolicy`
   - `AmazonEKSServicePolicy`
   - `AmazonEC2FullAccess`
   - `AmazonVPCFullAccess`

2. **Container Registry**:
   - `AmazonEC2ContainerRegistryFullAccess`

3. **Armazenamento**:
   - `AmazonS3FullAccess`
   - `AmazonDynamoDBFullAccess`

4. **IAM**:
   - `IAMFullAccess` (necessário para criar roles para EKS)

5. **Logs e Monitoramento**:
   - `CloudWatchLogsFullAccess`

### Opção C: Policy Customizada (Máxima Segurança)

Crie uma policy customizada com as permissões mínimas necessárias:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "eks:*",
        "ecr:*",
        "s3:*",
        "dynamodb:*",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:CreateInstanceProfile",
        "iam:DeleteInstanceProfile",
        "iam:AddRoleToInstanceProfile",
        "iam:RemoveRoleFromInstanceProfile",
        "iam:GetInstanceProfile",
        "iam:PassRole",
        "iam:CreateOpenIDConnectProvider",
        "iam:DeleteOpenIDConnectProvider",
        "iam:GetOpenIDConnectProvider",
        "iam:TagOpenIDConnectProvider",
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:PutRetentionPolicy",
        "logs:DescribeLogGroups",
        "elasticloadbalancing:*",
        "autoscaling:*",
        "kms:CreateKey",
        "kms:DescribeKey",
        "kms:EnableKeyRotation",
        "kms:CreateAlias",
        "kms:DeleteAlias"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Como Criar a Policy Customizada:

1. Acesse: https://console.aws.amazon.com/iam/
2. Clique em **Policies** → **Create policy**
3. Aba **JSON**, cole o JSON acima
4. Clique em **Next**
5. Nome: `NeuralHiveMindDeploymentPolicy`
6. Descrição: `Permissões necessárias para deployment do Neural Hive-Mind no EKS`
7. Clique em **Create policy**
8. Volte para **Users** → `jimy` → **Add permissions**
9. Anexe a policy `NeuralHiveMindDeploymentPolicy`

## ✅ Verificar Permissões

Após adicionar as permissões, verifique se estão funcionando:

```bash
# Testar permissão S3
aws s3 ls

# Testar permissão EC2
aws ec2 describe-vpcs --region us-east-1

# Testar permissão EKS
aws eks list-clusters --region us-east-1

# Testar permissão ECR
aws ecr describe-repositories --region us-east-1

# Testar permissão IAM
aws iam list-roles --max-items 1
```

Se algum comando falhar, significa que falta a permissão correspondente.

## 🔒 Boas Práticas de Segurança

### Para Desenvolvimento

1. **Use MFA (Multi-Factor Authentication)**:
   - IAM → Users → jimy → Security credentials → Assign MFA device

2. **Rotação de Credenciais**:
   - Troque access keys a cada 90 dias
   - IAM → Users → jimy → Security credentials → Create access key

3. **Budget Alerts**:
   - Configure alertas de custo para evitar surpresas
   - AWS Billing → Budgets → Create budget

### Para Produção

1. **Princípio do Menor Privilégio**:
   - Use a Opção C (Policy Customizada)
   - Remova permissões não utilizadas

2. **Use Roles IAM ao invés de Users**:
   - Para serviços e aplicações, use Roles
   - Para humanos em produção, use SSO/Federation

3. **Auditoria**:
   - Habilite CloudTrail para logs de auditoria
   - Revise periodicamente as permissões

4. **Separation of Duties**:
   - Deployment: Role específico para CI/CD
   - Administração: Role separado para admins
   - Read-only: Role para desenvolvedores

## 🚨 Troubleshooting de Permissões

### Erro: "AccessDenied" ou "not authorized"

```bash
# Ver qual identity está sendo usada
aws sts get-caller-identity

# Ver policies anexadas ao usuário
aws iam list-attached-user-policies --user-name jimy

# Ver policies inline do usuário
aws iam list-user-policies --user-name jimy
```

### Erro: "You are not authorized to perform this operation"

Isso geralmente significa:
1. A policy não está anexada corretamente
2. A policy não tem a permissão específica (Action)
3. Há uma política de negação explícita (Deny)

**Solução**:
- Verifique as policies anexadas
- Se usando policy customizada, adicione a Action necessária
- Verifique Service Control Policies (SCPs) se estiver usando AWS Organizations

### Erro ao criar recursos: "InsufficientPermissions"

**Para S3**:
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:CreateBucket",
    "s3:PutBucketVersioning",
    "s3:PutBucketEncryption",
    "s3:PutBucketPublicAccessBlock"
  ],
  "Resource": "arn:aws:s3:::terraform-state-neural-hive-*"
}
```

**Para EKS**:
```json
{
  "Effect": "Allow",
  "Action": [
    "eks:CreateCluster",
    "eks:DescribeCluster",
    "eks:ListClusters",
    "eks:UpdateClusterConfig",
    "eks:DeleteCluster"
  ],
  "Resource": "*"
}
```

## 📞 Suporte

Se continuar com problemas de permissões:

1. **Verifique o CloudTrail** para ver exatamente qual Action está falhando
2. **Use o IAM Policy Simulator**: https://policysim.aws.amazon.com/
3. **Consulte a documentação AWS IAM**: https://docs.aws.amazon.com/IAM/

## 🔄 Próximos Passos

Após configurar as permissões:

```bash
# 1. Verificar se permissões estão OK
aws sts get-caller-identity

# 2. Recarregar ambiente
source /root/.neural-hive-dev-env

# 3. Executar deployment
cd /jimy/Neural-Hive-Mind
export SKIP_S3_BACKEND=true
./scripts/deploy/deploy-eks-complete.sh
```

---

🤖 **Neural Hive-Mind - AWS Permissions Guide**
*Configuração segura de permissões IAM*
