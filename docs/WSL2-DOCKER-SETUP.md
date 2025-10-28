# 🐳 Guia de Configuração: Docker Desktop + WSL2 + Kubernetes

**Status**: Documentação criada em 2025-10-20
**Ambiente**: Windows 11 + WSL2 Ubuntu-22.04
**Docker Desktop**: v28.5.1
**Kubernetes**: v1.32.2

---

## 📋 Sumário Executivo

Atualmente, o Docker Desktop e Kubernetes estão **funcionando no Windows**, mas a integração com WSL2 não está ativa. Você tem **duas opções**:

1. **Solução Permanente** (Recomendada): Habilitar integração WSL2 no Docker Desktop
2. **Solução Temporária**: Usar scripts de link simbólico (precisa refazer após reiniciar)

---

## ✅ SOLUÇÃO PERMANENTE (Recomendada)

### Método 1: Interface Gráfica do Docker Desktop

#### Passo 1: Abrir Docker Desktop
1. Clique no ícone do **Docker Desktop** na bandeja do Windows
2. Aguarde até o ícone ficar **verde** (Docker totalmente iniciado)

#### Passo 2: Acessar Settings
1. Clique no ícone de **engrenagem** (⚙️) no canto superior direito
2. Ou use o menu: **Settings**

#### Passo 3: Habilitar Integração WSL2
1. No menu lateral esquerdo: **Resources** → **WSL Integration**
2. Marque as seguintes opções:

```
┌──────────────────────────────────────────────────────┐
│ ✅ Enable integration with my default WSL distro    │
│                                                       │
│ Enable integration with additional distros:          │
│                                                       │
│ ✅ Ubuntu-22.04                                      │
│ ☐  docker-desktop (não marcar)                      │
│ ☐  docker-desktop-data (não marcar)                 │
└──────────────────────────────────────────────────────┘
```

#### Passo 4: Aplicar e Reiniciar
1. Clique em **Apply & Restart** (canto inferior direito)
2. Aguarde 1-2 minutos para o Docker reiniciar
3. Verifique se o ícone fica verde novamente

#### Passo 5: Testar no WSL2
Abra o terminal WSL2 e execute:

```bash
# Teste Docker
docker ps

# Teste Kubernetes
kubectl get nodes

# Deve mostrar:
# NAME             STATUS   ROLES           AGE   VERSION
# docker-desktop   Ready    control-plane   92d   v1.32.2
```

Se funcionar, **você terminou!** ✅

---

### Método 2: Linha de Comando (PowerShell como Administrador)

```powershell
# 1. Parar Docker Desktop e WSL2
wsl --shutdown
Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue

# 2. Modificar settings.json
$settingsPath = "$env:APPDATA\Docker\settings.json"
$settings = Get-Content $settingsPath | ConvertFrom-Json

# Habilitar integração WSL2
$settings.integratedWslDistros = @("Ubuntu-22.04")
$settings.enableIntegrationWithDefaultWslDistro = $true

# Salvar configuração
$settings | ConvertTo-Json -Depth 10 | Set-Content $settingsPath

# 3. Reiniciar Docker Desktop
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# 4. Aguardar 30 segundos
Start-Sleep -Seconds 30

# 5. Testar
wsl -d Ubuntu-22.04 docker ps
```

---

## ⚡ SOLUÇÃO TEMPORÁRIA (Link Simbólico)

Se você precisa usar Docker/Kubectl **AGORA** no WSL2, mas não quer mexer nas configurações do Docker Desktop:

### Passo 1: Garantir que Docker Desktop está rodando

No Windows, abra o Docker Desktop e aguarde ficar verde.

### Passo 2: Executar script no WSL2

```bash
# Executar script de configuração temporária
bash /tmp/link-docker-socket.sh
```

Este script irá:
- Criar link simbólico `/var/run/docker.sock`
- Copiar configuração kubectl
- Testar conexões

### Passo 3: Testar

```bash
docker ps
kubectl get nodes
```

### ⚠️ Limitações da Solução Temporária

Você precisará **executar o script novamente** após:
- Reiniciar o WSL2 (`wsl --shutdown`)
- Reiniciar o computador
- Reiniciar o Docker Desktop

**Por isso a solução permanente é recomendada!**

---

## 🔍 Diagnóstico e Troubleshooting

### Script de Diagnóstico Completo

Execute para verificar o status de tudo:

```bash
bash /tmp/diagnose-docker-wsl2.sh
```

Este script verifica:
- ✅ Docker Desktop no Windows
- ✅ Integração WSL2
- ✅ Sockets e links simbólicos
- ✅ Kubernetes cluster
- ✅ Configurações e contextos

---

### Problemas Comuns

#### ❌ "Cannot connect to Docker daemon"

**Causa**: Docker Desktop não está rodando ou integração WSL2 desabilitada

**Solução**:
1. Abra Docker Desktop no Windows
2. Aguarde ícone verde
3. Verifique Settings → Resources → WSL Integration
4. Se necessário, use solução temporária

---

#### ❌ "Connection refused localhost:8080" (kubectl)

**Causa**: Kubeconfig não está configurado no WSL2

**Solução**:
```bash
# Copiar config do Windows
mkdir -p ~/.kube
cp /mnt/c/Users/armando.albino/.kube/config ~/.kube/config
chmod 600 ~/.kube/config

# Testar
kubectl get nodes
```

---

#### ❌ "Permission denied" ao executar docker

**Causa**: Usuário não está no grupo docker

**Solução**:
```bash
# Adicionar ao grupo
sudo usermod -aG docker $USER

# Fazer logout/login
exit
# Abrir novo terminal WSL2
```

---

#### ⚠️ Integração WSL2 não aparece nas Settings

**Causa**: Docker Desktop não está usando WSL2 backend

**Solução**:
1. Settings → General
2. Verificar: "Use the WSL 2 based engine" está marcado
3. Apply & Restart

---

## 📊 Arquivos e Scripts Criados

### Documentação
- 📄 [`/tmp/setup-docker-wsl2.md`](file:///tmp/setup-docker-wsl2.md) - Guia completo
- 📄 [`/home/jimy/Base/Neural-Hive-Mind/docs/WSL2-DOCKER-SETUP.md`](file:///home/jimy/Base/Neural-Hive-Mind/docs/WSL2-DOCKER-SETUP.md) - Este arquivo

### Scripts
- 🔧 [`/tmp/link-docker-socket.sh`](file:///tmp/link-docker-socket.sh) - Solução temporária
- 🔍 [`/tmp/diagnose-docker-wsl2.sh`](file:///tmp/diagnose-docker-wsl2.sh) - Diagnóstico completo

### Uso dos Scripts

```bash
# Solução temporária (criar links)
bash /tmp/link-docker-socket.sh

# Diagnóstico completo
bash /tmp/diagnose-docker-wsl2.sh

# Ver guia completo
cat /tmp/setup-docker-wsl2.md
```

---

## 🎯 Comandos Úteis Após Configuração

### Docker
```bash
# Listar containers
docker ps

# Listar imagens
docker images

# Ver logs
docker logs <container-id>

# Executar comando em container
docker exec -it <container-id> bash
```

### Kubernetes
```bash
# Verificar cluster
kubectl cluster-info

# Listar nodes
kubectl get nodes

# Listar todos os pods
kubectl get pods --all-namespaces

# Pods do Neural Hive
kubectl get pods -n neural-hive-mind

# Logs de um pod
kubectl logs -n neural-hive-mind <pod-name>

# Descrever pod (para debug)
kubectl describe pod -n neural-hive-mind <pod-name>
```

### Contextos
```bash
# Ver contexto Docker atual
docker context ls

# Ver contexto Kubernetes atual
kubectl config current-context

# Listar todos os contextos
kubectl config get-contexts
```

---

## 📚 Referências

- [Docker Desktop WSL2 Documentation](https://docs.docker.com/desktop/wsl/)
- [Kubernetes on Docker Desktop](https://docs.docker.com/desktop/kubernetes/)
- [WSL2 Best Practices](https://docs.microsoft.com/en-us/windows/wsl/best-practices)

---

## ✨ Status Atual do Ambiente

Após configurar a integração WSL2, você terá:

| Componente | Status | Versão |
|------------|--------|--------|
| Docker Desktop | ✅ Funcionando | 28.5.1 |
| Kubernetes | ✅ Ativo | v1.32.2 |
| Namespaces | ✅ 44 criados | - |
| Pods rodando | ✅ ~110 de 120 | - |
| Infraestrutura | ✅ MongoDB, Kafka, Redis | - |
| Istio Service Mesh | ✅ Completo | - |
| Neural Hive Agents | ✅ 10/10 | - |
| **Specialists** | 🔴 **10/10 falhando** | v1.0.0-1759844589 |

### ⚠️ Problema Conhecido: Specialists em CrashLoopBackOff

**Erro**: `ModuleNotFoundError: No module named 'structlog'`

**Próximo passo**: Corrigir imagens Docker dos specialists (adicionar `structlog` ao requirements.txt)

---

**Última atualização**: 2025-10-20
**Criado por**: Claude Code
**Para**: Neural Hive Mind Project
