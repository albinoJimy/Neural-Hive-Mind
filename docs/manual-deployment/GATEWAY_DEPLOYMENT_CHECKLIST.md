# Checklist de Deployment do Gateway de Intenções (Fluxo A)

**Data de início**: _________  
**Responsável**: _________  
**Cluster**: _________ (ex: kubeadm-local-01)  
**Versão**: 1.0.0  

---

## 1. Pré-requisitos

- [ ] Cluster Kubeadm acessível (1 master + 2 workers)
- [ ] kubectl configurado e conectado
- [ ] Helm 3.x instalado
- [ ] Namespace `kafka` com Kafka cluster rodando
- [ ] Namespace `redis-cluster` com Redis cluster rodando
- [ ] Namespace `observability` com Prometheus/Grafana (opcional)
- [ ] Imagem `neural-hive-mind/gateway-intencoes:1.0.0` importada no containerd de todos os nós
- [ ] Ferramentas instaladas: curl, jq, yq

**Validação**:
```bash
kubectl cluster-info
kubectl get nodes
kubectl get pods -n kafka
kubectl get pods -n redis-cluster
sudo ctr -n k8s.io images ls | grep gateway-intencoes
```

---

## 2. Preparação de Configuração

- [ ] Arquivo `environments/local/gateway-config.yaml` revisado
- [ ] Endpoints Kafka/Redis verificados e corretos
- [ ] Script `08-prepare-gateway-values.sh` executado com sucesso
- [ ] Arquivo `helm-charts/gateway-intencoes/values-local-generated.yaml` gerado
- [ ] Valores validados:
  - [ ] `image.pullPolicy: Never`
  - [ ] `config.kafka.bootstrapServers` correto
  - [ ] `config.redis.clusterNodes` correto
  - [ ] `resources.requests` adequados (500m CPU, 1Gi RAM)

**Comando**:
```bash
bash docs/manual-deployment/scripts/08-prepare-gateway-values.sh
cat helm-charts/gateway-intencoes/values-local-generated.yaml
```

---

## 3. Criação de Tópicos Kafka

- [ ] Chart `kafka-topics` instalado via Helm
- [ ] Tópicos criados:
  - [ ] `intentions.business`
  - [ ] `intentions.technical`
  - [ ] `intentions.infrastructure`
  - [ ] `intentions.security`
  - [ ] `intentions.dead-letter`
  - [ ] `intentions.audit`
- [ ] KafkaTopic CRDs visíveis: `kubectl get kafkatopics -n kafka`
- [ ] Tópicos listados via kafka-topics.sh

**Comando**:
```bash
helm upgrade --install kafka-topics helm-charts/kafka-topics \
  --namespace kafka \
  --set environment=local \
  --set topicDefaults.replicationFactor=1 \
  --set topicDefaults.partitions=3 \
  --wait --timeout 5m

kubectl get kafkatopics -n kafka
```

---

## 4. Instalação do Gateway

- [ ] Namespace `fluxo-a` criado
- [ ] Namespace rotulado: `neural-hive-mind.org/layer=application`
- [ ] Helm release `gateway-intencoes` instalado
- [ ] Comando `helm upgrade --install` executado com sucesso
- [ ] Rollout completado (`--wait` retornou 0)
- [ ] Recursos criados:
  - [ ] Deployment `gateway-intencoes`
  - [ ] Service `gateway-intencoes`
  - [ ] ConfigMap `gateway-intencoes-config`
  - [ ] Secret `gateway-intencoes-secret`

**Comando**:
```bash
kubectl create namespace fluxo-a
kubectl label namespace fluxo-a neural-hive-mind.org/layer=application

helm upgrade --install gateway-intencoes helm-charts/gateway-intencoes \
  --namespace fluxo-a \
  -f helm-charts/gateway-intencoes/values-local-generated.yaml \
  --wait --timeout 10m

kubectl get all -n fluxo-a
```

---

## 5. Validação de Deployment

- [ ] Pod em status `Running`
- [ ] Pod ready `1/1`
- [ ] Logs mostram "Application startup complete"
- [ ] Logs mostram "Kafka producer initialized"
- [ ] Logs mostram "Redis client initialized"
- [ ] Sem erros CRITICAL ou FATAL nos logs
- [ ] Health endpoint retorna `{ "status": "healthy" }`
- [ ] Readiness endpoint retorna `{ "status": "ready" }`
- [ ] Status endpoint mostra `kafka_producer_ready: true`
- [ ] Status endpoint mostra `nlu_pipeline_ready: true`

**Comandos**:
```bash
POD_NAME=$(kubectl get pods -n fluxo-a -l app.kubernetes.io/name=gateway-intencoes -o jsonpath='{.items[0].metadata.name}')
kubectl get pod $POD_NAME -n fluxo-a
kubectl logs $POD_NAME -n fluxo-a --tail=50

kubectl port-forward -n fluxo-a svc/gateway-intencoes 8080:80 &
curl -s http://localhost:8080/health | jq
curl -s http://localhost:8080/ready | jq
curl -s http://localhost:8080/status | jq
```

---

## 6. Teste de API

- [ ] Port-forward configurado (porta 8080 → 80)
- [ ] POST para `/api/v1/intents/text` retorna HTTP 200
- [ ] Resposta contém campos obrigatórios: `intent_id`, `status`, `confidence`, `domain`
- [ ] Campos opcionais (ex.: `classification`, `entities`, `kafka_topic`, `cached`) presentes quando habilitados
- [ ] Logs do pod mostram "Intent envelope published to Kafka"

**Comando de teste**:
```bash
INTENT_RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/intents/text \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Criar workflow de aprovação de compras com validação de estoque",
    "domain": "business",
    "context": {
      "user_id": "test-user-001",
      "session_id": "test-session-'$(date +%s)'",
      "tenant_id": "test-tenant"
    }
  }')

echo $INTENT_RESPONSE | jq
INTENT_ID=$(echo $INTENT_RESPONSE | jq -r '.intent_id')
kubectl logs $POD_NAME -n fluxo-a | grep $INTENT_ID
```

---

## 7. Verificação Kafka

- [ ] Mensagens visíveis no tópico `intentions.business`
- [ ] Mensagens contêm dados Avro serializados
- [ ] Consumer group criado (se STE já deployado)
- [ ] Offset do tópico incrementando

**Comando**:
```bash
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- \
  bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.business \
  --from-beginning \
  --max-messages 5
```

---

## 8. Verificação Redis

- [ ] Intenção cacheada no Redis
- [ ] Chave no formato `intent:<UUID>`
- [ ] TTL configurado (~600 segundos)
- [ ] Conteúdo JSON válido
- [ ] (Opcional) `/cache/stats` retorna métricas quando habilitado

**Comando**:
```bash
kubectl exec -n redis-cluster neural-hive-cache-0 -it -- redis-cli
# No prompt do redis-cli:
KEYS intent:*
GET intent:<INTENT_ID>
TTL intent:<INTENT_ID>

# Via API:
curl -s http://localhost:8080/cache/stats | jq
```

---

## 9. Validação Automatizada

- [ ] Script `09-validate-gateway-deployment.sh` executado
- [ ] Todos os checks passaram (38/38)
- [ ] Relatório salvo em `logs/gateway-validation-report.txt`
- [ ] Nenhum check FAIL crítico

**Comando**:
```bash
bash docs/manual-deployment/scripts/09-validate-gateway-deployment.sh --verbose
```

---

## 10. Observabilidade (Opcional)

- [ ] ServiceMonitor criado (se Prometheus habilitado)
- [ ] Métricas sendo coletadas no Prometheus
- [ ] Dashboard Grafana configurado
- [ ] Traces visíveis no Jaeger (se habilitado)
- [ ] Alertas configurados (opcional)

**Validação**:
```bash
kubectl get servicemonitor -n fluxo-a
curl -s http://localhost:8080/metrics | grep gateway_intencoes
```

---

## 11. Troubleshooting (se necessário)

**Problemas encontrados**:
- [ ] ImagePullBackOff → Solução: _________
- [ ] CrashLoopBackOff → Solução: _________
- [ ] Health endpoint unhealthy → Solução: _________
- [ ] Kafka connection error → Solução: _________
- [ ] Redis connection error → Solução: _________
- [ ] Low confidence scores → Solução: _________

**Logs de troubleshooting**:
```bash
kubectl describe pod $POD_NAME -n fluxo-a
kubectl logs $POD_NAME -n fluxo-a --previous  # Se pod reiniciou
kubectl get events -n fluxo-a --sort-by='.lastTimestamp'
```

---

## 12. Finalização

- [ ] Deployment validado e estável por 5+ minutos
- [ ] Documentação atualizada com IPs/endpoints específicos
- [ ] Credenciais salvas em local seguro (se aplicável)
- [ ] Backup do values-local-generated.yaml realizado
- [ ] Equipe notificada sobre conclusão do Fluxo A
- [ ] Próximos passos planejados (Fluxo B: STE + Specialists)

**Assinatura**: _________  
**Data de conclusão**: _________  

---

## Próximos Passos

1. **Fluxo B - Semantic Translation Engine**:
   - Deploy do STE para consumir `intentions.*` e produzir `plans.ready`
   - Guia: `docs/manual-deployment/06-ste-deployment-manual-guide.md`

2. **Fluxo B - Specialists**:
   - Deploy dos 5 specialists (business, technical, behavior, evolution, architecture)
   - Guia: `docs/manual-deployment/07-specialists-deployment-manual-guide.md`

3. **Fluxo C - Consensus Engine e Orchestrator**:
   - Deploy do consensus-engine e orchestrator-dynamic
   - Guia: `docs/manual-deployment/08-consensus-orchestrator-deployment-manual-guide.md`

4. **Teste E2E Completo**:
   - Executar `VALIDACAO_E2E_MANUAL.md`
   - Validar fluxo completo A → B → C
