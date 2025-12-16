# Checklist de Deployment do Fluxo C - Consensus Engine e Orchestrator Dynamic

Use este checklist para rastrear o progresso do deployment manual do Fluxo C em cluster Kubeadm local. Marque cada item com `[x]` conforme concluído.

**Metadados:**
*   **Data de Início:** __________________
*   **Responsável:** __________________
*   **Cluster Context:** __________________

## 1. Pré-requisitos
- [ ] Cluster Kubeadm acessível e saudável (`kubectl cluster-info`)
- [ ] Namespaces obrigatórios existem (kafka, mongodb-cluster, redis-cluster, semantic-translation, observability)
- [ ] Fluxo A (Gateway) operacional
- [ ] Fluxo B (STE + Specialists) operacional
- [ ] Imagens Docker presentes (`consensus-engine:1.0.0`, `orchestrator-dynamic:1.0.0`)
- [ ] Ferramentas instaladas (kubectl, helm, curl, jq, yq)
- [ ] Arquivo `environments/local/fluxo-c-config.yaml` revisado

## 2. Preparação
- [ ] Script `12-prepare-fluxo-c-values.sh` executado com sucesso
- [ ] Arquivo `helm-charts/consensus-engine/values-local-generated.yaml` gerado e verificado
- [ ] Arquivo `helm-charts/orchestrator-dynamic/values-local-generated.yaml` gerado e verificado

## 3. Tópicos Kafka
- [ ] Tópico `plans.consensus` criado
- [ ] Tópico `execution.tickets` criado
- [ ] Validação: `kubectl get kafkatopics -n kafka`

## 4. Instalação
- [ ] Namespace `consensus-orchestration` criado e rotulado
- [ ] Helm release `consensus-engine` instalado
- [ ] Helm release `orchestrator-dynamic` instalado
- [ ] Pods em estado `Running` (2/2)

## 5. Validação Funcional
- [ ] Health Check Consensus Engine (`/health` -> healthy)
- [ ] Health Check Orchestrator Dynamic (`/health` -> healthy)
- [ ] Consumer Groups Kafka ativos (`consensus-engine-local`, `orchestrator-dynamic-local`)
- [ ] Conexão gRPC com Specialists validada (via logs ou teste)
- [ ] Conexão MongoDB validada (collections criadas)
- [ ] Conexão Redis validada (PING/PONG)

## 5.1. Validações Profundas
- [ ] MongoDB: Collection `consensus_decisions` existe e contém documentos
- [ ] MongoDB: Collection `workflows` existe e contém documentos
- [ ] MongoDB: Documento de exemplo em `consensus_decisions` possui campos obrigatórios (`plan_id`, `confidence_score`, `decision_data`)
- [ ] MongoDB: Documento de exemplo em `workflows` possui campos obrigatórios (`ticket_id`, `workflow_definition`, `status`)
- [ ] Redis: Chaves `pheromone:*` existem
- [ ] Redis: TTL das chaves pheromone é positivo (próximo a 3600s)
- [ ] Redis: Valor de feromônio é numérico entre 0.0 e 1.0
- [ ] Kafka: Mensagem em `plans.consensus` contém campos essenciais (`plan_id`, `confidence`, `decision`)
- [ ] Kafka: Mensagem em `execution.tickets` contém campos essenciais (`ticket_id`, `workflow`, `tasks`)
- [ ] Logs Consensus Engine: Mensagens de agregação Bayesiana presentes
- [ ] Logs Orchestrator: Mensagens de geração de tickets presentes

## 6. Teste E2E Simplificado
- [ ] Intenção enviada ao Gateway
- [ ] Log Consensus Engine: "Bayesian aggregation completed"
- [ ] Log Orchestrator: "Execution ticket generated"
- [ ] Mensagem publicada em `execution.tickets`

## 7. Validação Final
- [ ] Script `13-validate-fluxo-c-deployment.sh` executado
- [ ] Resultado do script: **SUCCESS**

---
**Status Final:**
[ ] Sucesso Total
[ ] Sucesso Parcial (com observações)
[ ] Falha

**Observações:**
_________________________________________________________________________
_________________________________________________________________________
