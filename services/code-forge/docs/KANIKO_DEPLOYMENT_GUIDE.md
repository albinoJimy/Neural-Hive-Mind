# Code Forge Kaniko - Guia de Deployment

> **Epic:** CF-001 - Kaniko Production-Ready & Private Registries
> **Versão:** 1.0.0
> **Data:** 2026-04-06

---

## Índice

1. [Visão Geral](#visão-geral)
2. [ECR com IAM Roles](#ecr-com-iam-roles)
3. [GCR com Service Accounts](#gcr-com-service-accounts)
4. [ACR com Managed Identities](#acr-com-managed-identities)
5. [Builds Multi-Arch Paralelos](#builds-multi-arch-paralelos)
6. [Troubleshooting](#troubleshooting)

---

## Visão Geral

O Code Forge Kaniko suporta builds de container usando Kaniko em Kubernetes com autenticação automática para múltiplos registries privados:

| Registry | Método Principal | Fallback | TTL Cache |
|----------|------------------|----------|-----------|
| **AWS ECR** | IRSA (IAM Roles for Service Accounts) | Access Key/Secret | 12h |
| **GCP GCR** | Workload Identity Federation | Service Account Key | 1h |
| **Azure ACR** | Managed Identity (Pod Identity) | Service Principal | 2h |

---

## ECR com IAM Roles

### Configuração Recomendada (IRSA)

O IRSA (IAM Roles for Service Accounts) é o método recomendado para ECR em EKS.

#### 1. Criar Política IAM para ECR

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:GetRepositoryPolicy",
        "ecr:DescribeRepositories",
        "ecr:ListImages",
        "ecr:DescribeImages",
        "ecr:BatchGetImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage"
      ],
      "Resource": "arn:aws:ecr:<region>:<account-id>:repository/*"
    }
  ]
}
```

#### 2. Criar IAM Role e Trust Policy

```bash
# Criar OIDC provider para EKS (se não existir)
eksctl utils associate-iam-oidc-provider \
  --region=<region> \
  --cluster=<cluster-name> \
  --approve

# Criar IAM Role
kubectl create serviceaccount \
  -n code-forge \
  kaniko-builder

# Anotar service account
kubectl annotate serviceaccount \
  -n code-forge \
  kaniko-builder \
  eks.amazonaws.com/role-arn=arn:aws:iam::<account-id>:role/KanikoBuilderECR
```

#### 3. Variáveis de Ambiente

```yaml
env:
  - name: AWS_REGION
    value: "us-east-1"
```

### Fallback: Credenciais Estáticas

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ecr-credentials
  namespace: code-forge
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "AKIAIOSFODNN7EXAMPLE"
  AWS_SECRET_ACCESS_KEY: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

```yaml
envFrom:
  - secretRef:
      name: ecr-credentials
```

---

## GCR com Service Accounts

### Configuração Recomendada (Workload Identity)

O Workload Identity Federation permite que pods GKE autentiquem como GSA (Google Service Account).

#### 1. Ativar Workload Identity no GKE Cluster

```bash
gcloud container clusters update <cluster-name> \
  --region=<region> \
  --workload-pool=<project-id>.svc.id.goog
```

#### 2. Criar Google Service Account

```bash
gcloud iam service-accounts create kaniko-builder \
  --project=<project-id>
```

#### 3. Conceder permissões de GCR

```bash
# Para registry específico
gcloud projects add-iam-policy-binding <project-id> \
  --member="serviceAccount:kaniko-builder@<project-id>.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"

# Para escrita (push)
gcloud projects add-iam-policy-binding <project-id> \
  --member="serviceAccount:kaniko-builder@<project-id>.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

#### 4. Configurar IAM Policy Binding

```bash
gcloud iam service-accounts add-iam-policy-binding kaniko-builder@<project-id>.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:<project-id>.svc.id.goog[${namespace}/kaniko-builder]"
```

### Fallback: Service Account Key

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: gcr-service-account
  namespace: code-forge
type: Opaque
stringData:
  key.json: |
    {
      "type": "service_account",
      "project_id": "<project-id>",
      "private_key_id": "...",
      "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
      "client_email": "kaniko-builder@<project-id>.iam.gserviceaccount.com"
    }
```

Montar como volume no pod:

```yaml
volumes:
  - name: gcr-key
    secret:
      secretName: gcr-service-account
containers:
  - name: kaniko
    volumeMounts:
      - name: gcr-key
        mountPath: /var/secrets/google
    env:
      - name: GOOGLE_APPLICATION_CREDENTIALS
        value: /var/secrets/google/key.json
```

---

## ACR com Managed Identities

### Configuração Recomendada (Pod Identity)

O Azure Pod Identity permite que pods AKS autentiquem usando Managed Identity.

#### 1. Instalar Azure AD Pod Identity

```bash
helm repo add aad-pod-identity https://raw.githubusercontent.com/Azure/aad-pod-identity/master/charts
helm install aad-pod-identity aad-pod-identity/aad-pod-identity
```

#### 2. Criar Azure Identity

```bash
# Criar User Assigned Managed Identity
az identity create \
  --name kaniko-builder-identity \
  --resource-group <resource-group>

# Atribuir role ACRPush/ACRPull
az role assignment create \
  --assignee <identity-principal-id> \
  --role "AcrPush" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ContainerRegistry/registries/<registry-name>"
```

#### 3. Criar AzureIdentity e AzureIdentityBinding

```yaml
apiVersion: "aadpodidentity.k8s.io/v1"
kind: AzureIdentity
metadata:
  name: kaniko-identity
  namespace: code-forge
spec:
  type: 0  # UserAssigned
  resourceID: <azure-identity-resource-id>
  clientID: <azure-identity-client-id>
```

```yaml
apiVersion: "aadpodidentity.k8s.io/v1"
kind: AzureIdentityBinding
metadata:
  name: kaniko-binding
  namespace: code-forge
spec:
  azureIdentityRef:
    name: kaniko-identity
  selector: kaniko-builder
```

#### 4. Anotar Pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kaniko-builder
  namespace: code-forge
  labels:
    aadpodidbinding: kaniko-builder
spec:
  # ...
```

### Fallback: Service Principal

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: acr-sp-credentials
  namespace: code-forge
type: Opaque
stringData:
  ACR_CLIENT_ID: "<application-client-id>"
  ACR_CLIENT_SECRET: "<client-secret>"
  ACR_TENANT_ID: "<tenant-id>"
```

---

## Builds Multi-Arch Paralelos

### Uso do ParallelBuilder

```python
from src.services.kaniko.parallel_builder import ParallelBuilder

builder = ParallelBuilder(
    max_concurrent_builds=4,  # Máximo de builds simultâneos
    timeout_per_platform=3600,  # Timeout por plataforma
)

summary = await builder.build_parallel(
    dockerfile_path="Dockerfile",
    build_context=".",
    image_name="myapp",
    platforms=["linux/amd64", "linux/arm64"],
    registry="myregistry.com",
    tag="v1.0.0",
    cache=True,
    cache_repo="myregistry.com/cache",
)

if summary.success:
    print(f"Build completado! Manifest: {summary.manifest_digest}")
    print(f"Speedup: {summary.success_rate:.2f}x")
else:
    print(f"Build parcial: {len(summary.platforms_succeeded)}/{len(summary.platforms_requested)}")
    for platform, error in summary.platforms_failed.items():
        print(f"  {platform}: {error}")
```

### Plataformas Suportadas

| Arquitetura | Platform String | QEMU Necessário? |
|-------------|----------------|------------------|
| AMD64 | `linux/amd64` | Não |
| ARM64 | `linux/arm64` | Sim (`qemu-aarch64`) |
| ARM v7 | `linux/arm/v7` | Sim (`qemu-arm`) |
| PPC64LE | `linux/ppc64le` | Sim (`qemu-ppc64le`) |
| s390x | `linux/s390x` | Sim (`qemu-s390x`) |

### Speedup Esperado

| Plataformas | Sequencial | Paralelo (4 workers) | Speedup |
|-------------|------------|----------------------|---------|
| 2 | 200s | 110s | 1.8x |
| 3 | 300s | 120s | 2.5x |
| 4 | 400s | 130s | 3.1x |

---

## Troubleshooting

### Erro: "no space left on device"

**Sintoma:** Kaniko falha com erro de espaço em disco.

**Causa:** Contexto de build muito grande para ConfigMap (limite ~1MB).

**Solução:** PVC Manager é ativado automaticamente para contextos >1MB.

```python
from src.services.kaniko.pvc_manager import PVCManager

pvc_manager = PVCManager(namespace="code-forge")
size_bytes = pvc_manager.detect_context_size("Dockerfile", ".")

if pvc_manager.should_use_pvc(size_bytes):
    print(f"Contexto grande ({size_bytes / 1024 / 1024:.2f}MB), usando PVC")
```

### Erro: "no basic auth credentials" (ECR)

**Sintoma:** Autenticação ECR falha.

**Causa:** IRSA não configurado ou OIDC provider ausente.

**Solução:**

```bash
# Verificar se OIDC provider está configurado
eksctl get iam-oidc-provider --region=<region> --cluster=<cluster-name>

# Verificar anotação do service account
kubectl get sa kaniko-builder -n code-forge -o yaml
```

### Erro: "UNAVAILABLE: Getting credentials" (GCR)

**Sintoma:** Autenticação GCR falha.

**Causa:** Workload Identity não configurado ou service account inválido.

**Solução:**

```bash
# Verificar workload pool
gcloud container clusters describe <cluster-name> \
  --region=<region> \
  --format="value(workloadIdentityConfig)"

# Verificar IAM binding
gcloud iam service-accounts get-iam-policy \
  kaniko-builder@<project-id>.iam.gserviceaccount.com
```

### Erro: "unauthorized: authentication required" (ACR)

**Sintoma:** Autenticação ACR falha.

**Causa:** Pod Identity não configurado ou role não atribuída.

**Solução:**

```bash
# Verificar AzureIdentity
kubectl get azureidentity -n code-forge

# Verificar pods com label correto
kubectl get pods -n code-forge -L aadpodidbinding
```

### Erro: "QEMU not available"

**Sintoma:** Build multi-arch falha para arquiteturas não-nativas.

**Causa:** Binários QEMU não instalados no init container.

**Solução:** Binários QEMU são instalados automaticamente pelo init container. Verifique:

```bash
# Logs do init container qemu-setup
kubectl logs <kaniko-pod> -c qemu-setup
```

### Logs Úteis

```bash
# Logs do pod Kaniko
kubectl logs <kaniko-pod> -n code-forge

# Eventos do pod
kubectl describe pod <kaniko-pod> -n code-forge

# Status do PVC (se usado)
kubectl get pvc -n code-forge
kubectl describe pvc <pvc-name> -n code-forge
```

---

## Security Best Practices

1. **Nunca logar tokens ou credenciais** - Os clientes ECR/GCR/ACR nunca expõem tokens em logs.

2. **Tokens apenas em memória** - Tokens são cacheados apenas na memória do processo e nunca persistidos em disco.

3. **Usar identidade gerenciada quando disponível** - IRSA, Workload Identity, e Pod Identity são mais seguros que credenciais estáticas.

4. **Rotacionar credenciais regularmente** - Tokens têm TTL curto (1-12h) e são renovados automaticamente.

5. **Princípio de menor privilégio** - Conceder apenas permissões necessárias (leitura/escrita em registries específicos).
