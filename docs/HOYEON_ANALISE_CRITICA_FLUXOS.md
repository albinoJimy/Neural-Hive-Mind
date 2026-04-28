# Análise Crítica dos Fluxos NHM com `hoyeon`

> Guia operacional para auditar criticamente todos os fluxos do Neural-Hive-Mind usando o plugin `team-attention/hoyeon` (Claude Code).

**Data:** 2026-04-27
**Versão:** 1.0
**Repo hoyeon:** https://github.com/team-attention/hoyeon

---

## Sumário Executivo

A análise crítica dos fluxos do NHM combina **4 camadas** de skills `hoyeon`:

1. **Mapear** — inventário canónico dos fluxos (`/discuss` + `/reference-seek` + agente `Explore`/`code-explorer`)
2. **Criticar** — revisão adversarial 3-perspectivas por fluxo (`/tribunal`)
3. **Deliberar** — decisão multi-perspectiva nos riscos críticos (`/council`)
4. **Meta-revisão** — blind spots e validação contra checklists (`/stepback`, `/check`)

> **Nota:** o README do hoyeon menciona `/scope` mas essa skill **não está instalada** neste plugin. Usamos alternativas equivalentes (ver abaixo).

Output esperado: relatórios estruturados por fluxo + aprendizagens compostas + issues GitHub priorizadas.

---

## 1. Pré-requisitos

```bash
# Plugin já instalado nesta máquina (skills hoyeon:* disponíveis)
claude plugin add team-attention/hoyeon
npm install -g @team-attention/hoyeon-cli
```

Verificar disponibilidade (digitar `/` em Claude Code). Skills usadas neste guia:

| Skill | Disponível |
|-------|------------|
| `hoyeon:tribunal` | ✅ |
| `hoyeon:council` | ✅ |
| `hoyeon:stepback` | ✅ |
| `hoyeon:check` | ✅ |
| `hoyeon:compound` | ✅ |
| `hoyeon:issue` | ✅ |
| `hoyeon:discuss` | ✅ |
| `hoyeon:reference-seek` | ✅ |
| `hoyeon:tech-decision` | ✅ |
| `hoyeon:ultrawork` | ✅ |
| `hoyeon:scope` | ❌ não instalado — substituído por `/discuss` + agente `Explore` |

---

## 2. Estratégia em 4 Camadas

```
┌─────────────────────────────────────────────────────────────┐
│  Camada 1: MAPEAR                                           │
│    /discuss          → diálogo estruturado de alinhamento   │
│    /reference-seek   → padrões internos e externos          │
│    Agent(Explore)    → varredura paralela do codebase       │
│                                                             │
│  Camada 2: CRITICAR (paralelo, 1 fluxo por sessão)          │
│    /tribunal         → Risk + Value + Feasibility           │
│                                                             │
│  Camada 3: DELIBERAR (apenas top-riscos)                    │
│    /council          → tribunal + Codex + Gemini + comum.   │
│                                                             │
│  Camada 4: META-REVISÃO                                     │
│    /stepback         → reframing + 3 checks                 │
│    /check            → validação contra .hoyeon/rules/      │
│    /compound         → extrai learnings → docs/learnings/   │
│    /issue            → cria GitHub issue estruturada        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Fluxos do NHM a Auditar

Lista canónica baseada em `CLAUDE.md` e `MEMORY.md`:

| # | Fluxo | Componentes | Estado actual |
|---|-------|-------------|---------------|
| 1 | **Cognitive Pipeline** | Gateway → STE → Consensus → Orchestrator → Workers | ~95% |
| 2 | **Fluxo A** (intent simples) | Gateway → Workers directos | Documentado |
| 3 | **Fluxo B** (especialistas) | + Specialists + Consensus | Documentado |
| 4 | **Fluxo C** (cognitivo completo) | + Approval + Memory + Explainability | Documentado |
| 5 | **Fluxo G** (geração código) | Code-Forge + classificação automática | 80-85% reliability |
| 6 | **ML Feedback Loop** | Approval → Active Learning → Retrain → Promote → Rollback | FASE 0 100% |
| 7 | **Self-Healing Engine** | Detection → Diagnosis → Remediation | 107 testes |
| 8 | **Consensus Hierárquico** | 5 níveis de senioridade (GAPS-03) | 68 testes |
| 9 | **Active Learning Feedback** | Balance Analyzer → Queue → Estratégia | 76 testes |
| 10 | **Routing & Service Discovery** | Service Registry + MCP Tool Catalog | Documentado |

---

## 4. Workflow Concreto (5 dias)

### Dia 1 — Mapeamento

Como `/scope` não está disponível, usar a combinação:

**Passo 1.1** — Alinhamento estruturado:
```bash
/discuss "quais fluxos do NHM merecem análise crítica prioritária dado o
          estado actual (Fase 3 ~75%, Fluxo G 80-85% reliability,
          ML feedback loop recém-deployed)?"
```

**Passo 1.2** — Inventário paralelo via agente `Explore` (em vez de `/scope`):
```
Pedir ao Claude Code:
"Dispatch Agent(subagent_type=Explore, thoroughness=very thorough)
 para inventariar todos os fluxos NHM:
  - entry points (Gateway, Kafka topics, gRPC endpoints)
  - dependências entre serviços
  - pontos de falha conhecidos
  - estado de testes por fluxo
 Output: lista canónica em docs/analise-critica-2026-04-27/00-inventario.md"
```

**Passo 1.3** — Padrões existentes:
```bash
/reference-seek "implementações de circuit breakers, backpressure e
                 observabilidade nos fluxos NHM — identificar gaps"
```

**Saída esperada:** lista canónica de fluxos + diagrama de dependências + componentes críticos em `docs/analise-critica-2026-04-27/00-inventario.md`.

---

### Dias 2-3 — Crítica Adversarial (Paralelo)

Para cada fluxo, **uma sessão isolada** (cada `/tribunal` consome contexto):

```bash
/tribunal "Cognitive Pipeline end-to-end (Gateway → STE → Consensus →
           Orchestrator → Workers): avaliar latência, pontos de falha,
           backpressure, observabilidade"

/tribunal "ML Feedback Loop: approval → active learning → drift detection →
           retrain → promote → rollback. Avaliar dataset balance, model
           promotion safety, rollback automation"

/tribunal "Fluxo G (geração código): routing 80-85% reliability,
           classificação automática workflows, integração code-forge"

/tribunal "Self-healing engine: detection accuracy, diagnosis confidence,
           remediation safety, blast radius"

/tribunal "Consensus Hierárquico (GAPS-03): 5 níveis de senioridade,
           cálculo de pesos, fallback quando especialistas falham"

/tribunal "Active Learning Feedback collector: balance dataset 93/7,
           information value calculation, queue management"

/tribunal "Routing & Service Discovery: service registry, MCP tool catalog,
           failure modes em descoberta de serviços"
```

**Output por fluxo (cada `/tribunal` produz):**

```yaml
veredict: SHIP | NEEDS_FIXES
risks:
  - id: R1
    severity: HIGH | MEDIUM | LOW
    description: ...
    mitigation: ...
value:
  - alignment_score: 0-10
  - strengths: [...]
feasibility:
  - constraints: [...]
  - blockers: [...]
synthesis: parágrafo final
```

> **Convenção:** guardar cada relatório em `docs/analise-critica-2026-04-27/<fluxo>.md`.

---

### Dia 4 — Deliberação Profunda

Apenas para os **top-3 riscos críticos** identificados pelo `/tribunal`:

```bash
/council "Risco identificado: <descrição>.
          Avaliar trade-offs, alternativas arquitecturais, e impacto
          em fluxos adjacentes."
```

`/council` adiciona ao tribunal:
- **Opiniões externas** via Codex e Gemini (peer-to-peer debate)
- **Scan de comunidade** (Reddit, HN, dev.to, Lobsters)
- **Loop iterativo de stepback** moderado

Útil para decisões com trade-offs não óbvios (ex.: substituir broker, mudar estratégia de consenso, refactor de boundary).

---

### Dia 5 — Síntese e Meta-Revisão

```bash
# Apanhar blind spots após análise extensiva
/stepback

# Validar contra regras do projecto (CLAUDE.md, .hoyeon/rules/)
/check

# Compor aprendizagens estruturadas
/compound

# Criar issue GitHub estruturada com secções:
#   - AI-verificadas
#   - Carecem julgamento humano
#   - Cautelas
/issue "Análise crítica fluxos NHM 2026-04-27 — top riscos arquitecturais"
```

---

## 5. Outputs Esperados

```
docs/
├── analise-critica-2026-04-27/
│   ├── 01-cognitive-pipeline.md       # /tribunal output
│   ├── 02-ml-feedback-loop.md
│   ├── 03-fluxo-g.md
│   ├── 04-self-healing.md
│   ├── 05-consensus-hierarquico.md
│   ├── 06-active-learning.md
│   ├── 07-routing-discovery.md
│   ├── deliberation-top-risks.md      # /council output
│   ├── meta-review.md                 # /stepback output
│   └── INDEX.md                       # síntese final
└── learnings/
    └── 2026-04-27-flow-audit/         # /compound output
        ├── architectural-rules.md
        ├── observability-gaps.md
        └── failure-mode-patterns.md

GitHub Issues:
└── #N — "Análise crítica fluxos NHM 2026-04-27"
        ├── seção AI-verificadas
        ├── seção carecem julgamento humano
        └── seção cautelas
```

---

## 6. Alternativa Rápida (1 dia)

Se quiseres só vista crítica rápida sem o pipeline completo:

```bash
/ultrawork "auditoria crítica dos fluxos principais do NHM —
            identificar top-10 riscos arquitecturais com mitigações
            priorizadas por impacto/esforço"
```

`/ultrawork` corre `specify → blueprint → execute` automaticamente, mas direccionado para análise (não código). Produz:
- `requirements.md` — riscos catalogados
- `plan.json` — mitigações priorizadas com `fulfills` linkado
- Documentação executada

---

## 7. Critérios de Priorização dos Fluxos

Recomenda-se começar pelos fluxos com **maior risco residual**:

| Prioridade | Fluxo | Razão |
|------------|-------|-------|
| **P0** | ML Feedback Loop | Recém-deployed (FASE 0), automação de retrain/promote crítica |
| **P0** | Fluxo G | Apenas 80-85% reliability documentado |
| **P1** | Cognitive Pipeline | Coração do sistema, blast radius máximo |
| **P1** | Self-Healing | Auto-acção em produção, risco de feedback loops |
| **P2** | Consensus Hierárquico | Já validado com 68 testes, mas é base de decisão |
| **P2** | Active Learning | Já validado com 76 testes |
| **P3** | Routing & Discovery | Maturidade alta |

---

## 8. Regras de Execução

Alinhamento com `CLAUDE.md`:

- ✅ **Idioma:** todos os relatórios em **português**
- ✅ **Não criar ficheiros desnecessários:** apenas relatórios essenciais em `docs/analise-critica-2026-04-27/`
- ✅ **Validar duplicações:** verificar se `docs/ANALISE_*` já cobrem aspectos antes de gerar novo conteúdo
- ✅ **Branch dedicada:** `feat/HOYEON-audit-flows-2026-04-27`
- ✅ **Commits após sucesso:** apenas após `/check` passar verde
- ❌ **Não modificar `tests/`** durante a análise (regra 7)

---

## 9. Comandos de Referência Rápida

```bash
# Mapeamento (substituto de /scope)
/discuss "<pergunta>"                  # diálogo estruturado de alinhamento
/reference-seek "<padrão>"             # padrões internos + externos
# + invocar Agent(subagent_type=Explore) para varredura paralela do codebase

# Crítica
/tribunal "<fluxo>"                    # 3 agentes adversariais
/council "<decisão>"                   # tribunal + LLMs externos + comunidade
/tech-decision "<A vs B>"              # comparação técnica estruturada

# Meta
/stepback                              # reframing + blind spots
/check                                 # validar contra regras
/compound                              # extrair learnings
/issue "<título>"                      # GitHub issue estruturada

# Pipeline completo (alternativa rápida)
/ultrawork "<descrição>"               # specify → blueprint → execute

# CLI directo
hoyeon-cli plan get <task-id> <plan>
hoyeon-cli plan task <plan> --status <id>=done
```

---

## 10. Checklist Final

Antes de considerar a análise concluída:

- [ ] `/discuss` + `/reference-seek` + `Agent(Explore)` produziram inventário canónico
- [ ] `/tribunal` executado em todos os fluxos P0 e P1
- [ ] `/council` executado nos top-3 riscos críticos
- [ ] `/stepback` validou ausência de blind spots
- [ ] `/check` validou contra `CLAUDE.md` e `.hoyeon/rules/`
- [ ] `/compound` extraiu learnings para `docs/learnings/`
- [ ] `/issue` criou issue GitHub com 3 secções estruturadas
- [ ] `INDEX.md` em `docs/analise-critica-2026-04-27/` consolidado
- [ ] Branch dedicada com PR aberto

---

## Referências

- **Repo hoyeon:** https://github.com/team-attention/hoyeon
- **Filosofia:** "Requirements are not written — they are derived"
- **Cadeia derivativa:** `Goal → Context → Decisions → Requirements → Sub-requirements → Tasks`
- **Regras do projecto:** [CLAUDE.md](../CLAUDE.md)
- **Análises anteriores:** [ANALISE_FLUXOS.md](./ANALISE_FLUXOS.md), [ANALISE_PROFUNDA_FLUXOS_AGH_2026-04-19.md](./ANALISE_PROFUNDA_FLUXOS_AGH_2026-04-19.md)

---

*"O plano não prevê o futuro. Sobrevive a ele — sabendo o que manter firme e o que flexibilizar."*
