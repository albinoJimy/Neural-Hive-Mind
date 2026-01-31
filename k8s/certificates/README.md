# Migração de Certificados Auto-Assinados para CA Interna

Este diretório contém os recursos necessários para migrar certificados TLS auto-assinados para uma CA (Certificate Authority) interna confiável gerenciada pelo cert-manager.

## 🎯 Objetivo

Substituir certificados auto-assinados (self-signed) por certificados assinados por uma CA interna confiável, eliminando erros de `SSL: CERTIFICATE_VERIFY_FAILED` nos serviços.

## 📁 Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `neural-hive-ca.yaml` | Certificate que cria a CA Root interna |
| `neural-hive-ca-issuer.yaml` | ClusterIssuer que emite certificados usando a CA |
| `schema-registry-tls-updated.yaml` | Certificado do Schema Registry usando a nova CA |
| `distribute-neural-hive-ca.sh` | Script para distribuir a CA aos namespaces |

## 🚀 Como Aplicar

### 1. Criar a CA Root Interna

```bash
kubectl apply -f k8s/certificates/neural-hive-ca.yaml

# Aguardar criação (pode levar alguns segundos)
kubectl wait --for=condition=Ready certificate/neural-hive-ca -n cert-manager --timeout=60s
```

**Verificar:**
```bash
kubectl get certificate neural-hive-ca -n cert-manager
kubectl get secret neural-hive-ca-secret -n cert-manager
```

### 2. Criar o ClusterIssuer

```bash
kubectl apply -f k8s/certificates/neural-hive-ca-issuer.yaml

# Verificar
kubectl get clusterissuer neural-hive-ca-issuer
```

### 3. Re-emitir Certificado do Schema Registry

⚠️ **ATENÇÃO:** Este passo requer restart do Schema Registry (downtime ~30-60s)

```bash
# Backup do secret atual (opcional mas recomendado)
kubectl get secret schema-registry-tls-secret -n kafka -o yaml > /tmp/schema-registry-backup.yaml

# Aplicar novo certificado
kubectl apply -f k8s/certificates/schema-registry-tls-updated.yaml

# Aguardar emissão
kubectl wait --for=condition=Ready certificate/schema-registry-tls -n kafka --timeout=60s

# Verificar que agora tem a CA certa no secret
kubectl get secret schema-registry-tls-secret -n kafka -o jsonpath='{.data.ca\.crt}' | base64 -d | openssl x509 -subject -noout
# Deve mostrar: subject=CN = Neural Hive Internal CA
```

### 4. Distribuir a CA aos Namespaces

```bash
./scripts/distribute-neural-hive-ca.sh
```

Este script cria um ConfigMap `neural-hive-ca-bundle` em cada namespace com o certificado da CA.

### 5. Atualizar o Gateway (Staging)

#### 5.1 Atualizar ConfigMap do Gateway

```bash
# Verificar configuração atual
kubectl get configmap gateway-intencoes-config -n neural-hive-staging -o yaml | grep -A5 schema_registry

# Atualizar para usar o novo CA bundle
kubectl patch configmap gateway-intencoes-config -n neural-hive-staging --type merge -p '{
  "data": {
    "schema_registry_ssl_ca_location": "/etc/ssl/certs/neural-hive-ca.crt"
  }
}'
```

#### 5.2 Atualizar Deployment para Montar o ConfigMap

Editar `helm-charts/gateway-intencoes/values-staging.yaml`:

```yaml
volumes:
  - name: model-cache
    emptyDir: {}
  - name: neural-hive-ca  # NOVO
    configMap:
      name: neural-hive-ca-bundle
      items:
        - key: ca.crt
          path: neural-hive-ca.crt

volumeMounts:
  - name: model-cache
    mountPath: /app/models
  - name: neural-hive-ca  # NOVO
    mountPath: /etc/ssl/certs
    readOnly: true
```

#### 5.3 Aplicar Mudanças

```bash
helm upgrade gateway-intencoes helm-charts/gateway-intencoes \
  -n neural-hive-staging \
  -f helm-charts/gateway-intencoes/values-staging.yaml \
  --wait \
  --timeout=5m
```

### 6. Restart do Schema Registry (Obrigatório)

O Schema Registry (Apicurio/Quarkus) **não suporta hot-reload** de certificados TLS.

```bash
# Restart obrigatório
kubectl rollout restart deployment/apicurio-registry -n kafka

# Aguardar
kubectl wait --for=condition=available deployment/apicurio-registry -n kafka --timeout=120s
```

### 7. Validar

#### 7.1 Verificar Certificado

```bash
# Verificar cadeia de confiança
kubectl get secret schema-registry-tls-secret -n kafka -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -issuer -noout
# Deve mostrar: issuer=CN = Neural Hive Internal CA

# Verificar CA no secret
kubectl get secret schema-registry-tls-secret -n kafka -o jsonpath='{.data.ca\.crt}' | base64 -d | openssl x509 -subject -noout
# Deve mostrar: subject=CN = Neural Hive Internal CA
```

#### 7.2 Testar Conexão do Gateway

```bash
# Acessar pod do gateway
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -it -- bash

# Testar conexão com Schema Registry
openssl s_client -connect schema-registry.kafka.svc.cluster.local:8081 \
  -CAfile /etc/ssl/certs/neural-hive-ca.crt \
  -verify_return_error

# Deve mostrar: Verify return code: 0 (ok)
```

#### 7.3 Verificar Health Check

```bash
# Verificar se gateway consegue se conectar
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- \
  curl -s --cacert /etc/ssl/certs/neural-hive-ca.crt \
  https://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v6/subjects

# Deve retornar lista de subjects (HTTP 200)
```

## ⚠️ Considerações Importantes

### Sem Hot-reload
- O Schema Registry **NÃO** detecta automaticamente quando o certificado é renovado
- Quando o cert-manager renovar (30 dias antes da expiração), será necessário:
  - Restart manual do deployment
  - Ou criar um operator/sidecar para fazer isso automaticamente

### Downtime
- Schema Registry: ~30-60 segundos durante restart
- Gateways: Depende da estratégia de rollout (geralmente < 10s)

### Rotação Automática
O cert-manager renova automaticamente, mas o restart do Schema Registry é manual:
```bash
# Quando o Certificate mostrar "Renewal in progress"
kubectl rollout restart deployment/apicurio-registry -n kafka
```

## 🔧 Troubleshooting

### Erro: "Certificate is not yet ready"
```bash
kubectl describe certificate neural-hive-ca -n cert-manager
# Verificar se selfsigned-cluster-issuer existe
kubectl get clusterissuer
```

### Erro: "Failed to fetch certificate"
```bash
# Verificar logs do cert-manager
kubectl logs -n cert-manager deployment/cert-manager --tail=50
```

### Erro: "SSL certificate verify failed" após migração
```bash
# Verificar se o ConfigMap está montado corretamente
kubectl exec -n neural-hive-staging deployment/gateway-intencoes -- ls -la /etc/ssl/certs/

# Verificar conteúdo do certificado CA
kubectl get configmap neural-hive-ca-bundle -n neural-hive-staging -o jsonpath='{.data.ca\.crt}' | openssl x509 -text -noout | head -10
```

## 📚 Referências

- [cert-manager CA Issuer](https://cert-manager.io/docs/configuration/ca/)
- [cert-manager Certificate](https://cert-manager.io/docs/usage/certificate/)
- [OpenSSL Certificate Verification](https://www.openssl.org/docs/manmaster/man1/openssl-verification.html)

## 📞 Suporte

Se encontrar problemas durante a migração:
1. Verificar logs: `kubectl logs -n cert-manager deployment/cert-manager`
2. Descrever recursos: `kubectl describe certificate <nome> -n <namespace>`
3. Rollback: Restaurar do backup do secret TLS
