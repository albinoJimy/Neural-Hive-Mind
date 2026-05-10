# Auditoria de Duplicação PII — Decisão de Consolidação

> **Data:** 2026-05-10
> **Status:** Accepted (Opção D — diferir consolidação)
> **Spec relacionada:** `.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md` (TICKET-013)

## Resumo Executivo

A spec **TICKET-013** afirmava que existem ~395 LOC duplicados de PII entre
`libraries/python/neural_hive_specialists/compliance/` e
`libs/neural_hive_context/.../services/`. A auditoria read-only mostra que
o número está **sobre-estimado** e que os dois packages têm propósitos
**parcialmente complementares**, não redundantes:

- **~150-200 LOC** de regex genuinamente equivalente
- **~450 LOC** divergentes por design (Presidio vs regex; validação matemática)
- **~1.030 LOC** sem contraparte no outro lado (AuditLogger, FieldEncryptor, ComplianceLayer)

**Decisão:** **Opção D** — documentar a duplicação real, diferir a
consolidação física, manter a coexistência durante a estabilização do
pii-service. Quando o pii-service for o consumidor canónico de PII em
todo o monorepo, executar Opção A (eliminar `neural_hive_context.pii*`
substituindo por adapter sobre `PIIDetectorLite`) com ticket próprio.

## Mapeamento

### Package A — `libraries/python/neural_hive_specialists/compliance/`

| Ficheiro | LOC | Responsabilidade |
|----------|-----|------------------|
| `pii_detector.py` | 448 | `PIIDetector` (Presidio + spaCy) e `PIIDetectorLite` (regex + spaCy leve) |
| `pii_masker.py` | 329 | `PIIMasker` com 4 estratégias (PARTIAL/FULL/HASH/REDACT) e overlap resolution |
| `pii_patterns.py` | 304 | `PIIType` (23 tipos), `PIIPattern`, `PII_PATTERNS`, `PIIPatternRegistry` singleton |
| `audit_logger.py` | 440 | `AuditLogger` com persistência MongoDB, TTL index, query API |
| `compliance_layer.py` | 389 | `ComplianceLayer` orquestrador para planos cognitivos |
| `field_encryptor.py` | 284 | `FieldEncryptor` Fernet (AES-128) por campo |
| `__init__.py` | 31 | Exports |

**Total:** ~2.225 LOC.

### Package B — `libs/neural_hive_context/.../services/`

| Ficheiro | LOC | Responsabilidade |
|----------|-----|------------------|
| `services/pii_detector.py` | 396 | `RegexPIIDetector` — regex puro + validações matemáticas (Luhn, CPF check, CNH check) |
| `services/angolan_pii_detector.py` | 147 | `AngolanPIIDetector` — subclasse com NIF/BI/NUIT angolanos |
| `models/pii.py` | 103 | `PIIType`, `PIIRiskLevel`, `PIIEntity`, `PIIResult`, `PIIDetectionConfig` (Pydantic) |
| `interfaces/pii_detector.py` | 39 | `IPIIDetector` ABC com método `detect(text) -> PIIResult` |

**Total:** ~685 LOC.

## Importadores

### Package A — consumido em produção

Ficheiros em `services/` que importam:
- `services/pii-service/src/services/pii_service.py` → usa `PIIDetectorLite`, `PIIMasker`, `PIIType`
- `services/specialist-architecture/src/http_server_fastapi.py` → `AuditLogger`, `PIIDetector`
- `services/specialist-behavior/src/http_server_fastapi.py`
- `services/specialist-evolution/src/http_server_fastapi.py`
- `services/specialist-business/src/http_server_fastapi.py`
- `services/specialist-technical/src/http_server_fastapi.py`

**Conclusão:** consumido por 6 serviços de produção + pii-service central.

### Package B — sem importadores externos

Ficheiros que importam `neural_hive_context.pii*` ou `neural_hive_context.angolan_pii_detector`:
- Apenas testes internos do próprio package em `libs/neural_hive_context/tests/`
- Internamente: `workflow_classifier.py` consome `RegexPIIDetector` via interface `IPIIDetector`

**Conclusão:** zero importadores em `services/` ou em outros packages de `libraries/`. O code path é **estritamente interno** ao `neural_hive_context`.

## Diferenças funcionais reais

### Existem só no `specialists`
- `PIIDetector` baseado em Microsoft Presidio (multi-língua via spaCy)
- `PIIMasker` standalone com 4 estratégias
- `PIIPatternRegistry` singleton com lookup por tipo e categoria
- `AuditLogger` MongoDB
- `FieldEncryptor` Fernet
- `ComplianceLayer` orquestrador
- `MaskStrategy` enum (PARTIAL, FULL, HASH, REDACT)
- BI_AO regex `\d{9}[A-Z]{2}\d{3}` (formato 14 chars)
- Tipos NLP: PERSON, ORG, GPE, LOC, DATE, MONEY (via spaCy NER)

### Existem só no `context`
- `IPIIDetector` interface ABC
- Validação matemática pós-regex: **Luhn (cartões), CPF check, CNH check**
- `PIIDetectionConfig` Pydantic (`strict_mode`, `mask_by_default`, `min_confidence`)
- `PIIRiskLevel` com `NONE`
- `PIIResult` / `PIIEntity` Pydantic (em `specialists` são dataclasses)
- BI angolano com formato **diferente**: `\d{12}[A-Z]{2}` (ainda 14 chars)
- `_is_valid_match` com validação de domínio email
- CPF detection sem formatação obrigatória

### Conflitos a resolver caso se faça consolidação
1. `PIIType` enum com valores em UPPERCASE vs lowercase em três sítios
2. **BI angolano com dois formatos diferentes** (`9d+2L+3d` vs `12d+2L`)
3. CPF: `specialists` só aceita formato pontuado; `context` aceita ambos + valida
4. Validação Luhn/CPF/CNH não existe no `specialists` — perda funcional ao eliminar

## Análise de Opções

### Opção A — `specialists` é canon, eliminar `context.pii*`
- **Custo:** ~700 LOC alterados em 8 ficheiros.
- **Adapter necessário:** `IPIIDetector.detect(text) -> PIIResult` precisa wrapper sobre `PIIDetectorLite` (que retorna `list[dict]`).
- **Perda funcional:** Luhn / CPF check / CNH check.
- **Mitigação:** portar validações matemáticas para `specialists` antes de eliminar.
- **Risco:** Médio.
- **Blast radius:** `workflow_classifier.py` (1 ficheiro de produção interno) + 4 testes do próprio package `context`.

### Opção B — `context` é canon, migrar `specialists`
- **Custo:** Recriar `PIIMasker`, `AuditLogger`, `ComplianceLayer`, `FieldEncryptor` no `context`.
- **Risco:** Alto. Inverte direcção; afecta 6 serviços de produção e o pii-service central.
- **Recomendação:** rejeitada.

### Opção C — Novo package `neural_hive_pii_common`
- **Custo:** Médio-alto (setup pyproject.toml, CI, semver, changelog).
- **Risco:** Médio.
- **Blast radius:** ~15 ficheiros durante migração.
- **Vantagem:** Solução mais limpa a longo prazo.

### Opção D — Manter status quo + documentar (escolhida)
- **Custo:** ~50 LOC de docs (este ficheiro).
- **Risco:** Zero imediato.
- **Justificação:** O Package B está **isolado** (zero importadores externos). A duplicação real é menor (~150-200 LOC) e parcialmente irreconciliável (validações matemáticas são únicas do `context`; infraestrutura de audit/encrypt é única do `specialists`).

## Decisão

**Adoptamos a Opção D.** Razões:

1. **Risco/valor desfavorável.** Mexer em ambos os packages para eliminar
   ~150-200 LOC de duplicação real arrasta consigo o risco de regressão
   no `workflow_classifier.py` e nos testes internos do `context` —
   quando o `pii-service` ainda está a estabilizar (ver
   `services/pii-service/LIMITACOES.md`).

2. **Isolamento natural já existe.** `neural_hive_context.pii*` não é
   importado por nenhum serviço de produção. Não há "duas
   implementações concorrentes a serem chamadas pelo mesmo caller" —
   há duas implementações usadas por consumidores **disjuntos**.

3. **Conflitos não-triviais.** O BI angolano com dois formatos
   incompatíveis e a falta de validação matemática no `specialists`
   exigem trabalho de produto/QA antes da consolidação técnica.
   Forçar uma resolução agora em vez de adiar é risco evitável.

4. **Caminho de saída claro.** Quando o pii-service for o consumidor
   canónico de toda a detecção PII no monorepo (target da spec
   2026-05-01), a Opção A torna-se viável com baixo risco. Documentar
   o pré-requisito ("pii-service estável + validações matemáticas
   portadas") é suficiente por agora.

## Plano de Saída — quando reabrir

Reabrir como ticket separado quando se verificarem **simultaneamente**:

- [ ] `pii-service` em produção a 99.9% SLA por ≥2 sprints (sem incidents).
- [ ] Validações matemáticas (Luhn, CPF check, CNH check) portadas para
      `neural_hive_specialists.compliance.pii_detector` com testes próprios.
- [ ] Resolução do conflito de BI angolano: produto decide qual formato
      é canon (preferência por `\d{9}[A-Z]{2}\d{3}` por consistência com
      o `pii_patterns.py` actual e com testes existentes).
- [ ] `workflow_classifier.py` em `neural_hive_context` migrado para
      consumir o `pii-service` via gRPC em vez do `RegexPIIDetector` local.

Quando esses 4 pontos estiverem feitos, executar:
- Eliminar `libs/neural_hive_context/src/neural_hive_context/services/pii_detector.py`
- Eliminar `libs/neural_hive_context/src/neural_hive_context/services/angolan_pii_detector.py`
- Eliminar `libs/neural_hive_context/src/neural_hive_context/models/pii.py`
- Manter `libs/neural_hive_context/src/neural_hive_context/interfaces/pii_detector.py` apenas como ABC para clientes externos
- Remover os 4 testes internos do `context` ou re-aplicá-los como testes do adapter

## Referências

- Auditoria detalhada: gerada por `feature-dev:code-explorer` agent em 2026-05-10.
- Spec: `.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md`
- Tasks: `.agent-os/specs/2026-05-01-unified-gateway-architecture/tasks.md` TICKET-013
- Ficheiros essenciais para retomar:
  - `libraries/python/neural_hive_specialists/compliance/{pii_detector,pii_patterns,pii_masker,audit_logger,compliance_layer,field_encryptor}.py`
  - `libs/neural_hive_context/src/neural_hive_context/services/{pii_detector,angolan_pii_detector,workflow_classifier}.py`
  - `libs/neural_hive_context/src/neural_hive_context/models/pii.py`
  - `libs/neural_hive_context/src/neural_hive_context/interfaces/pii_detector.py`
  - `services/pii-service/src/services/pii_service.py`
