# Guia de Deployment Manual: Fluxo C (Consensus Engine + Orchestrator Dynamic)

Este guia descreve os passos para realizar o deployment manual do **Fluxo C** da Neural Hive-Mind em um cluster Kubernetes local (Kubeadm). O Fluxo C é responsável pela tomada de decisão consolidada e orquestração dinâmica de tarefas.

## 1. Pré-requisitos e Verificações Iniciais

Antes de iniciar, certifique-se de que o ambiente está pronto:

1.  **Cluster Saudável**:
    ```bash
    kubectl cluster-info
    kubectl get nodes
    ```
    Todos os nós devem estar `Ready`.

2.  **Namespaces Obrigatórios**:
    Verifique se os namespaces de infraestrutura e fluxos anteriores existem:
    ```bash
    kubectl get ns kafka mongodb-cluster redis-cluster semantic-translation observability
    ```

3.  **Fluxos Anteriores**:
    O Fluxo A (Gateway) e Fluxo B (Semantic Translation) devem estar operacionais, pois o Fluxo C consome mensagens geradas por eles.

4.  **Imagens Docker**:
    As imagens devem estar disponíveis no containerd do cluster (para `imagePullPolicy: Never`):
    ```bash
    sudo ctr -n k8s.io images ls | grep -E 'consensus-engine|orchestrator-dynamic'
    ```
    Se não estiverem, faça o build ou importação manual.

## 2. Visão Geral da Arquitetura do Fluxo C

O Fluxo C compõe a camada cognitiva de decisão e orquestração:

1.  **Consensus Engine**:
    *   Consome `plans.ready` (do Fluxo B).
    *   Consulta 5 Specialists via gRPC para obter opiniões técnicas.
    *   Realiza agregação Bayesiana das opiniões.
    *   Consulta/Atualiza feromônios no Redis.
    *   Persiste a decisão no MongoDB (`consensus_decisions`).
    *   Publica em `plans.consensus`.

2.  **Orchestrator Dynamic**:
    *   Consome `plans.consensus`.
    *   Gera Execution Tickets (DAG de tarefas).
    *   Persiste workflows no MongoDB (`workflows`) e opcionalmente no Temporal.
    *   Publica em `execution.tickets`.

## 3. Preparação dos Valores Locais

Utilize o script automatizado para gerar os arquivos `values.yaml` com os endpoints corretos do seu ambiente:

```bash
bash docs/manual-deployment/scripts/12-prepare-fluxo-c-values.sh
```

Este script irá:
*   Detectar IPs/Services do Kafka, MongoDB, Redis, etc.
*   Gerar `helm-charts/consensus-engine/values-local-generated.yaml`.
*   Gerar `helm-charts/orchestrator-dynamic/values-local-generated.yaml`.

Verifique o output do script para garantir que tudo foi detectado corretamente.

## 4. Criação dos Tópicos Kafka

Aplique os manifestos para criar os tópicos necessários:

```bash
kubectl apply -f k8s/kafka-topics/plans-consensus-topic.yaml
kubectl apply -f k8s/kafka-topics/execution-tickets-topic.yaml
```

Valide a criação:
```bash
kubectl get kafkatopics -n kafka
```

## 5. Criação do Namespace Dedicado

Crie o namespace para o Fluxo C:

```bash
kubectl create namespace consensus-orchestration
kubectl label namespace consensus-orchestration neural-hive-mind.org/layer=cognitiva
kubectl label namespace consensus-orchestration neural-hive-mind.org/flow=fluxo-c
```

## 6. Instalação do Consensus Engine

Instale o chart usando os valores gerados:

```bash
helm upgrade --install consensus-engine helm-charts/consensus-engine \
  --namespace consensus-orchestration \
  -f helm-charts/consensus-engine/values-local-generated.yaml \
  --wait --timeout 10m
```

## 7. Instalação do Orchestrator Dynamic

Instale o chart usando os valores gerados:

```bash
helm upgrade --install orchestrator-dynamic helm-charts/orchestrator-dynamic \
  --namespace consensus-orchestration \
  -f helm-charts/orchestrator-dynamic/values-local-generated.yaml \
  --wait --timeout 10m
```

## 8. Validação de Health e Readiness

Verifique se os pods subiram e estão saudáveis:

```bash
kubectl get pods -n consensus-orchestration
```

Faça um teste rápido de health (via port-forward):

```bash
# Consensus Engine
kubectl port-forward -n consensus-orchestration svc/consensus-engine 8080:8000 &
curl localhost:8080/health

# Orchestrator Dynamic
kubectl port-forward -n consensus-orchestration svc/orchestrator-dynamic 8081:8000 &
curl localhost:8081/health
```

## 9. Teste de Consumo e Geração (E2E Simplificado)

1.  **Monitore os logs do Consensus Engine**:
    ```bash
    kubectl logs -n consensus-orchestration -l app.kubernetes.io/name=consensus-engine -f
    ```

2.  **Envie uma requisição no Gateway (Fluxo A)**:
    (Em outro terminal)
    ```bash
    curl -X POST http://localhost:30000/api/v1/intents/text \
      -H "Content-Type: application/json" \
      -d '{"content": "Analisar segurança do cluster"}'
    ```

3.  **Verifique o fluxo**:
    *   Gateway -> Kafka (`intentions.*`)
    *   STE -> Kafka (`plans.ready`)
    *   **Consensus Engine** -> Log: "Bayesian aggregation completed" -> Kafka (`plans.consensus`)
    *   **Orchestrator** -> Log: "Execution ticket generated" -> Kafka (`execution.tickets`)

## 9.1. Validações Profundas de Decisão Consolidada e Tickets

### Leitura de Mensagens Kafka

**Tópico `plans.consensus` (saída do Consensus Engine):**

```bash
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.consensus \
  --from-beginning \
  --max-messages 1
```

**Campos principais esperados:**
- `plan_id`: Identificador único do plano
- `confidence`: Score de confiança da decisão (0.0 a 1.0)
- `decision`: Decisão consolidada
- `specialist_opinions`: Array com opiniões dos 5 specialists
- `bayesian_weights`: Pesos calculados pela agregação Bayesiana
- `timestamp`: Timestamp da decisão

**Tópico `execution.tickets` (saída do Orchestrator):**

```bash
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets \
  --from-beginning \
  --max-messages 1
```

**Campos principais esperados:**
- `ticket_id`: Identificador único do ticket de execução
- `workflow`: Definição do workflow (DAG de tarefas)
- `tasks`: Array de tarefas a executar
- `priority`: Prioridade do ticket
- `sla_timeout_ms`: Timeout SLA em milissegundos
- `created_at`: Timestamp de criação

### Consultas MongoDB

**Collection `consensus_decisions` (Consensus Engine):**

```bash
# Acessar o pod MongoDB
kubectl exec -it -n mongodb-cluster mongodb-0 -- mongosh

# Dentro do mongosh:
use neural_hive
db.consensus_decisions.countDocuments()
db.consensus_decisions.findOne()
```

**Campos esperados nos documentos:**
- `_id`: ID do documento
- `plan_id`: Referência ao plano
- `confidence_score`: Score de confiança
- `decision_data`: Dados da decisão consolidada
- `pheromone_influence`: Influência dos feromônios
- `created_at`: Timestamp

**Collection `workflows` (Orchestrator Dynamic):**

```bash
# Dentro do mongosh:
use neural_hive_orchestration
db.workflows.countDocuments()
db.workflows.findOne()
```

**Campos esperados:**
- `_id`: ID do documento
- `ticket_id`: Referência ao ticket
- `workflow_definition`: Definição completa do workflow
- `status`: Status atual (pending, running, completed, failed)
- `created_at`: Timestamp

### Validação Redis (Pheromones)

**Listar chaves de feromônios:**

```bash
kubectl exec -n redis-cluster neural-hive-cache-0 -- redis-cli KEYS "pheromone:*"
```

**Verificar TTL de uma chave:**

```bash
# Substitua <KEY> por uma chave retornada acima
kubectl exec -n redis-cluster neural-hive-cache-0 -- redis-cli TTL "pheromone:<KEY>"
```

O TTL deve ser positivo (em segundos) e próximo ao valor configurado em `pheromoneTtl` (padrão: 3600s).

**Inspecionar valor de um feromônio:**

```bash
kubectl exec -n redis-cluster neural-hive-cache-0 -- redis-cli GET "pheromone:<KEY>"
```

O valor deve ser um número decimal representando a intensidade do feromônio (0.0 a 1.0).

## 10. Validação Automatizada

Execute o script de validação completo para garantir que todos os componentes estão integrados corretamente:

```bash
bash docs/manual-deployment/scripts/13-validate-fluxo-c-deployment.sh
```

Se o script retornar `[SUCCESS]`, o deployment foi bem-sucedido.

## 11. Troubleshooting Comum

*   **Pods em Pending**: Verifique recursos (`kubectl describe pod ...`). Pode ser falta de CPU/RAM.
*   **CrashLoopBackOff**: Verifique logs. Geralmente é falha de conexão com Kafka, Mongo ou Redis. Confirme se os endpoints no `values-local-generated.yaml` estão corretos.
*   **Timeout no Helm**: Ocorre se a imagem não estiver no containerd (devido a `imagePullPolicy: Never`). Importe a imagem manualmente.
*   **Erro gRPC**: Se o Consensus Engine reclamar de conexão com Specialists, verifique se os serviços no namespace `semantic-translation` estão rodando e acessíveis.

## 12. Próximos Passos

*   Executar testes de carga.
*   Habilitar observabilidade avançada (Grafana Dashboards).
*   Integrar com Temporal (se necessário workflows complexos).
