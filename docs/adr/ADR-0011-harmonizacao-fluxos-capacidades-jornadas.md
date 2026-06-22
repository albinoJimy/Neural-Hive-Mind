# ADR-0011: Harmonização dos Fluxos NHM — Modelo Capacidades × Jornadas × Loops

## Status
Proposto

> Data: 2026-06-22 · Branch de origem da análise: `feat/convergencia-dbs`
> Substitui conceptualmente a taxonomia linear de "Fluxos A–H" do
> [documento-06](../../documento-06-fluxos-processos-neural-hive-mind.md) e reconcilia as
> contradições de nomenclatura em [FLUXOS_AGH_COMPARACAO.md](../FLUXOS_AGH_COMPARACAO.md).
> Análise de suporte: [ANALISE_FLUXOS_REAL_VS_CONCEPTUAL_2026-06-22.md](../ANALISE_FLUXOS_REAL_VS_CONCEPTUAL_2026-06-22.md).

## Contexto

A documentação do NHM descreve o sistema como uma lista linear de "Fluxos" nomeados por
letras (A–F no documento-06; G e H em documentos posteriores). Esta taxonomia degradou-se
e hoje é fonte de confusão arquitetural concreta:

1. **A–F e G/H não são o mesmo tipo de objeto.** A–F são *estágios/capacidades*
   (captura, planeamento, execução, observabilidade, autocura, aprendizado). G e H são
   *jornadas end-to-end* que **reutilizam** A–F. Listá-los juntos mistura níveis de
   abstração.
2. **Colisão de nomenclatura documentada.** No documento-06, `D=Observabilidade`,
   `E=Autocura`. Em `FLUXOS_AGH_COMPARACAO.md` (linhas 197-198, 219),
   `D=Code Generation`, `E=CI/CD`, `I=Data Migration`. A mesma letra significa coisas
   diferentes em documentos diferentes.
3. **Os loops estão desenhados como sequência.** D→E→F aparecem como "estágios 4,5,6",
   mas Observabilidade/Autocura/Aprendizado são planos *transversais* sempre-ativos que
   envolvem todas as jornadas, não passos que vêm "depois" da execução.
4. **A bifurcação que mais importa está escondida.** A decisão
   `ORCHESTRATION` vs `GENERATION` (`workflow_classifier.py`) é o que separa as jornadas,
   mas está documentada como subnota "B2.5".

A taxonomia errada estava a **mascarar dívida arquitetural real**: ao nomear mal os
objetos, escondia-se onde o código viola limites que um modelo correto tornaria
explícitos.

### Critérios de Avaliação
- **Coerência conceptual**: cada objeto tem um nível de abstração inequívoco.
- **Ausência de colisões**: um nome → um significado.
- **Reflexo no código**: a estrutura deve poder guiar refactors reais, não só renomear docs.
- **Custo/risco de adoção**: o produto está em construção; mudança de caminho é aceitável
  desde que o valor justifique.
- **Reuso explícito**: tornar visível que corrigir uma capacidade beneficia todas as
  jornadas que a usam.

## Decisão

Adotar um **modelo de três planos** em vez da lista linear de letras:

### Eixo X — Capacidades (building blocks, contrato artefacto-in → artefacto-out)

| Capacidade | Ex-Fluxo | Contrato | Serviço |
|---|---|---|---|
| **CAPTURE** | A | Intenção → Intent Envelope | gateway :8000 |
| **PLAN** | B | Intent Envelope → Cognitive Plan | STE :8001 + consensus :8002 |
| **EXECUTE** | C | Cognitive Plan → Execution Results | orchestrator :8003 + workers :8005 |
| **GENERATE** | G (núcleo) | Plan(GENERATION) → Code Artifact → Deployed SW | code-forge + activities G1-G8 |
| **MIGRATE** | H (núcleo) | Legacy Doc → Migrated System | doc-ingestion :8018 + data-migration :8019 |

### Plano Z — Loops transversais (sempre-on, não sequenciais)

| Loop | Ex-Fluxo | Cadência | Função |
|---|---|---|---|
| **OBSERVE** | D | contínuo | capta sinais de qualquer capacidade/jornada |
| **HEAL** | E | segundos | corrige runtime |
| **LEARN** | F | dias | evolui modelos/pesos |

### Eixo Y — Jornadas (composições nomeadas de capacidades)

| Jornada | Composição | Objetivo | Ex-nome |
|---|---|---|---|
| **J1 · PLAN-ONLY** | CAPTURE → PLAN | só planear | "Fluxo A" simples |
| **J2 · ORCHESTRATE** | CAPTURE → PLAN → EXECUTE | executar sobre sistemas existentes | pipeline cognitivo |
| **J3 · BUILD** | CAPTURE → PLAN → GENERATE → EXECUTE(deploy) | criar software do zero | "Fluxo G" |
| **J4 · MIGRATE** | INGEST → CAPTURE → PLAN → GENERATE → EXECUTE → MIGRATE | modernizar legado | "Fluxo H" |

O roteamento entre jornadas é decidido pela bifurcação `ORCHESTRATION`/`GENERATION`
(`workflow_classifier.py`), promovida a **ponto de roteamento de topo**.

### Escopo do alinhamento arquitetural

A harmonização **não é só documental** — ela expõe desalinhamentos reais. A decisão
distingue três níveis de profundidade e **prioriza explicitamente quais valem o risco**:

| Peça (alinhamento) | Custo | Valor | Decisão |
|---|---|---|---|
| **Fechar loop LEARN** (persistência D6 + telemetria uniforme) | médio (já em curso) | máximo — fundação cega de todo o sistema | ✅ **FAZER JÁ** |
| **Journey router explícito** (subir bifurcação ORCH/GEN) | baixo (lógica já existe) | alto — habilita jornadas, torna roteamento testável | ✅ **FAZER A SEGUIR** |
| **Extrair GENERATE como capacidade autónoma** | alto | alto **só quando G for fiável** | 🕐 **ADIAR** |
| **Consolidar PLAN** (STE + consensus) | médio-alto | negativo — separação está correta | ❌ **NÃO FAZER** |

**Princípio ordenador:** *Fundação → Roteamento → Capacidades. Nunca o inverso.*

### Sequência adotada
1. **Agora** — fechar o loop D6: `execution_result_consumer.py` passa a persistir
   `actual_duration_ms` na coleção `execution_tickets` (que `duration_predictor.py:206`
   lê), e LEARN consome telemetria uniforme. Estende `feat/convergencia-dbs`.
2. **A seguir** — extrair o **journey router** explícito a partir de
   `workflow_classifier.py` + `decision_consumer.py`.
3. **Quando J3/BUILD for fiável** — extrair GENERATE para capacidade autónoma.
4. **Nunca** — consolidar PLAN.

## Alternativas Consideradas

### Alternativa 1 — Manter a taxonomia linear de letras (status quo)
**Prós:**
- Zero custo de migração; documentos e conversas existentes não mudam.

**Contras:**
- Mantém a colisão de nomes (D/E com dois significados).
- Continua a esconder a dívida arquitetural sob nomes ambíguos.
- Onboarding lento: exige decifrar 8 letras com significados conflituantes.

### Alternativa 2 — Harmonização cosmética (só renomear nos documentos)
**Prós:**
- Custo quase nulo; resolve a confusão de leitura imediata.

**Contras:**
- O código continua a violar os limites do modelo → a divergência **regressa** na
  sessão seguinte. É maquilhagem sobre dívida estrutural.

### Alternativa 3 — Big-bang: alinhar TODA a arquitetura ao modelo de uma vez
**Prós:**
- Código = modelo no fim; máxima pureza estrutural.

**Contras:**
- Inclui refactors de valor negativo (consolidar PLAN) e prematuros (extrair GENERATE
  antes de G ser fiável).
- Risco de "reorganizar móveis numa casa com a fundação rachada": código mais limpo,
  cérebro ainda sem aprender (loop D6 continua cego).
- Colide com o trabalho em curso (`feat/convergencia-dbs`).

### Alternativa 4 (ESCOLHIDA) — Adotar como linguagem + alinhar incrementalmente por valor
**Prós:**
- Vocabulário comum imediato (custo ~0) + refactors guiados por rácio custo/valor.
- Prioriza a fundação (loop LEARN) que desbloqueia E, F, G e H de uma vez.
- Respeita o critério do produto: muda de caminho **onde vale a pena**, na ordem certa.

**Contras:**
- Exige disciplina para não pular para os refactors "limpos mas prematuros" (GENERATE).
- Período de coexistência: docs antigos com letras + modelo novo até migração completa.

## Consequências

### Positivas
- **Um nome → um significado**: fim da colisão D=Observabilidade vs D=CodeGen.
- **Reuso explícito**: fica visível que o loop D6 partido cega *todas* as jornadas, e que
  corrigir EXECUTE beneficia J2, J3 e J4 simultaneamente.
- **Contratos testáveis**: cada capacidade ganha in/out explícito → testes de integração
  por bloco, não só por jornada inteira.
- **Roadmap ancorado**: refactors futuros têm um modelo de referência e uma ordem
  justificada por custo/valor.
- **Onboarding rápido**: um plano cartesiano ensina o sistema em minutos.

### Negativas / Riscos
- **Coexistência terminológica temporária**: documentação legada (letras) convive com o
  modelo novo até reescrita. Mitigação: glossário de mapeamento no topo dos docs ativos.
- **Risco de adoção parcial**: adotar a linguagem (Nível 0) sem nunca avançar para o
  alinhamento (Níveis 1-2) faz a divergência regressar. Mitigação: este ADR fixa a
  sequência e o "fazer já" do passo 1.
- **Anti-padrão a vigiar**: atacar a extração de GENERATE antes de fechar o loop D6.
  Mitigação: o princípio *Fundação → Roteamento → Capacidades* é normativo neste ADR.

### Neutras
- Não há mudança de runtime imediata: o passo 1 (loop D6) já estava planeado via
  convergência de DBs; este ADR apenas o enquadra como fundação do modelo.

## Referências
- [documento-06 — Fluxos Operacionais (A–F)](../../documento-06-fluxos-processos-neural-hive-mind.md)
- [FLUXOS_AGH_COMPARACAO.md](../FLUXOS_AGH_COMPARACAO.md) — origem da colisão de nomenclatura
- [ANALISE_FLUXOS_REAL_VS_CONCEPTUAL_2026-06-22.md](../ANALISE_FLUXOS_REAL_VS_CONCEPTUAL_2026-06-22.md) — diagnóstico do verde falso e loop D6
- Código-âncora: `services/semantic-translation-engine/src/services/workflow_classifier.py`
  (bifurcação), `services/orchestrator-dynamic/src/consumers/decision_consumer.py`
  (roteamento), `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py`
  (loop D6), `services/orchestrator-dynamic/src/ml/duration_predictor.py:206` (consumidor cego)
