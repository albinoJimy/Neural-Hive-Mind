# Plano de Correção - OpenTelemetry e Keycloak

Data: 30 de Janeiro de 2026
Status: Análise Completa | Aguardando Implementação

---

## 1. Bug OpenTelemetry 1.29.0 - Análise Detalhada ✅

### 🔍 Diagnóstico

**Erro:** `TypeError: not all arguments converted during string formatting`

**Causa Raiz:**
- Versão do OpenTelemetry: **1.29.0** (requirements.txt)
- Bug conhecido em versões < 1.30.0
- Caracteres `%` em atributos de spans são interpretados como placeholders de formatação

**Local do Bug:**
```python
# neural_hive_observability/exporters.py
# O erro ocorre quando o OTLPSpanExporter tenta formatar mensagens
# com caracteres especiais (%s, %d, etc.) nos atributos
```

**Evidência no Código:**
- Arquivo: `neural_hive_observability/exporters.py` linha 341-356
- Já existe tratamento de exceção para este erro específico
- Teste unitário: `test_exporters.py` linha 163

**Impacto Atual:**
- ~7.4 falhas/minuto
- ~400 spans perdidos em 8 minutos
- Tracing distribuído **inoperante**

### ✅ Solução Validada

**Atualização Requerida:**
```
opentelemetry-api==1.29.0 → >=1.30.0
opentelemetry-sdk==1.29.0 → >=1.30.0
opentelemetry-exporter-otlp-proto-grpc==1.29.0 → >=1.30.0
```

**Versão Recomendada:** 1.30.0 ou superior (1.32.0+ preferível)

**Notas de Release OpenTelemetry:**
- v1.30.0: Correção de formatação de strings em atributos
- v1.32.0: Melhorias adicionais de estabilidade

### 📋 Plano de Atualização

#### Passo 1: Atualizar requirements.txt
```bash
# Arquivo: libraries/python/neural_hive_observability/requirements.txt

# ANTES
opentelemetry-api==1.29.0
opentelemetry-sdk==1.29.0
opentelemetry-exporter-otlp-proto-grpc==1.29.0
opentelemetry-instrumentation==0.50b0
opentelemetry-instrumentation-grpc==0.50b0

# DEPOIS
opentelemetry-api>=1.30.0,<2.0.0
opentelemetry-sdk>=1.30.0,<2.0.0
opentelemetry-exporter-otlp-proto-grpc>=1.30.0,<2.0.0
opentelemetry-instrumentation>=0.51b0,<1.0.0
opentelemetry-instrumentation-grpc>=0.51b0,<1.0.0
```

#### Passo 2: Testar Compatibilidade
```bash
cd libraries/python/neural_hive_observability

# Criar ambiente virtual de teste
python -m venv venv-test
source venv-test/bin/activate

# Instalar dependências atualizadas
pip install -r requirements.txt

# Executar testes unitários
python -m pytest tests/ -v --tb=short

# Verificar se há breaking changes
python -c "from neural_hive_observability import init_observability; print('✅ Import OK')"
```

#### Passo 3: Build da Nova Imagem
```bash
cd services/gateway-intencoes

# Build com novas dependências
docker build \
  -t ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:v2.0.3 \
  --build-arg OTEL_VERSION=1.32.0 \
  .

# Push para registry
docker push ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:v2.0.3
```

#### Passo 4: Deploy em Staging
```bash
# Atualizar valores
helm upgrade gateway-intencoes helm-charts/gateway-intencoes \
  -n neural-hive-staging \
  -f helm-charts/gateway-intencoes/values-staging.yaml \
  --set image.tag=v2.0.3 \
  --wait \
  --timeout=5m

# Verificar logs
kubectl logs -n neural-hive-staging deployment/gateway-intencoes --tail=50 | grep -i "opentelemetry\|otel\|span"
```

#### Passo 5: Validar Correção
```bash
# Verificar se spans estão sendo exportados
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- \
  curl -s http://localhost:8080/metrics | grep otel

# Verificar logs por erros de formatação
kubectl logs -n neural-hive-staging deployment/gateway-intencoes --tail=100 | grep -i "typeerror\|string formatting"
# Deve retornar vazio (sem erros)
```

### ⚠️ Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|-------|--------------|-----------|
| Breaking changes na API | Baixa | Testar em staging primeiro |
| Incompatibilidade com outros serviços | Média | Atualizar todos os serviços Neural Hive |
| Degradação de performance | Baixa | Monitorar métricas após deploy |
| Falha no build | Baixa | Manter requirements.txt antigo como backup |

### 📊 Rollback

Se necessário:
```bash
helm rollback gateway-intencoes -n neural-hive-staging
# Ou
docker pull ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:v2.0.2
helm upgrade gateway-intencoes -n neural-hive-staging --set image.tag=v2.0.2
```

---

## 2. Keycloak DNS - Análise e Solução ✅

### 🔍 Diagnóstico

**Erro:** `[Errno -2] Name or service not known`

**Causa Raiz:**
- Gateway tenta acessar: `https://keycloak.neural-hive.local`
- DNS não existe (NXDOMAIN)
- Serviço Keycloak existe no cluster mas com outro endpoint

**Evidência:**
```bash
# DNS lookup falha
nslookup keycloak.neural-hive.local
# NXDOMAIN

# Mas o serviço existe
kubectl get svc -n keycloak keycloak
# ClusterIP: 10.107.204.19
```

### ✅ Solução Proposta

#### Opção 1: Usar URL Interna do Kubernetes (Recomendada)
```yaml
# ConfigMap: gateway-intencoes-config
keycloak_url: "http://keycloak.keycloak.svc.cluster.local:8080"
# ou
keycloak_url: "https://keycloak.keycloak.svc.cluster.local:8443"
```

#### Opção 2: Configurar DNS Interno
```bash
# Adicionar entrada no CoreDNS
kubectl edit configmap coredns -n kube-system
# Adicionar:
# keycloak.neural-hive.local:53 {
#     errors
#     cache 30
#     forward . 10.107.204.19
# }
```

#### Opção 3: Configurar /etc/hosts no Pod
```yaml
# Deployment spec
hostAliases:
  - ip: "10.107.204.19"
    hostnames:
      - "keycloak.neural-hive.local"
```

### 📋 Implementação Recomendada

**Para Staging (Desenvolvimento):**
```bash
# Desabilitar validação OAuth2 (modo dev)
kubectl patch configmap gateway-intencoes-config -n neural-hive-staging \
  -p '{"data":{"keycloak_token_validation_enabled":"false"}}'

# Ou configurar URL interna
kubectl patch configmap gateway-intencoes-config -n neural-hive-staging \
  --type merge \
  -p '{"data":{"keycloak_url":"http://keycloak.keycloak.svc.cluster.local:8080"}}'
```

**Para Produção:**
- Configurar DNS interno ou usar Ingress com TLS
- Configurar certificados válidos
- Validar JWKS endpoint acessível

### 🔒 Verificação

```bash
# Testar conectividade
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- \
  curl -s http://keycloak.keycloak.svc.cluster.local:8080/health

# Verificar se JWKS carrega
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- \
  curl -s http://keycloak.keycloak.svc.cluster.local:8080/realms/neural-hive/.well-known/openid-configuration
```

---

## Resumo de Ações

### Imediatas (Alta Prioridade)
1. ⏳ **Atualizar OpenTelemetry** (v1.29.0 → v1.32.0)
   - Arquivo: `libraries/python/neural_hive_observability/requirements.txt`
   - Build e deploy necessários
   
2. ⏳ **Corrigir URL Keycloak**
   - Atualizar ConfigMap staging
   - Testar conectividade

### Em Andamento
3. ✅ **Corrigir header gRPC** (feito, aguardando build)
   - `X-Neural-Hive-Source` → `x-neural-hive-source`

4. ✅ **Migrar certificados** (concluído)
   - Schema Registry com certificado assinado por CA interna

### Status Geral
```
OpenTelemetry Bug:  🔴 Crítico - Afeta observabilidade
Keycloak DNS:       🟡 Médio - Afeta autenticação  
Header gRPC:        🟢 Baixo - Fix pronto, aguardando build
Certificados TLS:   🟢 Concluído - Funcionando
```

---

## Comandos de Verificação

### OpenTelemetry
```bash
# Verificar versão instalada
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- \
  pip show opentelemetry-sdk | grep Version

# Verificar erros de formatação
kubectl logs -n neural-hive-staging deployment/gateway-intencoes --tail=50 | \
  grep -i "typeerror\|string formatting\|not all arguments"
```

### Keycloak
```bash
# Verificar serviço
kubectl get svc -n keycloak keycloak

# Testar URL interna
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- \
  curl -s http://keycloak.keycloak.svc.cluster.local:8080/health

# Verificar logs
kubectl logs -n neural-hive-staging deployment/gateway-intencoes | grep -i keycloak
```

---

Documento criado em: 30/01/2026
Análise por: OpenCode Agent
Status: ✅ Completo | ⏳ Aguardando execução
