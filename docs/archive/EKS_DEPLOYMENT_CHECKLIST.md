# Checklist de Deployment EKS - Neural Hive-Mind

Use este checklist para garantir que todos os passos sejam executados corretamente.

## 📋 Pré-Deployment

### Pré-requisitos de Software

- [ ] AWS CLI v2 instalado (`aws --version`)
- [ ] Terraform >= 1.5 instalado (`terraform version`)
- [ ] kubectl >= 1.28 instalado (`kubectl version --client`)
- [ ] Helm >= 3.13 instalado (`helm version`)
- [ ] Docker >= 24.0 instalado (`docker --version`)
- [ ] jq instalado (`jq --version`)

### Configuração AWS

- [ ] Credenciais AWS configuradas (`aws configure`)
- [ ] Credenciais validadas (`aws sts get-caller-identity`)
- [ ] Região definida (recomendado: us-east-1)
- [ ] Usuário/Role IAM com permissões adequadas:
  - [ ] EC2 Full Access
  - [ ] EKS Full Access
  - [ ] ECR Full Access
  - [ ] IAM Create Roles/Policies
  - [ ] S3 Create/Manage Buckets
  - [ ] CloudWatch Logs

### Variáveis de Ambiente

- [ ] `ENV` definido (dev, staging ou prod)
- [ ] `AWS_REGION` definido
- [ ] `TF_VAR_mongodb_root_password` definido (senha forte!)
- [ ] `TF_VAR_neo4j_password` definido (senha forte!)
- [ ] `TF_VAR_clickhouse_admin_password` definido (senha forte!)
- [ ] `TF_VAR_clickhouse_readonly_password` definido (senha forte!)
- [ ] `TF_VAR_clickhouse_writer_password` definido (senha forte!)
- [ ] Variáveis salvas em `~/.neural-hive-env` (chmod 600)

### Revisão de Custos

- [ ] Revisado custos estimados (dev: ~$267/mês, prod: ~$1,127/mês)
- [ ] Budget alert configurado na AWS (recomendado)
- [ ] Aprovação de custos obtida (se aplicável)
- [ ] Plano de shutdown definido (para ambientes não-prod)

### Arquivos de Configuração

- [ ] `environments/${ENV}/terraform.tfvars` revisado
- [ ] Valores de `node_instance_types` adequados para carga esperada
- [ ] `repository_names` atualizado com todos os componentes necessários
- [ ] Tags customizadas adicionadas (se necessário)

## 🚀 Durante o Deployment

### Fase 1: Backend e Infraestrutura

- [ ] Backend S3 criado (`terraform-state-neural-hive-${ENV}`)
- [ ] DynamoDB table criada (`terraform-locks-neural-hive-${ENV}`)
- [ ] Terraform init executado com sucesso
- [ ] Terraform plan revisado (sem erros)
- [ ] Terraform apply executado com sucesso
- [ ] Cluster EKS criado (visível no console AWS)
- [ ] VPC e subnets criadas (3 public + 3 private)
- [ ] NAT Gateways criados (3, um por AZ)
- [ ] ECR registry criado

### Fase 2: Configuração kubectl

- [ ] kubeconfig atualizado (`aws eks update-kubeconfig`)
- [ ] Conectividade com cluster verificada (`kubectl cluster-info`)
- [ ] Nodes listados corretamente (`kubectl get nodes`)
- [ ] 3 nodes disponíveis (um por AZ) - ou conforme configurado

### Fase 3: Repositórios ECR

- [ ] Repositórios ECR criados para todos os componentes:
  - [ ] gateway-intencoes
  - [ ] semantic-translation-engine
  - [ ] specialist-business
  - [ ] specialist-technical
  - [ ] specialist-behavior
  - [ ] specialist-evolution
  - [ ] specialist-architecture
  - [ ] consensus-engine
  - [ ] memory-layer-api

### Fase 4: Build e Push de Imagens

- [ ] Login no ECR bem-sucedido
- [ ] Imagens Docker buildadas sem erros
- [ ] Todas as imagens enviadas para ECR
- [ ] Imagens verificadas no ECR (`aws ecr list-images`)
- [ ] Tags corretas aplicadas (latest + versão específica)

### Fase 5: Deploy Kubernetes

#### Segurança e Bootstrap

- [ ] Namespaces criados (`kubectl get namespaces`)
- [ ] RBAC configurado (service accounts, roles, bindings)
- [ ] Network policies aplicadas
- [ ] Resource quotas e limits configurados
- [ ] Istio instalado (se aplicável)
- [ ] OPA Gatekeeper instalado
- [ ] OPA Gatekeeper pods rodando (`kubectl get pods -n gatekeeper-system`)
- [ ] Constraint templates aplicados
- [ ] Constraints aplicados

#### Infraestrutura de Dados

- [ ] Kafka cluster deployado
- [ ] Kafka brokers rodando (3 replicas)
- [ ] Kafka topics criados
- [ ] MongoDB cluster deployado
- [ ] MongoDB replicas rodando (3 replicas)
- [ ] Neo4j cluster deployado
- [ ] Neo4j pods rodando (3 core servers)
- [ ] Redis cluster deployado
- [ ] Redis replicas rodando (3 replicas)
- [ ] ClickHouse deployado (opcional)

#### Serviços Cognitivos

- [ ] Gateway de Intenções deployado
- [ ] Gateway pods rodando
- [ ] Semantic Translation Engine deployado
- [ ] STE pods rodando
- [ ] Specialist Business deployado
- [ ] Specialist Technical deployado
- [ ] Specialist Behavior deployado
- [ ] Specialist Evolution deployado
- [ ] Specialist Architecture deployado
- [ ] Todos specialists pods rodando
- [ ] Consensus Engine deployado
- [ ] Consensus Engine pods rodando
- [ ] Memory Layer API deployado
- [ ] Memory Layer API pods rodando

## ✅ Pós-Deployment

### Validação Básica

- [ ] Todos os namespaces criados (`kubectl get namespaces`)
- [ ] Todos os pods rodando (`kubectl get pods --all-namespaces`)
- [ ] Nenhum pod em CrashLoopBackOff
- [ ] Todos os services com endpoints (`kubectl get endpoints --all-namespaces`)
- [ ] Logs dos pods sem erros críticos

### Validação Funcional

- [ ] Port-forward para Gateway funciona
- [ ] Endpoint de health check responde (`/health` ou `/ready`)
- [ ] Teste de intent básico bem-sucedido
- [ ] Kafka topics acessíveis
- [ ] MongoDB acessível e autenticando
- [ ] Neo4j acessível e autenticando
- [ ] Redis acessível

### Validação de Conectividade

- [ ] Pods podem resolver DNS internamente
- [ ] Pods podem acessar serviços em outros namespaces
- [ ] Network policies permitindo tráfego correto
- [ ] Egress para internet funciona (se necessário)

### Validação de Segurança

- [ ] mTLS configurado (se usando Istio)
- [ ] OPA policies enforcement ativo
- [ ] Nenhuma constraint violation crítica
- [ ] Secrets configurados corretamente
- [ ] RBAC funcionando (test com user não-admin)

### Testes E2E

- [ ] Script de validação executado (`./tests/phase1-pre-test-validation.sh`)
- [ ] Teste E2E completo executado (`./tests/phase1-end-to-end-test.sh`)
- [ ] Taxa de sucesso >= 95%
- [ ] Latências dentro dos SLOs (<200ms)
- [ ] Sem erros críticos nos logs

### Monitoramento e Observabilidade

- [ ] Métricas Prometheus coletadas
- [ ] Dashboards Grafana acessíveis (se deployado)
- [ ] Alertas configurados
- [ ] Logs agregados no CloudWatch (ou ELK/Loki)
- [ ] Tracing distribuído configurado (Jaeger/X-Ray)

### Documentação

- [ ] Endereços de serviços documentados
- [ ] Credenciais salvas em local seguro (Vault, Secrets Manager)
- [ ] Runbook atualizado com informações do cluster
- [ ] Contatos de suporte definidos
- [ ] Procedimentos de escalação documentados

## 🔒 Hardening de Segurança (Produção)

- [ ] Public access CIDRs restrito (remover 0.0.0.0/0)
- [ ] Endpoint privado habilitado
- [ ] Endpoint público desabilitado (ou restrito)
- [ ] AWS WAF configurado
- [ ] GuardDuty habilitado
- [ ] Security Hub habilitado
- [ ] Config Rules configuradas
- [ ] Image signing obrigatório (Sigstore)
- [ ] Vulnerability scanning ativo e bloqueando critical CVEs
- [ ] Secrets rotacionados
- [ ] Audit logs retidos (90+ dias)
- [ ] Backup automático configurado

## 🎯 Otimização (Opcional)

- [ ] HPA (Horizontal Pod Autoscaler) configurado
- [ ] VPA (Vertical Pod Autoscaler) configurado
- [ ] Cluster Autoscaler validado
- [ ] Resource requests/limits otimizados
- [ ] PDB (Pod Disruption Budget) configurado
- [ ] Node affinity/anti-affinity configurado
- [ ] Taints e tolerations para workloads especializados
- [ ] Cache layers implementados
- [ ] CDN configurado (CloudFront)

## 📊 Métricas de Sucesso

### Performance

- [ ] Latência P50 < 100ms
- [ ] Latência P95 < 200ms
- [ ] Latência P99 < 500ms
- [ ] Taxa de erro < 1%
- [ ] Disponibilidade > 99.5%

### Escalabilidade

- [ ] Pods escalando corretamente sob carga
- [ ] Nodes adicionados quando necessário
- [ ] Sem throttling de API do Kubernetes
- [ ] Kafka lag < 1000 mensagens

### Custo

- [ ] Custos dentro do budget aprovado
- [ ] Spot instances funcionando (se configurado)
- [ ] Recursos não utilizados identificados
- [ ] Right-sizing aplicado

## 🧹 Pós-Deployment Cleanup

- [ ] Planos Terraform salvos deletados
- [ ] Imagens Docker antigas limpas
- [ ] Logs de deploy arquivados
- [ ] Credenciais temporárias revogadas
- [ ] Screenshots/evidências de deployment salvos

## 🚨 Rollback Plan

### Antes de Deployment

- [ ] Snapshot/backup do estado anterior (se houver)
- [ ] Procedimento de rollback documentado
- [ ] Janela de manutenção definida
- [ ] Contatos de emergência disponíveis

### Em Caso de Falha

1. [ ] Identificar componente falhando
2. [ ] Coletar logs e métricas
3. [ ] Decidir: fix forward ou rollback
4. [ ] Se rollback:
   - [ ] Deletar recursos Kubernetes (`kubectl delete`)
   - [ ] Terraform destroy (se infraestrutura)
   - [ ] Restaurar backup (se houver)
5. [ ] Comunicar status aos stakeholders
6. [ ] Post-mortem agendado

## 📞 Contatos Importantes

- **AWS Support**: [seu-plano-de-suporte]
- **DevOps Team**: [contato]
- **Security Team**: [contato]
- **Platform Team**: [contato]

## 📚 Referências

- [DEPLOYMENT_EKS_GUIDE.md](DEPLOYMENT_EKS_GUIDE.md)
- [QUICK_START_EKS.md](QUICK_START_EKS.md)
- [OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md)
- [AWS EKS Best Practices](https://aws.github.io/aws-eks-best-practices/)

---

## ✍️ Sign-off

### Deployment Team

- **Deployed by**: _______________
- **Date**: _______________
- **Environment**: _______________
- **Cluster Name**: _______________

### Validation

- **Validated by**: _______________
- **Date**: _______________
- **Tests Passed**: ___/___
- **Status**: ✅ APPROVED / ❌ REJECTED

### Sign-off

- **Approved by**: _______________
- **Date**: _______________
- **Notes**: _______________

---

🤖 **Neural Hive-Mind - EKS Deployment Checklist**
*Garantia de deployment completo e seguro*
