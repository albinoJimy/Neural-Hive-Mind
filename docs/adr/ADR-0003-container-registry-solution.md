# ADR-0003: Solução de Container Registry para Neural Hive-Mind

## Status
Aceito

## Contexto
O Neural Hive-Mind requer um container registry seguro que implemente scanning de vulnerabilidades, assinatura de imagens, controle de acesso granular e integração com pipelines CI/CD para garantir supply chain security.

### Requisitos Funcionais
- **Vulnerability Scanning**: Detecção automática de CVEs
- **Image Signing**: Verificação de integridade com Sigstore/Notary
- **Access Control**: RBAC granular por repositório
- **Webhook Integration**: Notificações para pipelines CI/CD
- **Multi-Arch Support**: AMD64, ARM64 para diferentes workloads
- **Retention Policies**: Limpeza automática de imagens antigas
- **High Availability**: 99.9% uptime SLA
- **Audit Logging**: Compliance e troubleshooting

### Requisitos Não-Funcionais
- **Performance**: < 30s push/pull para imagens 1GB
- **Storage**: Suporte a 10TB+ com crescimento
- **Bandwidth**: 10Gbps+ para CI/CD paralelo
- **Security**: Encryption at rest e in transit
- **Compliance**: SOC2, PCI-DSS compatible

### Alternativas Consideradas

#### AWS ECR (Elastic Container Registry)
**Prós:**
- Integração nativa com EKS e IAM
- Scanning de vulnerabilidades com Amazon Inspector
- Encryption automática com KMS
- Lifecycle policies para retenção
- VPC Endpoints para rede privada
- Replicação cross-region built-in
- Pay-per-use sem custos fixos
- Compliance AWS (SOC, PCI, HIPAA)

**Contras:**
- Vendor lock-in com AWS
- Assinatura de imagens limitada (sem Sigstore nativo)
- Interface web básica
- Sem registry on-premises option

**Custos Estimados:**
- Storage: $0.10/GB-month
- Data Transfer: $0.09/GB
- Estimated: $500-2000/month

#### Harbor (Self-Hosted)
**Prós:**
- Open source CNCF project
- Registry distribuído com HA nativo
- Vulnerability scanning com Trivy/Clair
- Content trust com Notary
- RBAC granular por projeto
- Multi-tenancy robusto
- Replicação entre registries
- Webhook notifications
- Compliance scanning

**Contras:**
- Operational overhead significativo
- Requires expertise para maintenance
- Storage backend dependency (S3, NFS, etc.)
- Database dependency (PostgreSQL)
- Self-managed security patches

**Custos Estimados:**
- Infrastructure: $2000-5000/month
- Operations: 1-2 FTE
- Total: $15,000-25,000/month

#### Docker Hub (Managed)
**Prós:**
- Registry público líder
- Large ecosystem
- Docker official images
- Vulnerability scanning (Teams+)
- Automated builds

**Contras:**
- Rate limiting agressivo
- Custos altos para uso enterprise
- Menos controle de segurança
- Não adequado para imagens privadas sensíveis
- Compliance limitado

#### Google Container Registry (GCR) / Artifact Registry
**Prós:**
- Integration nativa com GKE
- Binary Authorization para policies
- Vulnerability scanning com Container Analysis
- IAM integration
- Global availability

**Contras:**
- Vendor lock-in com GCP
- Custos podem ser altos
- Menos expertise interna

#### Quay.io (Red Hat)
**Prós:**
- Security scanning robusto
- Time machine para rollbacks
- Geo-replication
- Fine-grained permissions

**Contras:**
- Custos enterprise altos
- Menos integração com AWS
- Learning curve

## Decisão
**Escolhemos AWS ECR como solução de container registry.**

### Justificativa Técnica

#### Integração Nativa
- **EKS Integration**: Zero-configuration com cluster
- **IAM Policies**: RBAC através de roles existentes
- **KMS Encryption**: Chaves gerenciadas centralmente
- **VPC Endpoints**: Tráfego privado sem internet

#### Segurança
- **Vulnerability Scanning**: Amazon Inspector v2 automático
- **Immutable Tags**: Proteção contra overwrites
- **Encryption**: At rest (KMS) e in transit (TLS)
- **Access Logging**: CloudTrail integration

#### Operacional
- **Zero Maintenance**: Fully managed pela AWS
- **Scalability**: Automática sem limites práticos
- **Backup**: Replicação cross-region disponível
- **SLA**: 99.9% uptime garantido

### Compensações Aceitas

#### Image Signing Limitation
**Problema**: ECR não suporta Sigstore nativamente
**Solução**:
- Implementar assinatura via pipeline CI/CD
- Usar SHA256 digests para verificação
- Política OPA para block unsigned images
- Migrar para Sigstore quando disponível

#### Vendor Lock-in
**Problema**: Dependência de AWS ECR
**Solução**:
- Images são OCI-compliant (portáveis)
- Backup images em registry secundário
- Terraform para infrastructure as code
- Multi-cloud strategy em roadmap futuro

### Configuração Implementada

```hcl
# Repositórios por componente
repositories = [
  "cognitive-processor",
  "orchestration-engine",
  "execution-agent",
  "memory-store",
  "event-bus"
]

# Scanning automático
scan_on_push = true

# Lifecycle policy
lifecycle_policy = {
  rules = [
    {
      rulePriority = 1
      description  = "Manter 20 imagens tagged"
      countType    = "imageCountMoreThan"
      countNumber  = 20
    },
    {
      rulePriority = 2
      description  = "Remover untagged após 7 dias"
      countType    = "sinceImagePushed"
      countNumber  = 7
    }
  ]
}

# Replicação cross-region
replication = {
  destination_region = "us-west-2"
  filter_patterns = ["neural-hive/*"]
}
```

## Consequências

### Positivas
- **Zero Operational Overhead**: Fully managed pela AWS
- **Tight EKS Integration**: ImagePullSecrets automáticos
- **Cost Effective**: Pay-per-use, sem fixed costs
- **High Performance**: Low latency para EKS clusters
- **Compliance Ready**: SOC2/PCI através de AWS

### Negativas
- **Vendor Lock-in**: Dependência de AWS ecosystem
- **Feature Limitations**: Menos features que Harbor
- **Sigstore Gap**: Assinatura de imagem não nativa
- **Interface**: Web UI básica comparado a alternativas

### Mitigações Implementadas

#### Supply Chain Security
```yaml
# OPA Policy para imagens assinadas
apiVersion: templates.gatekeeper.sh/v1beta1
kind: ConstraintTemplate
metadata:
  name: requiresignedimages
spec:
  # Requer SHA256 digest para verificação
  # Block latest tags
  # Allow apenas registries autorizados
```

#### Backup Strategy
- **Cross-Region Replication**: us-east-1 → us-west-2
- **Weekly Snapshots**: Critical images para S3
- **Disaster Recovery**: Restore procedures documentados

#### Cost Control
- **Lifecycle Policies**: Limpeza automática
- **Monitoring**: CloudWatch metrics e alerts
- **Budget Alerts**: Notificação se >$5000/month

### Métricas de Sucesso
- **Vulnerability Detection**: 100% imagens scanned
- **Policy Compliance**: Zero imagens unsigned em produção
- **Performance**: <30s push/pull para imagens 1GB
- **Availability**: >99.9% uptime
- **Cost**: <$3000/month primeiros 6 meses

## Implementação

### Fase 1 - Basic Registry (Atual)
- ✅ ECR repositories para componentes core
- ✅ Vulnerability scanning habilitado
- ✅ Lifecycle policies configuradas
- ✅ IAM roles para EKS integration

### Fase 2 - Security Hardening
- [ ] OPA policies para image validation
- [ ] CI/CD integration para signing
- [ ] Cross-region replication setup
- [ ] Monitoring e alerting

### Fase 3 - Advanced Features
- [ ] Automated vulnerability remediation
- [ ] Custom scanning rules
- [ ] Registry mirroring para upstreams
- [ ] Multi-account sharing

## Revisão
Esta decisão será revisada em 12 meses ou se:
- Custos excederem $5000/month consistentemente
- AWS ECR adicionar suporte nativo a Sigstore
- Requisitos multi-cloud tornarem-se críticos
- Harbor ou alternativa oferecer managed service superior

---
**Autor**: Neural Hive Platform Team
**Data**: 2024-01-15
**Revisores**: Security Team, DevOps Team, FinOps Team