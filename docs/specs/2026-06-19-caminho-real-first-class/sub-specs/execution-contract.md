# Contrato de Execução

Contrato aplicável a TODAS as tasks de @docs/specs/2026-06-19-caminho-real-first-class/tasks.md. Cada task só entra em execução se cumprir a DoR, e só é concluída se cumprir a DoD. As Políticas Transversais aplicam-se sempre. O Prompt Mestre é o ponto de entrada para o Claude Code executar cada task.

## 1. Princípio

O objetivo de cada task é converter um caminho de **fallback/simulação/heurística-de-lacuna** no **caminho real**, com **evidência verificável**. "Concluído" significa que o trabalho real acontece e é provável por evidência — nunca que o fallback foi apenas sinalizado.

## 2. Definition of Ready (DoR) — pré-condições para iniciar

Um ticket/task só entra em execução quando TODOS verdadeiros:

- [ ] **Alvo identificado**: o ponto de fallback a substituir está localizado com `file:line` e classificado (BROKEN/MISSING/RESILIENCE/FAIL-SAFE).
- [ ] **Caminho real conhecido**: existe e está localizado (ou está marcado como "a construir" no balde correto); dependências/infra necessárias enumeradas.
- [ ] **Evidência definida**: o artefacto verificável de "trabalho real" para este `task_type` está explicitado (ver tabela em technical-spec.md §Contrato de evidência).
- [ ] **Critério de falha definido**: o que constitui falha explícita quando o caminho real está indisponível (fail-fast), distinto de RESILIENCE legítima.
- [ ] **Testes planeados**: lista dos testes a escrever primeiro (TDD), cobrindo (a) caminho real, (b) falha explícita, (c) ausência de simulação silenciosa.
- [ ] **Ambiente preparado**: dependências/serviços/flags necessários disponíveis em dev, ou a sua ativação faz parte do escopo da task.
- [ ] **Branch criada**: `feat/CR-<n>-<descricao>` a partir de `main` atualizado (`git pull --rebase origin main`).

## 3. Definition of Done (DoD) — critérios de conclusão

Um ticket/task só é COMPLETED quando TODOS verdadeiros:

- [ ] **Caminho real entregue**: o trabalho real é executado; o caminho de simulação/`stub://`/`noop`/heurística-de-lacuna foi removido ou fechado por gate (não apenas marcado).
- [ ] **Evidência real produzida**: a execução produz e regista a evidência definida na DoR (digest de artefacto, recurso reconciliado, decisão OPA com `result`, output não-noop, código persistido). Verificada por consulta real (cluster/MongoDB/registry), não por `success=True`.
- [ ] **Fail-fast verificado**: quando o caminho real está indisponível, o resultado é falha explícita (não verde silencioso); coberto por teste.
- [ ] **Honestidade preservada**: qualquer RESILIENCE/FAIL-SAFE legítimo restante emite `degradation_total{component,reason}` e marca o registo (`simulated`/`degraded`/`model_source`/`method`).
- [ ] **Testes verdes**: unitários novos (caminho real + falha) e suite de regressão do serviço a passar 100%.
- [ ] **Qualidade verde**: `ruff check` e `black --check` (line-length 100) limpos nos ficheiros tocados; sem `ruff --fix` global (UP017 quebra py310 local — ver nota da sessão).
- [ ] **Sem segredos** nos ficheiros modificados.
- [ ] **Validação E2E** (quando o caminho é deployável): re-executado A→C6 e a evidência confirmada no cluster.
- [ ] **Documentação**: spec/memória atualizadas se houver achado; commit `fix(...)`/`feat(...)` + push; CI relevante verde ou falhas confirmadas como crónicas pré-existentes.

## 4. Gate de evidência por task_type (DoD específico)

O `execution_engine` (Task 1) materializa este contrato em runtime. Uma task `COMPLETED` exige a evidência do seu tipo:

| task_type | Evidência obrigatória para COMPLETED |
|---|---|
| query | `output.count` + documentos/results reais |
| transform | output derivado, `output.noop != True`, `operations` aplicadas |
| validate | decisão OPA com `result` presente (não `policy_undefined`) ou scan com findings; `metadata.simulated != True` |
| build | `{registry}/{artifact}:{version}` + digest verificável |
| deploy | recurso reconciliado (ArgoCD `Synced/Healthy` ou `helm --wait`+`rollout status` OK) |
| execute | exit code real + stdout/stderr capturados (não `[SIMULAÇÃO]`) |
| generate_code | `code_artifact_id` persistido (MongoDB) e, se exigido, commit/PR |

## 5. Políticas Transversais

Aplicam-se a todas as tasks, sem exceção:

### 5.1 Qualidade de código
- `ruff` (lint) + `black -l 100` (format) limpos; type hints em funções públicas; docstrings Google nas relevantes.
- Sem código morto: ramos de simulação/heurística substituídos ou removidos, não acumulados.
- DRY: caminho real e fail-fast partilham helpers; não duplicar lógica de fallback.
- Mudanças cirúrgicas: não reformatar código não-relacionado (evitar `ruff --fix` global).

### 5.2 Testes
- TDD: testes primeiro (RED → GREEN). Nunca modificar `tests/` como contrato.
- Cada função nova → teste unitário; cada ticket → teste de integração (E2E quando deployável).
- Cobertura obrigatória de 3 caminhos: real (sucesso), falha explícita (fail-fast), ausência de simulação silenciosa.

### 5.3 Segurança
- Fail-closed em segurança/validação: OPA real, SAST timeout → falha (nunca "passou"); sem fail-open de PII.
- Sem segredos no código; usar Secrets/Vault; `ghcr-secret`/tokens via referência.
- Operações destrutivas exigem o nível de confidencialidade da política.

### 5.4 Observabilidade
- Métricas: `degradation_total{component,reason}`, `simulated_total{executor,task_type}`, `real_path_unavailable_total`.
- Logs estruturados (`structlog`) com `degraded=true`/`reason` em toda a degradação; nível WARNING.
- Trace W3C propagado ponta-a-ponta (gateway→STE→consenso→worker); spans por etapa.
- Proibido "verde falso": nenhum `COMPLETED`/`healthy`/`allow` sem a evidência correspondente.

## 6. Prompt Mestre para Claude Code

Usar este prompt como ponto de entrada para executar QUALQUER task desta spec (substituir `<N>`):

```
Executa a Task <N> da spec docs/specs/2026-06-19-caminho-real-first-class/.

Antes de começar:
1. Lê spec.md, sub-specs/technical-spec.md e sub-specs/execution-contract.md.
2. Confirma a Definition of Ready (DoR §2) da Task <N>; se algo faltar, resolve ou reporta o bloqueio — não avances com DoR incompleta.

Durante a execução (TDD + Políticas Transversais §5):
3. Localiza o ponto de fallback alvo (file:line) e o caminho real correspondente.
4. Escreve os testes primeiro: (a) caminho real produz a evidência do task_type, (b) caminho real indisponível → falha explícita (fail-fast), (c) nenhuma simulação silenciosa emite COMPLETED.
5. Implementa o caminho real; remove ou fecha por gate o caminho de simulação/stub/noop/heurística-de-lacuna. Mantém RESILIENCE/FAIL-SAFE legítimos, mas instrumenta-os (degradation_total + marcação).
6. Mudanças cirúrgicas; ruff + black -l 100; sem segredos; sem ruff --fix global.

Antes de concluir (Definition of Done §3):
7. Corre os testes novos + regressão do serviço; tudo verde.
8. Valida a EVIDÊNCIA REAL no ambiente (cluster/MongoDB/registry) — não aceites success=True como prova. Confirma o gate de evidência (§4) para o task_type.
9. Confirma fail-fast: caminho real indisponível resulta em falha explícita, não verde.
10. Atualiza spec/memória se houver achado; commit fix(...)/feat(...) + push; verifica o CI (distingue falhas crónicas pré-existentes de regressões tuas).

Regra de ouro: "Concluído" = o trabalho real aconteceu e é provável por evidência. Se não consegues provar trabalho real, a task NÃO está concluída — reporta o gap honestamente em vez de marcar verde.
```
