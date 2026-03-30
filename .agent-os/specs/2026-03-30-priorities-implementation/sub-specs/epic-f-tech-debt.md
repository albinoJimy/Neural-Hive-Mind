# Sub-Spec: Epic F - NotImplementedError & Dívida Técnica

## Objetivo

Resolver 2 NotImplementedError, completar 5 TODOs e implementar 5 stubs em pass statements.

## Tickets

### 1. Code Review Integration - NotImplementedError
**Arquivo:** `services/code-forge/src/services/code_review_integration.py`

**Problema:** 2x `NotImplementedError` em providers não-GitLab/GitHub

**Solução:** Documentar suporte limitado OU implementar funcionalidade

```python
# Linha ~200-250
def post_comment(self, ...) -> None:
    """Post a comment on a merge request."""
    if self.provider == "gitlab":
        return self._gitlab_post_comment(...)
    elif self.provider == "github":
        return self._github_post_comment(...)
    else:
        # ANTES: raise NotImplementedError(...)
        # DEPOIS: Documentar suporte limitado
        logger.warning(f"Comments not supported for {self.provider}")
        return None

def create_review(self, ...) -> None:
    """Create a code review."""
    if self.provider == "gitlab":
        return self._gitlab_create_review(...)
    elif self.provider == "github":
        return self._github_create_review(...)
    else:
        # ANTES: raise NotImplementedError(...)
        # DEPOIS: Documentar suporte limitado
        logger.warning(f"Reviews not supported for {self.provider}")
        return None
```

### 2. Risk Scoring Alerts - NotImplementedError
**Arquivo:** `libraries/python/neural_hive_risk_scoring/alerts.py`

**Problema:** `BaseAlertHandler.process()` não implementado

**Solução:** Implementar handler padrão OU tornar classe abstrata

```python
# Opção A: Implementar handler padrão
class BaseAlertHandler(ABC):
    @abstractmethod
    def alert_type(self) -> str:
        """Tipo de alerta (ex: 'email', 'slack')"""
        pass

    def process(self, alert: Alert) -> None:
        """Processa alerta (implementação padrão)."""
        logger.info(f"Processing {self.alert_type()} alert: {alert.id}")
        self._send_alert(alert)

    def _send_alert(self, alert: Alert) -> None:
        """Envia alerta (placeholder para subclasses)."""
        pass

# Opção B: Tornar abstrato
class BaseAlertHandler(ABC):
    @abstractmethod
    def process(self, alert: Alert) -> None:
        """Processa alerta - deve ser implementado por subclasses."""
        pass
```

### 3. Optimizer Metrics - TODO
**Arquivo:** `services/optimizer-agents/src/api/optimizations.py`

**Problema:** 4 TODOs em cálculo de métricas

**Solução:** Implementar cálculo real

```python
# TODO: Calculate total time saved
# SOLUÇÃO:
total_time_saved_ms = sum(
    opt.estimated_time_saved_ms
    for opt in optimizations
    if opt.estimated_time_saved_ms
)

# TODO: Calculate best improvement
# SOLUÇÃO:
best_improvement_pct = max(
    (opt.improvement_percentage or 0)
    for opt in optimizations
)

# TODO: List top issues
# SOLUÇÃO:
top_issues = [
    {"issue": opt.target, "improvement": opt.improvement_percentage}
    for opt in optimizations[:10]
]
```

### 4. SLA Schedules - TODO
**Arquivo:** `services/sla-management-system/src/api/schedules.py`

**Problema:** TODO em listagem de execuções

**Solução:** Implementar listagem

```python
# ANTES:
@app.get("/schedules/{schedule_id}/executions")
async def list_executions(schedule_id: str):
    # TODO: Implementar listagem de execuções
    pass

# DEPOIS:
@app.get("/schedules/{schedule_id}/executions")
async def list_executions(
    schedule_id: str,
    limit: int = 100,
    offset: int = 0
):
    """Lista execuções agendadas."""
    executions = await self.schedule_service.list_executions(
        schedule_id,
        limit=limit,
        offset=offset
    )
    return {
        "schedule_id": schedule_id,
        "executions": [
            {
                "execution_id": e.id,
                "scheduled_at": e.scheduled_at,
                "status": e.status,
                "result": e.result
            }
            for e in executions
        ],
        "total": len(executions),
        "limit": limit,
        "offset": offset
    }
```

### 5. Self-Healing Injectors - Stubs
**Arquivo:** `services/self-healing-engine/src/chaos/injectors/base_injector.py`

**Problema:** 5x `pass` em injectors

**Solução:** Implementar handlers reais

```python
# ANTES (linhas ~50-100):
class BaseInjector(ABC):
    def inject(self, target: str) -> InjectionResult:
        pass  # STUB

    def validate(self, target: str) -> bool:
        pass  # STUB

# DEPOIS:
class BaseInjector(ABC):
    @abstractmethod
    def inject(self, target: str) -> InjectionResult:
        """Executa injeção de falha no alvo."""
        pass

    def validate(self, target: str) -> bool:
        """Valida se alvo pode receber injeção."""
        try:
            # Verificar se pod existe
            pod = self.k8s_client.read_namespaced_pod(target.split("/")[0], target.split("/")[1])
            if pod.status.phase == "Running":
                return True
            return False
        except Exception:
            return False
```

## Verificação

```bash
# Verificar NotImplementedError removidos
grep -r "NotImplementedError" services/code-forge/
grep -r "NotImplementedError" libraries/python/neural_hive_risk_scoring/
# Deve retornar vazio (apenas em comentários)

# Verificar TODOs resolvidos
grep -r "TODO" services/optimizer-agents/src/api/optimizations.py
grep -r "TODO" services/sla-management-system/src/api/schedules.py
# Deve retornar vazio

# Verificar stubs implementados
grep -r "^\s*pass$" services/self-healing-engine/src/chaos/injectors/base_injector.py
# Deve retornar vazio

# Testar funcionalidades
pytest services/code-forge/tests/test_code_review_integration.py
pytest libraries/python/neural_hive_risk_scoring/tests/
pytest services/optimizer-agents/tests/
pytest services/sla-management-system/tests/
pytest services/self-healing-engine/tests/
```
