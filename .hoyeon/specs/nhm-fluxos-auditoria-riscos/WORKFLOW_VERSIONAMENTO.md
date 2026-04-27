# Workflow de Versionamento e Rastreio — Auditoria NHM

> **Task:** T19 - Estabelecer workflow de versionamento e rastreio
> **Data:** 2026-04-27
> **Versão:** v1.0

---

## 1. Estratégia de Versionamento

### 1.1 Esquema de Versionamento

```
v{MAJOR}.{MINOR}.{PATCH}
```

| Componente | Uso | Exemplo |
|-------------|-----|---------|
| MAJOR | Auditoria completa ou mudança significativa | v1.0 → v2.0 |
| MINOR | Re-auditoria trimestral | v1.0 → v1.1 |
| PATCH | Correcções ou actualizações menores | v1.0 → v1.0.1 |

### 1.2 Ciclo de Vida

```
v1.0 (Draft) → v1.0 (Review) → v1.0 (Approved) → v1.0 (Published)
                                       ↓
                                  v1.0 (Archived)
```

**Estados:**
- **Draft:** Em elaboração, não partilhado
- **Review:** Em revisão por Tech Lead
- **Approved:** Aprovado por CTO/Engineering Manager
- **Published:** Publicado para stakeholders
- **Archived:** Versão antiga, substituída

---

## 2. Estrutura de Directórios

### 2.1 Layout de Ficheiros

```
.hoyeon/specs/nhm-fluxos-auditoria-riscos/
├── requirements.md                          # Requisitos da auditoria
├── plan.json                                # Plano de execução
├── contracts.md                             # Contratos entre módulos
│
├── v1.0/                                    # Versão 1.0 (Abr 2026)
│   ├── RELATORIO_AUDITORIA_V1.md            # Relatório consolidado
│   ├── BASELINE_GAP_ANALYSIS.md             # Baseline de gaps
│   ├── TOP10_RISCOS_PRIORIZADOS.md          # Top-10 riscos
│   ├── TICKETS_ACCIONAVEIS.md               # Tickets JIRA/GitHub
│   ├── RELATORIO_TECH_LEAD.md               # Executivo para Tech Lead
│   ├── CICLO_RE_AUDITORIA.md                # Processo de re-auditoria
│   └── WORKFLOW_VERSIONAMENTO.md            # Este documento
│
├── analysis/                                # Análises técnicas detalhadas
│   ├── ANALISE_ARQUITECTURA.md
│   ├── ANALISE_ESTADO.md
│   ├── ANALISE_OBSERVABILIDADE.md
│   ├── ANALISE_KUBERNETES.md
│   ├── ANALISE_PRIVACIDADE.md
│   ├── ANALISE_COMPATIBILIDADE.md
│   ├── ANALISE_SEGURANCA.md
│   ├── ANALISE_TIMEOUTS.md
│   ├── ANALISE_MENSAGENS.md
│   └── ANALISE_PERFORMANCE.md
│
└── CHANGELOG.md                             # Histórico de mudanças
```

### 2.2 Versionamento de Análises

As análises em `analysis/` são **version-independent** — aplicam a todas as versões até serem actualizadas.

Mudanças em análises específicas devem ser documentadas em `CHANGELOG.md`.

---

## 3. Workflow de Criação de Versão

### 3.1 Checklist Pré-Lançamento

- [ ] Todas as 10 análises técnicas completas
- [ ] Baseline Gap Analysis consolidado
- [ ] Top-10 riscos priorizados
- [ ] Tickets criados para todos os gaps P0
- [ ] Relatório executivo revisado
- [ ] Aprovação do Tech Lead
- [ ] Tag de versão criada

### 3.2 Processo de Lançamento

```bash
# 1. Criar branch de versão
git checkout -b release/auditoria-v1.0

# 2. Criar directório v1.0/
mkdir -p .hoyeon/specs/nhm-fluxos-auditoria-riscos/v1.0

# 3. Copiar relatórios principais
cp RELATORIO_AUDITORIA_V1.md v1.0/
cp BASELINE_GAP_ANALYSIS.md v1.0/
cp TOP10_RISCOS_PRIORIZADOS.md v1.0/
cp TICKETS_ACCIONAVEIS.md v1.0/
cp RELATORIO_TECH_LEAD.md v1.0/

# 4. Actualizar versão nos ficheiros
sed -i 's/v1.0/v1.0/' v1.0/*.md

# 5. Criar tag
git tag -a auditoria-v1.0 -m "Auditoria NHM v1.0 - Abril 2026"

# 6. Push
git push origin release/auditoria-v1.0
git push origin auditoria-v1.0
```

### 3.3 Após Lançamento

```bash
# 7. Merge para main
git checkout main
git merge release/auditoria-v1.0

# 8. Actualizar CHANGELOG.md
# 9. Anunciar via email / Slack
```

---

## 4. Rastreio de Gaps

### 4.1 Identificador de Gap

```
NHM-{DIMENSÃO}-{SEQUÊNCIA}
```

**Dimensões:**
- `ARCH` — Arquitectura
- `PERF` — Performance
- `STATE` — Consistência de Estado
- `MSG` — Mensageria
- `PRIV` — Privacidade
- `K8S` — Kubernetes
- `COMPAT` — Compatibilidade
- `SEC` — Segurança
- `TIMEOUT` — Timeouts
- `OBS` — Observabilidade

**Exemplo:**
```
NHM-MSG-001: DLQ não implementada no consensus-engine
NHM-PRIV-002: PII em plaintext logs
NHM-STATE-003: State divergence Redis→Mongo
```

### 4.2 Ciclo de Vida do Gap

```
ABERTO → EM ANÁLISE → PRIORIZADO → TICKET CRIADO → EM RESOLUÇÃO → RESOLVIDO → VERIFICADO → FECHADO
```

| Estado | Descrição |
|--------|-----------|
| ABERTO | Gap identificado, em análise |
| EM ANÁLISE | Avaliando impacto, esforço, probabilidade |
| PRIORIZADO | Incluído em top-10 ou lista P0-P3 |
| TICKET CRIADO | Ticket JIRA/GitHub criado |
| EM RESOLUÇÃO | Sprint em progresso |
| RESOLVIDO | Implementação completada |
| VERIFICADO | Testes passaram, critérios de aceite cumpridos |
| FECHADO | Gap fechado, monitorização activa |

### 4.3 Rastreio em JIRA

**Epic:** `AUDITORIA-FLUXOS-{VERSÃO}`
**Tickets:** `AUDITORIA-{N}`

**Campos Customizados:**
- `Gap ID`: NHM-XXX-NNN
- `Dimensão`: ARCH, PERF, STATE, etc.
- `Prioridade Score`: 0-180
- `Invariante Violado`: INV-1 até INV-10
- `Versão Auditoria`: v1.0

---

## 5. Matriz de Rastreio

### 5.1 Gap vs Ticket vs Versão

| Gap ID | Descrição | Versão Detectada | Ticket ID | Versão Resolvida | Estado |
|--------|-----------|------------------|-----------|------------------|--------|
| NHM-MSG-001 | DLQ não implementada | v1.0 | AUDITORIA-1 | v1.1 | EM RESOLUÇÃO |
| NHM-PRIV-002 | PII em logs | v1.0 | AUDITORIA-2 | v1.1 | TICKET CRIADO |
| NHM-STATE-003 | State divergence | v1.0 | AUDITORIA-3 | v1.2 | ABERTO |

### 5.2 Dashboard de Rastreio

**Métricas por Versão:**

| Versão | Data | Gaps Detectados | Gaps Resolvidos | % Resolvido | P0 Pendentes |
|--------|------|-----------------|-----------------|-------------|--------------|
| v1.0 | 2026-04-27 | 67 | 0 | 0% | 12 |
| v1.1 | 2026-07-27 | 55 | 12 | 18% | 10 |
| v1.2 | 2026-10-27 | 48 | 19 | 28% | 8 |

---

## 6. Comunicação de Mudanças

### 6.1 CHANGELOG.md

```markdown
# Changelog - Auditoria Neural Hive Mind

## [v1.0] - 2026-04-27

### Adicionado
- Auditoria completa de 9 dimensões
- 67 gaps identificados (12 P0, 23 P1, 21 P2, 11 P3)
- Top-10 riscos priorizados
- Tickets accionáveis NHM-001 até NHM-010
- Relatório executivo para Tech Lead

### Alterado
- N/A (versão inicial)

### Removido
- N/A

## [v1.1] - 2026-07-27 (Planeado)

### Adicionado
- [Gap NHM-XXX: descrição]

### Resolvido
- NHM-001: DLQ implementada
- NHM-002: PII masking integrado
- NHM-004: OpenTelemetry sincronizado
- NHM-005: time.sleep() removido
- NHM-006: TTL indexes criados
- NHM-009: Health checks configurados
```

### 6.2 Release Notes

**Template:**

```markdown
# Neural Hive Mind — Auditoria v{N} Release Notes

**Data:** {DATA}
**Versão:** v{N}
**Tipo:** Completa / Parcial

## Resumo
- {N} gaps identificados
- {N} gaps P0
- {N} invariantes violados

## Novos Gaps Críticos
1. {Gap 1}
2. {Gap 2}

## Gaps Resolvidos
1. {Gap 1} — {Resolução}
2. {Gap 2} — {Resolução}

## Recomendações
1. {Rec 1}

## Próximos Passos
- Sprint {N}: {Descrição}
- Re-auditoria prevista para {DATA}
```

---

## 7. Git Workflow

### 7.1 Branches

| Branch | Propósito | Protegido? |
|--------|-----------|------------|
| `main` | Versão actual publicada | Sim |
| `release/auditoria-v{N}` | Preparação de versão | Não |
| `feat/auditoria-{dimensão}` | Análise de dimensão específica | Não |

### 7.2 Commits

**Convenção de Commit:**

```
[auditoria] <tipo>: <descrição>
```

**Tipos:**
- `analysis`: Nova análise ou actualização
- `gap`: Gap identificado
- `report`: Relatório criado/actualizado
- `docs`: Documentação de processo
- `chore:releasen`: Release preparation

**Exemplos:**
```
[auditoria] analysis: adicionar ANALISE_OBSERVABILIDADE.md
[auditoria] gap: NHM-MSG-001 DLQ não implementada
[auditoria] report: criar RELATORIO_AUDITORIA_V1.md
[auditoria] docs: documentar workflow de versionamento
```

### 7.3 Tags

```bash
# Criar tag de versão
git tag -a auditoria-v1.0 -m "Auditoria NHM v1.0"

# Listar tags
git tag -l "auditoria-*"

# Push tags
git push origin auditoria-v1.0
```

---

## 8. Integração com Ferramentas

### 8.1 JIRA Integration

**Script de Sync:**

```python
# scripts/audit/sync_to_jira.py
import jira

def sync_gaps_to_jira(gaps_file, jira_project):
    gaps = load_gaps(gaps_file)
    jira_client = jira.JIRA(server=JIRA_URL)

    for gap in gaps:
        if gap['ticket_id']:
            continue

        issue = jira_client.create_issue({
            'project': {'key': jira_project},
            'summary': gap['title'],
            'description': gap['description'],
            'issuetype': {'name': 'Bug'},
            'customfield_10000': gap['id'],  # Gap ID
            'priority': map_priority(gap['priority'])
        })

        print(f"Created {issue.key} for {gap['id']}")
```

### 8.2 GitHub Issues

**Template de Issue:**

```markdown
## NHM-XXX-NNN: {Título}

**Dimensão:** {DIMENSÃO}
**Prioridade:** P0/P1/P2/P3
**Score:** {SCORE}
**Versão Detectada:** v{N}

### Descrição
{Descrição detalhada}

### Impacto
- {Impacto técnico}
- {Impacto de negócio}

### Critérios de Aceite
- [ ] {Critério 1}
- [ ] {Critério 2}

### References
- [Relatório v{N}](link)
- [Análise Detalhada](link)
```

---

## 9. Retenção e Arquivo

### 9.1 Política de Retenção

| Artefacto | Retenção | Arquivo |
|-----------|----------|---------|
| Relatórios de Auditoria | 7 anos | Permanente |
| Análises Técnicas | 7 anos | Permanente |
| Tickets JIRA | 7 anos | Export trimestral |
| CHANGELOG | Permanente | Git history |
| Versões Antigas | 7 anos | Tagged no Git |

### 9.2 Arquivo

**Versões anteriores são mantidas em:**
```
.hoyeon/specs/nhm-fluxos-auditoria-riscos/archive/v{N}/
```

**Versão actual sempre em:**
```
.hoyeon/specs/nhm-fluxos-auditoria-riscos/v{N}/
```

---

## 10. Checklist de Execução

### 10.1 Para Nova Versão

- [ ] Actualizar número de versão em todos os ficheiros
- [ ] Revisar CHANGELOG.md
- [ ] Criar tag no Git
- [ ] Copiar artefactos para v{N}/
- [ ] Actualizar dashboard de rastreio
- [ ] Enviar release notes por email
- [ ] Sync tickets para JIRA se aplicável
- [ ] Arquivar versão anterior

### 10.2 Para Re-Auditoria

- [ ] Criar branch `release/auditoria-v{N}`
- [ ] Executar análise de todas as dimensões
- [ ] Consolidar gaps em BASELINE_GAP_ANALYSIS.md
- [ ] Priorizar top-10 riscos
- [ ] Criar tickets accionáveis
- [ ] Gerar relatório executivo
- [ ] Obter aprovação do Tech Lead
- [ ] Publicar v{N}

---

**Documento compilado por:** Orchestrator (Round 2, Task T19)
**Data:** 2026-04-27
**Status:** Todos os tasks concluídos
**Próximo:** Commit final e push
