# EPIC-003: datetime.utcnow() Migration

**ID:** EPIC-003
**Status:** Pending
**Priority:** P1 - Alta
**Effort:** XL (2 semanas)
**Related Services:** 21 serviços com 1,547 ocorrências

---

## Resumo Executivo

Migrar `datetime.utcnow()` para `datetime.now(timezone.utc)` em 21 serviços (1,547 ocorrências). O método `datetime.utcnow()` foi removido no Python 3.12+, tornando esta migração crítica para compatibilidade futura.

---

## Análise Técnica

### Serviços por Prioridade

| Priority | Service | Ocorrências | Risco |
|----------|---------|-------------|-------|
| 🔴 P0 | orchestrator-dynamic | 215 | Crítico |
| 🔴 P0 | optimizer-agents | 110 | Crítico |
| 🔴 P0 | semantic-translation-engine | 109 | Crítico |
| 🔴 P0 | sla-management-system | 98 | Crítico |
| 🔴 P0 | self-healing-engine | 83 | Crítico |
| 🟡 P1 | memory-layer-api | 77 | Alto |
| 🟡 P1 | approval-service | 63 | Alto |
| 🟡 P1 | scout-agents | 53 | Alto |
| 🟡 P1 | analyst-agents | 49 | Alto |
| 🟢 P2 | code-forge | 35 | Médio |
| 🟢 P2 | explainability-api | 30 | Médio |
| 🟢 P2 | guard-agents | 17 | Médio |
| 🟢 P2 | gateway-intencoes | 17 | Médio |
| 🟢 P2 | queen-agent | 12 | Médio |
| 🟢 P2 | worker-agents | 11 | Médio |
| 🟢 P3 | execution-ticket-service | 8 | Baixo |
| 🟢 P3 | architect-agent | 8 | Baixo |
| 🟢 P3 | consensus-engine | 6 | Baixo |
| 🟢 P3 | feature-store | 4 | Baixo |
| 🟢 P3 | service-registry | 3 | Baixo |
| 🟢 P3 | mcp-tool-catalog | 3 | Baixo |

### Padrões de Uso Identificados

#### Padrão 1: Timestamp Simples
```python
# ANTES
created_at = datetime.utcnow()
timestamp = datetime.utcnow().timestamp()

# DEPOIS
created_at = datetime.now(timezone.utc)
timestamp = datetime.now(timezone.utc).timestamp()
```

#### Padrão 2: Cálculos Temporais
```python
# ANTES
start_time = datetime.utcnow()
elapsed = datetime.utcnow() - start_time

# DEPOIS
start_time = datetime.now(timezone.utc)
elapsed = datetime.now(timezone.utc) - start_time
```

#### Padrão 3: com timedelta
```python
# ANTES
expiry = datetime.utcnow() + timedelta(hours=1)
deadline = datetime.utcnow() + timedelta(days=7)

# DEPOIS
expiry = datetime.now(timezone.utc) + timedelta(hours=1)
deadline = datetime.now(timezone.utc) + timedelta(days=7)
```

---

## Ticket EPIC-003-01: Migrate Priority P0 Services

**ID:** TICKET-EPIC-003-01
**Priority:** P0
**Effort:** M (5 dias)
**Services:** orchestrator-dynamic, optimizer-agents, semantic-translation-engine, sla-management-system, self-healing-engine

### Abordagem: Migração Automatizada

**Script de Migração:**
```python
#!/usr/bin/env python3
"""
Migração datetime.utcnow() -> datetime.now(timezone.utc)
"""
import re
from pathlib import Path

def migrate_datetime_utcnow(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    original = content

    # 1. Adicionar timezone import se necessário
    if 'timezone' not in content and 'from datetime import' in content:
        content = re.sub(
            r'from datetime import datetime',
            'from datetime import datetime, timezone',
            content
        )

    # 2. Substituir datetime.utcnow()
    content = re.sub(
        r'datetime\.utcnow\(\)',
        'datetime.now(timezone.utc)',
        content
    )

    # 3. Salvar apenas se modificou
    if content != original:
        with open(file_path, 'w') as f:
            f.write(content)
        print(f"✅ Migrated: {file_path}")
        return True
    return False

# Executar
services = [
    'orchestrator-dynamic',
    'optimizer-agents',
    'semantic-translation-engine',
    'sla-management-system',
    'self-healing-engine'
]

for service in services:
    service_path = Path(f'services/{service}/src')
    for py_file in service_path.rglob('*.py'):
        migrate_datetime_utcnow(py_file)
```

### Passo a Passo

1. **Backup dos serviços**
```bash
cd services
for svc in orchestrator-dynamic optimizer-agents semantic-translation-engine sla-management-system self-healing-engine; do
    tar -czf ${svc}-backup-$(date +%Y%m%d).tar.gz ${svc}/
done
```

2. **Executar script de migração**
```bash
python3 scripts/migrate_datetime.py
```

3. **Validar imports**
```bash
# Verificar se timezone foi importado
grep -r "from datetime import.*timezone" services/*/src/

# Verificar se não há mais utcnow()
grep -r "datetime\.utcnow()" services/*/src/
```

4. **Executar testes**
```bash
pytest services/orchestrator-dynamic/tests/ -v
pytest services/optimizer-agents/tests/ -v
pytest services/semantic-translation-engine/tests/ -v
pytest services/sla-management-system/tests/ -v
pytest services/self-healing-engine/tests/ -v
```

### Critérios de Aceite
- [ ] Zero ocorrências de `datetime.utcnow()`
- [ ] `timezone` importado onde necessário
- [ ] Todos os testes passando
- [ ] Timestamps corretos em banco de dados

---

## Ticket EPIC-003-02: Migrate Priority P1 Services

**ID:** TICKET-EPIC-003-02
**Priority:** P1
**Effort:** M (3 dias)
**Services:** memory-layer-api, approval-service, scout-agents, analyst-agents

### Mesma Abordagem

Usar script automatizado com serviços P1.

### Validações Específicas

**memory-layer-api:** Verificar timestamps em vetores e embeddings
```bash
# Verificar timestamps nos vetores
python3 -c "
from services.memory_layer_api.src.repositories.vector_repository import VectorRepository
# Timestamps devem ser timezone-aware
"
```

**approval-service:** Verificar timestamps em feedbacks
```bash
# Verificar specialist_feedback timestamps
python3 -c "
from services.approval_service.src.models.approval import PlanApproval
# created_at e updated_at devem ser UTC
"
```

### Critérios de Aceite
- [ ] Zero ocorrências de `datetime.utcnow()`
- [ ] Testes passando
- [ ] Timestamps em banco validados

---

## Ticket EPIC-003-03: Migrate Priority P2/P3 Services

**ID:** TICKET-EPIC-003-03
**Priority:** P2
**Effort:** S (2 dias)
**Services:** code-forge, explainability-api, guard-agents, gateway-intencoes, queen-agent, worker-agents, execution-ticket-service, architect-agent, consensus-engine, feature-store, service-registry, mcp-tool-catalog

### Mesma Abordagem

Usar script automatizado com serviços restantes.

### Critérios de Aceite
- [ ] Zero ocorrências em todos os serviços
- [ ] Todos os testes passando
- [ ] CI/CD verde

---

## Validação Global

### Script de Verificação Final

```bash
#!/bin/bash
# Verificar migração completa

echo "=== Verificando datetime.utcnow() remanescentes ==="
REMANESCENTES=$(grep -r "datetime\.utcnow()" services/ --include="*.py" | grep -v test | grep -v __pycache__ | wc -l)

if [ $REMANESCENTES -eq 0 ]; then
    echo "✅ Nenhuma ocorrência remanescente"
else
    echo "❌ Ainda há $REMANESCENTES ocorrências"
    grep -r "datetime\.utcnow()" services/ --include="*.py" | grep -v test | grep -v __pycache__
    exit 1
fi

echo "=== Verificando imports timezone ==="
TIMEZONE_IMPORTS=$(grep -r "from datetime import.*timezone" services/ --include="*.py" | wc -l)
echo "✅ $TIMEZONE_IMPORTS imports timezone encontrados"

echo "=== Executando testes de smoke ==="
for svc in orchestrator-dynamic optimizer-agents semantic-translation-engine; do
    echo "Testing $svc..."
    pytest services/$svc/tests/ -q --tb=no || exit 1
done

echo "✅ Migração datetime completa!"
```

---

## Impactos e Riscos

### Impactos Positivos
- Compatibilidade com Python 3.12+
- Timestamps timezone-aware corretos
- Eliminação de warnings de deprecation

### Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Timestamps em banco mudam | Baixa | Alto | Validar schema e dados |
| Dados históricos afetados | Baixa | Médio | Migration script |
| Testes quebram | Média | Baixo | Mocks ajustados |

---

## Resumo do Epic

| Ticket | Services | Effort | Ocorrências |
|--------|----------|--------|-------------|
| EPIC-003-01 | P0 (5 serviços) | 5 dias | 615 |
| EPIC-003-02 | P1 (4 serviços) | 3 dias | 242 |
| EPIC-003-03 | P2/P3 (12 serviços) | 2 dias | 690 |
| **TOTAL** | **21 serviços** | **10 dias** | **1,547** |

---

## Ordem de Execução

1. **Dia 1-5:** EPIC-003-01 (P0 - serviços críticos)
2. **Dia 6-8:** EPIC-003-02 (P1 - serviços altos)
3. **Dia 9-10:** EPIC-003-03 (P2/P3 - restantes)
4. **Dia 11-12:** Testes globais e validação

---

## Handoff para Claude Code

Para executar este Epic, use:
```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-003 - datetime.utcnow() Migration
Tickets: EPIC-003-01, EPIC-003-02, EPIC-003-03
Script: scripts/migrate_datetime.py
```
