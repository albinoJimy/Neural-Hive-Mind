# Handoff para Claude Code

## Spec Pronta

A spec **"Completude Gap Correction"** está pronta para execução.

## Localização
```
.agent-os/specs/2026-03-30-completude-gap-correction/
├── spec.md           # Requisitos completos
├── spec-lite.md      # Resumo executivo
├── tasks.md          # Breakdown em tickets (4 epics, 13 tasks)
└── sub-specs/
    └── technical-spec.md  # Detalhes técnicos
```

## Resumo Executivo

**Objetivo:** Elevar completude de 83.5% → ~88%

**Scope:**
1. **Epic A (Crítico):** Corrigir `allowed_hosts: ["*"]` em gateway-intencoes
2. **Epic B:** Criar 2 READMEs (feature-store, software-engineering-pipeline)
3. **Epic C:** Criar 2 Helm charts (feature-store, software-engineering-pipeline)
4. **Epic D:** Validação final

## Como Executar

```bash
# 1. Navegar para o diretório
cd /home/jimy/NHM/Neural-Hive-Mind

# 2. Ler a spec
cat .agent-os/specs/2026-03-30-completude-gap-correction/spec.md

# 3. Ler as tarefas
cat .agent-os/specs/2026-03-30-completude-gap-correction/tasks.md

# 4. Criar branch
git checkout -b feat/completude-gap-correction

# 5. Começar pela Epic A (Crítico)
#    Editar services/gateway-intencoes/src/config/settings.py
```

## Ordem de Execução Recomendada

1. **Epic A** (Segurança Crítica) - 1-2 horas
2. **Epic B** (READMEs) - 2-3 horas
3. **Epic C** (Helm Charts) - 3-4 horas
4. **Epic D** (Validação) - 30 minutos

## Arquivos Críticos a Modificar

### Epic A
- `services/gateway-intencoes/src/config/settings.py`

### Epic B
- `services/feature-store/README.md` (NOVO)
- `services/software-engineering-pipeline/README.md` (NOVO)

### Epic C
- `services/feature-store/helm/` (NOVO - 8 templates + Chart.yaml + values.yaml)
- `services/software-engineering-pipeline/helm/` (NOVO - 8 templates + Chart.yaml + values.yaml)

## Success Criteria

```bash
# Security
grep -r 'allowed_hosts.*\[*\*"\]' services/gateway-intencoes/
# Deve retornar vazio

# Documentation
ls services/*/README.md | wc -l
# Deve retornar 29

# Helm Charts
find services/ -name Chart.yaml | wc -l
# Deve retornar 28
```

## Estimativa de Tempo

| Epic | Estimativa |
|------|------------|
| A | 1-2 horas |
| B | 2-3 horas |
| C | 3-4 horas |
| D | 30 min |
| **Total** | **6-10 horas** |

## Próximos Passos

1. Revisar a spec completa
2. Aprovar plano
3. Iniciar execução pela Epic A
