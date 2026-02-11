# Setup Local Runner para CI/CD

Este workflow configura automaticamente um GitHub Actions Runner na sua máquina local.

## Pré-requisitos

1. **Docker instalado** na máquina local
2. **Acesso SSH** à máquina local
3. **GitHub PAT** (Personal Access Token)

## Configurar Secrets no GitHub

Vá até: `https://github.com/jimysoares76/Neural-Hive-Mind/settings/secrets/actions`

E adicione:

| Secret | Descrição |
|---------|-------------|
| `SSH_KEY` | Sua chave SSH privada (conteúdo de `~/.ssh/id_rsa` ou `id_ed25519`) |
| `GITHUB_TOKEN` | Personal Access Token do GitHub com scopes: `repo`, `workflow`, `admin:org` |

## Como Usar

### Via GitHub UI (Mais Fácil)

1. Vá até: `https://github.com/jimysoares76/Neural-Hive-Mind/actions/workflows/setup-local-runner.yml`
2. Clique em: **"Run workflow"**
3. Preencha:
   - **ssh_host**: IP ou hostname da sua máquina (ex: `192.168.1.100` ou `vmi3075398`)
   - **ssh_user**: Seu usuário (ex: `jimy`)
   - **runner_name**: (opcional) Nome do runner, padrão: `local-neural-hive-runner`
4. Clique em **"Run workflow"** (botão verde)

### Via CLI (gh)

```bash
gh workflow run setup-local-runner.yml \
  -f ssh_host=192.168.1.100 \
  -f ssh_user=jimy
  -f runner_name=local-neural-hive-runner
```

## O que o workflow faz

1. Conecta via SSH na sua máquina
2. Verifica/instala Docker
3. Baixa o GitHub Actions Runner (v2.319.1)
4. Configura com label `neural-hive`
5. Instala como serviço (persistente)

## Verificar Runner Depois

Vá até: `https://github.com/jimysoares76/Neural-Hive-Mind/settings/actions/runners`

Você deve ver:
- **local-neural-hive-runner** com ícone verde 🟢

## Troubleshooting

### Runner aparece com ícone cinza (offline)
```bash
# Na máquina local:
cd ~/actions-runner
./svc.sh status
sudo ./svc.sh start
```

### Erro de permissão Docker
```bash
# Adicione seu usuário ao grupo docker
sudo usermod -aG docker $USER
# Faça logout e login novamente
newgrp docker
```

### Remover runner (se necessário)
```bash
cd ~/actions-runner
./config.sh remove --token $GITHUB_TOKEN
```

## Workflows que usam este runner

Todos os workflows com `runs-on: [self-hosted, neural-hive]` usarão este runner:

- build-gateway.yml
- test-specialists.yml
- ml-integration-tests.yml
- performance-test.yml
- online-learning-pipeline.yml
- dependency-audit.yml
- test-mcp-tool-catalog.yml
- validate-*.yml
