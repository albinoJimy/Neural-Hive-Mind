# Correções Aplicadas - Gateway Neural Hive-Mind

## Resumo das Correções

Data: 30 de Janeiro de 2026
Ambiente: neural-hive-staging

---

## 1. Migração de Certificados Auto-Assinados para CA Interna ✅

### Problema
Certificados TLS auto-assinados causavam erro `SSL: CERTIFICATE_VERIFY_FAILED` na comunicação entre Gateway e Schema Registry.

### Solução Aplicada
1. **Criada Neural Hive Internal CA** (`neural-hive-ca`)
   - Tipo: ECDSA P-256
   - Validade: 10 anos
   - Namespace: cert-manager

2. **Criado ClusterIssuer** (`neural-hive-ca-issuer`)
   - Emite certificados assinados pela CA interna
   - Disponível cluster-wide

3. **Re-emitido certificado do Schema Registry**
   - Assinado pela Neural Hive Internal CA
   - Secret: `schema-registry-tls-secret` (namespace: kafka)

4. **Copiado secret para staging**
   - Gateway agora consegue validar o certificado TLS
   - Comunicação segura estabelecida

### Resultado
- ✅ Schema Registry: 2/2 Ready
- ✅ Gateway: 1/1 Running  
- ✅ TLS: `Verify return code: 0 (ok)`
- ✅ Health checks: Todos OK

---

## 2. Correção do Header gRPC Inválido ✅

### Problema
Header `X-Neural-Hive-Source` em maiúsculas causava erro em gRPC:
```
Metadata key 'X-Neural-Hive-Source' is invalid: INTERNAL: Illegal header key
```

### Causa
Headers gRPC devem ser lowercase (conforme especificação HTTP/2).

### Solução Aplicada
**Arquivos modificados:**
1. `libraries/python/neural_hive_observability/neural_hive_observability/context.py`
   - Linha 202: `X-Neural-Hive-Source` → `x-neural-hive-source`

2. `libraries/python/neural_hive_observability/tests/test_observability.py`
   - Atualizado testes para novo nome do header

3. `libraries/python/neural_hive_observability/tests/test_context.py`
   - Atualizado testes para novo nome do header

### Próximo Passo
⚠️ **Build necessário:** Para aplicar essa correção no staging, é preciso:
1. Build da nova imagem Docker com as alterações
2. Push para registry
3. Helm upgrade do gateway

---

## 3. Bug OpenTelemetry 1.39.1 - Em Análise 🔍

### Problema
Erro contínuo na exportação de spans:
```
TypeError: not all arguments converted during string formatting
```

### Impacto
- Perda de tracing distribuído
- ~7.4 falhas/minuto
- ~400 spans perdidos em 8 minutos

### Solução Proposta
Atualizar biblioteca `opentelemetry-api` e `opentelemetry-sdk` para versão >= 1.40.0

### Status
⏳ **Aguardando build** - Requer atualização de dependências e nova imagem

---

## 4. Keycloak Indisponível - Verificado ⚠️

### Problema
DNS `keycloak.neural-hive.local` não resolvido:
```
[Errno -2] Name or service not known
```

### Impacto
- Autenticação OAuth2 pode falhar
- JWKS não carregado

### Solução Proposta
Verificar disponibilidade do serviço Keycloak no cluster ou atualizar URLs no ConfigMap.

### Status
📋 **Baixa prioridade** - Staging pode operar sem Keycloak (modo dev)

---

## Status Geral do Gateway

| Componente | Status | Observação |
|------------|--------|------------|
| **Gateway API** | 🟢 OK | Respondendo requisições |
| **Health Checks** | 🟢 OK | HTTP 200, todos componentes healthy |
| **Kafka Producer** | 🟢 OK | Conectado ao Schema Registry |
| **Redis** | 🟢 OK | Conexão estabelecida |
| **ASR/NLU Pipelines** | 🟢 OK | Health checks ativos |
| **TLS/Schema Registry** | 🟢 OK | Comunicação segura funcionando |
| **OpenTelemetry** | 🟡 Degradado | Header corrigido, aguardando build |
| **Keycloak** | 🟡 Indisponível | DNS não resolvido |

---

## Próximos Passos Recomendados

### Imediato (Alta Prioridade)
1. **Build e deploy da imagem corrigida**
   ```bash
   cd services/gateway-intencoes
   docker build -t gateway-intencoes:v2.0.2 .
   docker push <registry>/gateway-intencoes:v2.0.2
   helm upgrade gateway-intencoes -n neural-hive-staging --set image.tag=v2.0.2
   ```

2. **Validar correção do header gRPC**
   - Verificar logs após deploy
   - Confirmar ausência de "Illegal header key"

### Curto Prazo (Média Prioridade)
3. **Atualizar OpenTelemetry**
   - Atualizar requirements.txt
   - Testar exportação de spans
   - Validar tracing distribuído

4. **Verificar Keycloak**
   - Confirmar se serviço existe no cluster
   - Atualizar URLs se necessário

### Longo Prazo (Baixa Prioridade)
5. **Aplicar migração em produção**
   - Replicar certificados CA para neural-hive
   - Atualizar gateway production
   - Validar comunicação TLS

---

## Arquivos Criados/Modificados

### Novos Arquivos
- `k8s/certificates/neural-hive-ca.yaml`
- `k8s/certificates/neural-hive-ca-issuer.yaml`
- `k8s/certificates/schema-registry-tls-updated.yaml`
- `scripts/distribute-neural-hive-ca.sh`
- `k8s/certificates/README.md`

### Arquivos Modificados
- `libraries/python/neural_hive_observability/neural_hive_observability/context.py`
- `libraries/python/neural_hive_observability/tests/test_observability.py`
- `libraries/python/neural_hive_observability/tests/test_context.py`
- `helm-charts/gateway-intencoes/templates/configmap.yaml`
- `helm-charts/gateway-intencoes/values-staging.yaml`

---

## Comandos Úteis

### Verificar status
```bash
# Gateway
kubectl get pods -n neural-hive-staging
kubectl logs -n neural-hive-staging deployment/gateway-intencoes --tail=50

# Schema Registry
kubectl get pods -n kafka -l app=apicurio-registry
kubectl get certificate schema-registry-tls -n kafka

# Certificados
kubectl get secret schema-registry-tls-secret -n kafka -o jsonpath='{.data.ca\.crt}' | base64 -d | openssl x509 -subject -noout
```

### Testar TLS
```bash
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- \
  openssl s_client -connect schema-registry.kafka.svc.cluster.local:8081 \
  -CAfile /etc/ssl/certs/schema-registry-ca.crt <<< "Q" 2>&1 | grep "Verify return code"
```

---

## Notas

- **Staging**: Ambiente funcional com observabilidade parcialmente degradada
- **Produção**: Aguardando validação em staging antes de aplicar
- **Build**: Necessário para aplicar correção de header e OTEL
- **Rollback**: Disponível via helm rollback se necessário

---

Documentação criada em: 30/01/2026
Responsável: OpenCode Agent
Status: ✅ Migração de certificados concluída | ⏳ Aguardando build para correções de código
