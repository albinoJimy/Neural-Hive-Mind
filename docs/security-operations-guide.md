# Security Operations Guide

This document has been organized into more comprehensive security documentation.

## Comprehensive Security Documentation

The security operations documentation has been expanded and organized into specialized guides:

### 🔐 [Security Operations Guide](operations/security-operations.md)
Complete security operations guide with security monitoring, incident response, compliance procedures, and security best practices.

### 🚨 [Security Incident Response](operations/runbook.md#security-incidents)
Security-specific incident response procedures and escalation paths.

### 🔍 [Security Troubleshooting](operations/troubleshooting-guide.md#security-issues)
Troubleshooting procedures for security-related issues and vulnerabilities.

### 📊 [Security Monitoring](operations/monitoring-alerting.md#security-monitoring)
Security monitoring configuration, SIEM integration, and security alerting rules.

## Quick Links

- **Security Incidents**: See [Security Operations](operations/security-operations.md#incident-response)
- **Compliance Checks**: See [Security Operations](operations/security-operations.md#compliance-management)
- **Access Control**: See [Security Operations](operations/security-operations.md#access-control-management)
- **Security Auditing**: See [Security Operations](operations/security-operations.md#security-auditing)
- **Vulnerability Management**: See [Security Operations](operations/security-operations.md#vulnerability-management)

## Key Security Components

### mTLS with SPIFFE/SPIRE

O Neural Hive-Mind implementa **mTLS (mutual TLS)** usando **SPIFFE/SPIRE** para autenticacao e autorizacao de workloads.

#### Arquitetura

- **Camada de Transporte (mTLS)**: Usar X.509-SVID do SPIFFE para autenticacao mutua no handshake TLS
- **Camada de Aplicacao (JWT)**: JWT-SVID em metadata gRPC para autorizacao granular
- **Verificacao de Peer**: Service Registry valida SPIFFE IDs dos clientes via interceptor

#### Componentes

| Componente | Role | SPIFFE ID Pattern |
|------------|------|-------------------|
| **Worker Agent** | gRPC Client | `spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents` |
| **Service Registry** | gRPC Server | `spiffe://neural-hive.local/ns/neural-hive-execution/sa/service-registry` |

---

### SPIFFE/SPIRE mTLS Setup Guide

Esta secao detalha o setup completo de SPIFFE/SPIRE para mTLS no Neural Hive-Mind.

#### Pre-requisitos

1. **SPIRE Server** instalado no cluster (namespace `spire-system`)
2. **SPIRE Agent** rodando como DaemonSet em todos os nodes
3. Kubernetes com suporte a HostPath volumes para o socket do SPIRE Agent

#### Environment Variables e Helm Values

##### Worker Agent

**Environment Variables** (`.env` ou ConfigMap):
```bash
# SPIFFE Configuration
SPIFFE_ENABLED=true
SPIFFE_SOCKET_PATH=unix:///run/spire/sockets/agent.sock
SPIFFE_TRUST_DOMAIN=neural-hive.local
SPIFFE_JWT_AUDIENCE=service-registry.neural-hive.local
SPIFFE_JWT_TTL_SECONDS=3600
SPIFFE_ENABLE_X509=true
ENVIRONMENT=production
```

**Helm Values** (`helm-charts/worker-agents/values.yaml`):
```yaml
spiffe:
  enabled: true
  enableX509: true
  socketPath: "unix:///run/spire/sockets/agent.sock"
  trustDomain: "neural-hive.local"
  jwtAudience: "service-registry.neural-hive.local"
  jwtTtlSeconds: 3600

# Volume mount para SPIRE Agent socket
extraVolumes:
  - name: spire-agent-socket
    hostPath:
      path: /run/spire/sockets
      type: DirectoryOrCreate

extraVolumeMounts:
  - name: spire-agent-socket
    mountPath: /run/spire/sockets
    readOnly: true
```

##### Service Registry

**Environment Variables** (`.env` ou ConfigMap):
```bash
# SPIFFE Configuration
SPIFFE_ENABLED=true
SPIFFE_SOCKET_PATH=unix:///run/spire/sockets/agent.sock
SPIFFE_TRUST_DOMAIN=neural-hive.local
SPIFFE_JWT_AUDIENCE=service-registry.neural-hive.local
SPIFFE_VERIFY_PEER=true
SPIFFE_ENABLE_X509=true
ENVIRONMENT=production
```

**Helm Values** (`helm-charts/service-registry/values.yaml`):
```yaml
spiffe:
  enabled: true
  enableX509: true
  verifyPeer: true
  socketPath: "unix:///run/spire/sockets/agent.sock"
  trustDomain: "neural-hive.local"
  jwtAudience: "service-registry.neural-hive.local"

# Volume mount para SPIRE Agent socket
extraVolumes:
  - name: spire-agent-socket
    hostPath:
      path: /run/spire/sockets
      type: DirectoryOrCreate

extraVolumeMounts:
  - name: spire-agent-socket
    mountPath: /run/spire/sockets
    readOnly: true
```

#### Montagem do Socket do SPIRE Agent

O socket do SPIRE Agent deve ser montado em todos os pods que usam SPIFFE:

```yaml
# Deployment template
spec:
  template:
    spec:
      containers:
        - name: app
          volumeMounts:
            - name: spire-agent-socket
              mountPath: /run/spire/sockets
              readOnly: true
      volumes:
        - name: spire-agent-socket
          hostPath:
            path: /run/spire/sockets
            type: DirectoryOrCreate
```

#### Criacao de Entries no SPIRE Server

Execute os seguintes comandos para criar as entries SPIFFE no SPIRE Server:

```bash
# Entry para Worker Agents
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents \
  -parentID spiffe://neural-hive.local/ns/spire-system/sa/spire-agent \
  -selector k8s:ns:neural-hive-execution \
  -selector k8s:sa:worker-agents \
  -ttl 3600

# Entry para Service Registry
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/neural-hive-execution/sa/service-registry \
  -parentID spiffe://neural-hive.local/ns/spire-system/sa/spire-agent \
  -selector k8s:ns:neural-hive-execution \
  -selector k8s:sa:service-registry \
  -ttl 3600

# Listar entries criadas
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry show
```

**Nota**: Ajuste os seletores (`-selector`) conforme a configuracao do seu cluster.

#### Comandos de Verificacao

##### Verificar SPIRE Agent

```bash
# Status do SPIRE Agent
kubectl exec -n spire-system daemonset/spire-agent -- \
  /opt/spire/bin/spire-agent healthcheck -socketPath /run/spire/sockets/agent.sock

# Listar SVIDs disponiveis
kubectl exec -n neural-hive-execution <worker-pod> -- \
  curl -s --unix-socket /run/spire/sockets/agent.sock \
  http://localhost/v1/spiffe/workload/x509svid | jq .
```

##### Verificar X.509-SVID

```bash
# Buscar X.509-SVID do pod
kubectl exec -n neural-hive-execution <pod-name> -- \
  curl -s --unix-socket /run/spire/sockets/agent.sock \
  -H "Content-Type: application/json" \
  http://localhost/v1/spiffe/workload/x509svid

# Verificar certificado (se openssl disponivel)
kubectl exec -n neural-hive-execution <pod-name> -- \
  sh -c 'curl -s --unix-socket /run/spire/sockets/agent.sock \
  http://localhost/v1/spiffe/workload/x509svid | \
  jq -r ".svids[0].x509_svid" | base64 -d | \
  openssl x509 -text -noout'
```

##### Verificar JWT-SVID

```bash
# Buscar JWT-SVID para audience especifico
kubectl exec -n neural-hive-execution <pod-name> -- \
  curl -s --unix-socket /run/spire/sockets/agent.sock \
  -H "Content-Type: application/json" \
  -d '{"audience": ["service-registry.neural-hive.local"]}' \
  http://localhost/v1/spiffe/workload/jwtsvid

# Decodificar JWT (se jq disponivel)
kubectl exec -n neural-hive-execution <pod-name> -- \
  sh -c 'curl -s --unix-socket /run/spire/sockets/agent.sock \
  -H "Content-Type: application/json" \
  -d '\''{"audience": ["service-registry.neural-hive.local"]}'\'' \
  http://localhost/v1/spiffe/workload/jwtsvid | \
  jq -r ".svids[0].svid" | cut -d"." -f2 | base64 -d 2>/dev/null | jq .'
```

##### Verificar Conexao mTLS

```bash
# Logs do Worker Agent
kubectl logs -n neural-hive-execution <worker-pod> | grep -E "(mtls|spiffe|x509)"

# Logs do Service Registry
kubectl logs -n neural-hive-execution <service-registry-pod> | grep -E "(mtls|spiffe|secure_port)"
```

#### Troubleshooting

##### Problema: UNAUTHENTICATED error

**Causa**: JWT-SVID nao esta sendo enviado ou audience incorreto.

**Solucao**:
```bash
# Verificar se JWT esta sendo buscado
kubectl logs -n neural-hive-execution <worker-pod> | grep jwt_svid

# Verificar audience configurado
kubectl get configmap -n neural-hive-execution worker-agents-config -o yaml | grep -i audience

# Verificar entry no SPIRE Server
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry show -spiffeID spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents
```

##### Problema: SSL handshake failed

**Causa**: X.509-SVID nao disponivel ou socket nao montado.

**Solucao**:
```bash
# Verificar se socket esta montado
kubectl exec -n neural-hive-execution <pod-name> -- ls -la /run/spire/sockets/

# Verificar se SPIRE Agent esta rodando no node
kubectl get pods -n spire-system -o wide | grep spire-agent

# Testar conectividade com socket
kubectl exec -n neural-hive-execution <pod-name> -- \
  curl --unix-socket /run/spire/sockets/agent.sock \
  http://localhost/v1/spiffe/workload/x509svid
```

##### Problema: Server credentials creation failed

**Causa**: SPIFFE_ENABLE_X509 nao esta habilitado no Service Registry.

**Solucao**:
```bash
# Verificar configuracao do Service Registry
kubectl get configmap -n neural-hive-execution service-registry-config -o yaml | grep -i x509

# Deve mostrar:
# SPIFFE_ENABLE_X509: "true"

# Se ausente, atualizar Helm values e fazer upgrade
helm upgrade service-registry ./helm-charts/service-registry \
  --set spiffe.enableX509=true
```

##### Problema: Entry not found for SPIFFE ID

**Causa**: Entry SPIFFE nao criada no SPIRE Server.

**Solucao**:
```bash
# Listar todas as entries
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry show

# Criar entry se ausente (veja secao "Criacao de Entries" acima)
```

##### Problema: Socket permission denied

**Causa**: Permissoes incorretas no HostPath ou securityContext.

**Solucao**:
```yaml
# Adicionar ao deployment se necessario
spec:
  template:
    spec:
      securityContext:
        fsGroup: 1000
      containers:
        - name: app
          securityContext:
            runAsUser: 1000
            runAsGroup: 1000
```

#### Referencias

- [VAULT_SPIFFE_DEPLOYMENT_GUIDE.md](security/VAULT_SPIFFE_DEPLOYMENT_GUIDE.md)
- [VAULT_SPIFFE_OPERATIONS_GUIDE.md](security/VAULT_SPIFFE_OPERATIONS_GUIDE.md)
- [SPIFFE Official Documentation](https://spiffe.io/docs/)
- [SPIRE Quick Start](https://spiffe.io/docs/latest/spire/installing/)

### mTLS and Service Mesh Security (Legacy)
- Configuration details in [Security Operations](operations/security-operations.md#service-mesh-security)
- Troubleshooting in [Troubleshooting Guide](operations/troubleshooting-guide.md#mtls-issues)

### Policy Enforcement
- OPA Gatekeeper policies: [Security Operations](operations/security-operations.md#policy-enforcement)
- Network policies: [Security Operations](operations/security-operations.md#network-security)

### Secret Management
- Secret rotation procedures: [Operational Procedures](operations/operational-procedures.md#secret-rotation)
- Vault integration: [Security Operations](operations/security-operations.md#secret-management)

## Migration Notice

This consolidated document has been reorganized into specialized guides in the `operations/` directory for better maintainability and clearer organization. Please update your references accordingly.

## Emergency Contacts

For security incidents, refer to the escalation matrix in [Security Operations](operations/security-operations.md#escalation-procedures).

---

*For security-related questions or to report security issues, please refer to the documentation in the [operations/](operations/) directory or contact the security team.*