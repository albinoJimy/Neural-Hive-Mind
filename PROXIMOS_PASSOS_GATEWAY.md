# Próximos Passos - Deploy do Gateway de Intenções

**Data:** 31 de Outubro de 2025
**Status Atual:** 4 Specialists deployados ✅ | Gateway pendente ⏳

---

## Situação Atual

### ✅ Completado com Sucesso

**4 Neural Specialists Operacionais:**
- specialist-technical (1/1 Running)
- specialist-behavior (1/1 Running)
- specialist-evolution (1/1 Running)
- specialist-architecture (1/1 Running)

**Infraestrutura Base:**
- MongoDB (1/1 Running)
- Neo4j (1/1 Running)
- Redis (Running)
- MLflow (Running)

**Documentação Criada:**
- DEPLOYMENT_SPECIALISTS_FASE3.md (25KB) - Documentação completa
- COMANDOS_SPECIALISTS.md (11KB) - Comandos rápidos
- STATUS_DEPLOYMENT_ATUAL.md (5.3KB) - Status visual
- RESUMO_EXECUTIVO_DEPLOYMENT.txt (13KB) - Resumo executivo

---

## Próximo Componente: Gateway de Intenções

### Objetivo

O **Gateway de Intenções** é o ponto de entrada do sistema Neural Hive-Mind. Ele:
- Recebe requisições de usuários (REST API)
- Processa áudio e texto
- Roteia intenções para os specialists apropriados
- Agrega respostas dos specialists
- Retorna resultado consolidado

### Arquivos Existentes

**Código fonte:**
- `services/gateway-intencoes/` - Código da aplicação
- `services/gateway-intencoes/Dockerfile` - Imagem Docker

**Helm chart:**
- `helm-charts/gateway-intencoes/Chart.yaml`
- `helm-charts/gateway-intencoes/values.yaml`
- `helm-charts/gateway-intencoes/values-local.yaml`
- `helm-charts/gateway-intencoes/templates/`

---

## Processo de Deployment do Gateway

### Passo 1: Build da Imagem Docker

O Dockerfile do gateway é mais complexo que os specialists pois inclui:
- **Whisper** para processamento de áudio (modelo 'base')
- **spaCy** pt_core_news_sm e en_core_web_sm
- **FFmpeg** para conversão de áudio
- **PortAudio** para captura de áudio

**Comando de build:**
```bash
docker build -t neural-hive/gateway-intencoes:v1 \
  -f services/gateway-intencoes/Dockerfile .
```

**Tempo estimado:** 15-20 minutos (download dos modelos Whisper)

**Tamanho esperado da imagem:** ~10-12GB (inclui modelo Whisper base ~150MB + spaCy)

### Passo 2: Import para Containerd

```bash
# Export da imagem
docker save neural-hive/gateway-intencoes:v1 -o /tmp/gateway-intencoes-v1.tar

# Import no containerd do Kubernetes
ctr -n k8s.io images import /tmp/gateway-intencoes-v1.tar

# Limpeza
rm /tmp/gateway-intencoes-v1.tar

# Verificação
ctr -n k8s.io images ls | grep gateway-intencoes
```

### Passo 3: Criar values-k8s.yaml

Criar arquivo `helm-charts/gateway-intencoes/values-k8s.yaml` baseado no padrão dos specialists:

```yaml
# Kubernetes production values for gateway-intencoes
replicaCount: 1

image:
  repository: neural-hive/gateway-intencoes
  tag: v1
  pullPolicy: IfNotPresent

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 4Gi

config:
  environment: production
  logLevel: INFO
  enableJwtAuth: false

  specialists:
    technical:
      grpcHost: specialist-technical.specialist-technical.svc.cluster.local
      grpcPort: 50051
      httpHost: specialist-technical.specialist-technical.svc.cluster.local
      httpPort: 8000
    behavior:
      grpcHost: specialist-behavior.specialist-behavior.svc.cluster.local
      grpcPort: 50051
      httpHost: specialist-behavior.specialist-behavior.svc.cluster.local
      httpPort: 8000
    evolution:
      grpcHost: specialist-evolution.specialist-evolution.svc.cluster.local
      grpcPort: 50051
      httpHost: specialist-evolution.specialist-evolution.svc.cluster.local
      httpPort: 8000
    architecture:
      grpcHost: specialist-architecture.specialist-architecture.svc.cluster.local
      grpcPort: 50051
      httpHost: specialist-architecture.specialist-architecture.svc.cluster.local
      httpPort: 8000

  mongodb:
    uri: mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive
    database: neural_hive

  neo4j:
    uri: bolt://neo4j.neo4j-cluster.svc.cluster.local:7687
    user: neo4j
    database: neo4j

  redis:
    clusterNodes: neural-hive-cache.redis-cluster.svc.cluster.local:6379
    sslEnabled: false

secrets:
  mongodbUri: mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin
  neo4jPassword: neo4j
  redisPassword: ""
  jwtSecretKey: "neural-hive-dev-secret-key-change-in-production-12345678"

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1001
  fsGroup: 1001

livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 60
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

service:
  type: ClusterIP
  ports:
    http: 8000
    grpc: 50051
```

### Passo 4: Atualizar Templates Helm (se necessário)

Verificar se os templates do gateway precisam de ajustes:

**deployment.yaml** - Adicionar variáveis de ambiente:
```yaml
env:
- name: ENABLE_JWT_AUTH
  value: {{ .Values.config.enableJwtAuth | ternary "true" "false" | quote }}
- name: JWT_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "gateway-intencoes.secretName" . }}
      key: jwt_secret_key
- name: SPECIALIST_TECHNICAL_GRPC
  value: "{{ .Values.config.specialists.technical.grpcHost }}:{{ .Values.config.specialists.technical.grpcPort }}"
- name: SPECIALIST_BEHAVIOR_GRPC
  value: "{{ .Values.config.specialists.behavior.grpcHost }}:{{ .Values.config.specialists.behavior.grpcPort }}"
- name: SPECIALIST_EVOLUTION_GRPC
  value: "{{ .Values.config.specialists.evolution.grpcHost }}:{{ .Values.config.specialists.evolution.grpcPort }}"
- name: SPECIALIST_ARCHITECTURE_GRPC
  value: "{{ .Values.config.specialists.architecture.grpcHost }}:{{ .Values.config.specialists.architecture.grpcPort }}"
```

### Passo 5: Deploy via Helm

```bash
helm install gateway-intencoes helm-charts/gateway-intencoes \
  --values helm-charts/gateway-intencoes/values-k8s.yaml \
  --namespace gateway-intencoes \
  --create-namespace \
  --wait --timeout=5m
```

### Passo 6: Validação

```bash
# Verificar pod
kubectl get pods -n gateway-intencoes

# Health check
kubectl run test-gateway-health --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s http://gateway-intencoes.gateway-intencoes.svc.cluster.local:8000/health

# Ver logs
kubectl logs -n gateway-intencoes -l app=gateway-intencoes -f

# Port-forward para teste local
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8000:8000
```

---

## Teste End-to-End Completo

### Cenário de Teste

**Objetivo:** Validar fluxo completo de uma intenção através do sistema

**Fluxo:**
1. Cliente envia requisição ao Gateway
2. Gateway processa e identifica specialists relevantes
3. Gateway envia requisição aos specialists via gRPC
4. Cada specialist avalia e retorna opinião
5. Gateway agrega opiniões
6. Gateway retorna resposta consolidada ao cliente

### Script de Teste

```python
#!/usr/bin/env python3
"""
Teste End-to-End do Neural Hive-Mind
"""
import requests
import json

# Configuração
GATEWAY_URL = "http://localhost:8000"  # Após port-forward

# Payload de teste
intent_payload = {
    "intent_text": "Implementar autenticação JWT para API REST",
    "context": {
        "project": "neural-hive-mind",
        "domain": "backend",
        "priority": "high"
    },
    "user_id": "test-user-001"
}

# Enviar requisição
print("=== Enviando intenção ao Gateway ===")
print(f"URL: {GATEWAY_URL}/api/v1/intents")
print(f"Payload: {json.dumps(intent_payload, indent=2)}")
print()

response = requests.post(
    f"{GATEWAY_URL}/api/v1/intents",
    json=intent_payload,
    headers={"Content-Type": "application/json"}
)

print(f"=== Resposta do Gateway ===")
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
print()

# Verificar opinões dos specialists
if response.status_code == 200:
    data = response.json()
    print("=== Opiniões dos Specialists ===")
    for specialist, opinion in data.get("opinions", {}).items():
        print(f"\n{specialist}:")
        print(f"  Confiança: {opinion.get('confidence', 0):.2f}")
        print(f"  Score: {opinion.get('score', 0):.2f}")
        print(f"  Recomendação: {opinion.get('recommendation', 'N/A')}")
```

### Executar Teste

```bash
# 1. Port-forward do gateway
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8000:8000 &

# 2. Executar script de teste
python3 test-end-to-end.py

# 3. Ver logs dos specialists para verificar processamento
for ns in specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
    echo "=== $ns ==="
    kubectl logs -n $ns -l app=$ns --tail=50 | grep "Received"
done
```

### Métricas de Sucesso

- ✅ Gateway responde HTTP 200
- ✅ Todos os 4 specialists foram consultados
- ✅ Cada specialist retornou uma opinião
- ✅ Gateway agregou opiniões corretamente
- ✅ Tempo de resposta < 5 segundos
- ✅ Sem erros nos logs

---

## Troubleshooting Comum

### Problema 1: Build do Gateway Falha

**Sintoma:** Erro ao baixar modelo Whisper
```
ERROR: Could not download model 'base'
```

**Solução:**
```bash
# Verificar conectividade
docker run --rm python:3.11-slim python -c "import urllib.request; urllib.request.urlopen('https://openaipublic.azureedge.net')"

# Build com cache se já foi buildado antes
docker build --cache-from neural-hive/gateway-intencoes:v1 \
  -t neural-hive/gateway-intencoes:v1 \
  -f services/gateway-intencoes/Dockerfile .
```

### Problema 2: Gateway Não Consegue Conectar aos Specialists

**Sintoma:** Logs mostram `Connection refused` ou `Deadline exceeded`

**Solução:**
```bash
# Verificar DNS interno
kubectl run test-dns --rm -i --restart=Never --image=busybox -- \
  nslookup specialist-technical.specialist-technical.svc.cluster.local

# Testar conectividade gRPC
kubectl run test-grpc --rm -i --restart=Never --image=fullstorydev/grpcurl -- \
  grpcurl -plaintext specialist-technical.specialist-technical.svc.cluster.local:50051 list
```

### Problema 3: Gateway Lento ou Timeout

**Sintoma:** Requisições demoram > 10 segundos

**Solução:**
```bash
# Aumentar recursos do gateway
# Editar values-k8s.yaml:
#   resources.limits.cpu: 4000m
#   resources.limits.memory: 8Gi

# Aumentar timeout nos health checks
# readinessProbe.timeoutSeconds: 10
```

---

## Considerações Importantes

### Recursos do Gateway

O Gateway requer mais recursos que os specialists individuais pois:
- Mantém conexões gRPC com todos os specialists
- Processa modelos ML (Whisper para áudio)
- Agrega múltiplas respostas
- Gerencia estado de requisições

**Recomendações de recursos:**
- CPU: 500m request, 2000m limit (mínimo)
- Memory: 1Gi request, 4Gi limit (mínimo)
- Para produção: 1000m request, 4000m limit (CPU), 2Gi request, 8Gi limit (Memory)

### Segurança

Para produção, considerar:
- Habilitar JWT authentication
- Implementar rate limiting
- Configurar network policies
- Usar TLS para comunicação gRPC
- Validar inputs rigorosamente

### Escalabilidade

Para alta carga:
- Habilitar HorizontalPodAutoscaler (HPA)
- Configurar múltiplas réplicas (minReplicas: 2)
- Implementar circuit breakers
- Usar connection pooling para gRPC
- Considerar cache de resultados frequentes

---

## Checklist Final

Antes de considerar Fase 3 completamente concluída:

- [ ] Build da imagem do gateway concluído
- [ ] Imagem importada para containerd
- [ ] values-k8s.yaml criado e configurado
- [ ] Templates Helm atualizados (se necessário)
- [ ] Gateway deployado via Helm
- [ ] Pod do gateway rodando (1/1 Ready)
- [ ] Health check do gateway respondendo
- [ ] Teste end-to-end executado com sucesso
- [ ] Logs dos specialists mostram requisições sendo processadas
- [ ] Documentação atualizada
- [ ] Métricas coletadas e validadas

---

## Documentação para Criar

Após completar o deploy do gateway:

1. **DEPLOYMENT_GATEWAY_COMPLETO.md**
   - Processo completo de build e deploy
   - Configurações específicas do gateway
   - Integração com specialists

2. **TESTE_END_TO_END_FASE3.md**
   - Script de teste completo
   - Cenários de teste
   - Validação de métricas
   - Troubleshooting de testes

3. **ARQUITETURA_COMPLETA_FASE3.md**
   - Diagrama de arquitetura
   - Fluxo de dados
   - Protocolos de comunicação
   - Padrões de design utilizados

---

## Comandos Úteis

### Status Geral do Sistema

```bash
#!/bin/bash
echo "========================================="
echo "  STATUS COMPLETO - NEURAL HIVE-MIND"
echo "========================================="
echo ""

echo "=== INFRAESTRUTURA ==="
kubectl get pods -n mongodb-cluster
kubectl get pods -n neo4j-cluster
echo ""

echo "=== SPECIALISTS ==="
for ns in specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
    echo "$ns:"
    kubectl get pods -n $ns --no-headers
done
echo ""

echo "=== GATEWAY ==="
kubectl get pods -n gateway-intencoes 2>/dev/null || echo "Gateway não deployado ainda"
echo ""

echo "========================================="
```

### Health Check Completo

```bash
#!/bin/bash
echo "=== HEALTH CHECKS ==="

# Specialists
for spec in technical behavior evolution architecture; do
    echo "$spec:"
    kubectl run test-$spec --rm -i --restart=Never --image=curlimages/curl -- \
        curl -s http://specialist-$spec.specialist-$spec.svc.cluster.local:8000/health | jq -r '.status'
done

# Gateway
echo "gateway:"
kubectl run test-gateway --rm -i --restart=Never --image=curlimages/curl -- \
    curl -s http://gateway-intencoes.gateway-intencoes.svc.cluster.local:8000/health | jq -r '.status' 2>/dev/null || echo "não deployado"
```

---

**Criado em:** 31 de Outubro de 2025
**Versão:** 1.0
**Status:** Pronto para execução
