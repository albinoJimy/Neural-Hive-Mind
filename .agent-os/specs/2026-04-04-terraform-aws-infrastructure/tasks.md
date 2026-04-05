# Tasks - Terraform/IaC AWS Infrastructure

> **Spec:** `.agent-os/specs/2026-04-04-terraform-aws-infrastructure/spec.md`
> **Data:** 2026-04-04
> **Estimativa Total:** 424 horas (~10 semanas)

---

## Epic 1: Foundation (56 horas)

### 1.1 Módulo VPC com Subnets Multi-AZ

**ID:** IaC-001
**Estimativa:** 16 horas
**Dependências:** Nenhuma

**Descrição Detalhada:**
Criar módulo Terraform reutilizável para provisionamento de VPC em múltiplas regiões AWS. O módulo deve suportar 3 Availability Zones por região com subnets públicas, privadas e de banco de dados isoladas.

**Requisitos:**
- VPC com CIDR configurável (padrão: 10.0.0.0/16)
- 3 subnets públicas (1 por AZ) para LBs/NAT Gateways
- 3 subnets privadas (1 por AZ) para aplicações
- 3 subnets de database (1 por AZ) isoladas
- Internet Gateway
- NAT Gateways (1 por AZ) em subnets públicas
- VPC Endpoints para S3, DynamoDB, ECR, Secrets Manager
- VPC Flow Logs para CloudWatch Logs (retenção 30 dias)
- DHCP Options Set customizado
- DNS habilitado (DNS support + DNS hostnames)

**Critérios de Aceite:**
- [ ] `terraform validate` passa sem erros
- [ ] `terraform fmt` aplicado
- [ ] Módulo criado em `terraform/modules/vpc/`
- [ ] Variáveis documentadas em `variables.tf`
- [ ] Outputs exportados (vpc_id, subnet_ids, security_group_id)
- [ ] Teste de aplicação completa em dev
- [ ] VPC Flow Logs configurados e enviando para CW Logs

---

### 1.2 Módulo EKS Cluster com Node Pools

**ID:** IaC-002
**Estimativa:** 20 horas
**Dependências:** 1.1 (VPC)

**Descrição Detalhada:**
Criar módulo Terraform para provisionamento de cluster EKS AWS com node pools especializados para diferentes workloads (general, compute, ML).

**Requisitos:**
- EKS Cluster versão 1.29+
- Endpoint privado habilitado
- 3 node pools separados:
  - `general_pool`: t3.xlarge (3 nodes min, 10 max)
  - `compute_pool`: c5.2xlarge (2 nodes min, 8 max)
  - `ml_pool`: g4dn.xlarge (1 node min, 5 max)
- Cluster Autoscaler configurado via IRSA
- VPC CNI com prefix assignment customizado
- Security Groups específicos por node pool
- Labels e taints para seleção de pods
- Kubernetes dashboard habilitado (opcional)
- AWS EBS CSI Driver instalado
- EBS encryption habilitado

**Critérios de Aceite:**
- [ ] EKS cluster criado e reachable
- [ ] kubectl get nodes mostra 3 node pools
- [ ] Nodes têm labels corretos (workload=general/compute/ml)
- [ ] Taints aplicados corretamente
- [ ] Cluster Autoscaler funcional
- [ ] Teste de pod scheduling em cada pool

---

### 1.3 Módulo IAM e KMS

**ID:** IaC-003
**Estimativa:** 12 horas
**Dependências:** Nenhuma

**Descrição Detalhada:**
Criar módulo Terraform para gestão de IAM roles, policies e KMS keys necessárias para todos os componentes da infraestrutura.

**Requisitos:**
- KMS Key para encryption de EBS
- KMS Key para S3 encryption
- KMS Key para Secrets Manager
- KMS Key para RDS encryption
- IAM Role para EKS cluster
- IAM Role para EKS node groups
- IAM Roles para IRSA (pod identity):
  - Cluster Autoscaler
  - AWS Load Balancer Controller
  - External DNS
  - CSI Drivers
- IAM Policies granulares following least privilege
- OIDC provider para EKS

**Critérios de Aceite:**
- [ ] KMS keys criadas com key policies corretas
- [ ] IAM roles seguem nomenclatura padronizada
- [ ] OIDC provider criado e configurado
- [ ] IRSA roles podem ser assumidas pelos pods
- [ ] tfsec scan passa (sem critical issues)

---

### 1.4 Backend Terraform (S3 + DynamoDB)

**ID:** IaC-004
**Estimativa:** 8 horas
**Dependências:** Nenhuma

**Descrição Detalhada:**
Configurar backend remoto Terraform usando S3 para state storage e DynamoDB para locking, com versionamento e encryption.

**Requisitos:**
- Bucket S3 para Terraform state
  - Versionamento habilitado
  - Server-side encryption (SSE-KMS)
  - Lifecycle policy (90 dias non-current)
  - Block public access
- Tabela DynamoDB para state locking
  - Partition key: LockID
  - On-demand capacity
  - Encryption at rest
- Backend config para múltiplos ambientes (dev/staging/prod)
- State segregation por ambiente/região

**Critérios de Aceite:**
- [ ] Backend S3 configurado
- [ ] DynamoDB lock functional
- [ ] `terraform init -backend-config=...` funciona
- [ ] Teste de lock/release
- [ ] State versionamento ativo

---

## Epic 2: Data Layer (120 horas)

### 2.1 Módulo RDS PostgreSQL

**ID:** IaC-005
**Estimativa:** 24 horas
**Dependências:** 1.1 (VPC), 1.3 (IAM/KMS)

**Descrição Detalhada:**
Criar módulo Terraform para provisionamento de instâncias RDS PostgreSQL Multi-AZ com alta disponibilidade.

**Requisitos:**
- RDS PostgreSQL 15.x
- Instance class: db.r6g.xlarge (gravar memória mínima)
- Multi-AZ deployment
- Storage: gp3 (100GB min, autoscaling)
- Encryption: KMS
- Backup: retenção 30 dias, window 03:00-04:00 UTC
- Maintenance window: domingo 04:00-05:00 UTC
- Performance Insights habilitado
- Enhanced Monitoring (interval 15s)
- Parameter groups customizadas
- Option groups
- Security Group restrito (apenas subnets privadas)
- 3 instâncias separadas:
  - execution-ticket-db
  - code-forge-db
  - temporal-db
  - (4a para outros serviços se necessário)

**Critérios de Aceite:**
- [ ] RDS instâncias em Available state
- [ ] Multi-AZ replicação ativa
- [ ] Conexão via psql possível
- [ ] Backup automático configurado
- [ ] Metrics no CloudWatch

---

### 2.2 Módulo ElastiCache Redis

**ID:** IaC-006
**Estimativa:** 20 horas
**Dependências:** 1.1 (VPC)

**Descrição Detalhada:**
Criar módulo Terraform para cluster ElastiCache Redis com modo cluster ou replicação.

**Requisitos:**
- ElastiCache Redis 7.x
- Node type: cache.r6g.large
- Cluster mode: desabilitado (replication group)
- 3 shards (primário + 2 réplicas)
- Automatic failover
- Multi-AZ
- Encryption at-rest (KMS)
- Encryption in-transit (TLS)
- AUTH token
- Parameter group (maxmemory-policy: allkeys-lru)
- Security group customizado
- 10 clusters separados (ou 1 com databases separados):
  - gateway-cache
  - orchestrator-cache
  - optimizer-cache
  - queen-cache
  - service-registry-cache
  - guard-cache
  - analyst-cache
  - self-healing-cache
  - feature-store-cache
  - (outros se necessário)

**Critérios de Aceite:**
- [ ] Redis clusters criados e reachable
- [ ] Replication funcionando
- [ ] Teste de failover manual
- [ ] Conexão via redis-cli
- [ ] TLS obrigatório funcionando

---

### 2.3 Módulo MSK Kafka

**ID:** IaC-007
**Estimativa:** 24 horas
**Dependências:** 1.1 (VPC), 1.3 (IAM/KMS)

**Descrição Detalhada:**
Criar módulo Terraform para Amazon MSK (Managed Streaming for Kafka) com configuração de cluster e tópicos.

**Requisitos:**
- MSK Cluster provisioned
- Kafka 3.x
- Broker type: kafka.t3.small
- 3 brokers (1 por AZ)
- Storage: 100GB per broker
- Throughput: auto throughput
- Encryption at-rest (SSE-KMS)
- Encryption in-transit (TLS 1.2)
- SASL/IAM authentication
- Client authentication: mTLS + SASL/IAM
- Log delivery to CloudWatch
- Monitoring: broker-level metrics
- Tópicos padrão:
  - intentions
  - cognitive-plans
  - execution-tickets
  - specialist-opinions
  - consensus-decisions
  - telemetry
  - alerts
  - feedback
  - workflow-events
  - (outros conforme necessário)

**Critérios de Aceite:**
- [ ] MSK cluster em Active state
- [ ] Tópicos criados automaticamente
- [ ] Producer/Consumer teste funcionam
- [ ] SASL/IAM auth funcional
- [ ] Metrics no CloudWatch

---

### 2.4 Módulo Neptune

**ID:** IaC-008
**Estimativa:** 20 horas
**Dependências:** 1.1 (VPC), 1.3 (IAM/KMS)

**Descrição Detalhada:**
Criar módulo Terraform para Amazon Neptune Graph Database para uso do Queen Agent e Analyst Agents.

**Requisitos:**
- Neptune Engine 1.2.x
- Instance class: db.r6g.large
- Multi-AZ (reader instance)
- Storage: 100GB min, autoscaling
- Encryption: KMS
- IAM authentication
- Neptune cluster endpoint
- Neptune reader endpoint
- Security group específico
- Snapshot retention: 7 dias
- Parameter groups
- Clusters:
  - queen-knowledge-graph
  - analyst-knowledge-graph

**Critérios de Aceite:**
- [ ] Neptune cluster criado e available
- [ ] Gremlin queries funcionam
- [ ] Loader endpoint para bulk upload
- [ ] Backup automático configurado

---

### 2.5 Módulo MongoDB Atlas

**ID:** IaC-009
**Estimativa:** 12 horas
**Dependências:** 1.1 (VPC)

**Descrição Detalhada:**
Criar módulo Terraform usando provider MongoDB Atlas para provisionar clusters na nuvem.

**Requisitos:**
- MongoDB Atlas Cluster
- Tier: M30 (prod) / M10 (dev)
- Provider: AWS
- Region: us-east-1
- Replication factor: 3
- Auto-scaling: habilitado
- Backup: habilitado
- Encryption at-rest
- Network peering com VPC AWS
- Database users
- Clusters:
  - specialist-feedback
  - cognitive-plans
  - ml-models-metadata

**Critérios de Aceite:**
- [ ] Cluster Atlas criado
- [ ] VPC peering estabelecido
- [ ] Conexão via connection string privada
- [ ] Usuários criados com roles corretas

---

### 2.6 Integração Data Layer com EKS

**ID:** IaC-010
**Estimativa:** 20 horas
**Dependências:** 2.1, 2.2, 2.3, 2.4, 2.5, 1.2 (EKS)

**Descrição Detalhada:**
Criar recursos de integração entre data layer e EKS (secrets, endpoints, connectivity).

**Requisitos:**
- Kubernetes Secrets para endpoints
- External Secrets Operator
- Secret entries para:
  - RDS connection strings
  - Redis endpoints
  - MSK bootstrap servers
  - Neptune endpoints
  - Atlas connection strings
- Kubernetes Services para PrivateLink
- Network policies (se CNI calico/ cilium)

**Critérios de Aceite:**
- [ ] Secrets sincronizados do AWS Secrets Manager
- [ ] Pods podem conectar a todos os databases
- [ ] DNS resolution funcionando
- [ ] Teste de conectividade E2E

---

## Epic 3: Networking (32 horas)

### 3.1 Módulo VPC Peering

**ID:** IaC-011
**Estimativa:** 12 horas
**Dependências:** 1.1 (VPC)

**Descrição Detalhada:**
Criar módulo Terraform para estabelecer peering connections entre VPCs em diferentes regiões.

**Requisitos:**
- VPC Peering entre:
  - us-east-1 ↔ us-west-2
  - us-east-1 ↔ eu-west-1
- Route table entries para rotas
- Peering accepter automaticamente
- DNS resolution habilitado
- State file compartilhado ou remote state data

**Critérios de Aceite:**
- [ ] Peering connections em Active state
- [ ] Ping entre instâncias em regiões diferentes
- [ ] Route tables atualizadas
- [ ] Teste de conectividade trans-regional

---

### 3.2 Módulo Route53

**ID:** IaC-012
**Estimativa:** 12 horas
**Dependências:** 1.1 (VPC), 1.2 (EKS)

**Descrição Detalhada:**
Criar módulo Terraform para DNS management via Route53.

**Requisitos:**
- Hosted Zone pública
- Hosted Zones privadas por VPC
- Registros:
  - API Gateway (*.api.neuralhive.io)
  - Apps (*.app.neuralhive.io)
  - Internal services (*.internal)
- Health checks para endpoints críticos
- DNSSEC (opcional)
- Certificates via ACM

**Critérios de Aceite:**
- [ ] Hosted zone delegada
- [ ] DNS resolution funcionando
- [ ] Health checks passando
- [ ] Certificados ACM emitidos

---

### 3.3 Security Groups

**ID:** IaC-013
**Estimativa:** 8 horas
**Dependências:** 1.1 (VPC), 1.2 (EKS)

**Descrição Detalhada:**
Criar módulo Terraform para gestão centralizada de security groups seguindo princípios de least privilege.

**Requisitos:**
- SGs separados por camada:
  - Public LB (80, 443)
  - Private LB (8080, 8443)
  - EKS control plane
  - EKS nodes
  - RDS
  - ElastiCache
  - MSK
  - Neptune
- Regras baseadas em prefix lists
- Security Group references
- Auditoria de regras abertas (0.0.0.0/0)

**Critérios de Aceite:**
- [ ] SGs criadas com regras mínimas
- [ ] Nenhuma regra 0.0.0.0/0 em portas não-HTTP
- [ ] tfsec scan passa
- [ ] Documentação de regras

---

## Epic 4: Observabilidade (32 horas)

### 4.1 Módulo CloudWatch

**ID:** IaC-014
**Estimativa:** 16 horas
**Dependências:** 1.2 (EKS)

**Descrição Detalhada:**
Criar módulo Terraform para configuração completa de CloudWatch (logs, metrics, alarms, dashboards).

**Requisitos:**
- Log Groups:
  - /eks/applications
  - /eks/cluster-autoscaler
  - /rds/postgresql
  - /elasticache/redis
  - /msk/broker
  - /neptune
  - lambda/functions
- Metric filters para logs estruturados
- CloudWatch Dashboards (JSON import)
  - EKS Cluster Overview
  - Data Layer Health
  - Application Metrics
- Alarms críticos:
  - CPU > 80%
  - Memory > 85%
  - 5xx errors
  - Latency P99 > 1s
  - Disk space < 20%
  - Replica lag
- SNS topics para alarmes
- CloudWatch Agent DaemonSet
- Fluent Bit para logs de aplicação

**Critérios de Aceite:**
- [ ] Log groups criados
- [ ] Dashboard visível no CW Console
- [ ] Alarms disparando corretamente
- [ ] Logs de pods chegando ao CW Logs
- [ ] Fluent Bit DaemonSet running

---

### 4.2 Módulo S3 para Logs/Backups

**ID:** IaC-015
**Estimativa:** 8 horas
**Dependências:** 1.3 (KMS)

**Descrição Detalhada:**
Criar módulo Terraform para buckets S3 para armazenamento de logs e backups.

**Requisitos:**
- S3 Buckets:
  - neuralhive-application-logs
  - neuralhive-backups
  - neuralhive-model-artifacts
  - neuralhive-traces
- Encryption: SSE-KMS
- Versionamento habilitado
- Lifecycle policies:
  - Glacier após 30 dias
  - Deep Archive após 90 dias
  - Expiração após 1 ano
- Bucket policies restritivas
- Access logging habilitado

**Critérios de Aceite:**
- [ ] Buckets criados com encryption
- [ ] Lifecycle policies ativas
- [ ] Teste de upload/download
- [ ] Bucket policy denying public access

---

### 4.3 OpenTelemetry Integration

**ID:** IaC-016
**Estimativa:** 8 horas
**Dependências:** 1.2 (EKS), 4.1 (CloudWatch)

**Descrição Detalhada:**
Criar módulo Terraform para部署 do OpenTelemetry Collector e AWS Distro for OpenTelemetry (ADOT).

**Requisitos:**
- ADOT Collector deployment
- Cert Manager para mTLS
- Prometheus Receiver
- CloudWatch EMF Exporter
- X-Ray Centralized Sampling
- Jaeger exporter (para dev)
- Service Graph
- Trace ingestion para X-Ray

**Critérios de Aceite:**
- [ ] Collector pods running
- [ ] Traces visíveis no X-Ray console
- [ ] Metrics no CloudWatch
- [ ] Service map funcionando

---

## Epic 5: Ambientes (80 horas)

### 5.1 Ambiente Dev (us-east-1)

**ID:** IaC-017
**Estimativa:** 16 horas
**Dependências:** Todos módulos dos Epics 1-4

**Descrição Detalhada:**
Configurar ambiente de desenvolvimento com recursos reduzidos e flags de desenvolvimento habilitadas.

**Requisitos:**
- Workspace Terraform `dev`
- Região: us-east-1
- VPC: 10.0.0.0/16
- EKS: node pools menores (1 node cada)
- RDS: db.t4g.micro
- ElastiCache: cache.t4g.small
- MSK: kafka.t3.small
- Neptune: db.t4g.medium
- Tags: Environment=dev, Team=platform
- Cost estimation: ~$500/mês

**Critérios de Aceite:**
- [ ] `terraform workspace new dev` criado
- [ ] `terraform apply` completa sem erros
- [ ] EKS cluster funcional
- [ ] Todos databases conectáveis
- [ ] Cost estimation documentada

---

### 5.2 Ambiente Staging (us-east-1)

**ID:** IaC-018
**Estimativa:** 16 horas
**Dependências:** 5.1 (Dev)

**Descrição Detalhada:**
Configurar ambiente de staging com especificações próximas de produção para testes realistas.

**Requisitos:**
- Workspace Terraform `staging`
- Região: us-east-1
- VPC: 10.1.0.0/16
- EKS: node pools médios (2-3 nodes)
- RDS: db.r6g.large
- ElastiCache: cache.r6g.medium
- MSK: kafka.m5.large
- Neptune: db.r6g.large
- Tags: Environment=staging, Team=platform
- Cost estimation: ~$1500/mês

**Critérios de Aceite:**
- [ ] `terraform workspace new staging` criado
- [ ] `terraform apply` completa sem erros
- [ ] Testes de carga funcionando
- [ ] Produtos instalados via Helm

---

### 5.3 Ambiente Prod East (us-east-1)

**ID:** IaC-019
**Estimativa:** 16 horas
**Dependências:** 5.2 (Staging)

**Descrição Detalhada:**
Configurar ambiente de produção primário na região leste dos EUA com alta disponibilidade.

**Requisitos:**
- Workspace Terraform `prod-east`
- Região: us-east-1
- VPC: 10.2.0.0/16
- EKS: node pools completos (3-10 nodes)
- RDS: db.r6g.2xlarge Multi-AZ
- ElastiCache: cache.r6g.large Multi-AZ
- MSK: kafka.m5.2xlarge Multi-AZ
- Neptune: db.r6g.2xlarge Multi-AZ
- Tags: Environment=production, Region=east, Critical=true
- Cost estimation: ~$5000/mês
- Maintenance windows configurados

**Critérios de Aceite:**
- [ ] Workspace prod configurado
- [ ] HA verificado (failover test)
- [ ] Performance baseline estabelecido
- [ ] Runbooks documentados

---

### 5.4 Ambiente Prod West (us-west-2)

**ID:** IaC-020
**Estimativa:** 16 horas
**Dependências:** 5.3 (Prod East), 3.1 (VPC Peering)

**Descrição Detalhada:**
Configurar ambiente de produção na região oeste dos EUA com DR capability.

**Requisitos:**
- Workspace Terraform `prod-west`
- Região: us-west-2
- VPC: 10.3.0.0/16
- VPC Peering com prod-east
- Mesmas specs que prod-east
- Data replication: cross-region
- Tags: Environment=production, Region=west, DR=true

**Critérios de Aceite:**
- [ ] Cross-region peering ativo
- [ ] Replicação de dados funcionando
- [ ] DNS routing com latency-based routing
- [ ] DR test documentado

---

### 5.5 Ambiente Prod EU (eu-west-1)

**ID:** IaC-021
**Estimativa:** 16 horas
**Dependências:** 5.3 (Prod East), 3.1 (VPC Peering)

**Descrição Detalhada:**
Configurar ambiente de produção na Europa para compliance e latência local.

**Requisitos:**
- Workspace Terraform `prod-eu`
- Região: eu-west-1
- VPC: 10.4.0.0/16
- VPC Peering com prod-east
- Specs alinhadas com prod-east
- GDPR compliance
- Tags: Environment=production, Region=eu, Compliance=GDPR

**Critérios de Aceite:**
- [ ] Região europeia ativa
- [ ] Dados residindo na UE
- [ ] Latência <100ms para usuários EU
- [ ] Compliance verificado

---

## Epic 6: CI/CD (64 horas)

### 6.1 GitHub Actions para Terraform

**ID:** IaC-022
**Estimativa:** 24 horas
**Dependências:** Todos os módulos

**Descrição Detalhada:**
Criar workflows GitHub Actions para CI/CD de Terraform com validação, planejamento e aplicação automatizada.

**Requisitos:**
- Workflows:
  - `.github/workflows/terraform-validate.yml`
  - `.github/workflows/terraform-plan-dev.yml`
  - `.github/workflows/terraform-plan-prod.yml`
  - `.github/workflows/terraform-apply-dev.yml`
  - `.github/workflows/terraform-apply-prod.yml`
- Steps incluem:
  - checkout
  - setup terraform
  - terraform fmt -check
  - terraform init
  - terraform validate
  - tflint
  - tfsec
  - terraform plan
  - terraform apply (manual approval)
- OIDC role para GitHub Actions
- Secrets necessárias configuradas
- Comentarios no PR com plan output

**Critérios de Aceite:**
- [ ] PR trigger validate + fmt + security scan
- [ ] Plan comentado no PR
- [ ] Apply requer 2 approvals para prod
- [ ] Workflow logs disponíveis
- [ ] OIDC authentication funcionando

---

### 6.2 Documentação de Módulos

**ID:** IaC-023
**Estimativa:** 16 horas
**Dependências:** Todos os módulos

**Descrição Detalhada:**
Criar documentação completa para todos os módulos Terraform seguindo padrão da comunidade.

**Requisitos:**
- README.md em cada módulo com:
  - Descrição
  - Arquitetura (diagrama)
  - Variáveis de entrada
  - Outputs
  - Exemplos de uso
  - Requisitos
  - Limitações
  - Licença
- Exemplos em `examples/`
- Terraform docs gerado automaticamente
- Diagramas em Mermaid ou TF-Visualize

**Critérios de Aceite:**
- [ ] README.md em todos módulos
- [ ] `terraform-docs` gera documentação
- [ ] Exemplos funcionais
- [ ] Diagramas visuais

---

### 6.3 Deployment Guides

**ID:** IaC-024
**Estimativa:** 12 horas
**Dependências:** 6.2 (Documentação)

**Descrição Detalhada:**
Criar guias de deployment para diferentes cenários e usuários.

**Requisitos:**
- `docs/deployment-guide.md`:
  - Pré-requisitos
  - Setup inicial
  - Deploy dev
  - Deploy staging
  - Deploy prod
  - Rollback procedures
  - Troubleshooting
- `docs/runbooks/`:
  - Scale EKS nodes
  - Recover RDS
  - Restore backup
  - Handle VPC peering failure
- `docs/cost-optimization.md`:
  - Rightsizing guide
  - Reserved instances
  - Savings plans

**Critérios de Aceite:**
- [ ] Guide completo em markdown
- [ ] Steps validados manualmente
- [ ] Screenshots incluídos
- [ ] Runbooks prontos

---

### 6.4 Testes de Terraform

**ID:** IaC-025
**Estimativa:** 12 horas
**Dependências:** Todos os módulos

**Descrição Detalhada:**
Implementar testes automatizados para código Terraform usando terraform-test ou kitchen-terraform.

**Requisitos:**
- Unit tests com `terraform-test`:
  - Teste de variáveis
  - Teste de outputs
  - Teste de recursos criados
- Integration tests com `terratest`:
  - Teste de módulo VPC
  - Teste de módulo EKS
  - Teste de módulo RDS
- Testes de configuração:
  - tflint
  - tfsec
  - checkov
  - terraform-compliance
- Coverage >80%

**Critérios de Aceite:**
- [ ] Testes unitários passando
- [ ] Testes de integração passando
- [ ] Pipeline executa testes
- [ ] Coverage report

---

## Epic 7: Security & Compliance (40 horas)

### 7.1 Security Hardening

**ID:** IaC-026
**Estimativa:** 16 horas
**Dependências:** Todos os módulos

**Descrição Detalhada:**
Implementar security hardening em todos os recursos Terraform.

**Requisitos:**
- Security Hub enabled
- GuardDuty enabled
- Config Rules
- Security Groups sem regras abertas
- KMS para todos dados sensíveis
- Secrets Manager para credenciais
- IAM roles sem access keys
- Public access blocked
- Encryption at-rest e in-transit
- AWS WAF para APIs
- Shield Standard

**Critérios de Aceite:**
- [ ] Security Hub findings < critical
- [ ] GuardDuty configurado
- [ ] tfsec scan sem críticos
- [ ] Compliance report

---

### 7.2 Compliance & Auditing

**ID:** IaC-027
**Estimativa:** 12 horas
**Dependências:** 7.1

**Descrição Detalhada:**
Configurar recursos para compliance e auditoria.

**Requisitos:**
- CloudTrail habilitado (multi-region)
- Trail para S3 com encryption
- CloudTrail Insights
- AWS Config (all resources)
- Config rules para compliance
- Audit logs centralizados
- Athena para queries de audit

**Critérios de Aceite:**
- [ ] CloudTrail coletando eventos
- [ ] Logs no S3
- [ ] Config rules evaluando
- [ ] Athena queries funcionando

---

### 7.3 Cost Controls

**ID:** IaC-028
**Estimativa:** 12 horas
**Dependências:** Todos os ambientes

**Descrição Detalhada:**
Implementar controles de custo e alertas de billing.

**Requisitos:**
- Billing alerts
- Budgets mensais por ambiente
- Cost Explorer tags
- Anomaly detection
- Reserved Instances recommendations
- Cost allocation tags

**Critérios de Aceite:**
- [ ] Alertas de custo configurados
- [ ] Budgets definidos
- [ ] Tag enforcement
- [ ] Relatório mensal

---

## Resumo Consolidado

| Epic | Tickets | Horas | Dias |
|------|---------|-------|------|
| 1. Foundation | 4 | 56 | 7 |
| 2. Data Layer | 6 | 120 | 15 |
| 3. Networking | 3 | 32 | 4 |
| 4. Observabilidade | 3 | 32 | 4 |
| 5. Ambientes | 5 | 80 | 10 |
| 6. CI/CD | 4 | 64 | 8 |
| 7. Security & Compliance | 3 | 40 | 5 |
| **TOTAL** | **28** | **424** | **53** |

### Ordem Sugerida de Implementação

1. **Semana 1-2:** Epic 1 (Foundation)
2. **Semana 3-5:** Epic 2 (Data Layer)
3. **Semana 6:** Epic 3 (Networking) + Epic 4 (Observabilidade)
4. **Semana 7-8:** Epic 5 (Ambientes)
5. **Semana 9:** Epic 6 (CI/CD)
6. **Semana 10:** Epic 7 (Security & Compliance)

### Marcos (Milestones)

- **M1 (Fim Semana 2):** Foundation completa, backend configurado
- **M2 (Fim Semana 5):** Data Layer funcional, databases prontos
- **M3 (Fim Semana 8):** Ambientes dev/staging/prod-east operacionais
- **M4 (Fim Semana 10):** CI/CD automatizado, security hardening completo

---

*Tasks document gerado por Claude Code - 2026-04-04*
