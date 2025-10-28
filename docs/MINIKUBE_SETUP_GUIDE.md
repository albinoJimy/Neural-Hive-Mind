# Guia de Configuração do Minikube

Este guia orienta a configuração de um ambiente de desenvolvimento local Minikube para o projeto Neural Hive-Mind.

## Pré-requisitos

Antes de começar, certifique-se de ter os seguintes componentes instalados no seu sistema:

### Ferramentas Necessárias

- **Docker** (versão estável mais recente)
  - macOS: [Docker Desktop para Mac](https://docs.docker.com/desktop/install/mac-install/)
  - Linux: [Docker Engine](https://docs.docker.com/engine/install/)
  - Windows: [Docker Desktop para Windows](https://docs.docker.com/desktop/install/windows-install/)

- **Minikube** (v1.30.0+)
  ```bash
  # macOS
  brew install minikube

  # Linux
  curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
  sudo install minikube-linux-amd64 /usr/local/bin/minikube

  # Windows (PowerShell como Administrador)
  choco install minikube
  ```

- **kubectl** (v1.29.0+)
  ```bash
  # macOS
  brew install kubectl

  # Linux
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  sudo install kubectl /usr/local/bin/kubectl

  # Windows (PowerShell como Administrador)
  choco install kubernetes-cli
  ```

- **yq** (processador YAML, v4.0+)
  ```bash
  # macOS
  brew install yq

  # Linux
  wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/local/bin/yq
  chmod +x /usr/local/bin/yq

  # Windows (PowerShell como Administrador)
  choco install yq
  ```

- **envsubst** (geralmente incluído no gettext)
  ```bash
  # macOS
  brew install gettext
  brew link --force gettext

  # Linux (Debian/Ubuntu)
  sudo apt-get install gettext

  # Linux (RHEL/CentOS)
  sudo yum install gettext

  # Windows (Git Bash inclui envsubst)
  ```

### Requisitos de Sistema

- **CPU**: 4+ núcleos recomendados
- **Memória**: 8GB+ RAM disponível
- **Disco**: 20GB+ espaço livre
- **SO**: macOS 11+, Ubuntu 20.04+, Windows 10+ (com WSL2)

### Verificar Instalações

```bash
docker --version          # Docker version 20.10+
minikube version          # minikube version v1.30.0+
kubectl version --client  # Client Version: v1.29.0+
yq --version             # yq version 4.0+
envsubst --version       # envsubst (GNU gettext) 0.19+
```

## Configuração Automatizada

A maneira mais fácil de configurar seu ambiente Minikube é usando o script de configuração automatizado:

```bash
# Da raiz do projeto
make minikube-setup
```

Este comando irá:
1. Iniciar o Minikube com alocação apropriada de recursos
2. Habilitar addons necessários (ingress, metrics-server, storage-provisioner, registry)
3. Aplicar manifests de bootstrap (namespaces, RBAC, network policies, etc.)
4. Executar verificações de validação

### Configuração Limpa

Se precisar começar do zero:

```bash
# Deletar cluster existente e configurar um novo
make minikube-reset
```

## Passos de Configuração Manual

Se preferir configurar manualmente ou precisar solucionar problemas:

### Passo 1: Iniciar Minikube

```bash
minikube start \
  --driver=docker \
  --cpus=4 \
  --memory=8192 \
  --disk-size=20g \
  --kubernetes-version=v1.29.0
```

### Passo 2: Habilitar Addons

```bash
minikube addons enable ingress
minikube addons enable metrics-server
minikube addons enable storage-provisioner
minikube addons enable registry
```

### Passo 3: Verificar Cluster

```bash
kubectl cluster-info
kubectl get nodes
```

Saída esperada:
```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   1m    v1.29.0
```

### Passo 4: Aplicar Manifests de Bootstrap

```bash
export ENVIRONMENT=local
./scripts/deploy/apply-bootstrap-manifests.sh
```

Isso criará:
- Namespaces Neural Hive (cognition, orchestration, execution, observability, system)
- Namespaces de segurança (cosign-system, gatekeeper-system, cert-manager)
- Namespace auth
- Roles e bindings RBAC
- Network policies
- Resource quotas e limit ranges
- CRDs de governança de dados

### Passo 5: Validar Bootstrap

```bash
./scripts/validation/validate-bootstrap-phase.sh
```

Todas as verificações devem passar antes de prosseguir para deploy de serviços.

## Checklist de Validação

Após a configuração, verifique o seguinte:

- [ ] Minikube está executando (`minikube status`)
- [ ] kubectl pode conectar (`kubectl cluster-info`)
- [ ] Todos os addons necessários estão habilitados (`minikube addons list`)
- [ ] Todos os namespaces existem (`kubectl get namespaces`)
- [ ] Network policies estão aplicadas (`kubectl get networkpolicies -A`)
- [ ] Resource quotas estão configurados (`kubectl get resourcequotas -A`)
- [ ] CRDs estão instalados (`kubectl get crds | grep neural-hive`)
- [ ] Validação de bootstrap passa (`./scripts/validation/validate-bootstrap-phase.sh`)

## Solução de Problemas

### Minikube Não Inicia

**Problema**: Minikube falha ao iniciar com erros de driver

**Solução**:
```bash
# Verificar se Docker está executando
docker ps

# Deletar cluster existente e tentar novamente
minikube delete
minikube start --driver=docker --cpus=4 --memory=8192
```

### Recursos Insuficientes

**Problema**: Node mostra condições de pressão ou pods estão pendentes

**Solução**:
```bash
# Aumentar recursos do Minikube
minikube delete
minikube start --driver=docker --cpus=6 --memory=12288 --disk-size=30g
```

### Instalação de Addon Falha

**Problema**: Addons falham ao habilitar

**Solução**:
```bash
# Verificar status do addon
minikube addons list

# Desabilitar e re-habilitar
minikube addons disable <addon-name>
minikube addons enable <addon-name>

# Verificar pods do addon
kubectl get pods -n kube-system
kubectl get pods -n ingress-nginx
```

### Erros em Bootstrap Manifest

**Problema**: apply-bootstrap-manifests.sh falha com erros de placeholder

**Solução**:
```bash
# Verificar se config de ambiente existe
cat environments/local/bootstrap-config.yaml

# Executar em modo dry-run para inspecionar manifests gerados
DRY_RUN=true ./scripts/deploy/apply-bootstrap-manifests.sh

# Verificar os arquivos gerados em .tmp/bootstrap-dry-run/
```

### Problemas com Network Policy

**Problema**: Pods não conseguem se comunicar após network policies serem aplicadas

**Solução**:
```bash
# Verificar network policies
kubectl get networkpolicies -A

# Temporariamente desabilitar para debug (não recomendado para produção)
# Editar environments/local/bootstrap-config.yaml:
# local_network_policies_default_deny: "false"
```

### Avisos de Instalação de CRD

**Problema**: Avisos sobre CRDs ausentes durante bootstrap

**Solução**: Estes avisos são esperados na fase de bootstrap. CRDs para governança de dados são opcionais nesta etapa e serão usados em fases posteriores de deployment.

### Conflitos de Porta

**Problema**: Minikube reporta porta já em uso

**Solução**:
```bash
# Verificar o que está usando a porta
lsof -i :8443  # ou outra porta em conflito

# Parar serviço conflitante ou usar portas diferentes
minikube start --apiserver-port=8444
```

### Problemas Específicos do macOS

**Problema**: Comandos sed falham no macOS

**Solução**: Os scripts são projetados para detectar macOS e usar sintaxe sed compatível. Se ainda encontrar problemas:
```bash
# Instalar GNU sed
brew install gnu-sed
# Adicionar ao PATH em ~/.zshrc ou ~/.bash_profile
export PATH="/usr/local/opt/gnu-sed/libexec/gnubin:$PATH"
```

## Próximos Passos

Após configurar com sucesso o Minikube e validar a fase de bootstrap:

1. **Deployar Serviços de Infraestrutura**
   - Seguir os guias de deployment para Kafka, MongoDB, Neo4j, Redis
   - Ver `docs/DEPLOYMENT_GUIDE.md` para configuração de infraestrutura

2. **Deployar Serviços de Aplicação**
   - Deployar specialists (behavior, business, evolution, technical)
   - Deployar componentes de orchestration
   - Deployar serviços de execution

3. **Acessar Serviços**
   ```bash
   # Obter IP do Minikube
   minikube ip

   # Acessar via Ingress
   # Adicionar entradas em /etc/hosts se necessário
   ```

4. **Monitorar o Cluster**
   ```bash
   # Abrir dashboard do Kubernetes
   make minikube-dashboard

   # Verificar status do cluster
   make minikube-status
   ```

5. **Workflow de Desenvolvimento**
   ```bash
   # Ver logs
   kubectl logs -f <pod-name> -n <namespace>

   # Executar comandos em pods
   kubectl exec -it <pod-name> -n <namespace> -- /bin/bash

   # Port forward para acesso local
   kubectl port-forward -n <namespace> <pod-name> 8080:8080
   ```

## Referência de Comandos Úteis

```bash
# Iniciar/Parar Minikube
make minikube-start
make minikube-stop

# Limpeza
make minikube-clean      # Deletar cluster
make minikube-reset      # Limpar e configurar novo

# Status e Monitoramento
make minikube-status     # Mostrar status
make minikube-logs       # Mostrar logs
make minikube-dashboard  # Abrir dashboard

# Gerenciamento de Bootstrap
make bootstrap-apply     # Aplicar manifests
make bootstrap-validate  # Executar validação

# Acesso direto kubectl
kubectl get all -A                           # Todos os recursos
kubectl get namespaces                       # Todos os namespaces
kubectl get pods -n neural-hive-cognition   # Pods em namespace
kubectl describe pod <pod-name> -n <ns>     # Detalhes do pod
kubectl logs <pod-name> -n <ns>             # Logs do pod
```

## Recursos Adicionais

- [Documentação Minikube](https://minikube.sigs.k8s.io/docs/)
- [Documentação Kubernetes](https://kubernetes.io/docs/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- Documentação do Projeto Neural Hive-Mind: `docs/`

## Suporte

Se encontrar problemas não cobertos neste guia:

1. Verificar o relatório de validação: `.tmp/bootstrap-validation-report.json`
2. Revisar logs do Minikube: `make minikube-logs`
3. Examinar logs dos pods: `kubectl logs <pod-name> -n <namespace>`
4. Consultar o README.md principal para orientações específicas do projeto
