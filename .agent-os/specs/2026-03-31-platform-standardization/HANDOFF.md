# Handoff - Platform Standardization Spec

**Para:** Claude Code (Execution)
**Data:** 2026-03-31
**Spec:** 2026-03-31-platform-standardization

---

## 🎯 Objetivo da Spec

Padronizar completamente a plataforma Neural-Hive-Mind para aumentar consistência de 72% para 94% e reduzir Risk Score de 7.2 para 2.5.

---

## 📁 Estrutura da Spec

```
.agent-os/specs/2026-03-31-platform-standardization/
├── spec.md                 # Requisitos completos
├── spec-lite.md            # Resumo executivo
├── tasks.md                # 16 tarefas detalhadas
├── HANDOFF.md              # Este documento
└── sub-specs/
    └── technical-spec.md    # Especificação técnica
```

---

## 🚀 Como Executar

### Opção 1: Execução Completa (Recomendado)

Usar **subagent-driven-development** skill:

```
/skill superpowers:subagent-driven-development
```

Esse skill irá:
1. Dispachar um subagente por tarefa
2. Fazer review de conformidade com spec após cada tarefa
3. Fazer review de qualidade de código após cada tarefa
4. Marcar tarefas como completas

### Opção 2: Execução Inline

Usar **executing-plans** skill:

```
/skill superpowers:executing-plans
```

---

## 📋 Tarefas por Ordem de Prioridade

### 🔴 CRÍTICO - Fase 0 (48h)

1. **SEC-001:** Padronizar OpenTelemetry v1.29.0
2. **SEC-002:** Implementar security scans (Trivy)
3. **SEC-003:** Remover secrets padrão
4. **SEC-004:** Habilitar HTTPS

### 🟡 ALTA - Fase 1 (1-2 semanas)

5. **PAD-001:** Nomenclatura gRPC consistente
6. **PAD-002:** Endpoints REST kebab-case
7. **PAD-003:** Health check único (/health)
8. **VER-001:** requirements-base.txt
9. **VER-002:** Python 3.12 padronizado
10. **PAD-004:** Tópicos Kafka padronizados

### 🟢 MÉDIA - Fase 2 (3-4 semanas)

11. **BIB-001:** Biblioteca exceções
12. **BIB-002:** BaseInfrastructureSettings
13. **LOG-001:** Migrar para structlog
14. **TYP-001:** Completar type hints
15. **DOCKER-001:** Base image única
16. **DEVOPS-001:** Implementar Dependabot

---

## ⚠️ Pontos de Atenção

### 1. Dependências Críticas
- Tarefas SEC-001 a SEC-004 devem ser feitas PRIMEIRO
- Não prosseguir para Fase 1 sem completar Fase 0

### 2. Serviços Afetados
- **16 serviços** Python diferentes
- **4 clientes gRPC** para renomear
- **10+ health checks** para padronizar

### 3. Riscos
- Mudanças em OpenTelemetry podem quebrar tracing
- Mudanças em dependências podem causar conflitos
- SEMPRE testar após cada mudança

---

## 🧪 Validação

### Testes Obrigatórios Após Cada Tarefa
```bash
# 1. Unit tests
pytest services/nome-servico/tests/

# 2. Integration tests (se existir)
pytest tests/integration/

# 3. Build Docker
docker-compose build nome-servico

# 4. Security scan (pós Fase 0)
trivy image nome-servico:latest
```

---

## 📊 Métricas de Sucesso

| Métrica | Antes | Meta | Como Medir |
|---------|-------|------|-------------|
| Consistência Global | 72/100 | 94/100 | Análise automatizada |
| Security Score | 40/100 | 90/100 | Trivy scans |
| OpenTelemetry Versions | 6 | 1 | grep requirements.txt |
| Health Check Padrão | 40% | 100% | grep -r "GET /health" |
| Python Version | 3.11+3.12 | 3.12 | grep Dockerfile |

---

## 🔗 Referências Úteis

- **Análise completa:** `docs/RELATORIO_CONSOLIDADO_PADRONIZACAO_2026-03-31.md`
- **Checklist:** `docs/CHECKLIST_PADRONIZACAO.md`
- **Technical spec:** `sub-specs/technical-spec.md`
- **Task list:** `tasks.md`

---

## ✅ Pré-requisitos

Antes de começar:
1. Ler `spec.md` para contexto completo
2. Ler `tasks.md` para lista detalhada
3. Ler `sub-specs/technical-spec.md` para detalhes técnicos

---

## 🎯 Comando para Iniciar

```bash
# Opção 1: Subagent-driven (recomendado)
/skill superpowers:subagent-driven-development

# Opção 2: Executing-plans
/skill superpowers:executing-plans

# Depois, seguir instruções do skill
```

---

**Boa sorte! 🚀**
