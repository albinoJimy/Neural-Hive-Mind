# Checklist de Deploy e Validação - Consensus Engine

## Pré-Deploy

### Infraestrutura
- [ ] Kafka está Running com tópicos `plans.ready` e `plans.consensus` criados
  - **Nota**: Nomenclatura atual difere do padrão `specialists.opinions.*` / `decisions.*`
  - O Consensus Engine consome `plans.ready` e produz `plans.consensus`
  - Para migração futura, consultar documentação de versionamento de tópicos
- [ ] MongoDB está Running e acessível na porta 27017
- [ ] Redis está Running e acessível na porta 6379
- [ ] Neo4j está Running (usado indiretamente via specialists)
- [ ] Todos os 5 specialists estão Running (1/1 Ready)

### Imagem Docker
- [ ] Imagem `neural-hive-mind/consensus-engine:1.0.0` existe localmente
- [ ] Se Minikube: `eval $(minikube docker-env)` executado
- [ ] Dockerfile multi-stage completo (builder + runtime)
- [ ] Schemas Avro copiados para `/app/schemas/`

### Configuração Helm
- [ ] `values-local.yaml` tem `config.kafka.saslMechanism` definido
- [ ] `image.tag` corresponde à tag da imagem buildada
- [ ] `image.pullPolicy: IfNotPresent` para usar imagem local
- [ ] Todos os 5 endpoints de specialists configurados corretamente
- [ ] MongoDB URI inclui autenticação (`root:local_dev_password`)
- [ ] Redis `clusterEnabled: false` e `sslEnabled: false` para dev local

### Recursos do Cluster
- [ ] CPU disponível > 500m (verificar `kubectl top nodes`)
- [ ] Se CPU > 90%: Escalar MLflow/Redis para 0 réplicas temporariamente

---

## Deploy

### Execução do Script
- [ ] Executar `ONLY=consensus-engine ./deploy-fase1-componentes-faltantes.sh`
- [ ] Namespace `consensus-engine` criado
- [ ] Labels aplicados: `neural-hive.io/component` e `neural-hive.io/layer`
- [ ] Helm chart instalado com sucesso (exit code 0)
- [ ] Deployment criado
- [ ] Service criado (ClusterIP)
- [ ] ConfigMap criado
- [ ] Secret criado

### Status do Pod
- [ ] Pod criado: `kubectl get pods -n consensus-engine`
- [ ] Status: `Running` (não `Pending`, `CrashLoopBackOff`, `Error`)
- [ ] Ready: `1/1` (não `0/1`)
- [ ] Restarts: `0` (não > 0)
- [ ] Age: > 2 minutos (tempo suficiente para inicialização)

---

## Validação Básica

### Logs de Inicialização
- [ ] "Iniciando Consensus Engine" presente nos logs
- [ ] "MongoDB client inicializado" presente
- [ ] "Redis client inicializado" presente
- [ ] "Specialists gRPC client inicializado" presente
- [ ] "Plan consumer inicializado" presente
- [ ] "Decision producer inicializado" presente
- [ ] "Consensus Engine iniciado com sucesso" presente
- [ ] Nenhum erro crítico (ValueError, TypeError, ConnectionError)

### Health Endpoints
- [ ] `/health` retorna `{"status":"healthy"}`
- [ ] `/ready` retorna `{"ready":true}`
- [ ] `/ready` checks: `mongodb=true`
- [ ] `/ready` checks: `redis=true`
- [ ] `/ready` checks: `specialists=true`
- [ ] `/metrics` retorna métricas Prometheus

### Conectividade
- [ ] Service tem ClusterIP atribuído
- [ ] Endpoint aponta para IP do pod
- [ ] Porta 8000 (HTTP) acessível via port-forward
- [ ] Porta 8080 (metrics) acessível via port-forward

---

## Validação de Integração

### Conectividade gRPC com Specialists
- [ ] `specialist-business` acessível na porta 50051
- [ ] `specialist-technical` acessível na porta 50051
- [ ] `specialist-behavior` acessível na porta 50051
- [ ] `specialist-evolution` acessível na porta 50051
- [ ] `specialist-architecture` acessível na porta 50051
- [ ] Health check gRPC retorna `SERVING` para todos

### Kafka Consumer
- [ ] Consumer subscrito ao tópico `plans.ready`
  - **Nota**: Tópico de entrada corrente. Futura migração para `specialists.opinions.*` planejada
- [ ] Consumer group `consensus-engine` criado
- [ ] Offsets inicializados (verificar `kafka-consumer-groups.sh`)
- [ ] Logs mostram "Plan consumer iniciado"

### Kafka Producer
- [ ] Producer conectado ao bootstrap servers
- [ ] Tópico `plans.consensus` existe
  - **Nota**: Tópico de saída corrente. Futura migração para `decisions.*` planejada
- [ ] Logs mostram "Decision producer iniciado"

### MongoDB
- [ ] Conexão estabelecida com autenticação
- [ ] Database `neural_hive` acessível
- [ ] Collection `consensus_decisions` criada
- [ ] Índices criados (6 índices: decision_id, plan_id, intent_id, created_at, hash, compound)

### Redis
- [ ] Conexão estabelecida (modo standalone)
- [ ] Comando `PING` retorna `PONG`
- [ ] PheromoneClient inicializado

---

## Teste End-to-End

### Execução do Script de Teste
- [ ] Executar `./tests/consensus-engine-integration-test.sh`
- [ ] Fase 1: Pré-requisitos verificados
- [ ] Fase 2: Cognitive Plan publicado no Kafka
- [ ] Fase 3: Plan detectado nos logs (timeout < 60s)
- [ ] Fase 4: Mínimo 3/5 specialists invocados
- [ ] Fase 5: Agregação Bayesiana executada
- [ ] Fase 6: Voting Ensemble executado
- [ ] Fase 7: Decisão persistida no MongoDB
- [ ] Fase 8: Feromônios publicados no Redis (opcional)
- [ ] Fase 9: Decisão publicada em `plans.consensus`
- [ ] Fase 10: Métricas Prometheus disponíveis

### Validação de Dados
- [ ] Decisão tem `decision_id` válido (UUID)
- [ ] Decisão tem `plan_id` correspondente ao teste
- [ ] `final_decision` é um dos valores: approve, reject, review_required, conditional
- [ ] `consensus_method` é um dos valores: bayesian, voting, unanimous, fallback
- [ ] `aggregated_confidence` está entre 0.0 e 1.0
- [ ] `aggregated_risk` está entre 0.0 e 1.0
- [ ] `specialist_votes` contém 3-5 votos
- [ ] `consensus_metrics` tem todos os campos preenchidos
- [ ] `hash` SHA-256 presente (64 caracteres hexadecimais)

### Métricas Prometheus
- [ ] `consensus_decisions_total` > 0
- [ ] `bayesian_aggregation_duration_seconds_count` > 0
- [ ] `voting_ensemble_duration_seconds_count` > 0
- [ ] Métricas de erro = 0 (se existirem)

---

## Validação de Sistema de Feromônios

### Publicação
- [ ] Feromônios publicados no Redis após decisão
- [ ] Key format: `pheromone:<specialist>:<domain>:<type>`
- [ ] TTL configurado (3600s = 1h)
- [ ] Strength entre 0.0 e 1.0

### Consulta
- [ ] Endpoint `/api/v1/pheromones/stats` acessível (pode retornar "em progresso")
- [ ] Feromônios recuperáveis via Redis CLI
- [ ] Decay temporal funcionando (strength diminui com o tempo)

---

## Validação de Governança

### Auditoria
- [ ] Cada decisão tem hash SHA-256 único
- [ ] Hash calculado a partir de campos imutáveis
- [ ] Integridade verificável via `verify_integrity()` API
- [ ] Decisões marcadas como `immutable=true` no MongoDB

### Explicabilidade
- [ ] Cada decisão tem `explainability_token`
- [ ] `reasoning_summary` presente e não vazio
- [ ] Specialist votes incluem `reasoning_factors`
- [ ] Mitigations sugeridas quando aplicável

### Compliance
- [ ] `compliance_checks` dict presente
- [ ] `guardrails_triggered` lista presente (pode estar vazia)
- [ ] `requires_human_review` flag presente

---

## Performance

### Latências
- [ ] Tempo de inicialização < 60s (liveness probe)
- [ ] Tempo para ready < 30s (readiness probe)
- [ ] Processamento de plan < 10s (5 specialists + consenso)
- [ ] Persistência no MongoDB < 1s
- [ ] Publicação no Kafka < 500ms

### Recursos
- [ ] CPU usage < 1000m (limit)
- [ ] Memory usage < 2Gi (limit)
- [ ] Sem memory leaks (usage estável ao longo do tempo)
- [ ] Sem restarts inesperados

---

## Troubleshooting (se necessário)

### Logs Detalhados
- [ ] Logs de erro analisados
- [ ] Stack traces capturados
- [ ] Eventos do Kubernetes revisados

### Conectividade
- [ ] DNS resolution testado para todas as dependências
- [ ] Portas TCP testadas com `nc -zv`
- [ ] Timeouts ajustados se necessário

### Configuração
- [ ] ConfigMap validado (todas as variáveis presentes)
- [ ] Secret validado (mesmo que vazio)
- [ ] Values Helm corretos

---

## Pós-Deploy

### Documentação
- [ ] Atualizar `STATUS_DEPLOY_ATUAL.md` com status do consensus-engine
- [ ] Registrar versão deployada (1.0.0)
- [ ] Documentar problemas encontrados e soluções
- [ ] Atualizar checklist com lições aprendidas

### Próximos Passos
- [ ] Deploy do Memory Layer API (próximo componente da Fase 1)
- [ ] Teste E2E completo da Fase 1 (Intent → STE → Consensus → Decision)
- [ ] Deploy de Observabilidade (Prometheus + Grafana + Jaeger)
- [ ] Deploy de Governança (OPA Gatekeeper)

---

## Critérios de Aceitação Final

### Mínimo para Sucesso
- [ ] Pod Running 1/1 Ready por > 5 minutos
- [ ] /health e /ready retornam true
- [ ] Teste E2E passa com sucesso (decision_id gerado)
- [ ] Mínimo 3/5 specialists respondendo
- [ ] Decisão persistida no MongoDB
- [ ] Métricas Prometheus disponíveis

### Ideal (100% Completo)
- [ ] Todos os 5 specialists respondendo
- [ ] Feromônios publicados e recuperáveis
- [ ] Decisão publicada em plans.consensus
- [ ] Latências dentro dos SLOs
- [ ] Zero erros nos logs
- [ ] Integridade do ledger verificada

---

**Status Final**: ⬜ Não Iniciado | 🟡 Em Progresso | ✅ Completo | ❌ Falhou

**Data de Conclusão**: __________

**Responsável**: __________

**Observações**: __________
