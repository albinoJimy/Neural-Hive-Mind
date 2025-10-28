# Gateway de Intenções - Guia de Implantação (Kubernetes Local)

## Visão Geral

O serviço gateway-intencoes é o ponto de entrada para capturar intenções de usuários no sistema Neural Hive-Mind. Suas principais funções incluem:

- **Ponto de entrada** para captura de intenções de usuários (texto e voz)
- **Pipeline ASR** (Automatic Speech Recognition) usando Whisper para reconhecimento de fala
- **Pipeline NLU** (Natural Language Understanding) usando spaCy para processamento de linguagem natural
- **Classificação de intenções** com pontuação de confiança
- **Produtor Kafka** para publicação de envelopes de intenção nos tópicos apropriados
- **Cache Redis** para deduplicação e melhoria de desempenho
- **Integração OAuth2/Keycloak** para autenticação (opcional em desenvolvimento)

## Pré-requisitos

Antes de implantar o gateway-intencoes, certifique-se de que você tem:

1. **Minikube** em execução com recursos adequados:
   - Mínimo: 4 CPUs, 8GB RAM
   - Recomendado: 6 CPUs, 12GB RAM (para executar todos os serviços)

2. **kubectl** configurado para acessar o cluster:
   ```bash
   kubectl cluster-info
   ```

3. **Helm 3** instalado:
   ```bash
   helm version
   ```

4. **Docker** para construção de imagens:
   ```bash
   docker --version
   ```

5. **Infraestrutura implantada**:
   - **Cluster Kafka** no namespace `kafka`
   - **Cluster Redis** no namespace `redis-cluster`
   - **Keycloak** no namespace `keycloak` (opcional para desenvolvimento local)
   - **Tópicos Kafka criados**:
     - `intentions.business`
     - `intentions.technical`
     - `intentions.infrastructure`
     - `intentions.security`

### Verificação de Pré-requisitos

```bash
# Verificar Kafka
kubectl get pods -n kafka
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --list

# Verificar Redis
kubectl get pods -n redis-cluster
kubectl exec -n redis-cluster <redis-pod> -- redis-cli ping

# Verificar Keycloak (opcional)
kubectl get pods -n keycloak
```

## Arquitetura

### Componentes do Gateway

O gateway-intencoes é construído como uma aplicação **FastAPI** assíncrona com os seguintes componentes:

#### Endpoints da API

- **Health Checks**:
  - `GET /health` - Verifica saúde básica do serviço (liveness probe)
  - `GET /ready` - Verifica prontidão incluindo dependências (readiness probe)

- **Processamento de Intenções**:
  - `POST /api/v1/intents/text` - Processa intenções de texto
  - `POST /api/v1/intents/voice` - Processa intenções de voz (arquivos de áudio)
  - `GET /api/v1/intents/{intent_id}` - Recupera intenção em cache

- **Observabilidade**:
  - `GET /metrics` - Métricas Prometheus

#### Dependências

- **Kafka**: Para streaming de eventos e publicação de envelopes de intenção
- **Redis**: Para cache e deduplicação de intenções
- **Keycloak**: Para autenticação OAuth2 (pode ser desabilitado em desenvolvimento)

#### Modelos de Machine Learning

- **Whisper** (tiny/base): Para reconhecimento automático de fala (ASR)
- **spaCy pt_core_news_sm**: Para processamento de linguagem natural em português (NLU)

## Etapas de Implantação

### Etapa 1: Verificar Infraestrutura

Antes de implantar o gateway, verifique se todas as dependências estão funcionando:

```bash
# Verificar Kafka
kubectl get pods -n kafka
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --list

# Verificar Redis
kubectl get pods -n redis-cluster
kubectl exec -n redis-cluster <redis-pod> -- redis-cli ping

# Verificar Keycloak (opcional)
kubectl get pods -n keycloak
```

**Todos os pods devem estar no estado Running e Ready.**

### Etapa 2: Construir Imagem Docker

A imagem Docker do gateway deve ser construída usando o daemon Docker do Minikube para evitar problemas de pull:

```bash
# Configurar para usar o daemon Docker do Minikube
eval $(minikube docker-env)

# Construir a partir da raiz do projeto
cd /home/jimy/Base/Neural-Hive-Mind
docker build -t neural-hive-mind/gateway-intencoes:local -f services/gateway-intencoes/Dockerfile .

# Verificar imagem
docker images | grep gateway-intencoes
```

#### Detalhes do Dockerfile

O Dockerfile do gateway (`services/gateway-intencoes/Dockerfile`) inclui:

- **Imagem base**: `python:3.11-slim` para um ambiente leve
- **Dependências do sistema**:
  - `ffmpeg` - Para processamento de áudio
  - `portaudio19-dev` - Para captura de áudio
  - `libsndfile1` - Para manipulação de arquivos de áudio
- **Modelos ML**:
  - Download do Whisper base durante o build
  - Download do spaCy pt_core_news_sm durante o build
- **Código da aplicação**: Copia o código do serviço e o schema Avro
- **Usuário não-root**: Executa como `appuser:1001` para segurança
- **Porta exposta**: 8000 para o servidor FastAPI

### Etapa 3: Implantar com Helm

Use o Helm para implantar o gateway no Kubernetes:

```bash
# Opção 1: Usar o script de deploy (recomendado)
bash scripts/deploy/deploy-gateway.sh --environment dev --namespace gateway-intencoes

# Opção 2: Deploy manual com Helm
kubectl create namespace gateway-intencoes

helm upgrade --install gateway-intencoes \
  helm-charts/gateway-intencoes/ \
  --namespace gateway-intencoes \
  --values helm-charts/gateway-intencoes/values-local.yaml \
  --set image.tag=local \
  --wait --timeout=5m

# Verificar status da implantação
kubectl rollout status deployment/gateway-intencoes -n gateway-intencoes
```

#### Estrutura do Chart Helm

O chart Helm em `helm-charts/gateway-intencoes/` contém:

- **`values.yaml`**: Configuração de produção
  - 3 réplicas para alta disponibilidade
  - Autoscaling habilitado (HPA)
  - Resource limits definidos
  - Network policies restritivas
  - PodDisruptionBudget configurado

- **`values-local.yaml`**: Configuração para desenvolvimento local
  - 1 réplica para economizar recursos
  - Recursos reduzidos (512Mi RAM, 500m CPU)
  - Debug habilitado
  - Modelo Whisper menor (tiny)
  - Validação de token Keycloak desabilitada

- **Templates**:
  - `deployment.yaml` - Deployment principal
  - `service.yaml` - Service ClusterIP
  - `configmap.yaml` - Configurações da aplicação
  - `secret.yaml` - Credenciais sensíveis
  - `networkpolicy.yaml` - Políticas de rede
  - `servicemonitor.yaml` - Monitoramento Prometheus
  - `hpa.yaml` - HorizontalPodAutoscaler
  - `pdb.yaml` - PodDisruptionBudget

### Etapa 4: Verificar Implantação

Após a implantação, verifique se o pod está funcionando corretamente:

```bash
# Verificar pods
kubectl get pods -n gateway-intencoes

# Ver detalhes do pod
kubectl describe pod -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes

# Verificar logs
kubectl logs -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes --tail=100

# Verificar service
kubectl get svc -n gateway-intencoes
```

**Saída esperada**:
- Pod no estado `Running`
- Todas as condições `Ready: True`
- Logs mostrando inicialização bem-sucedida do FastAPI
- Service com ClusterIP atribuído

## Testes

### Testes Automatizados

#### Script de Teste Abrangente

Execute o script de teste completo que verifica toda a implantação:

```bash
bash scripts/test/test-gateway-local.sh
```

Este script executa:
1. Verificação de pré-implantação (infraestrutura)
2. Build da imagem Docker
3. Implantação usando scripts/deploy/deploy-gateway.sh
4. Verificação de saúde do pod
5. Testes de conectividade (Kafka, Redis usando netshoot)
6. Teste de health endpoint com validação JSON
7. Teste da API de intenções de texto
8. Publicação de intenção de teste no Kafka
9. Validação de logs do gateway
10. Validação de integração
11. Resumo com informações de acesso

#### Script de Validação de Integração

Execute apenas a validação de integração:

```bash
bash scripts/validation/validate-gateway-integration.sh
```

### Testes Manuais

#### 1. Health Check

Verifique os endpoints de saúde:

```bash
# Port-forward para o serviço
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8080:80

# Em outro terminal, teste os endpoints
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

**Resposta esperada**:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-06T12:00:00Z"
}
```

#### 2. Publicar Intenção de Teste (via Kafka)

Use o script de publicação de teste:

```bash
# Intenção de negócio
bash scripts/test/publish-test-intent.sh \
  --domain business \
  --text "Criar fluxo de aprovação para pedidos de compra"

# Intenção técnica
bash scripts/test/publish-test-intent.sh \
  --domain technical \
  --text "Implantar microsserviço de autenticação" \
  --topic intentions.technical

# Alta prioridade
bash scripts/test/publish-test-intent.sh \
  --domain business \
  --text "Correção crítica de segurança" \
  --priority critical
```

#### 3. Teste Direto da API (Intenção de Texto)

Teste o endpoint da API diretamente:

```bash
# Port-forward se ainda não estiver ativo
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8080:80

# Enviar intenção de texto
curl -X POST http://localhost:8080/api/v1/intents/text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Criar um fluxo de trabalho para aprovar pedidos de compra com validação de estoque",
    "domain": "business",
    "context": {
      "user_id": "test-user",
      "session_id": "test-session",
      "tenant_id": "test-tenant"
    }
  }'
```

**Resposta esperada**:
```json
{
  "intent_id": "gateway-1728220800123-abc123",
  "status": "published",
  "confidence": 0.95,
  "topic": "intentions.business",
  "timestamp": "2025-10-06T12:00:00.123Z"
}
```

#### 4. Verificar Tópico Kafka

Verifique se as mensagens foram publicadas no Kafka:

```bash
# Consumir do tópico intentions.business
kubectl run kafka-consumer-test --restart=Never \
  --image=docker.io/bitnami/kafka:4.0.0-debian-12-r10 \
  --namespace=kafka \
  --command -- kafka-console-consumer.sh \
  --bootstrap-server neural-hive-kafka-kafka-bootstrap:9092 \
  --topic intentions.business \
  --from-beginning \
  --max-messages 5

# Aguardar alguns segundos e ver os logs
sleep 5
kubectl logs kafka-consumer-test -n kafka

# Limpar
kubectl delete pod kafka-consumer-test -n kafka --force --grace-period=0
```

## Solução de Problemas

### Pod Não Está Iniciando

**Sintomas**: Pod em estado `Pending`, `CrashLoopBackOff` ou `ImagePullBackOff`

**Diagnóstico**:
```bash
kubectl describe pod -n gateway-intencoes <pod-name>
kubectl logs -n gateway-intencoes <pod-name>
```

**Possíveis causas**:

1. **ImagePullBackOff**: Imagem não encontrada no Minikube
   - Solução: Certifique-se de executar `eval $(minikube docker-env)` antes do build
   - Reconstrua a imagem: `docker build -t neural-hive-mind/gateway-intencoes:local -f services/gateway-intencoes/Dockerfile .`

2. **Recursos insuficientes**: Minikube sem recursos suficientes
   - Solução: Aumente os recursos do Minikube: `minikube delete && minikube start --cpus=6 --memory=12288`

3. **Init containers falhando**: Download de modelos ML falhou
   - Solução: Verifique conectividade de rede, os modelos são baixados durante o build

### Health Check Falhando

**Sintomas**: Readiness probe falha, pod não fica `Ready`

**Diagnóstico**:
```bash
kubectl logs -n gateway-intencoes <pod-name>
kubectl exec -n gateway-intencoes <pod-name> -- curl http://localhost:8000/health
```

**Possíveis causas**:

1. **Redis não acessível**: Gateway não consegue conectar ao Redis
   - Solução: Verifique se o Redis cluster está rodando: `kubectl get pods -n redis-cluster`
   - Teste conectividade usando netshoot:
   ```bash
   kubectl run netshoot-test --restart=Never --rm -i --tty -n gateway-intencoes \
     --image=nicolaka/netshoot \
     --command -- bash -lc "nc -zv neural-hive-cache.redis-cluster.svc.cluster.local 6379"
   ```

2. **Kafka não acessível**: Gateway não consegue conectar ao Kafka
   - Solução: Verifique se o Kafka está rodando: `kubectl get pods -n kafka`
   - Teste conectividade usando netshoot:
   ```bash
   kubectl run netshoot-kafka --restart=Never --rm -i --tty -n gateway-intencoes \
     --image=nicolaka/netshoot \
     --command -- bash -lc "nc -zv neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local 9092"
   ```

3. **Erros na aplicação**: Exceções durante a inicialização
   - Solução: Verifique logs para stacktraces: `kubectl logs -n gateway-intencoes <pod-name> | grep -A 20 "ERROR\|Exception"`

### Problemas de Conexão com Kafka

**Sintomas**: Intenções não estão sendo publicadas, erros de timeout do Kafka nos logs

**Diagnóstico**:
```bash
# Verificar DNS do Kafka
kubectl exec -n gateway-intencoes <pod-name> -- nslookup neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local

# Testar conectividade usando netshoot
kubectl run netshoot-kafka --restart=Never --rm -i --tty -n gateway-intencoes \
  --image=nicolaka/netshoot \
  --command -- bash -lc "nc -zv neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local 9092"

# Verificar se Kafka está pronto
kubectl get pods -n kafka
kubectl logs -n kafka neural-hive-kafka-kafka-0 --tail=50
```

**Possíveis soluções**:

1. Kafka não está pronto: Aguarde o Kafka ficar completamente operacional
2. Network policies bloqueando: Verifique policies: `kubectl get networkpolicies -n gateway-intencoes`
3. Tópicos não criados: Crie os tópicos necessários (ver pré-requisitos)

### Problemas de Conexão com Redis

**Sintomas**: Erros de conexão Redis nos logs, cache não funciona

**Diagnóstico**:
```bash
# Verificar pods Redis
kubectl get pods -n redis-cluster

# Testar conectividade usando netshoot
kubectl run netshoot-redis --restart=Never --rm -i --tty -n gateway-intencoes \
  --image=nicolaka/netshoot \
  --command -- bash -lc "nc -zv neural-hive-cache.redis-cluster.svc.cluster.local 6379"

# Testar Redis diretamente
kubectl exec -n redis-cluster <redis-pod> -- redis-cli ping
```

**Possíveis soluções**:

1. Redis não está pronto: Aguarde o cluster Redis ficar operacional
2. Configuração incorreta: Verifique `config.redis.clusterNodes` em `values-local.yaml`
3. Senha incorreta: Verifique o secret do Redis

## Configuração

### Opções de Configuração em values-local.yaml

As principais opções de configuração para desenvolvimento local:

```yaml
# Réplicas
replicaCount: 1  # Uma única réplica para dev

# Imagem
image:
  repository: neural-hive-mind/gateway-intencoes
  tag: local  # Tag para imagem construída localmente
  pullPolicy: IfNotPresent

# Recursos
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "1Gi"
    cpu: "1000m"

# Configuração da aplicação
config:
  logLevel: DEBUG  # Log verboso para desenvolvimento
  debug: true  # Modo debug habilitado

  # Kafka
  kafka:
    bootstrapServers: "neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"

  # Redis
  redis:
    clusterNodes: "neural-hive-cache.redis-cluster.svc.cluster.local:6379"

  # Keycloak (desabilitado para dev)
  keycloak:
    tokenValidationEnabled: false

  # ASR (Whisper)
  asr:
    modelName: tiny  # Modelo menor para dev (base, small, medium, large)

  # NLU (spaCy)
  nlu:
    modelName: pt_core_news_sm  # Modelo em português
```

### Variáveis de Ambiente Importantes

O gateway usa as seguintes variáveis de ambiente (configuradas via ConfigMap e Secret):

- `KAFKA_BOOTSTRAP_SERVERS` - Servidores bootstrap do Kafka
- `REDIS_CLUSTER_NODES` - Nós do cluster Redis
- `REDIS_PASSWORD` - Senha do Redis (do Secret)
- `LOG_LEVEL` - Nível de log (DEBUG, INFO, WARNING, ERROR)
- `DEBUG_MODE` - Habilita modo debug (true/false)
- `KEYCLOAK_URL` - URL do Keycloak
- `KEYCLOAK_REALM` - Realm do Keycloak
- `KEYCLOAK_TOKEN_VALIDATION_ENABLED` - Habilita validação de token (true/false)
- `ASR_MODEL_NAME` - Nome do modelo Whisper
- `NLU_MODEL_NAME` - Nome do modelo spaCy

## Monitoramento

### Logs

Visualize os logs do gateway:

```bash
# Seguir logs em tempo real
kubectl logs -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes -f

# Buscar por ID de intenção específico
kubectl logs -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes | grep <intent-id>

# Buscar erros
kubectl logs -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes | grep -i "error\|exception"

# Últimas 100 linhas
kubectl logs -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes --tail=100
```

### Métricas

Acesse as métricas Prometheus:

```bash
# Port-forward para o serviço
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8080:80

# Acessar métricas
curl http://localhost:8080/metrics
```

**Métricas disponíveis**:
- `gateway_intents_total` - Total de intenções processadas
- `gateway_intents_by_domain` - Intenções por domínio
- `gateway_kafka_publish_duration_seconds` - Duração de publicação no Kafka
- `gateway_cache_hits_total` - Hits de cache Redis
- `gateway_cache_misses_total` - Misses de cache Redis

### Uso de Recursos

Monitore o uso de recursos do pod:

```bash
# Ver uso atual de CPU e memória
kubectl top pod -n gateway-intencoes

# Ver uso ao longo do tempo
watch -n 5 kubectl top pod -n gateway-intencoes
```

## Próximos Passos

Após implantar e testar com sucesso o gateway:

1. **Implantar semantic-translation-engine**:
   - Consome de tópicos `intentions.*`
   - Traduz intenções de usuário em semântica estruturada
   - Publica em tópicos `semantic.*`

2. **Implantar os 5 serviços especialistas**:
   - `specialist-business` - Especialista em processos de negócio
   - `specialist-technical` - Especialista em decisões técnicas
   - `specialist-behavior` - Especialista em padrões comportamentais
   - `specialist-evolution` - Especialista em evolução de código
   - `specialist-architecture` - Especialista em arquitetura de sistema

3. **Implantar consensus-engine**:
   - Consolida opiniões dos especialistas
   - Resolve conflitos e gera decisão final
   - Publica decisões consolidadas

4. **Executar teste end-to-end da Fase 1**:
   ```bash
   bash tests/phase1-end-to-end-test.sh
   ```

## Referências

### Código e Configuração

- **Código do serviço**: `services/gateway-intencoes/`
  - `app/main.py` - Aplicação FastAPI principal
  - `app/pipelines/` - Pipelines ASR e NLU
  - `app/clients/` - Clientes Kafka e Redis
  - `app/models/` - Modelos de dados

- **Chart Helm**: `helm-charts/gateway-intencoes/`
  - `values.yaml` - Configuração de produção
  - `values-local.yaml` - Configuração local
  - `templates/` - Templates Kubernetes

### Scripts

- **Script de implantação**: `scripts/deploy/deploy-gateway.sh`
- **Script de validação**: `scripts/validation/validate-gateway-integration.sh`
- **Script de teste completo**: `scripts/test/test-gateway-local.sh`
- **Script de publicação de teste**: `scripts/test/publish-test-intent.sh`

### Schemas

- **Schema Avro do envelope de intenção**: `schemas/intent-envelope/intent-envelope.avsc`
  - Define a estrutura das mensagens de intenção
  - Usado para serialização/desserialização Avro
  - Contém metadados, contexto, QoS

### Testes

- **Teste E2E Fase 1**: `tests/phase1-end-to-end-test.sh`
  - Testa o fluxo completo: gateway → semantic-translation-engine → especialistas → consensus-engine
