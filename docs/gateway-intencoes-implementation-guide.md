# Guia de Implementação - Gateway de Intenções Neural Hive-Mind

## Visão Geral

O Gateway de Intenções é um componente central da arquitetura Neural Hive-Mind que processa requisições de análise de intenções através de pipelines ASR (Automatic Speech Recognition) e NLU (Natural Language Understanding). Este documento fornece um guia completo para implementação, configuração e operação do gateway.

## Arquitetura

### Componentes Principais

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Cliente/UI    │───▶│ Gateway de      │───▶│ Processamento   │
│                 │    │ Intenções       │    │ ASR/NLU         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │ Cache Redis     │    │ Kafka           │
                       │ Cluster         │    │ (Mensageria)    │
                       └─────────────────┘    └─────────────────┘
```

### Tecnologias Utilizadas

- **Framework**: FastAPI com Python 3.11+
- **Cache**: Redis Cluster com SSL/TLS
- **Mensageria**: Apache Kafka com SASL/SSL
- **Autenticação**: OAuth2/OIDC (Keycloak)
- **Observabilidade**: OpenTelemetry + Jaeger + Prometheus
- **Containerização**: Docker + Kubernetes
- **Orquestração**: Helm Charts

## Pré-requisitos

### Infraestrutura Necessária

1. **Kubernetes Cluster** (v1.24+)
   - Pelo menos 3 nós worker
   - 8GB RAM e 4 vCPUs por nó mínimo
   - StorageClass para volumes persistentes

2. **Dependências de Cluster**
   - Redis Cluster (namespace: `redis-cluster`)
   - Apache Kafka (namespace: `neural-hive-kafka`)
   - Keycloak (para autenticação OAuth2)
   - Prometheus + Grafana (namespace: `monitoring`)

3. **Ferramentas de Deploy**
   - kubectl (v1.24+)
   - Helm (v3.8+)
   - Docker (v20.10+)

### Configurações de Rede

- **Namespace**: `neural-hive-gateway`
- **Porta do Serviço**: 8000 (HTTP)
- **Ingress**: Configurável via Istio ou NGINX

## Instalação e Configuração

### Passo 1: Preparar o Ambiente

```bash
# Criar namespace
kubectl create namespace neural-hive-gateway

# Adicionar labels ao namespace
kubectl label namespace neural-hive-gateway \
  neural-hive-mind.org/component=gateway \
  neural-hive-mind.org/environment=prod
```

### Passo 2: Configurar Secrets

Crie um arquivo `secrets.yaml` com as credenciais necessárias:

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: gateway-secrets
  namespace: neural-hive-gateway
type: Opaque
data:
  # JWT Secret (base64)
  jwt-secret-key: <base64-encoded-secret>

  # Redis credentials
  redis-password: <base64-encoded-password>
  redis-ca-cert: <base64-encoded-certificate>

  # Kafka SASL credentials
  kafka-username: <base64-encoded-username>
  kafka-password: <base64-encoded-password>

  # Kafka mTLS certificates (se necessário)
  kafka-ca-cert: <base64-encoded-ca-cert>
  kafka-client-cert: <base64-encoded-client-cert>
  kafka-client-key: <base64-encoded-client-key>

  # Keycloak credentials
  keycloak-client-secret: <base64-encoded-client-secret>
```

Aplicar secrets:

```bash
kubectl apply -f secrets.yaml
```

### Passo 3: Configurar Values do Helm

Edite o arquivo `helm-charts/gateway-intencoes/values.yaml`:

```yaml
# Configurações de ambiente
config:
  environment: "prod"
  logLevel: "INFO"

  # Kafka configuration
  kafka:
    bootstrapServers: "neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092"
    tls:
      enabled: true  # Habilitar se usando SSL
      caVerifyMode: "required"
    sasl:
      enabled: true  # Habilitar se usando SASL
      mechanism: "SCRAM-SHA-256"

  # Redis configuration
  redis:
    clusterNodes: "neural-hive-cache.redis-cluster.svc.cluster.local:6379"
    ssl:
      enabled: true  # Habilitar se usando SSL
      certReqs: "required"

  # Keycloak configuration
  keycloak:
    url: "https://keycloak.neural-hive.local"
    realm: "neural-hive"
    clientId: "gateway-intencoes"

# Resources para produção
resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 1000m
    memory: 2Gi

# Autoscaling
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

### Passo 4: Deploy Automatizado

Use o script de deploy fornecido:

```bash
# Deploy em produção
./scripts/deploy/deploy-gateway.sh --environment prod

# Deploy em staging com dry-run
./scripts/deploy/deploy-gateway.sh --environment staging --dry-run

# Deploy em desenvolvimento
./scripts/deploy/deploy-gateway.sh --environment dev
```

### Passo 5: Deploy Manual com Helm

Alternativamente, use Helm diretamente:

```bash
# Build da imagem Docker
cd services/gateway-intencoes
docker build -t neural-hive-mind/gateway-intencoes:1.0.0 .

# Deploy com Helm
helm upgrade --install gateway-intencoes \
  ./helm-charts/gateway-intencoes \
  --namespace neural-hive-gateway \
  --create-namespace \
  --wait \
  --timeout 600s
```

## Configurações Avançadas

### Configuração SSL/TLS

#### Redis SSL

Para habilitar SSL no Redis, configure os seguintes parâmetros:

```yaml
config:
  redis:
    ssl:
      enabled: true
      certReqs: "required"  # none, optional, required
      caCerts: "/etc/ssl/certs/redis-ca.crt"
      certFile: "/etc/ssl/certs/redis-client.crt"  # Opcional
      keyFile: "/etc/ssl/certs/redis-client.key"   # Opcional

secrets:
  redis:
    caCert: |  # Certificado CA em Base64
      LS0tLS1CRUdJTi...
```

#### Kafka SSL/SASL

Para habilitar SSL e SASL no Kafka:

```yaml
config:
  kafka:
    tls:
      enabled: true
      caVerifyMode: "required"
      protocol: "TLSv1_2"
    sasl:
      enabled: true
      mechanism: "SCRAM-SHA-256"  # ou PLAIN, SCRAM-SHA-512

secrets:
  kafka:
    username: "gateway-user"
    password: "secure-password"
    tls:
      caCert: |  # Certificado CA em Base64
        LS0tLS1CRUdJTi...
      clientCert: |  # Certificado cliente (se mTLS)
        LS0tLS1CRUdJTi...
      clientKey: |   # Chave privada cliente (se mTLS)
        LS0tLS1CRUdJTi...
```

### Configuração OAuth2/OIDC

Configure a integração com Keycloak:

```yaml
config:
  keycloak:
    url: "https://keycloak.neural-hive.local"
    realm: "neural-hive"
    clientId: "gateway-intencoes"
    jwksUri: "https://keycloak.neural-hive.local/auth/realms/neural-hive/protocol/openid-connect/certs"
    tokenValidationEnabled: true

secrets:
  keycloak:
    clientSecret: "client-secret-value"
```

### Configuração de Observabilidade

#### Métricas Prometheus

O gateway expõe métricas no endpoint `/metrics`:

- `redis_operations_total` - Total de operações Redis
- `redis_operation_duration_seconds` - Duração das operações Redis
- `redis_hit_ratio` - Taxa de acerto do cache
- `kafka_messages_sent_total` - Mensagens enviadas para Kafka
- `asr_processing_duration_seconds` - Duração do processamento ASR
- `nlu_processing_duration_seconds` - Duração do processamento NLU

#### Tracing Jaeger

Configure o endpoint do Jaeger:

```yaml
observability:
  jaeger:
    endpoint: "http://jaeger-collector.monitoring.svc.cluster.local:14268/api/traces"
```

## Validação e Testes

### Validação Automática

Execute o script de validação:

```bash
./scripts/validation/validate-gateway-integration.sh
```

Este script verifica:
- Status do deployment
- Conectividade com Redis
- Conectividade com Kafka
- Endpoints de saúde
- Configurações SSL/TLS
- Métricas Prometheus
- Logs do gateway

### Testes Manuais

#### Health Check

```bash
# Port-forward para acessar localmente
kubectl port-forward -n neural-hive-gateway svc/gateway-intencoes 8080:80

# Testar endpoint de saúde
curl http://localhost:8080/health
```

#### Teste de Processamento

```bash
# Exemplo de requisição de análise de intenção
curl -X POST http://localhost:8080/api/v1/analyze-intent \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt-token>" \
  -d '{
    "text": "Quero fazer uma transferência bancária",
    "context": {
      "user_id": "user123",
      "session_id": "session456"
    }
  }'
```

#### Verificar Métricas

```bash
# Acessar métricas Prometheus
curl http://localhost:8080/metrics | grep neural_hive
```

## Troubleshooting

### Problemas Comuns

#### 1. Pods não Iniciam

**Sintomas**: Pods ficam em estado `Pending` ou `CrashLoopBackOff`

**Soluções**:
```bash
# Verificar logs do pod
kubectl logs -n neural-hive-gateway -l app.kubernetes.io/name=gateway-intencoes

# Verificar eventos
kubectl describe pod -n neural-hive-gateway <pod-name>

# Verificar recursos disponíveis
kubectl top nodes
kubectl describe nodes
```

#### 2. Falha na Conexão com Redis

**Sintomas**: Logs mostram erros de conexão Redis

**Soluções**:
- Verificar se Redis Cluster está operacional:
  ```bash
  kubectl get pods -n redis-cluster
  ```
- Verificar configurações SSL se habilitado
- Validar credenciais e certificados

#### 3. Falha na Conexão com Kafka

**Sintomas**: Erros de timeout ou autenticação Kafka

**Soluções**:
- Verificar status do Kafka:
  ```bash
  kubectl get pods -n neural-hive-kafka
  ```
- Verificar configurações SASL/SSL
- Validar permissões de ACL no Kafka

#### 4. Problemas de Autenticação OAuth2

**Sintomas**: Erro 401 Unauthorized

**Soluções**:
- Verificar se Keycloak está acessível
- Validar configurações de client ID/secret
- Verificar se JWKS URI está correto

### Logs Detalhados

Para debugging, configure log level DEBUG:

```bash
# Atualizar ConfigMap
kubectl patch configmap gateway-intencoes-config -n neural-hive-gateway \
  --patch '{"data":{"log_level":"DEBUG"}}'

# Reiniciar deployment
kubectl rollout restart deployment/gateway-intencoes -n neural-hive-gateway
```

### Monitoramento em Tempo Real

```bash
# Acompanhar logs em tempo real
kubectl logs -n neural-hive-gateway -l app.kubernetes.io/name=gateway-intencoes -f

# Monitorar recursos
kubectl top pods -n neural-hive-gateway

# Verificar eventos do namespace
kubectl get events -n neural-hive-gateway --sort-by='.lastTimestamp'
```

## Operação e Manutenção

### Backup e Restauração

#### Backup de Configurações

```bash
# Backup das configurações Helm
helm get values gateway-intencoes -n neural-hive-gateway > gateway-backup.yaml

# Backup dos secrets
kubectl get secrets -n neural-hive-gateway -o yaml > secrets-backup.yaml
```

#### Restauração

```bash
# Restaurar com Helm
helm upgrade gateway-intencoes ./helm-charts/gateway-intencoes \
  -n neural-hive-gateway \
  -f gateway-backup.yaml

# Restaurar secrets
kubectl apply -f secrets-backup.yaml
```

### Atualizações

#### Atualização da Imagem

```bash
# Build nova imagem
docker build -t neural-hive-mind/gateway-intencoes:1.1.0 .

# Atualizar deployment
kubectl set image deployment/gateway-intencoes \
  gateway-intencoes=neural-hive-mind/gateway-intencoes:1.1.0 \
  -n neural-hive-gateway

# Verificar rollout
kubectl rollout status deployment/gateway-intencoes -n neural-hive-gateway
```

#### Rollback

```bash
# Ver histórico de rollouts
kubectl rollout history deployment/gateway-intencoes -n neural-hive-gateway

# Rollback para versão anterior
kubectl rollout undo deployment/gateway-intencoes -n neural-hive-gateway

# Rollback para versão específica
kubectl rollout undo deployment/gateway-intencoes -n neural-hive-gateway --to-revision=2
```

### Scaling

#### Manual Scaling

```bash
# Escalar horizontalmente
kubectl scale deployment gateway-intencoes --replicas=5 -n neural-hive-gateway

# Escalar verticalmente (atualizar resources no Helm values)
helm upgrade gateway-intencoes ./helm-charts/gateway-intencoes \
  -n neural-hive-gateway \
  --set resources.limits.cpu=4000m \
  --set resources.limits.memory=8Gi
```

#### Autoscaling

O HPA (Horizontal Pod Autoscaler) está configurado por padrão:

```yaml
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

## Segurança

### Práticas Recomendadas

1. **Secrets Management**
   - Use ferramentas como Sealed Secrets ou External Secrets
   - Rotacione secrets regularmente
   - Nunca commit secrets no código

2. **Network Policies**
   - Configurar NetworkPolicies restritivas
   - Limitar comunicação entre namespaces
   - Usar TLS para todas as comunicações

3. **RBAC**
   - Criar ServiceAccount específica
   - Conceder apenas permissões mínimas necessárias
   - Auditar permissões regularmente

4. **Container Security**
   - Executar como usuário não-root
   - Usar imagens mínimas (distroless)
   - Scan regular por vulnerabilidades

### Certificados TLS

#### Geração de Certificados

```bash
# Gerar CA privada
openssl genrsa -out ca-key.pem 4096

# Gerar certificado CA
openssl req -new -x509 -days 365 -key ca-key.pem -out ca-cert.pem

# Gerar chave privada cliente
openssl genrsa -out client-key.pem 4096

# Gerar CSR cliente
openssl req -new -key client-key.pem -out client.csr

# Assinar certificado cliente
openssl x509 -req -days 365 -in client.csr -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial -out client-cert.pem
```

## Performance e Otimização

### Tuning do Gateway

#### Configurações de Performance

```yaml
config:
  # Limites de processamento
  limits:
    maxAudioSizeMb: 10
    maxTextLength: 10000

  # Redis optimizations
  redis:
    maxConnections: 100
    poolSize: 10
    timeout: 5000
    connectionPoolMaxConnections: 100

  # ASR/NLU settings
  asr:
    device: "cpu"  # ou "cuda" se GPU disponível
  nlu:
    confidenceThreshold: 0.75
```

#### Resources Kubernetes

Para produção high-performance:

```yaml
resources:
  limits:
    cpu: 4000m
    memory: 8Gi
  requests:
    cpu: 2000m
    memory: 4Gi

# Usar nós com GPU se necessário
nodeSelector:
  neural-hive-mind.org/gpu: "true"
```

### Monitoramento de Performance

#### Métricas Chave

- **Latência**: `asr_processing_duration_seconds`, `nlu_processing_duration_seconds`
- **Throughput**: Rate de requisições processadas
- **Cache Hit Ratio**: `redis_hit_ratio`
- **Resource Usage**: CPU e memória dos pods

#### Alertas Recomendados

```yaml
# Exemplo de alertas Prometheus
groups:
- name: gateway-intencoes
  rules:
  - alert: HighLatency
    expr: histogram_quantile(0.95, asr_processing_duration_seconds) > 2
    for: 5m

  - alert: LowCacheHitRatio
    expr: redis_hit_ratio < 0.7
    for: 10m

  - alert: HighErrorRate
    expr: rate(redis_operations_total{status="error"}[5m]) > 0.1
    for: 5m
```

## Conclusão

Este guia fornece uma base sólida para implementar e operar o Gateway de Intenções do Neural Hive-Mind. Para questões específicas ou problemas não cobertos neste documento, consulte:

- **Logs**: `kubectl logs -n neural-hive-gateway -l app.kubernetes.io/name=gateway-intencoes`
- **Métricas**: Dashboards Grafana ou endpoint `/metrics`
- **Documentação da API**: Endpoint `/docs` (Swagger UI)
- **Status de Saúde**: Endpoint `/health`

Mantenha este documento atualizado conforme a evolução da arquitetura e requisitos do sistema.