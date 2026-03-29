# GAP-05: CORS Wildcards em Produção

**Status:** 🟡 Planejado
**Prioridade:** P1 - ALTA (Segurança)
**Esforço Estimado:** 5 dias
**Responsável:** Security Team + DevOps Team

---

## Problema

Múltiplos serviços configurados com CORS wildcard (`*`), permitindo que **qualquer origem** faça requests.

### Serviços Afetados

| Serviço | Arquivo | Tipo | Risco |
|---------|---------|------|-------|
| queen-agent | `src/config/settings.py:22` | HTTP/gRPC | ALTO |
| analyst-agents | `src/config/settings.py:17` | HTTP/gRPC | ALTO |
| software-engineering-pipeline | `src/config/settings.py:19` | HTTP | MÉDIO |
| gateway-intencoes | `src/config/settings.py:206` | HTTP | **CRÍTICO** |
| approval-service | `src/main.py:359` (hardcoded) | HTTP | ALTO |

### Risco

```
CORS: "*" → Qualquer site pode fazer requests para a API
Ataque: Site malicioso pode engajar usuários a fazer requests autenticados
Impacto: Data exfiltration, CSRF attacks
```

---

## Análise de Serviços

### Serviços PÚBLICOS (requerem CORS)

| Serviço | Origens Produção | Frontend? |
|---------|------------------|-----------|
| **gateway-intencoes** | `https://neural-hive.com`, `https://app.neural-hive.com` | ✅ Sim |
| **approval-service** | `https://approval.neural-hive.com` | ✅ Sim |

### Serviços INTERNOS (podem desabilitar CORS)

| Serviço | Protocolo Principal | CORS? |
|---------|---------------------|-------|
| queen-agent | gRPC + Kafka | ❌ Não |
| analyst-agents | gRPC + Kafka | ❌ Não |
| orchestrator-dynamic | gRPC + Kafka | ❌ Não |
| execution-ticket-service | gRPC + Kafka | ❌ Não |
| software-engineering-pipeline | HTTP interno | ❌ Não |
| sla-management-system | HTTP interno | ❌ Não |

---

## Solução

### Biblioteca Centralizada

**CRIAR:** `libraries/python/neural_hive_security/neural_hive_security/cors.py`

```python
"""CORS configuration utilities for Neural Hive Mind services."""
from typing import List

class CORSConfig:
    """Centralized CORS configuration by environment."""

    DEV_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

    STAGING_ORIGINS: List[str] = [
        "https://staging.neural-hive.local",
        "https://staging-app.neural-hive.local",
        "https://gateway-staging.neural-hive.local",
        "https://approval-staging.neural-hive.local",
        "https://grafana.neural-hive.local",
    ]

    PROD_ORIGINS: List[str] = [
        "https://neural-hive.com",
        "https://app.neural-hive.com",
        "https://gateway.neural-hive.com",
        "https://approval.neural-hive.com",
        "https://admin.neural-hive.com",
        "https://grafana.neural-hive.com",
    ]

    INTERNAL_SERVICES: List[str] = []  # Vazio = CORS desabilitado

    @classmethod
    def get_origins_for_environment(
        cls,
        environment: str,
        is_public_api: bool = False
    ) -> List[str]:
        """Get CORS origins for environment."""
        if not is_public_api:
            return cls.INTERNAL_SERVICES

        env = environment.lower()
        if env == "dev":
            return cls.DEV_ORIGINS
        elif env == "staging":
            return cls.STAGING_ORIGINS
        elif env == "prod":
            return cls.PROD_ORIGINS
        else:
            return cls.DEV_ORIGINS
```

---

## Implementação

### Passo 1: Atualizar gateway-intencoes

```python
# services/gateway-intencoes/src/config/settings.py

from neural_hive_security.cors import CORSConfig

class Settings(BaseSettings):
    # ... existente ...

    # Atualizar CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: CORSConfig.get_origins_for_environment(
            ENVIRONMENT.lower(),
            is_public_api=True  # Gateway é API pública
        )
    )
```

### Passo 2: Atualizar queen-agent (INTERNO)

```python
# services/queen-agent/src/config/settings.py

from neural_hive_security.cors import CORSConfig

class Settings(BaseSettings):
    # ... existente ...

    # Serviço interno = sem CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: CORSConfig.INTERNAL_SERVICES
    )
    IS_PUBLIC_API: bool = Field(default=False)

    @model_validator(mode='after')
    def validate_cors_in_production(self) -> 'Settings':
        """Validate CORS in production."""
        is_prod = self.ENVIRONMENT.lower() in ('production', 'prod')

        if not is_prod:
            return self

        # Internal services NÃO podem usar wildcard
        if not self.IS_PUBLIC_API and "*" in self.CORS_ORIGINS:
            raise ValueError(
                "Internal services cannot use wildcard CORS in production"
            )

        return self
```

### Passo 3: Atualizar approval-service (remover hardcoded)

```python
# services/approval-service/src/main.py

# ANTES (linha 359):
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    ...
)

# DEPOIS:
from .config.settings import get_settings

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### Passo 4: Helm Charts

```yaml
# helm-charts/gateway-intencoes/values.yaml

config:
  fastapi:
    corsOrigins:
      dev:
        - "http://localhost:3000"
        - "http://localhost:8000"
      staging:
        - "https://staging.neural-hive.local"
      prod:
        - "https://neural-hive.com"
        - "https://app.neural-hive.com"
    isPublicApi: true
```

```yaml
# helm-charts/queen-agent/values.yaml

config:
  fastapi:
    corsOrigins: []  # Interno - sem CORS
    isPublicApi: false
```

---

## Testes

### Pre-flight OPTIONS

```bash
# Test pre-flight request
curl -X OPTIONS http://gateway-intencoes:8000/api/v1/intent \
  -H "Origin: https://app.neural-hive.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" \
  -v

# Headers esperados:
# Access-Control-Allow-Origin: https://app.neural-hive.com
# Access-Control-Allow-Methods: POST, GET, OPTIONS
# Access-Control-Allow-Credentials: true
```

### Origem Permitida

```bash
# Test request from allowed origin
curl http://gateway-intencoes:8000/api/v1/intent \
  -H "Origin: https://app.neural-hive.com" \
  -H "Content-Type: application/json" \
  -v

# Esperado: Request aceita, retorna CORS header
```

### Origem Bloqueada

```bash
# Test request from blocked origin
curl http://gateway-intencoes:8000/api/v1/intent \
  -H "Origin: https://malicious-site.com" \
  -H "Content-Type: application/json" \
  -v

# Esperado: Sem CORS header (browser bloqueia)
```

### Serviço Interno

```bash
# Test internal service (sem CORS headers)
curl http://analyst-agents:8000/api/v1/insights \
  -H "Origin: https://app.neural-hive.com" \
  -v

# Esperado: Sem headers CORS
```

---

## Deploy Strategy

### Ordem (do menor para o maior impacto)

1. **analyst-agents** (interno, menor risco)
2. **queen-agent** (interno)
3. **software-engineering-pipeline** (interno)
4. **approval-service** (público, mas menos crítico)
5. **gateway-intencoes** (ÚLTIMO - mais crítico)

### Validação por Ambiente

```bash
# 1. Dev (localhost)
# Testar com http://localhost:3000

# 2. Staging
# Testar com https://staging.neural-hive.local

# 3. Produção (CANARY)
# Deploy para 1 pod primeiro
# Monitorar por 1 hora
# Restante dos pods
```

---

## Rollback Plan

```bash
# Rollback individual
helm rollback gateway-intencoes -n neural-hive-mind

# Rollback via ConfigMap override
kubectl create configmap cors-emergency-override \
  --from-literal=CORS_ORIGINS='["*"]' \
  -n neural-hive-mind
```

---

## Checklist

**Pre-Implementação:**
- [ ] Biblioteca CORS criada
- [ ] Services PÚBLICOS identificados
- [ ] Services INTERNOS identificados
- [ ] Origens por ambiente definidas
- [ ] Testes escritos

**Pos-Implementação:**
- [ ] Wildcards removidos de produção
- [ ] Serviços públicos com origens explícitas
- [ ] Serviços internos com CORS desabilitado
- [ ] Validators de produção ativos
- [ ] Testes executados em staging
- [ ] Frontends validados
- [ ] Monitoramento ativo

---

## Arquivos Críticos

| Ação | Arquivo |
|------|---------|
| **CRIAR** | `libraries/python/neural_hive_security/neural_hive_security/cors.py` |
| **MODIFICAR** | `services/gateway-intencoes/src/config/settings.py` |
| **MODIFICAR** | `services/queen-agent/src/config/settings.py` |
| **MODIFICAR** | `services/approval-service/src/main.py` |
| **MODIFICAR** | `helm-charts/*/values.yaml` |

---

**Documento baseado em análise do agente Plan (2026-03-29)**
