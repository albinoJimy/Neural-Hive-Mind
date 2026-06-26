# Spec Tasks

> Passo 3 do ADR-0011 (eixo Capacidades) — extrair GENERATE como capacidade autónoma por fronteira
> de contrato, desbloqueado pelo gate "J3/BUILD fiável" (spec 2026-06-23-j3-build-generate).
>
> **Princípios:** fronteira de contrato (não novo serviço); FluxoGWorkflow mantém-se como
> implementação; multi-linguagem-ready (contrato/registry stack-neutros, só FastAPI implementado);
> anti-verde-falso (stack desconhecida / G-step falhado → FAILED); TDD estrito; diffs mínimos
> (py3.10). Cada fase é um gate: só avança com testes verdes. Detalhe em `sub-specs/technical-spec.md`.

## Tasks

### Fase 0 — Contrato + registry de stacks (multi-linguagem-ready)

- [x] 1. Definir o contrato da capacidade e o registry de stacks extensível
  - **DoD:** `src/capabilities/generate/contract.py` (`GenerateTarget`/`GenerateRequest`/
    `GenerateResult`, fail-closed, target stack-neutro) e `stacks.py` (`StackRegistry` +
    `GenerationStrategy`, FastAPI registado, `resolve` desconhecida→erro sem fallback). Sem lógica
    de orquestração ainda. **FEITO** — 25 testes verdes; pipeline dev→auditoria(qualidade+completude)
    →remediação (M1 verde-falso whitespace + B1/B2/B3/B4). Ver `sub-specs/fase0-evidence.md`.
  - **Evidência:** `sub-specs/fase0-evidence.md`.
  - [x] 1.1 Testes: contrato valida campos obrigatórios; `GenerateResult.failed` exige
    `failure_reason`; registry resolve `("python","fastapi")` e estratégia "fake" registada em teste;
    stack desconhecida → erro (sem cair em FastAPI) — 5 pontos cobertos + casos fail-closed extra
  - [x] 1.2 Implementar contract.py + stacks.py com FastAPI registado (porta 8080, `/health`, TEMPLATE)
  - [x] 1.3 Documentar no módulo o ponto de extensão (como registar nova linguagem)

### Fase 1 — GenerateCapability encapsula o FluxoGWorkflow

- [x] 2. Adaptador fino capacidade → FluxoGWorkflow (`start` durável + `map_result` puro)
  - **DoR:** Fase 0 fechada. ✓
  - **DoD:** `GenerateCapability.start(GenerateRequest)` resolve a estratégia e **inicia** o
    `FluxoGWorkflow` (cliente Temporal injetado, id por plano, task_queue) devolvendo um
    `GenerateHandle`; stack desconhecida → FAILED sem iniciar. `map_result(workflow_output)` (puro)
    traduz `code_generation/build/deployment/journey → GenerateResult`; output falhado/incompleto →
    `failed`. **Sem await bloqueante no consumer** (preserva a cadência durável do Temporal). Não
    reimplementa G1–G8. **FEITO** — 38 testes verdes; pipeline dev→auditoria→remediação (gate
    `verified` anti-verde-falso; propagação da estratégia completa p/ multi-linguagem; normalização
    datetime; não-mutação). Ver `sub-specs/fase1-evidence.md`.
  - **Evidência:** `sub-specs/fase1-evidence.md`.
  - [x] 2.1 Testes (cliente Temporal mockado): `start` inicia com o input certo; stack desconhecida →
    FAILED sem iniciar; `map_result` sucesso → `completed` (code_artifact_id/container_image_ref/
    deployment); output falhado/incompleto → `failed` — + gate `verified`, datetime, não-mutação
  - [x] 2.2 Implementar capability.py (`start` + `map_result` + resolução de estratégia)
  - [x] 2.3 Gate: teste de contrato em bloco verde (in→out sem jornada inteira)

### Fase 2 — Des-vazar a fronteira no routing

- [x] 3. `decision_consumer` invoca a capacidade em vez de conhecer FluxoGWorkflow
  - **DoR:** Fase 1 fechada. ✓
  - **DoD:** para jornadas de geração (J3_BUILD), o handler invoca `GenerateCapability`; deixa de
    iniciar `FluxoGWorkflow` directamente nesse caminho. Preservados: J1 não executa; J2/J4 →
    Orchestration; fallback por `workflow_type`; resume pós-aprovação honra a capacidade. **FEITO
    (código+contrato)** — 18 testes verdes, zero regressão; pipeline dev→auditoria(qualidade SHIP +
    completude COMPLETO)→remediação (CR-001 autoridade única `_requires_generate_capability` p/
    consumer↔resume não divergirem; CR-002 documentado). Equivalência provada: teste congelado
    `test_workflow_start_journey_routing.py` (asserts `FluxoGWorkflow.run`) continua verde.
    Ver `sub-specs/fase2-evidence.md`. **3.3 (gate cluster) PENDENTE** — control-plane instável.
  - **Evidência:** `sub-specs/fase2-evidence.md`.
  - [x] 3.1 Testes: J3_BUILD → invoca capacidade; J1/UNKNOWN sem execução; J2/J4 → Orchestration;
    journey ausente → fallback workflow_type; resume pós-aprovação → capacidade — + anti-verde-falso
    (stack não suportada: consumer commit+return / resume HTTP 422)
  - [x] 3.2 Refactor do routing para a capacidade (sem mudar comportamento das outras jornadas)
  - [ ] 3.3 Gate cluster: plano J3 aprovado é processado via a capacidade (log/Temporal coerentes)
    — DIFERIDO (deploy + cluster; control-plane instável). Prova E2E "software a correr" = Fase 4.

### Fase 3 — Prova de extensibilidade multi-linguagem (sem implementar outra stack)

- [x] 4. Garantir que adicionar uma stack não toca contrato/routing
  - **DoR:** Fase 2 fechada. ✓
  - **DoD:** uma `GenerationStrategy` "fake" registada apenas em teste é selecionada pela capacidade
    via `target` e percorre o mesmo caminho de contrato (mockando o workflow), sem qualquer alteração
    a `GenerateRequest`/`GenerateResult` nem ao routing; stack desconhecida continua FAILED. **FEITO**
    — 8 testes verdes (`test_generate_extensibility.py`, stack fake `elixir/phoenix` com valores
    distintos de FastAPI); pipeline dev→auditoria(qualidade SHIP por mutation testing + completude
    COMPLETO)→remediação. **4.2 sem ajuste de produção** (`src/capabilities/generate/` sem diff): a
    propagação completa da estratégia já fora feita na Fase 1; greps confirmam zero acoplamento
    FastAPI fora da entrada do registry. Anti-verde-falso provado por mutação (desactivar gate
    `verified`/fallback FastAPI/hardcode → derruba ≥1 teste). Flake da auditoria diagnosticado como
    artefacto do mutation testing paralelo (não bug de isolamento; 18+ runs combinados verdes). Ver
    `sub-specs/fase3-evidence.md`.
  - **Evidência:** `sub-specs/fase3-evidence.md`.
  - [x] 4.1 Testes: registo de stack "fake" → capacidade seleciona-a; contrato inalterado; remoção
    da stack → FAILED (sem fallback FastAPI) — + `map_result` stack-agnóstico em SUCESSO e FALHA;
    fake não contamina `default_stack_registry`
  - [x] 4.2 Ajustes mínimos se o teste revelar acoplamento a FastAPI fora da entrada do registry —
    NENHUM necessário (greps confirmam zero acoplamento fora do registry; produção sem diff)

### Fase 4 — Gate de equivalência E2E (zero regressão)

- [ ] 5. Paridade comportamental: intenção J3 produz software a correr via a capacidade
  - **DoR:** Fase 3 fechada.
  - **DoD:** intenção de geração FastAPI (J3_BUILD) → `Deployment ready 1/1` + `/health` 200 num
    namespace dedicado; `code_artifact` com `journey=J3_BUILD`; comportamento equivalente ao caminho
    FluxoG anterior. Falha real em qualquer G-step → FAILED (sem verde falso).
  - **Evidência:** `sub-specs/fase4-evidence.md` (plano real, Deployment ready, healthcheck 200,
    journey no code_artifact).
  - [ ] 5.1 Gate cluster E2E: intenção J3 → software FastAPI real a correr via `GenerateCapability`
  - [ ] 5.2 Confirmar ausência de regressão em J2/J4 (caminho Orchestration inalterado)
