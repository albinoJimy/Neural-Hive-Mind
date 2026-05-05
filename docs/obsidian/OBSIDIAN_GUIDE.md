# 📓 Guia do Obsidian - Neural Hive Mind

Este guia explica como usar o Obsidian com o projeto Neural Hive Mind.

## 🚀 Configuração Inicial

### 1. Abrir o Vault no Obsidian

1. Abra o Obsidian
2. Clique em "Abrir pasta como vault"
3. Navegue até: `/home/jimy/NHM/Neural-Hive-Mind`
4. O Obsidian detectará automaticamente a configuração em `.obsidian/`

### 2. Instalar Plugins Recomendados

Vá em **Configurações → Plugins de Comunidade** e procure por:

| Plugin | Propósito |
|--------|-----------|
| **Dataview** | Queries em Markdown |
| **Excalidraw** | Diagramas e desenhos |
| **Kanban** | Quadros de tarefas estilo Trello |
| **Obsidian Git** | Sincronização com Git |
| **Templater** | Templates avançados |
| **Advanced Tables** | Edição fácil de tabelas |
| **CM Editor Syntax Highlight** | Syntax highlighting em code blocks |
| **Tag Wrangler** | Gerenciamento de tags |
| **Homepage** | Página inicial do vault |

## 📁 Estrutura de Notas

```
docs/obsidian/
├── 00-INICIO.md              # Página inicial do vault
├── OBSIDIAN_GUIDE.md         # Este arquivo
├── arquitetura/              # Notas sobre arquitetura
│   ├── cognitive-pipeline.md
│   ├── agentes.md
│   └── servicoregistry.md
├── specs/                    # Especificações e requisitos
│   ├── gaps-pendentes.md
│   └── roadmap.md
├── reunioes/                 # Notas de reuniões
│   └── 2026-05-03-daily.md
├── tarefas/                  # Tracking de tarefas
│   └── kanban.md
└── templates/                # Templates para novas notas
    ├── template-reuniao.md
    ├── template-ticket.md
    └── template-arquitetura.md
```

## 🏷️ Sistema de Tags

Use estas tags padronizadas:

| Tag | Uso |
|-----|-----|
| `#arquitetura` | Design e arquitetura |
| `#especialista` | Agentes especialistas |
| `#fluxo` | Fluxos de trabalho |
| `#gaps` | Gaps de implementação |
| `#deploy` | Deploy e CI/CD |
| `#reunião` | Notas de reuniões |
| `#bug` | Bugs e problemas |
| `#idea` | Ideias e sugestões |
| `#status/proposta` | Status: proposto |
| `#status/em-progresso` | Status: em andamento |
| `#status/concluido` | Status: concluído |
| `#prioridade/alta` | Prioridade: alta |
| `#prioridade/media` | Prioridade: média |
| `#prioridade/baixa` | Prioridade: baixa |

## 🔗 Links Úteis

- [[00-INICIO]] - Página inicial do vault
- [[../README.md]] - README principal do projeto
- [[../CLAUDE.md]] - Instruções para agentes de IA
- [[../MEMORY.md]] - Memória do projeto

## 💡 Dicas de Uso

### Criar Nova Nota a Partir de Template

1. Pressione `Cmd+P` para abrir a Command Palette
2. Digite "Templater: Create new note from template"
3. Selecione o template desejado

### Consultas Dataview Úteis

**Todas as notas modificadas recentemente:**
```dataview
TABLE file.ctime as "Criado", file.mtime as "Modificado"
FROM "docs/obsidian"
SORT file.mtime DESC
LIMIT 10
```

**Todas as tarefas por status:**
```dataview
TASK
FROM "docs/obsidian/tarefas"
GROUP BY status
```

**Reuniões do último mês:**
```dataview
LIST
FROM "docs/obsidian/reunioes"
WHERE file.ctime >= date(today) - dur(30 days)
SORT file.ctime DESC
```

### Sincronização com Git

Com o plugin **Obsidian Git** instalado:

1. Vá em **Configurações → Obsidian Git**
2. Configure:
   - **Auto-save interval:** 5 minutos
   - **Auto-commit interval:** 15 minutos
   - **Auto-push interval:** 30 minutos
3. Use `Cmd+P` → "Git: Commit all changes" para commits manuais

## 🎨 Personalização

### Trocar Tema

1. Vá em **Configurações → Aparência**
2. Temas recomendados:
   - **Minimal** - Limpo e minimalista
   - **Things** - Inspirado no Things app
   - **AnuPpuccin** - Tema pastel moderno

### Configurar Fonte

1. Vá em **Configurações → Fontes**
2. Fonte monospace recomendada: **JetBrains Mono** ou **Fira Code**

---

**Dúvidas?** Consulte a [documentação oficial do Obsidian](https://help.obsidian.md)
