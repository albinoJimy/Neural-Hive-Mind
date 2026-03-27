# Phase 1: Segurança Crítica — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover JWT secret hardcoded e CORS wildcard do gateway-intencoes para mitigar vulnerabilidades de segurança críticas.

**Architecture:**
1. Modificar `auth.py` para usar JWT_SECRET do settings em vez de "secret" hardcoded
2. Modificar `settings.py` para tornar jwt_secret_key e allowed_origins obrigatórios (required Field)
3. Adicionar validator em settings para parsear CORS_ORIGINS de string para lista
4. Adicionar validação no startup (bootstrap.py) que lança SettingsError se vars faltarem
5. Criar .env.example com template obrigatório
6. Atualizar README do serviço

**Tech Stack:** FastAPI, Pydantic Settings, python-dotenv, pytest

---

## File Structure

**Files to modify:**
- `services/gateway-intencoes/src/security/auth.py` — Remover hardcoded "secret"
- `services/gateway-intencoes/src/config/settings.py` — Required fields + validator
- `services/gateway-intencoes/src/bootstrap.py` — Startup validation
- `services/gateway-intencoes/src/main.py` — Usar allowed_origins do settings
- `services/gateway-intencoes/.env.example` — NOVO: template de environment
- `services/gateway-intencoes/README.md` — Atualizar instruções

**Tests to create:**
- `services/gateway-intencoes/tests/unit/test_auth_security.py` — NOVO: testes JWT com env var
- `services/gateway-intencoes/tests/unit/test_settings_security.py` — NOVO: testes validação

---

## Task 1: Teste para JWT via Environment Variable

**Files:**
- Create: `services/gateway-intencoes/tests/unit/test_auth_security.py`

- [ ] **Step 1: Criar ficheiro de teste com importações**

```python
"""Unit tests for JWT security - environment variables"""
import pytest
from unittest.mock import patch, Mock
from src.security.auth import verify_token, get_current_user
```

- [ ] **Step 2: Escrever teste para verify_token com env var**

```python
@pytest.mark.asyncio
async def test_verify_token_uses_secret_from_settings():
    """Test that verify_token uses JWT_SECRET from settings"""
    mock_settings = Mock()
    mock_settings.jwt_secret_key = "test-secret-from-env"

    with patch('src.security.auth.settings', mock_settings):
        # Create a valid token with the same secret
        import jwt
        test_payload = {'sub': 'user123', 'exp': 9999999999}
        test_token = jwt.encode(test_payload, "test-secret-from-env", algorithm="HS256")

        # Should decode successfully
        result = await verify_token(test_token)
        assert result['sub'] == 'user123'
```

- [ ] **Step 3: Escrever teste para token inválido**

```python
@pytest.mark.asyncio
async def test_verify_token_raises_for_invalid_token():
    """Test that verify_token raises HTTPException for invalid tokens"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await verify_token("invalid-token")

    assert exc_info.value.status_code == 401
    assert "Token inválido" in exc_info.value.detail
```

- [ ] **Step 4: Rodar testes para verificar falham (auth.py ainda usa hardcoded secret)**

Run: `cd services/gateway-intencoes && pytest tests/unit/test_auth_security.py -v`

Expected: FAIL - verify_token ainda usa "secret" hardcoded

- [ ] **Step 5: Commit dos testes**

```bash
git add services/gateway-intencoes/tests/unit/test_auth_security.py
git commit -m "test(gateway): add JWT security tests"
```

---

## Task 2: Modificar auth.py para usar JWT_SECRET do settings

**Files:**
- Modify: `services/gateway-intencoes/src/security/auth.py:7-16`

- [ ] **Step 1: Ler ficheiro auth.py**

Execute: `cat services/gateway-intencoes/src/security/auth.py`

Current line 11: `payload = jwt.decode(token, "secret", algorithms=["HS256"])`

- [ ] **Step 2: Importar settings**

Add import at top of file:

```python
from config.settings import get_settings
```

- [ ] **Step 3: Modificar verify_token para usar settings.jwt_secret_key**

Replace line 11:

```python
# Before:
payload = jwt.decode(token, "secret", algorithms=["HS256"])

# After:
settings = get_settings()
payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
```

- [ ] **Step 4: Rodar testes para verificar passam**

Run: `cd services/gateway-intencoes && pytest tests/unit/test_auth_security.py -v`

Expected: PASS (todos testes passam)

- [ ] **Step 5: Rodar todos os testes existentes para garantir compatibilidade**

Run: `cd services/gateway-intencoes && pytest tests/unit/test_oauth2_validator.py -v`

Expected: PASS (testes existentes continuam a funcionar)

- [ ] **Step 6: Commit**

```bash
git add services/gateway-intencoes/src/security/auth.py
git commit -m "fix(gateway): use JWT_SECRET from settings instead of hardcoded 'secret'"
```

---

## Task 3: Testes para Settings Validation

**Files:**
- Create: `services/gateway-intencoes/tests/unit/test_settings_security.py`

- [ ] **Step 1: Criar ficheiro de teste**

```python
"""Unit tests for Settings security validation"""
import pytest
from pydantic import ValidationError
from src.config.settings import Settings

def test_jwt_secret_key_required_in_production():
    """Test that jwt_secret_key is required in production"""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            environment="prod",
            # jwt_secret_key intentionally omitted
        )

    assert "jwt_secret_key" in str(exc_info.value).lower()

def test_cors_origins_parse_from_string():
    """Test that CORS_ORIGINS string is parsed to list"""
    settings = Settings(
        environment="dev",
        jwt_secret_key="test-secret",
        allowed_origins="http://localhost:3000,https://example.com"
    )

    assert settings.allowed_origins == ["http://localhost:3000", "https://example.com"]

def test_cors_origins_accepts_list():
    """Test that allowed_origins accepts list directly"""
    settings = Settings(
        environment="dev",
        jwt_secret_key="test-secret",
        allowed_origins=["http://localhost:3000", "https://example.com"]
    )

    assert settings.allowed_origins == ["http://localhost:3000", "https://example.com"]

def test_cors_origins_default_removed():
    """Test that wildcard '*' is no longer the default"""
    # This test ensures settings require explicit CORS configuration
    with pytest.raises(ValidationError):
        Settings(
            environment="prod",
            jwt_secret_key="test-secret"
            # allowed_origins omitted - should fail
        )
```

- [ ] **Step 2: Rodar testes para verificar falham**

Run: `cd services/gateway-intencoes && pytest tests/unit/test_settings_security.py -v`

Expected: FAIL - settings.py ainda tem defaults inseguros

- [ ] **Step 3: Commit**

```bash
git add services/gateway-intencoes/tests/unit/test_settings_security.py
git commit -m "test(gateway): add settings security validation tests"
```

---

## Task 4: Modificar settings.py para campos obrigatórios

**Files:**
- Modify: `services/gateway-intencoes/src/config/settings.py:198-204`

- [ ] **Step 1: Remover defaults inseguros de jwt_secret_key e allowed_origins**

Find lines 198-204:

```python
# Segurança (mantido para compatibilidade)
jwt_secret_key: str = Field(default="your-secret-key")
jwt_algorithm: str = Field(default="HS256")

# CORS e hosts
allowed_origins: List[str] = Field(default=["*"])
allowed_hosts: List[str] = Field(default=["*"])
```

Replace with:

```python
# Segurança (OBRIGATÓRIO em production)
jwt_secret_key: str = Field(
    ...,
    description="JWT secret key (OBRIGATÓRIO - usar valor forte em produção)"
)
jwt_algorithm: str = Field(default="HS256")

# CORS e hosts (OBRIGATÓRIO)
allowed_origins: List[str] = Field(
    ...,
    description="CORS allowed origins (comma-separated string or list). Use ['*'] ONLY for development."
)
allowed_hosts: List[str] = Field(
    default=["*"],
    description="Allowed hosts for TrustedHostMiddleware"
)
```

- [ ] **Step 2: Adicionar validator para parsear allowed_origins string**

Add after line 267 (after validate_routing_thresholds validator):

```python
@validator("allowed_origins", pre=True)
def parse_cors_origins(cls, v):
    """Parse CORS_ORIGINS from comma-separated string to list."""
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(",")]
    return v
```

- [ ] **Step 3: Rodar testes de settings**

Run: `cd services/gateway-intencoes && pytest tests/unit/test_settings_security.py -v`

Expected: PASS (settings agora requer campos obrigatórios)

- [ ] **Step 4: Commit**

```bash
git add services/gateway-intencoes/src/config/settings.py
git commit -m "fix(gateway): make jwt_secret_key and allowed_origins required"
```

---

## Task 5: Startup Validation no Bootstrap

**Files:**
- Modify: `services/gateway-intencoes/src/bootstrap.py`

- [ ] **Step 1: Ler ApplicationBootstrapper**

Execute: `cat services/gateway-intencoes/src/bootstrap.py | head -150`

- [ ] **Step 2: Adicionar fase de validação de segurança**

Add new phase class after line 103 (after InfrastructurePhase class):

```python
class SecurityValidationPhase(InitializationPhase):
    """Fase 0: Validação de configurações de segurança OBRIGATÓRIAS."""

    def __init__(self, settings):
        super().__init__("security_validation", required=True)
        self.settings = settings

    async def execute(self, context: ApplicationContext) -> bool:
        """Valida que variáveis de segurança obrigatórias estão definidas."""
        try:
            logger.info("phase_security_validation_start")

            # Verificar JWT secret não é o default (que não existe mais, mas defensive check)
            if self.settings.jwt_secret_key in ("", "your-secret-key", "secret", "change-me"):
                error_msg = (
                    "JWT_SECRET_KEY não está configurado corretamente. "
                    "Use uma string forte e única em produção."
                )
                logger.error("phase_security_validation_failed", reason="invalid_jwt_secret")
                context.errors.append(error_msg)
                return False

            # Verificar CORS não é wildcard em produção
            if self.settings.environment in ("production", "prod"):
                if "*" in self.settings.allowed_origins:
                    error_msg = (
                        "CORS wildcard (*) não é permitido em produção. "
                        "Configure ALLOWED_ORIGINS com domínios específicos."
                    )
                    logger.error("phase_security_validation_failed", reason="cors_wildcard_in_prod")
                    context.errors.append(error_msg)
                    return False

            logger.info("phase_security_validation_complete")
            return True

        except Exception as e:
            error_msg = f"Security validation phase failed: {str(e)}"
            logger.error("phase_security_validation_failed", error=str(e), exc_info=True)
            context.errors.append(error_msg)
            return False
```

- [ ] **Step 3: Adicionar SecurityValidationPhase ao ApplicationBootstrapper**

Find the `bootstrap()` method in ApplicationBootstrapper class (around line 150+):

Add the security phase BEFORE infrastructure phase:

```python
# Find this line in bootstrap() method:
phases = [
    InfrastructurePhase(self.settings),
    # ... other phases
]

# Change to:
phases = [
    SecurityValidationPhase(self.settings),  # PRIMEIRO: validar segurança
    InfrastructurePhase(self.settings),
    # ... other phases
]
```

- [ ] **Step 4: Rodar teste manual de startup com vars faltando**

Run: `cd services/gateway-intencoes && python -c "from src.config.settings import Settings; Settings()"`

Expected: ValidationError (jwt_secret_key é obrigatório)

- [ ] **Step 5: Commit**

```bash
git add services/gateway-intencoes/src/bootstrap.py
git commit -m "feat(gateway): add security validation phase on startup"
```

---

## Task 6: Modificar main.py para usar allowed_origins do settings

**Files:**
- Modify: `services/gateway-intencoes/src/main.py:336-346`

- [ ] **Step 1: Remover hardcoded CORS middleware**

Find lines 336-346:

```python
# Middleware de CORS - deve ser o PRIMEIRO middleware adicionado
# em produção, considere limitar allow_origins para domínios específicos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, usar domínios específicos
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Type", "X-Request-ID"],
    max_age=600,
)
```

Replace with:

```python
# Middleware de CORS - configurado via ALLOWED_ORIGINS environment variable
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # From settings, not hardcoded
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Type", "X-Request-ID"],
    max_age=600,
)
```

- [ ] **Step 2: Commit**

```bash
git add services/gateway-intencoes/src/main.py
git commit -m "fix(gateway): use allowed_origins from settings instead of wildcard"
```

---

## Task 7: Criar .env.example

**Files:**
- Create: `services/gateway-intencoes/.env.example`

- [ ] **Step 1: Criar ficheiro .env.example**

```bash
# Environment Configuration - Gateway de Intenções
# Copie este ficheiro para .env e preencha com valores reais

# ============================================
# SEGURANÇA CRÍTICA - OBRIGATÓRIO
# ============================================

# JWT Secret Key - OBRIGATÓRIO
# Use uma string forte e única em produção (mínimo 32 caracteres)
# Exemplo de geração: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=change-me-to-a-strong-random-string-in-production

# CORS Allowed Origins - OBRIGATÓRIO
# Lista de origens permitidas separadas por vírgula
# Em desenvolvimento: http://localhost:3000
# Em produção: https://app.example.com,https://admin.example.com
# NUNCA use "*" em produção!
CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# ============================================
# Ambiente
# ============================================
ENVIRONMENT=dev
DEBUG=false
LOG_LEVEL=INFO

# ============================================
# Kafka
# ============================================
KAFKA_BOOTSTRAP_SERVERS=neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092
SCHEMA_REGISTRY_URL=https://schema-registry.neural-hive-kafka.svc.cluster.local:8081

# ============================================
# Redis
# ============================================
REDIS_CLUSTER_NODES=neural-hive-cache.redis-cluster.svc.cluster.local:6379
REDIS_PASSWORD=

# ============================================
# OAuth2 / Keycloak
# ============================================
KEYCLOAK_URL=https://keycloak.neural-hive.local
KEYCLOAK_REALM=neural-hive
KEYCLOAK_CLIENT_ID=gateway-intencoes
KEYCLOAK_CLIENT_SECRET=

# ============================================
# Rate Limiting
# ============================================
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=1000
RATE_LIMIT_BURST_SIZE=100

# ============================================
# PII Masking
# ============================================
ENABLE_PII_MASKING=true
PII_MASKING_STRATEGY=partial
PII_MASKING_SPACY_MODEL=pt_core_news_sm
```

- [ ] **Step 2: Adicionar .env.example ao .gitignore (se ainda não estiver)**

Check: `cat .gitignore | grep .env`

If not present, add to .gitignore:
```
# Environment variables
.env
.env.local
.env.*.local
```

- [ ] **Step 3: Commit**

```bash
git add services/gateway-intencoes/.env.example
git add .gitignore  # if modified
git commit -m "docs(gateway): add .env.example template"
```

---

## Task 8: Atualizar README

**Files:**
- Modify: `services/gateway-intencoes/README.md`

- [ ] **Step 1: Ler README atual**

Execute: `cat services/gateway-intencoes/README.md | head -50`

- [ ] **Step 2: Adicionar secção de configuração de segurança**

Add section after "Instalação":

```markdown
## Configuração de Segurança

Este serviço requer configuração OBRIGATÓRIA de variáveis de ambiente para funcionar em segurança.

### Variáveis Obrigatórias

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `JWT_SECRET_KEY` | Secret key para assinar tokens JWT | Use `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `CORS_ORIGINS` | Origens CORS permitidas (separadas por vírgula) | `http://localhost:3000,https://app.example.com` |

### Setup Rápido

```bash
# 1. Copiar template
cp .env.example .env

# 2. Gerar JWT secret
JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 3. Editar .env
nano .env
# Precha JWT_SECRET_KEY e CORS_ORIGINS

# 4. Verificar configuração
python -c "from src.config.settings import Settings; print(Settings().dict())"
```

### ⚠️ Importante

- **NUNCA** faza commit de ficheiros `.env` com valores reais
- **NUNCA** use `JWT_SECRET_KEY="secret"` ou valores padrão em produção
- **NUNCA** use `CORS_ORIGINS="*"` em produção
- Rodar o serviço sem estas variáveis causará erro no startup
```

- [ ] **Step 3: Commit**

```bash
git add services/gateway-intencoes/README.md
git commit -m "docs(gateway): add security configuration section to README"
```

---

## Task 9: Verificação Final

**Files:**
- All modified files

- [ ] **Step 1: Verificar zero credenciais hardcoded**

```bash
# Buscar por "secret" hardcoded no código
grep -r "secret" services/gateway-intencoes/src/ --include="*.py" | grep -v "# " | grep -v "test"
```

Expected: Nenhum resultado (ou apenas comentários/testes)

- [ ] **Step 2: Verificar CORS não está hardcoded**

```bash
# Buscar por CORS wildcard hardcoded
grep -r 'allow_origins=\["\*"\]' services/gateway-intencoes/src/
```

Expected: Nenhum resultado

- [ ] **Step 3: Rodar todos os testes unitários**

```bash
cd services/gateway-intencoes
pytest tests/unit/ -v
```

Expected: PASS (todos testes passam)

- [ ] **Step 4: Verificar que .env.example existe**

```bash
ls -la services/gateway-intencoes/.env.example
```

Expected: Ficheiro existe

- [ ] **Step 5: Verificar settings requer campos obrigatórios**

```bash
cd services/gateway-intencoes
python -c "from src.config.settings import Settings; s = Settings()"
```

Expected: ValidationError (jwt_secret_key é obrigatório)

- [ ] **Step 6: Commit final**

```bash
git add -A
git commit -m "feat(gateway): complete Phase 1 - security hardening"
```

---

## Self-Review Results

**1. Spec coverage:**
- ✅ JWT via environment — Task 2
- ✅ CORS via environment — Task 4, 6
- ✅ Startup validation — Task 5
- ✅ Environment template — Task 7
- ✅ Documentation — Task 8

**2. Placeholder scan:**
- ✅ Zero TBD, TODO, or "implement later"
- ✅ Todo o código está completo nos steps
- ✅ Comandos exatos fornecidos

**3. Type consistency:**
- ✅ jwt_secret_key é consistente (settings.jwt_secret_key)
- ✅ allowed_origins é consistente (settings.allowed_origins)
- ✅ Field types correspondem (List[str] com validator)
