# Plano de Testes Manual: Fluxo Completo A → C

## Objetivo

Validar manualmente cada etapa do fluxo de intenções, desde a captura no Gateway até a execução nos Workers, garantindo cobertura de cenários normais, edge cases e falhas.

---

## Índice

1. [Pré-requisitos](#pré-requisitos)
2. [Parte 1: Fluxo A - Gateway de Intenções](#parte-1-fluxo-a---gateway-de-intenções)
3. [Parte 2: Fluxo B - Tradução Semântica](#parte-2-fluxo-b---tradução-semântica)
4. [Parte 3: Fluxo B - Consensus Engine](#parte-3-fluxo-b---consensus-engine)
5. [Parte 4: Fluxo C - Orquestração](#parte-4-fluxo-c---orquestração)
6. [Parte 5: Fluxo C - Execução nos Workers](#parte-5-fluxo-c---execução-nos-workers)
7. [Parte 6: Testes de Observabilidade](#parte-6-testes-de-observabilidade)
8. [Parte 7: Testes de Resiliência](#parte-7-testes-de-resiliência)
9. [Parte 8: Testes de Edge Cases](#parte-8-testes-de-edge-cases)
10. [Registro de Resultados](#registro-de-resultados)

---

## Pré-requisitos

### Verificar Infraestrutura

```bash
# 1. Verificar pods em execução
kubectl get pods -n neural-hive

# 2. Verificar serviços Kafka
kubectl get pods -n neural-hive-kafka

# 3. Verificar MongoDB
kubectl get pods -n mongodb-cluster

# 4. Verificar Redis
kubectl get pods -n redis-cluster

# 5. Verificar Temporal (se habilitado)
kubectl get pods -n temporal
```

### Obter Endpoints para Testes

```bash
# Gateway Intenções
kubectl get svc -n neural-hive gateway-intencoes

# Port-forward para acesso local (execute em terminal separado)
kubectl port-forward -n neural-hive svc/gateway-intencoes 8000:8000
```

---

## Parte 1: Fluxo A - Gateway de Intenções

### Teste A1: Intenção Texto Simples (Happy Path)

**Objetivo:** Validar processamento básico de intenção textual

**Passos:**

1. Enviar requisição POST para o Gateway:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Preciso gerar um relatório de vendas do último trimestre",
       "language": "pt-BR"
     }'
   ```

2. **Verificar resposta:**
   - [ ] Status HTTP 200 ou 201
   - [ ] Campo `intent_id` presente (UUID válido)
   - [ ] Campo `status` igual a "processed" ou "success"
   - [ ] Campo `domain` classificado (esperado: "business")
   - [ ] Campo `confidence` presente (valor entre 0.0 e 1.0)

3. **Anotar valores retornados:**
   - intent_id: _______________
   - domain: _______________
   - confidence: _______________

4. **Verificar logs do Gateway:**
   ```bash
   kubectl logs -n neural-hive -l app=gateway-intencoes --tail=50
   ```
   - [ ] Log de recebimento da requisição
   - [ ] Log de processamento NLU
   - [ ] Log de publicação no Kafka

5. **Verificar mensagem no Kafka:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic intentions.business \
     --from-beginning \
     --max-messages 1
   ```
   - [ ] Mensagem presente no tópico correto
   - [ ] intent_id corresponde ao retornado

---

### Teste A2: Intenção com Domínio Technical

**Objetivo:** Validar classificação para domínio técnico

**Passos:**

1. Enviar requisição:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Preciso corrigir um bug na API REST que está retornando erro 500",
       "language": "pt-BR"
     }'
   ```

2. **Verificar resposta:**
   - [ ] Campo `domain` igual a "technical"
   - [ ] Keywords extraídas incluem: "bug", "API", "REST", "erro"

3. **Verificar tópico Kafka correto:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic intentions.technical \
     --from-beginning \
     --max-messages 1
   ```

---

### Teste A3: Intenção com Domínio Infrastructure

**Objetivo:** Validar classificação para domínio de infraestrutura

**Passos:**

1. Enviar requisição:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Fazer deploy da nova versão no cluster Kubernetes de produção",
       "language": "pt-BR"
     }'
   ```

2. **Verificar resposta:**
   - [ ] Campo `domain` igual a "infrastructure"
   - [ ] Keywords incluem: "deploy", "Kubernetes", "produção"

3. **Verificar tópico:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic intentions.infrastructure \
     --from-beginning \
     --max-messages 1
   ```

---

### Teste A4: Intenção com Domínio Security

**Objetivo:** Validar classificação para domínio de segurança

**Passos:**

1. Enviar requisição:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Implementar autenticação OAuth2 e criptografia de dados sensíveis",
       "language": "pt-BR"
     }'
   ```

2. **Verificar resposta:**
   - [ ] Campo `domain` igual a "security"
   - [ ] Keywords incluem: "autenticação", "OAuth2", "criptografia"

3. **Verificar tópico:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic intentions.security \
     --from-beginning \
     --max-messages 1
   ```

---

### Teste A5: Intenção com Baixa Confiança

**Objetivo:** Validar roteamento para validação quando confiança é baixa

**Passos:**

1. Enviar requisição ambígua:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "fazer coisa",
       "language": "pt-BR"
     }'
   ```

2. **Verificar resposta:**
   - [ ] Campo `confidence` abaixo de 0.5
   - [ ] Campo `status` indica "low_confidence" ou "routed_to_validation"

3. **Verificar tópico de validação:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic intentions.validation \
     --from-beginning \
     --max-messages 1
   ```
   - [ ] Mensagem presente no tópico `intentions.validation`

---

### Teste A6: Intenção com Constraints e QoS

**Objetivo:** Validar processamento de constraints opcionais

**Passos:**

1. Enviar requisição completa:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Gerar relatório financeiro urgente para a diretoria",
       "language": "pt-BR",
       "correlation_id": "test-manual-001",
       "constraints": {
         "priority": "critical",
         "max_retries": 5,
         "timeout_ms": 60000,
         "security_level": "confidential"
       },
       "qos": {
         "delivery_mode": "exactly-once",
         "durability": "persistent",
         "consistency": "strong"
       }
     }'
   ```

2. **Verificar resposta:**
   - [ ] Constraints preservados no envelope
   - [ ] QoS preservado no envelope
   - [ ] correlation_id igual ao enviado

3. **Verificar no Kafka (headers):**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic intentions.business \
     --from-beginning \
     --max-messages 1 \
     --property print.headers=true
   ```
   - [ ] Header `correlation-id` presente
   - [ ] Header `confidence-score` presente

---

### Teste A7: Deduplicação com Correlation ID

**Objetivo:** Validar idempotência usando correlation_id

**Passos:**

1. Enviar primeira requisição:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Teste de deduplicação",
       "language": "pt-BR",
       "correlation_id": "dedup-test-12345"
     }'
   ```
   - Anotar intent_id retornado: _______________

2. Enviar mesma requisição novamente (dentro de 5 minutos):
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Teste de deduplicação",
       "language": "pt-BR",
       "correlation_id": "dedup-test-12345"
     }'
   ```

3. **Verificar resposta:**
   - [ ] Status indica "duplicate_detected" ou similar
   - [ ] intent_id retornado é IGUAL ao primeiro
   - [ ] Não há nova mensagem no Kafka (contagem igual)

---

### Teste A8: Validação de Campos Obrigatórios

**Objetivo:** Validar tratamento de erros de payload

**Passos:**

1. Enviar requisição sem campo `text`:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "language": "pt-BR"
     }'
   ```

2. **Verificar resposta:**
   - [ ] Status HTTP 400 ou 422
   - [ ] Mensagem de erro clara sobre campo obrigatório

3. Enviar requisição com texto vazio:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "",
       "language": "pt-BR"
     }'
   ```

4. **Verificar resposta:**
   - [ ] Status HTTP 400 ou 422
   - [ ] Mensagem de erro sobre texto vazio

---

### Teste A9: Texto com Entidades

**Objetivo:** Validar extração de entidades pelo NLU

**Passos:**

1. Enviar requisição com entidades claras:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Enviar email para joao.silva@empresa.com sobre o projeto Alpha da Microsoft",
       "language": "pt-BR"
     }'
   ```

2. **Verificar resposta:**
   - [ ] Campo `entities` presente
   - [ ] Entidade EMAIL detectada (mascarada como [EMAIL])
   - [ ] Entidade PERSON ou ORG detectada (Microsoft)
   - [ ] Entidade PRODUCT detectada (projeto Alpha)

---

### Teste A10: Métricas Prometheus

**Objetivo:** Validar exposição de métricas

**Passos:**

1. Acessar endpoint de métricas:
   ```bash
   curl http://localhost:8000/metrics | grep neural_hive
   ```

2. **Verificar métricas presentes:**
   - [ ] `neural_hive_requests_total` com labels domain, status
   - [ ] `neural_hive_captura_duration_seconds`
   - [ ] `neural_hive_intent_confidence`

3. Verificar valores incrementados após testes anteriores

---

## Parte 2: Fluxo B - Tradução Semântica

### Preparação

```bash
# Port-forward para STE (se necessário debug)
kubectl port-forward -n neural-hive svc/semantic-translation-engine 8001:8000

# Verificar logs do STE
kubectl logs -n neural-hive -l app=semantic-translation-engine --tail=100 -f
```

---

### Teste B1: Consumo de Intenção e Geração de Plano

**Objetivo:** Validar que STE consome intenções e gera planos cognitivos

**Passos:**

1. Enviar nova intenção via Gateway (Teste A1)

2. **Aguardar processamento (10-30 segundos)**

3. **Verificar logs do STE:**
   ```bash
   kubectl logs -n neural-hive -l app=semantic-translation-engine --tail=50
   ```
   - [ ] Log de consumo do Kafka (intent_id)
   - [ ] Log de enriquecimento semântico
   - [ ] Log de geração de DAG
   - [ ] Log de avaliação de risco
   - [ ] Log de publicação do plano

4. **Verificar plano no Kafka:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic plans.ready \
     --from-beginning \
     --max-messages 1
   ```
   - [ ] CognitivePlan presente
   - [ ] intent_id corresponde
   - [ ] tasks[] não vazio
   - [ ] execution_order[] presente
   - [ ] risk_score presente

5. **Anotar valores:**
   - plan_id: _______________
   - risk_band: _______________
   - número de tasks: _______________

---

### Teste B2: Validação de Risk Bands

**Objetivo:** Validar cálculo de risco para diferentes cenários

**Passos:**

1. Enviar intenção de BAIXO RISCO:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Consultar status do pedido 12345",
       "language": "pt-BR",
       "constraints": {
         "priority": "low",
         "security_level": "public"
       }
     }'
   ```

2. **Aguardar e verificar plano:**
   - [ ] risk_band = "low"
   - [ ] risk_score < 0.3

3. Enviar intenção de ALTO RISCO:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Deletar todos os dados de clientes inativos e atualizar sistema de pagamentos",
       "language": "pt-BR",
       "constraints": {
         "priority": "critical",
         "security_level": "restricted"
       }
     }'
   ```

4. **Aguardar e verificar plano:**
   - [ ] risk_band = "high" ou "critical"
   - [ ] risk_score > 0.6

---

### Teste B3: Geração de DAG com Dependências

**Objetivo:** Validar decomposição em tarefas com dependências

**Passos:**

1. Enviar intenção complexa:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Criar novo microserviço de pagamentos, configurar CI/CD, fazer deploy em staging e executar testes de integração",
       "language": "pt-BR"
     }'
   ```

2. **Verificar plano gerado:**
   - [ ] Múltiplas tasks (esperado: 3-5)
   - [ ] Campo `dependencies` populado em algumas tasks
   - [ ] execution_order respeita dependências

3. **Validar ordem topológica:**
   - Task de "criar" deve vir antes de "deploy"
   - Task de "deploy" deve vir antes de "testes"

---

### Teste B4: Persistência no MongoDB (Ledger)

**Objetivo:** Validar registro imutável no ledger

**Passos:**

1. Anotar plan_id do teste anterior

2. **Consultar MongoDB:**
   ```bash
   kubectl exec -n mongodb-cluster mongodb-0 -- \
     mongosh --quiet --eval '
       db = db.getSiblingDB("neural_hive");
       db.cognitive_ledger.findOne({"plan_id": "PLAN_ID_AQUI"})
     '
   ```

3. **Verificar registro:**
   - [ ] Documento existe
   - [ ] Campo `hash` presente (SHA-256)
   - [ ] Campo `created_at` presente
   - [ ] Campo `status` = "validated"

---

## Parte 3: Fluxo B - Consensus Engine

### Preparação

```bash
# Verificar especialistas
kubectl get pods -n neural-hive | grep specialist

# Verificar logs do Consensus Engine
kubectl logs -n neural-hive -l app=consensus-engine --tail=100 -f
```

---

### Teste B5: Consumo de Plano e Invocação de Especialistas

**Objetivo:** Validar consulta aos 5 especialistas

**Passos:**

1. Usar plan_id do teste B1

2. **Aguardar processamento (15-60 segundos)**

3. **Verificar logs do Consensus Engine:**
   ```bash
   kubectl logs -n neural-hive -l app=consensus-engine --tail=100
   ```
   - [ ] Log de consumo do plano
   - [ ] Log de invocação de cada especialista:
     - [ ] specialist-business
     - [ ] specialist-technical
     - [ ] specialist-behavior
     - [ ] specialist-evolution
     - [ ] specialist-architecture
   - [ ] Log de agregação de votos
   - [ ] Log de decisão final

4. **Verificar tempo de resposta de cada especialista:**
   - business: _____ ms
   - technical: _____ ms
   - behavior: _____ ms
   - evolution: _____ ms
   - architecture: _____ ms

---

### Teste B6: Decisão Consolidada

**Objetivo:** Validar decisão final e publicação

**Passos:**

1. **Verificar decisão no Kafka:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic plans.consensus \
     --from-beginning \
     --max-messages 1
   ```

2. **Validar ConsolidatedDecision:**
   - [ ] decision_id presente (UUID)
   - [ ] plan_id corresponde
   - [ ] final_decision = "approve" (para caso normal)
   - [ ] consensus_method presente (bayesian, voting, unanimous)
   - [ ] aggregated_confidence entre 0.0 e 1.0
   - [ ] aggregated_risk entre 0.0 e 1.0
   - [ ] specialist_votes[] com 5 votos
   - [ ] requires_human_review = false

3. **Anotar valores:**
   - decision_id: _______________
   - final_decision: _______________
   - consensus_method: _______________
   - aggregated_confidence: _______________

---

### Teste B7: Cenário de Rejeição

**Objetivo:** Validar decisão de rejeição quando risco é muito alto

**Passos:**

1. Enviar intenção de altíssimo risco:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Apagar completamente o banco de dados de produção sem backup",
       "language": "pt-BR",
       "constraints": {
         "priority": "critical",
         "security_level": "restricted"
       }
     }'
   ```

2. **Aguardar fluxo completo (30-60 segundos)**

3. **Verificar decisão:**
   - [ ] final_decision = "reject" OU "review_required"
   - [ ] requires_human_review = true (se conditional)
   - [ ] guardrails_triggered não vazio

---

### Teste B8: Persistência de Decisão no MongoDB

**Objetivo:** Validar registro de decisões

**Passos:**

1. Usar decision_id do teste B6

2. **Consultar MongoDB:**
   ```bash
   kubectl exec -n mongodb-cluster mongodb-0 -- \
     mongosh --quiet --eval '
       db = db.getSiblingDB("neural_hive");
       db.consensus_decisions.findOne({"decision_id": "DECISION_ID_AQUI"})
     '
   ```

3. **Verificar registro:**
   - [ ] Documento existe
   - [ ] specialist_votes[] com detalhes de cada voto
   - [ ] consensus_metrics presente
   - [ ] hash presente

---

### Teste B9: Verificar Opiniões dos Especialistas

**Objetivo:** Validar persistência detalhada de opiniões

**Passos:**

1. **Consultar opiniões no MongoDB:**
   ```bash
   kubectl exec -n mongodb-cluster mongodb-0 -- \
     mongosh --quiet --eval '
       db = db.getSiblingDB("neural_hive");
       db.specialist_opinions.find({"plan_id": "PLAN_ID_AQUI"}).pretty()
     '
   ```

2. **Verificar para cada especialista:**
   - [ ] opinion_id único
   - [ ] specialist_type correto
   - [ ] confidence_score entre 0.0 e 1.0
   - [ ] risk_score entre 0.0 e 1.0
   - [ ] recommendation (approve, reject, conditional)
   - [ ] reasoning presente

---

## Parte 4: Fluxo C - Orquestração

### Preparação

```bash
# Verificar Orchestrator Dynamic
kubectl get pods -n neural-hive | grep orchestrator

# Verificar logs
kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=100 -f

# Port-forward para API (opcional)
kubectl port-forward -n neural-hive svc/orchestrator-dynamic 8002:8000
```

---

### Teste C1: Consumo de Decisão e Início de Workflow

**Objetivo:** Validar início de workflow Temporal

**Passos:**

1. Usar decision_id do teste B6 (decisão aprovada)

2. **Aguardar processamento (10-30 segundos)**

3. **Verificar logs do Orchestrator:**
   ```bash
   kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=100
   ```
   - [ ] Log de consumo da decisão
   - [ ] Log de recuperação do CognitivePlan
   - [ ] Log de início do workflow Temporal
   - [ ] workflow_id registrado

4. **Verificar workflow via API (se disponível):**
   ```bash
   curl http://localhost:8002/api/v1/workflows
   ```

---

### Teste C2: Validação de Plano (Fase C1)

**Objetivo:** Validar activity de validação

**Passos:**

1. **Verificar logs de validação:**
   ```bash
   kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=100 | grep -i "validat"
   ```
   - [ ] Log de validação de campos obrigatórios
   - [ ] Log de validação de DAG
   - [ ] Log de validação OPA (se habilitado)
   - [ ] Status: "valid" ou erros específicos

---

### Teste C3: Geração de Tickets (Fase C2)

**Objetivo:** Validar transformação de tasks em tickets

**Passos:**

1. **Verificar logs de geração:**
   ```bash
   kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=100 | grep -i "ticket"
   ```
   - [ ] Log de geração de tickets
   - [ ] Número de tickets = número de tasks
   - [ ] ticket_id para cada task

2. **Verificar tickets no Kafka:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic execution.tickets \
     --from-beginning \
     --max-messages 3
   ```

3. **Validar estrutura do ExecutionTicket:**
   - [ ] ticket_id (UUID)
   - [ ] plan_id corresponde
   - [ ] task_type (BUILD, DEPLOY, TEST, VALIDATE, EXECUTE)
   - [ ] dependencies[] mapeados para ticket_ids
   - [ ] status = "PENDING"
   - [ ] sla.deadline presente
   - [ ] sla.timeout_ms presente
   - [ ] qos definido

---

### Teste C4: Validação de Políticas OPA

**Objetivo:** Validar rejeição por política

**Passos:**

1. **Verificar se OPA está habilitado:**
   ```bash
   kubectl get pods -n neural-hive | grep opa
   ```

2. **Se habilitado, verificar logs de validação OPA:**
   ```bash
   kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=100 | grep -i "opa\|policy"
   ```
   - [ ] Log de consulta à política
   - [ ] Resultado: allow ou deny
   - [ ] Violações listadas (se houver)

3. **Testar violação de política (se aplicável):**
   - Enviar intenção que viole limites de recursos
   - Verificar que workflow falha com erro de política

---

## Parte 5: Fluxo C - Execução nos Workers

### Preparação

```bash
# Verificar Worker Agents
kubectl get pods -n neural-hive | grep worker

# Verificar logs
kubectl logs -n neural-hive -l app=worker-agents --tail=100 -f
```

---

### Teste C5: Consumo de Tickets pelos Workers

**Objetivo:** Validar consumo e execução de tickets

**Passos:**

1. **Verificar logs dos Workers:**
   ```bash
   kubectl logs -n neural-hive -l app=worker-agents --tail=100
   ```
   - [ ] Log de consumo do ticket
   - [ ] Log de verificação de dependências
   - [ ] Log de início de execução
   - [ ] ticket_id registrado

2. **Verificar status do ticket:**
   - [ ] Status mudou de PENDING para RUNNING

---

### Teste C6: Execução com Dependências

**Objetivo:** Validar coordenação de dependências

**Passos:**

1. Usando plano com múltiplas tasks dependentes (Teste B3)

2. **Verificar ordem de execução nos logs:**
   ```bash
   kubectl logs -n neural-hive -l app=worker-agents --tail=200 | grep -E "ticket|executing|completed"
   ```
   - [ ] Tasks sem dependências executam primeiro
   - [ ] Tasks com dependências aguardam conclusão
   - [ ] Ordem respeita execution_order do plano

3. **Verificar tempos:**
   - Ticket 1 started_at: _______________
   - Ticket 1 completed_at: _______________
   - Ticket 2 started_at: _______________
   - [ ] Ticket 2 started APÓS Ticket 1 completed (se dependente)

---

### Teste C7: Publicação de Resultados

**Objetivo:** Validar publicação de ExecutionResult

**Passos:**

1. **Verificar resultados no Kafka:**
   ```bash
   kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
     /opt/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic execution.results \
     --from-beginning \
     --max-messages 3
   ```

2. **Validar estrutura do ExecutionResult:**
   - [ ] ticket_id corresponde
   - [ ] status = "COMPLETED" ou "FAILED"
   - [ ] result.success = true/false
   - [ ] actual_duration_ms presente
   - [ ] agent_id presente
   - [ ] timestamp presente

3. **Anotar métricas:**
   - estimated_duration_ms (do ticket): _______________
   - actual_duration_ms (do result): _______________
   - diferença: _______________

---

### Teste C8: Cenário de Falha e Retry

**Objetivo:** Validar comportamento de retry em falhas

**Passos:**

1. **Simular falha (se possível via configuração ou ticket especial)**

2. **Verificar logs de retry:**
   ```bash
   kubectl logs -n neural-hive -l app=worker-agents --tail=100 | grep -i "retry\|attempt\|fail"
   ```
   - [ ] Log de falha inicial
   - [ ] Log de retry (attempt 2, 3, etc.)
   - [ ] retry_count incrementado

3. **Verificar resultado final:**
   - [ ] Se esgotou retries: status = FAILED
   - [ ] error_message presente

---

### Teste C9: Consolidação de Resultados (Fase C5)

**Objetivo:** Validar consolidação no Orchestrator

**Passos:**

1. **Verificar logs de consolidação:**
   ```bash
   kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=100 | grep -i "consolidat"
   ```
   - [ ] Log de recebimento de resultados
   - [ ] Log de validação de consistência
   - [ ] Log de workflow completo

2. **Verificar status final do workflow:**
   - [ ] Todos tickets COMPLETED
   - [ ] Workflow status = "success"
   - [ ] sla_status.met = true

---

### Teste C10: Feedback Loop ML

**Objetivo:** Validar registro de feedback para aprendizado

**Passos:**

1. **Verificar logs de ML feedback:**
   ```bash
   kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=100 | grep -i "ml\|feedback\|prediction"
   ```
   - [ ] Log de registro de allocation outcome
   - [ ] predicted_duration vs actual_duration
   - [ ] error_ms calculado

2. **Verificar métricas Prometheus:**
   ```bash
   curl http://localhost:8002/metrics | grep ml_prediction
   ```
   - [ ] ml_prediction_errors_total incrementado
   - [ ] ml_prediction_latency_seconds registrado

---

## Parte 6: Testes de Observabilidade

### Teste O1: Rastreamento End-to-End

**Objetivo:** Validar propagação de correlation_id

**Passos:**

1. Enviar intenção com correlation_id conhecido:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Teste de rastreamento end-to-end",
       "language": "pt-BR",
       "correlation_id": "trace-e2e-test-001"
     }'
   ```

2. **Aguardar fluxo completo (60-120 segundos)**

3. **Verificar correlation_id em cada serviço:**

   **Gateway:**
   ```bash
   kubectl logs -n neural-hive -l app=gateway-intencoes --tail=200 | grep "trace-e2e-test-001"
   ```
   - [ ] correlation_id presente nos logs

   **STE:**
   ```bash
   kubectl logs -n neural-hive -l app=semantic-translation-engine --tail=200 | grep "trace-e2e-test-001"
   ```
   - [ ] correlation_id presente nos logs

   **Consensus:**
   ```bash
   kubectl logs -n neural-hive -l app=consensus-engine --tail=200 | grep "trace-e2e-test-001"
   ```
   - [ ] correlation_id presente nos logs

   **Orchestrator:**
   ```bash
   kubectl logs -n neural-hive -l app=orchestrator-dynamic --tail=200 | grep "trace-e2e-test-001"
   ```
   - [ ] correlation_id presente nos logs

   **Workers:**
   ```bash
   kubectl logs -n neural-hive -l app=worker-agents --tail=200 | grep "trace-e2e-test-001"
   ```
   - [ ] correlation_id presente nos logs

---

### Teste O2: Health Checks

**Objetivo:** Validar endpoints de saúde

**Passos:**

1. **Gateway:**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/ready
   ```
   - [ ] /health retorna status "healthy"
   - [ ] /ready retorna componentes OK

2. **Orchestrator:**
   ```bash
   curl http://localhost:8002/health
   curl http://localhost:8002/ready
   ```
   - [ ] /health retorna status "healthy"
   - [ ] /ready mostra kafka_consumer, temporal, etc.

---

### Teste O3: Métricas Consolidadas

**Objetivo:** Validar métricas Prometheus de todos os serviços

**Passos:**

1. **Coletar métricas de cada serviço:**

   **Gateway (8000):**
   ```bash
   curl http://localhost:8000/metrics | grep -E "^neural_hive|^intent"
   ```

   **Orchestrator (8002):**
   ```bash
   curl http://localhost:8002/metrics | grep -E "^orchestration|^ml_"
   ```

2. **Verificar métricas presentes:**

   **Fluxo A:**
   - [ ] neural_hive_requests_total
   - [ ] neural_hive_captura_duration_seconds
   - [ ] neural_hive_intent_confidence

   **Fluxo B:**
   - [ ] semantic_translation_plans_generated_total
   - [ ] consensus_decisions_total
   - [ ] specialist_response_time_ms

   **Fluxo C:**
   - [ ] orchestration_workflows_started_total
   - [ ] orchestration_tickets_generated_total
   - [ ] orchestration_sla_violations_total

---

## Parte 7: Testes de Resiliência

### Teste R1: Kafka Indisponível Temporariamente

**Objetivo:** Validar comportamento quando Kafka está indisponível

> ⚠️ **ATENÇÃO:** Execute apenas em ambiente de teste!

**Passos:**

1. **Escalar Kafka para 0 réplicas:**
   ```bash
   kubectl scale statefulset -n neural-hive-kafka neural-hive-kafka --replicas=0
   ```

2. **Tentar enviar intenção:**
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{"text": "Teste de resiliência Kafka", "language": "pt-BR"}'
   ```

3. **Verificar comportamento:**
   - [ ] Timeout ou erro apropriado
   - [ ] Não há crash do serviço
   - [ ] Circuit breaker ativado (verificar logs)

4. **Restaurar Kafka:**
   ```bash
   kubectl scale statefulset -n neural-hive-kafka neural-hive-kafka --replicas=3
   ```

5. **Aguardar recuperação e retentar**
   - [ ] Serviço volta a funcionar normalmente

---

### Teste R2: Especialista Indisponível

**Objetivo:** Validar consenso com especialista offline

**Passos:**

1. **Escalar um especialista para 0:**
   ```bash
   kubectl scale deployment -n neural-hive specialist-business --replicas=0
   ```

2. **Enviar nova intenção e aguardar consenso**

3. **Verificar logs do Consensus Engine:**
   - [ ] Timeout ou erro para specialist-business
   - [ ] Consenso ainda é atingido com 4 especialistas
   - [ ] Warning logado

4. **Restaurar especialista:**
   ```bash
   kubectl scale deployment -n neural-hive specialist-business --replicas=1
   ```

---

### Teste R3: MongoDB Lento

**Objetivo:** Validar comportamento com MongoDB lento

**Passos:**

1. **Verificar timeout configurado para MongoDB**

2. **Enviar intenções durante período de alta carga do MongoDB**

3. **Verificar:**
   - [ ] Logs de timeout ou retry
   - [ ] Fallback para operação sem contexto histórico (STE)
   - [ ] Sistema não falha completamente

---

## Parte 8: Testes de Edge Cases

### Teste E1: Texto Muito Longo

**Objetivo:** Validar limite de tamanho de texto

**Passos:**

1. Gerar texto longo (10001 caracteres):
   ```bash
   LONG_TEXT=$(python3 -c "print('A' * 10001)")
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d "{\"text\": \"$LONG_TEXT\", \"language\": \"pt-BR\"}"
   ```

2. **Verificar resposta:**
   - [ ] Status 400 ou 422
   - [ ] Mensagem sobre limite de tamanho

---

### Teste E2: Caracteres Especiais e Unicode

**Objetivo:** Validar processamento de caracteres especiais

**Passos:**

1. Enviar texto com emojis e unicode:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Criar relatório 📊 com dados financeiros €€€ para análise 中文测试",
       "language": "pt-BR"
     }'
   ```

2. **Verificar:**
   - [ ] Processamento bem-sucedido
   - [ ] Caracteres preservados no envelope
   - [ ] Não há erros de encoding

---

### Teste E3: Intenção em Inglês

**Objetivo:** Validar processamento de outro idioma

**Passos:**

1. Enviar em inglês:
   ```bash
   curl -X POST http://localhost:8000/intentions \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Generate a sales report for the last quarter",
       "language": "en-US"
     }'
   ```

2. **Verificar:**
   - [ ] Classificação correta (business)
   - [ ] Entidades extraídas apropriadamente
   - [ ] language preservado no envelope

---

### Teste E4: Múltiplas Intenções Concorrentes

**Objetivo:** Validar processamento paralelo

**Passos:**

1. Enviar 5 intenções simultaneamente (em terminais separados ou usando &):
   ```bash
   for i in {1..5}; do
     curl -X POST http://localhost:8000/intentions \
       -H "Content-Type: application/json" \
       -d "{\"text\": \"Intenção concorrente número $i\", \"language\": \"pt-BR\"}" &
   done
   wait
   ```

2. **Verificar:**
   - [ ] Todas 5 retornam sucesso
   - [ ] Todas 5 têm intent_id únicos
   - [ ] Mensagens no Kafka em ordem de chegada
   - [ ] Não há erros de concorrência

---

## Registro de Resultados

### Sumário de Testes

| Teste | Status | Observações |
|-------|--------|-------------|
| A1 - Intenção Simples | ☐ Pass / ☐ Fail | |
| A2 - Domínio Technical | ☐ Pass / ☐ Fail | |
| A3 - Domínio Infrastructure | ☐ Pass / ☐ Fail | |
| A4 - Domínio Security | ☐ Pass / ☐ Fail | |
| A5 - Baixa Confiança | ☐ Pass / ☐ Fail | |
| A6 - Constraints/QoS | ☐ Pass / ☐ Fail | |
| A7 - Deduplicação | ☐ Pass / ☐ Fail | |
| A8 - Validação Campos | ☐ Pass / ☐ Fail | |
| A9 - Entidades | ☐ Pass / ☐ Fail | |
| A10 - Métricas | ☐ Pass / ☐ Fail | |
| B1 - Geração Plano | ☐ Pass / ☐ Fail | |
| B2 - Risk Bands | ☐ Pass / ☐ Fail | |
| B3 - DAG Dependências | ☐ Pass / ☐ Fail | |
| B4 - MongoDB Ledger | ☐ Pass / ☐ Fail | |
| B5 - Especialistas | ☐ Pass / ☐ Fail | |
| B6 - Decisão Consolidada | ☐ Pass / ☐ Fail | |
| B7 - Cenário Rejeição | ☐ Pass / ☐ Fail | |
| B8 - Persistência Decisão | ☐ Pass / ☐ Fail | |
| B9 - Opiniões Especialistas | ☐ Pass / ☐ Fail | |
| C1 - Início Workflow | ☐ Pass / ☐ Fail | |
| C2 - Validação Plano | ☐ Pass / ☐ Fail | |
| C3 - Geração Tickets | ☐ Pass / ☐ Fail | |
| C4 - Políticas OPA | ☐ Pass / ☐ Fail | |
| C5 - Consumo Workers | ☐ Pass / ☐ Fail | |
| C6 - Dependências | ☐ Pass / ☐ Fail | |
| C7 - Resultados | ☐ Pass / ☐ Fail | |
| C8 - Retry | ☐ Pass / ☐ Fail | |
| C9 - Consolidação | ☐ Pass / ☐ Fail | |
| C10 - ML Feedback | ☐ Pass / ☐ Fail | |
| O1 - Rastreamento E2E | ☐ Pass / ☐ Fail | |
| O2 - Health Checks | ☐ Pass / ☐ Fail | |
| O3 - Métricas | ☐ Pass / ☐ Fail | |
| R1 - Kafka Down | ☐ Pass / ☐ Fail | |
| R2 - Especialista Down | ☐ Pass / ☐ Fail | |
| R3 - MongoDB Lento | ☐ Pass / ☐ Fail | |
| E1 - Texto Longo | ☐ Pass / ☐ Fail | |
| E2 - Unicode | ☐ Pass / ☐ Fail | |
| E3 - Inglês | ☐ Pass / ☐ Fail | |
| E4 - Concorrência | ☐ Pass / ☐ Fail | |

---

### Métricas Coletadas

| Métrica | Valor |
|---------|-------|
| Tempo médio Gateway (A) | _____ ms |
| Tempo médio STE (B) | _____ ms |
| Tempo médio Consensus (B) | _____ ms |
| Tempo médio Orchestrator (C) | _____ ms |
| Tempo médio Worker (C) | _____ ms |
| Tempo total E2E | _____ ms |
| Taxa de sucesso | _____ % |

---

### Bugs/Issues Encontrados

| # | Descrição | Severidade | Teste Relacionado |
|---|-----------|------------|-------------------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

---

### Informações da Execução

| Campo | Valor |
|-------|-------|
| **Data da Execução** | |
| **Executor** | |
| **Ambiente** | |
| **Versão do Sistema** | |
| **Observações Gerais** | |

---

## Anexo: Comandos Úteis

### Monitoramento de Logs em Tempo Real

```bash
# Todos os serviços do Neural Hive
kubectl logs -n neural-hive -l app.kubernetes.io/part-of=neural-hive -f --tail=100

# Serviço específico
kubectl logs -n neural-hive -l app=gateway-intencoes -f --tail=100
kubectl logs -n neural-hive -l app=semantic-translation-engine -f --tail=100
kubectl logs -n neural-hive -l app=consensus-engine -f --tail=100
kubectl logs -n neural-hive -l app=orchestrator-dynamic -f --tail=100
kubectl logs -n neural-hive -l app=worker-agents -f --tail=100
```

### Verificação de Tópicos Kafka

```bash
# Listar tópicos
kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Contar mensagens em tópico
kubectl exec -n neural-hive-kafka neural-hive-kafka-0 -- \
  /opt/kafka/bin/kafka-run-class.sh kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 --topic intentions.business
```

### Queries MongoDB

```bash
# Conectar ao MongoDB
kubectl exec -it -n mongodb-cluster mongodb-0 -- mongosh

# Dentro do mongosh:
use neural_hive
db.cognitive_ledger.find().sort({created_at: -1}).limit(5)
db.consensus_decisions.find().sort({created_at: -1}).limit(5)
db.specialist_opinions.find().sort({created_at: -1}).limit(10)
```

### Verificar Redis

```bash
# Conectar ao Redis
kubectl exec -it -n redis-cluster redis-cluster-0 -- redis-cli

# Dentro do redis-cli:
KEYS *
GET dedup:*
```
