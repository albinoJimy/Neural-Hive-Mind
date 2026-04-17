# Mermaid CLI Setup Guide

> Guia de instalação e configuração do Mermaid CLI (mmdc) para geração de diagramas.

---

## Visão Geral

O **architect-agent** utiliza o **Mermaid CLI** (`mmdc`) para renderizar diagramas Mermaid para SVG. Esta ferramenta é necessária para a funcionalidade de geração de diagramas arquiteturais.

---

## Instalação

### Opção 1: Via NPM (Recomendado)

```bash
npm install -g @mermaid-js/mermaid-cli
```

### Opção 2: Via Docker

```bash
docker pull ghcr.io/mermaid-js/mermaid-cli/latest
```

---

## Verificar Instalação

```bash
mmdc --version
```

Expected output: `@mermaid-js/mermaid-cli/x.x.x`

---

## Configuração

### Variáveis de Ambiente

O serviço espera as seguintes variáveis de ambiente (opcional):

```bash
# Caminho para o executável mmdc (se não no PATH)
MERMAID_CLI_PATH=/usr/local/bin/mmdc

# Timeout para renderização (ms)
MERMAID_RENDER_TIMEOUT=30000
```

### Configuração do Serviço

No `src/config/settings.py`:

```python
# Mermaid CLI configuration
mermaid_cli_path: str = Field(
    default="mmdc",
    description="Caminho para o executável mmdc"
)
mermaid_timeout_ms: int = Field(
    default=30000,
    description="Timeout para renderização em ms"
)
```

---

## Dockerfile

O `Dockerfile` já inclui a instalação do Mermaid CLI:

```dockerfile
# Instalar Node.js e Mermaid CLI
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @mermaid-js/mermaid-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
```

---

## Uso

### Via API REST

```bash
curl -X POST "http://localhost:8008/api/v1/architecture/diagrams/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "User -> API -> Database",
    "diagram_type": "c4_context"
  }'
```

### Via Código Python

```python
from src.generators.mermaid_renderer import MermaidRenderer

renderer = MermaidRenderer()

# Gerar SVG
svg_content = await renderer.render_to_svg(
    mermaid_code="graph TD\nA[User] --> B[API]"
)

# Gerar PNG (opcional)
png_content = await renderer.render_to_png(
    mermaid_code="graph TD\nA[User] --> B[API]"
)
```

---

## Troubleshooting

### mmdc: command not found

**Solução:**
1. Verificar instalação: `which mmdc`
2. Adicionar ao PATH ou configurar `MERMAID_CLI_PATH`

### Timeout ao renderizar diagramas complexos

**Solução:**
Aumentar `MERMAID_RENDER_TIMEOUT` ou simplificar diagrama

### Erro de permissão no Docker

**Solução:**
```dockerfile
RUN npm install -g --unsafe-perm @mermaid-js/mermaid-cli
```

---

## Performance

| Tamanho do Diagrama | Tempo de Renderização |
|---------------------|----------------------|
| Pequeno (<20 nós)   | ~1-2 segundos |
| Médio (20-50 nós)   | ~3-5 segundos |
| Grande (>50 nós)    | ~5-10 segundos |

---

## Alternativas

Se o Mermaid CLI não estiver disponível, o serviço pode retornar o código Mermaid bruto para renderização no client-side:

```json
{
  "diagram_id": "diag-123",
  "type": "c4_context",
  "mermaid_code": "graph TD\nA[User] --> B[System]",
  "svg_url": null
}
```

O client pode então usar bibliotecas como:
- `mermaid.js` (browser)
- `react-mermaid` (React)
- `vue-mermaid` (Vue)

---

## Referências

- [Mermaid CLI Documentation](https://github.com/mermaid-js/mermaid-cli)
- [Mermaid Syntax](https://mermaid.js.org/intro/)
- [C4 Model with Mermaid](https://mermaid.js.org/syntax/c4)

---

**Última atualização:** 2026-04-17
**Versão:** 1.0.0
