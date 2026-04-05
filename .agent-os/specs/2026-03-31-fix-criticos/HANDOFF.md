# Handoff para Claude Code - Fix Críticos Sprint 1

**Data:** 2026-03-31
**Spec:** 2026-03-31-fix-criticos
**Status:** Ready for Execution

---

## Resumo Executivo

Estrutura completa de specs criada para corrigir 45 issues críticos identificados na análise profunda dos 26 serviços do Neural-Hive-Mind. Implementação dividida em 4 epics com 139 tarefas decompostas.

---

## Estrutura de Arquivos Criada

```
.agent-os/specs/2026-03-31-fix-criticos/
├── spec.md                          # Spec principal
├── spec-lite.md                     # Resumo executivo
├── tasks.md                         # 139 tarefas decompostas
├── HANDOFF.md                       # Este arquivo
└── sub-specs/
    ├── epic-001-test-criticalos.md  # Fix Test Críticos (91 testes)
    ├── epic-002-pydantic-v2.md      # Pydantic V2 Migration (34 validators)
    ├── epic-003-datetime-migration.md  # datetime.utcnow() (1,547 ocorrências)
    └── epic-004-fastmcp-fix.md      # FastMCP API Fix (4 servidores)
```

---

## Como Executar

### Opção 1: Executar Epic Completo

```bash
# No terminal Claude Code
@~/.agent-os/instructions/execute-tasks.md

Espec: .agent-os/specs/2026-03-31-fix-criticos/
Epic: EPIC-001 (ou EPIC-002, EPIC-003, EPIC-004)
```

### Opção 2: Executar Ticket Específico

```bash
@~/.agent-os/instructions/execute-tasks.md

Espec: .agent-os/specs/2026-03-31-fix-criticos/
Ticket: EPIC-001-01 (Fix worker-agents import errors)
```

### Opção 3: Executar Tarefa Individual

```bash
@~/.agent-os/instructions/execute-task.md

Espec: .agent-os/specs/2026-03-31-fix-criticos/
Tarefa: 1.2 (Modificar src/executors/deploy_executor.py)
```

---

## Epics e Tamanhos

| Epic | Descrição | Effort | Tasks |
|------|-----------|--------|-------|
| EPIC-001 | Fix Test Críticos | 4 semanas | 38 |
| EPIC-002 | Pydantic V2 Migration | 2 semanas | 22 |
| EPIC-003 | datetime.utcnow() Migration | 2 semanas | 25 |
| EPIC-004 | FastMCP API Fix | 2 dias | 14 |
| **TOTAL** | | **8 semanas** | **139** |

---

## Ordem de Execução Recomendada

### Fase 1: Quick Wins (Semana 1)
1. **EPIC-004** (FastMCP) - 2 dias
   - Mais simples (apenas 4 linhas)
   - Desbloqueia MCP servers imediatamente
   - Alto impacto visual

### Fase 2: Test Críticos (Semanas 1-2)
2. **EPIC-001-01** (worker-agents) - 1 semana
3. **EPIC-001-02** (semantic-translation-engine NLP) - 1 semana
   - Podem ser feitos em paralelo
   - Desbloqueiam CI/CD

### Fase 3: Pydantic Migration (Semanas 3-4)
4. **EPIC-002** (Pydantic V2) - 2 semanas
   - Elimina warnings de deprecation
   - Prepara para futuro

### Fase 4: datetime Migration (Semanas 5-6)
5. **EPIC-003-01 + EPIC-003-02** (datetime P0/P1) - 1 semana
   - Serviços críticos e altos

### Fase 5: Refactor Tests (Semanas 5-7)
6. **EPIC-001-03** (specialist-behavior) - 2 semanas
   - Refactor mais complexo
   - Pode começar durante Fase 4

### Fase 6: Finalização (Semana 8)
7. **EPIC-003-03** (datetime P2/P3) - 2 dias
8. Testes globais e validação

---

## Scripts Auxiliares

### Migração datetime

```python
# scripts/migrate_datetime.py
import re
from pathlib import Path

def migrate_datetime_utcnow(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    original = content

    # Adicionar timezone import
    if 'timezone' not in content and 'from datetime import' in content:
        content = re.sub(
            r'from datetime import datetime',
            'from datetime import datetime, timezone',
            content
        )

    # Substituir datetime.utcnow()
    content = re.sub(
        r'datetime\.utcnow\(\)',
        'datetime.now(timezone.utc)',
        content
    )

    if content != original:
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    return False

for service in ['orchestrator-dynamic', 'optimizer-agents']:
    for py_file in Path(f'services/{service}/src').rglob('*.py'):
        migrate_datetime_utcnow(py_file)
```

### Verificação Final

```bash
#!/bin/bash
# Verificar migrações completas

echo "=== datetime.utcnow() ==="
grep -r "datetime\.utcnow()" services/ --include="*.py" | grep -v test | wc -l

echo "=== @validator ==="
grep -r "@validator" services/ --include="*.py" | grep -v test | wc -l

echo "=== FastMCP description ==="
grep -r "FastMCP.*description=" services/mcp-servers/ --include="*.py" | wc -l
```

---

## Critérios de Sucesso

### EPIC-001: Test Críticos
- [ ] 0 testes falhando em worker-agents
- [ ] 0 testes NLP falhando em semantic-translation-engine
- [ ] >70% coverage real em specialist-behavior
- [ ] CI/CD verde

### EPIC-002: Pydantic V2
- [ ] 0 @validator remanescentes
- [ ] 0 warnings de deprecation Pydantic
- [ ] Todos os serviços testando

### EPIC-003: datetime Migration
- [ ] 0 datetime.utcnow() em código fonte
- [ ] Todos os timestamps timezone-aware
- [ ] Dados em banco validados

### EPIC-004: FastMCP
- [ ] 0 erros de inicialização MCP servers
- [ ] Todos os servidores respondendo
- [ ] Ferramentas MCP acessíveis

---

## Dependências Externas

### Para EPIC-001-02 (NLP Tests)
```bash
pip install numpy==1.26.4
python3 -m spacy download en_core_web_sm
python3 -m spacy download pt_core_news_sm
```

### Para EPIC-004 (FastMCP)
```txt
# requirements.txt
fastmcp>=3.0.0  # API estável
```

---

## Comandos Úteis

### Verificar progresso por Epic
```bash
# EPIC-001
pytest services/worker-agents/tests/ -v
pytest services/semantic-translation-engine/tests/ -v
pytest services/specialist-behavior/tests/ --cov

# EPIC-002
grep -r "@validator" services/ --include="*.py"

# EPIC-003
grep -r "datetime\.utcnow()" services/ --include="*.py"

# EPIC-004
python3 -m services.mcp-servers.scout-mcp-server.src.main
```

---

## Contingências

### Se EPIC-001-02 (NLP) falhar
- Usar fallback heurístico temporariamente
- Considerar upgrade spaCy para 3.8+ (não testado)
- Desabilitar testes NLP temporariamente

### Se EPIC-003 (datetime) causar problemas
- Reverter serviços individualmente
- Validar timestamps em banco antes de cada commit
- Usar migração incremental por serviço

### Se EPIC-002 (Pydantic) quebrar validações
- Verificar se mode='before' ou mode='after' está correto
- Reverter @model_validator problemáticos
- Usar field_validator para validações simples

---

## Próximos Passos

1. **Revisar specs** - Ler todas as sub-specs
2. **Priorizar** - Confirmar ordem de execução
3. **Iniciar** - Começar com EPIC-004 (quick win)
4. **Monitorar** - Track progresso em tasks.md
5. **Validar** - CI/CD verde após cada Epic

---

## Documentos de Referência

- Análise completa: `docs/RELATORIO_FINAL_COMPILADO_2026-03-31.md`
- Dashboard: `docs/DASHBOARD_FINAL_2026-03-31.md`
- Issues críticos: Identificados na análise de 26 serviços

---

**Status:** ✅ Specs prontas para execução
**Handoff Completo:** 2026-03-31
**Próxima Ação:** Executar EPIC-004 (FastMCP Fix)
