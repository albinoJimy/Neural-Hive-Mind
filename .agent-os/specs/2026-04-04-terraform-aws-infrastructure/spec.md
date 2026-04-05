# Spec: Terraform/IaC - AWS Infrastructure

> **Data:** 2026-04-04
> **Status:** Planning
> **Prioridade:** 🔴 CRÍTICA

## Resumo Executivo

Implementar infraestrutura como código (Terraform) completa para o Neural Hive-Mind na AWS, provisionando todos os recursos necessários para suportar 41 microsserviços distribuídos em 3 regiões.

## Contexto da Análise

**Status Atual:** ❌ 0% - Nenhum código Terraform encontrado

**O que precisa ser provisionado:**
- 41 microsserviços Python/FastAPI
- VPCs em 3 regiões (us-east-1, us-west-2, eu-west-1)
- EKS clusters com node pools especializados
- RDS PostgreSQL (4 serviços)
- ElastiCache Redis (10+ serviços)
- MSK Kafka (15+ serviços)
- Neptune Graph Database
- MongoDB Atlas via provider

## User Stories

### US-IaC-001: VPC Multi-Região
Como arquiteto de cloud, quero VPCs em 3 regiões com subnets públicas/privadas/database isoladas, para operação com baixa latência e HA.

**Requisitos:**
- VPC CIDRs: 10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16
- 3 AZs por região
- NAT Gateways, VPC Endpoints
- VPC Flow Logs (30 dias)

### US-IaC-002: Cluster EKS com Node Pools
Como engenheiro de plataforma, quero EKS com node pools separados (general, compute, ML), para escalonamento eficiente.

**Requisitos:**
- Kubernetes 1.29+
- Pools: t3.xlarge (general), c5.2xlarge (compute), g4dn.xlarge (ML)
- Cluster Autoscaler
- Private endpoint

### US-IaC-003: Bancos de Dados Gerenciados
Como DBA, quero RDS PostgreSQL Multi-AZ, ElastiCache Redis Global, MSK Kafka, Neptune Graph.

**Serviços por database:**
- PostgreSQL: execution-ticket-service, code-forge, temporal
- Redis: gateway, orchestrator, optimizer, queen, service-registry, guard, analyst, self-healing, feature-store
- Kafka: 15+ tópicos (intentions, plans, tickets, telemetry, etc.)
- Neptune: analyst-agents, queen-agent (knowledge graph)

## Escopo

### IN SCOPE
1. Módulos Terraform: vpc, eks, rds, elasticache, msk, neptune, mongodb-atlas, route53, iam, kms, s3, security-groups, cloudwatch
2. Ambientes: dev, staging, prod (3 regiões)
3. Integração CI/CD (GitHub Actions)
4. Documentação completa

### OUT OF SCOPE
- Migração de recursos existentes
- Helm charts de aplicações
- Testes E2E
- Multi-cloud

## Tickets

### Epic 1: Foundation (8 dias)
- [ ] 1.1 Módulo VPC com subnets multi-AZ
- [ ] 1.2 Módulo EKS Cluster com node pools
- [ ] 1.3 Módulo IAM e KMS
- [ ] 1.4 Backend Terraform (S3 + DynamoDB)

### Epic 2: Data Layer (15 dias)
- [ ] 2.1 Módulo RDS PostgreSQL
- [ ] 2.2 Módulo ElastiCache Redis
- [ ] 2.3 Módulo MSK Kafka
- [ ] 2.4 Módulo Neptune
- [ ] 2.5 Módulo MongoDB Atlas

### Epic 3: Networking (6 dias)
- [ ] 3.1 Módulo VPC Peering
- [ ] 3.2 Módulo Route53
- [ ] 3.3 Security Groups

### Epic 4: Observabilidade (6 dias)
- [ ] 4.1 Módulo CloudWatch
- [ ] 4.2 Módulo S3 para Logs/Backups
- [ ] 4.3 OpenTelemetry Integration

### Epic 5: Ambientes (10 dias)
- [ ] 5.1 Ambiente Dev (us-east-1)
- [ ] 5.2 Ambiente Staging (us-east-1)
- [ ] 5.3 Ambiente Prod East (us-east-1)
- [ ] 5.4 Ambiente Prod West (us-west-2)
- [ ] 5.5 Ambiente Prod EU (eu-west-1)

### Epic 6: CI/CD (8 dias)
- [ ] 6.1 GitHub Actions para Terraform
- [ ] 6.2 Documentação de Módulos
- [ ] 6.3 Deployment Guides
- [ ] 6.4 Testes de Terraform

## Estimativa Total

**24 tickets | 53 dias (~10 semanas)**

## Critérios de Aceite

- [ ] Todos módulos aplicam sem erros
- [ ] terraform validate passa
- [ ] terraform fmt aplicado
- [ ] Testes unitários >80%
- [ ] Documentação completa
- [ ] Security scan (tfsec) passa
- [ ] Custo estimado documentado

---

*Spec criada por Claude Code - 2026-04-04*
