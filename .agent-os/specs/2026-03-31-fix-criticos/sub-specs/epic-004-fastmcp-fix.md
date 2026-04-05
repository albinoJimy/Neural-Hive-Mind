# EPIC-004: FastMCP API Fix

**ID:** EPIC-004
**Status:** Pending
**Priority:** P0 - Blocker
**Effort:** S (2 dias)
**Related Services:** scout-mcp-server, ai-codegen-mcp-server, sonarqube-mcp-server, trivy-mcp-server

---

## Resumo Executivo

Corrigir incompatibilidade da API FastMCP onde o argumento `description` foi removido e substituído por `instructions`. 4 MCP servers estão inoperantes devido a este erro.

---

## Análise Técnica

### Causa Raiz

O FastMCP mudou sua API entre versões:
- **Versão 0.1.x:** `FastMCP(name, version, description=...)`
- **Versão 3.x:** `FastMCP(name, version, instructions=...)`

O parâmetro `description` foi completamente removido.

### Serviços Afetados

| Service | Arquivo | Linha | Versão FastMCP |
|---------|---------|-------|----------------|
| scout-mcp-server | src/scout_mcp_server/server.py | 21 | >=0.2.0 |
| ai-codegen-mcp-server | src/server.py | 21 | >=0.2.0 |
| sonarqube-mcp-server | src/server.py | 21 | >=0.2.0 |
| trivy-mcp-server | src/server.py | 21 | >=0.2.0 |

**Nota:** optimizer-mcp-server usa `fastmcp==0.1.0` e não tem o problema.

---

## Ticket EPIC-004-01: Fix scout-mcp-server

**ID:** TICKET-EPIC-004-01
**Priority:** P0
**Effort:** XS (2 horas)
**Service:** scout-mcp-server

### Arquivo a Modificar

**services/mcp-servers/scout-mcp-server/src/scout_mcp_server/server.py**

```python
# ANTES (linhas 18-22)
mcp = FastMCP(
    name="Scout MCP Server",
    version=settings.service_version,
    description="Ferramentas de descoberta e análise de código para Scout Agents"
)

# DEPOIS
mcp = FastMCP(
    name="Scout MCP Server",
    version=settings.service_version,
    instructions="Ferramentas de descoberta e análise de código para Scout Agents"
)
```

### Validação

```bash
cd services/mcp-servers/scout-mcp-server
python3 -m src.main  # Verificar se inicia sem erro
```

### Critérios de Aceite
- [ ] Servidor inicia sem erro
- [ ] Ferramentas MCP registradas corretamente
- [ ] Cliente pode conectar e listar ferramentas

---

## Ticket EPIC-004-02: Fix ai-codegen-mcp-server

**ID:** TICKET-EPIC-004-02
**Priority:** P0
**Effort:** XS (2 horas)
**Service:** ai-codegen-mcp-server

### Arquivo a Modificar

**services/mcp-servers/ai-codegen-mcp-server/src/server.py**

```python
# ANTES (linhas 20-23)
mcp = FastMCP(
    "AI Codegen MCP Server",
    version="1.0.0",
    description="Geração e explicação de código via GitHub Copilot e OpenAI"
)

# DEPOIS
mcp = FastMCP(
    "AI Codegen MCP Server",
    version="1.0.0",
    instructions="Geração e explicação de código via GitHub Copilot e OpenAI"
)
```

### Critérios de Aceite
- [ ] Servidor inicia sem erro
- [ ] Ferramentas de codegen funcionando
- [ ] Integração com GitHub/OpenAI mantida

---

## Ticket EPIC-004-03: Fix sonarqube-mcp-server

**ID:** TICKET-EPIC-004-03
**Priority:** P0
**Effort:** XS (2 horas)
**Service:** sonarqube-mcp-server

### Arquivo a Modificar

**services/mcp-servers/sonarqube-mcp-server/src/server.py**

```python
# ANTES (linhas 20-23)
mcp = FastMCP(
    "SonarQube MCP Server",
    version="1.0.0",
    description="Análise de qualidade de código e métricas via SonarQube"
)

# DEPOIS
mcp = FastMCP(
    "SonarQube MCP Server",
    version="1.0.0",
    instructions="Análise de qualidade de código e métricas via SonarQube"
)
```

### Critérios de Aceite
- [ ] Servidor inicia sem erro
- [ ] Métricas SonarQube acessíveis
- [] Análise de qualidade funcionando

---

## Ticket EPIC-004-04: Fix trivy-mcp-server

**ID:** TICKET-EPIC-004-04
**Priority:** P0
**Effort:** XS (2 horas)
**Service:** trivy-mcp-server

### Arquivo a Modificar

**services/mcp-servers/trivy-mcp-server/src/server.py**

```python
# ANTES (linhas 20-24)
mcp = FastMCP(
    "Trivy MCP Server",
    version="1.0.0",
    description="Scanner de vulnerabilidades para containers, filesystems e repositórios"
)

# DEPOIS
mcp = FastMCP(
    "Trivy MCP Server",
    version="1.0.0",
    instructions="Scanner de vulnerabilidades para containers, filesystems e repositórios"
)
```

### Critérios de Aceite
- [ ] Servidor inicia sem erro
- [ ] Scanner de vulnerabilidades funcionando
- [ ] Relatórios Trivy acessíveis

---

## Validação Global

### Script de Teste

```bash
#!/bin/bash
# Testar todos os MCP servers

MCP_SERVERS=(
    "scout-mcp-server"
    "ai-codegen-mcp-server"
    "sonarqube-mcp-server"
    "trivy-mcp-server"
)

for server in "${MCP_SERVERS[@]}"; do
    echo "=== Testing $server ==="
    cd services/mcp-servers/$server

    # Verificar syntax
    python3 -m py_compile src/main.py || exit 1
    python3 -m py_compile src/server.py || exit 1

    # Tentar iniciar (timeout 5s)
    timeout 5 python3 -m src.main || {
        echo "❌ $server failed to start"
        exit 1
    }

    echo "✅ $server OK"
    cd -
done

echo "✅ All MCP servers fixed!"
```

---

## Atualização de Documentação

### requirements.txt padronização

Recomendar fixar versão do FastMCP:

```txt
# Antes
fastmcp>=0.2.0

# Depois
fastmcp>=3.0.0  # API estável com instructions
```

---

## Resumo do Epic

| Ticket | Service | Effort | Linhas Modificadas |
|--------|---------|--------|-------------------|
| EPIC-004-01 | scout-mcp-server | 2h | 1 |
| EPIC-004-02 | ai-codegen-mcp-server | 2h | 1 |
| EPIC-004-03 | sonarqube-mcp-server | 2h | 1 |
| EPIC-004-03 | trivy-mcp-server | 2h | 1 |
| **TOTAL** | **4 serviços** | **8h** | **4 linhas** |

---

## Ordem de Execução

Todos os tickets podem ser executados em **paralelo** pois são independentes.

**Dia 1 (Manhã):**
1. EPIC-004-01 (scout)
2. EPIC-004-02 (ai-codegen)

**Dia 1 (Tarde):**
3. EPIC-004-03 (sonarqube)
4. EPIC-004-04 (trivy)

**Dia 2:**
- Validação global
- Testes de integração
- Documentação

---

## Handoff para Claude Code

Para executar este Epic, use:
```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-004 - FastMCP API Fix
Tickets: EPIC-004-01, EPIC-004-02, EPIC-004-03, EPIC-004-04
Pattern: description → instructions
```

---

## Nota Importante

Esta é a **correção mais simples e rápida** de todos os epics. Apenas 4 linhas precisam ser modificadas (1 por servidor). Recomenda-se executar este Epic primeiro para desbloquear os MCP servers rapidamente.
