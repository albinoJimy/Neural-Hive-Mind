# 🧠 Neural Hive Mind - Obsidian Vault

Bem-vindo ao vault do projeto Neural Hive Mind no Obsidian.

## 📁 Estrutura do Vault

```
docs/
├── obsidian/           # Notas e documentação no Obsidian
│   ├── 00-INICIO.md   # Este arquivo
│   ├── arquitetura/   # Notas sobre arquitetura
│   ├── specs/         # Especificações e requisitos
│   ├── reuniões/      # Notas de reuniões
│   └── tarefas/       # Tarefas e tracking
├── specs/             # Especificações formais
└── api/               # Documentação de APIs
```

## 🔗 Links Rápidos

- [[README]] - Documentação principal do projeto
- [[CLAUDE]] - Instruções para agentes de IA
- [[ARQUITETURA]] - Visão geral da arquitetura

## 🚀 Início Rápido

### Atalhos Úteis

| Atalho | Ação |
|--------|------|
| `Cmd+P` | Command Palette |
| `Cmd+G` | Grafo de conhecimento |
| `Cmd+[` | Toggle sidebar esquerda |
| `Cmd+]` | Toggle sidebar direita |

### Plugins Recomendados

1. **Dataview** - Queries em Markdown
2. **Excalidraw** - Diagramas visuais
3. **Kanban** - Quadros de tarefas
4. **Obsidian Git** - Sincronização com Git
5. **Templater** - Templates de notas
6. **Advanced Tables** - Tabelas avançadas

## 📊 Consultas Dataview

```dataview
TABLE file.ctime as "Criado", file.mtime as "Modificado"
FROM "docs/obsidian"
SORT file.mtime DESC
```

## 🏷️ Tags Principais

- #arquitetura - Design e arquitetura
- #especialista - Agentes especialistas
- #fluxo - Fluxos de trabalho
- #gaps - Gaps de implementação
- #deploy - Deploy e CI/CD
- #reunião - Notas de reuniões

---

*Última atualização: 2026-05-03*
