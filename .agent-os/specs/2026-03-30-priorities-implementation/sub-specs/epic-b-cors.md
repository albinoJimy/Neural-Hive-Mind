# Sub-Spec: Epic B - Remover CORS Wildcards

## Objetivo

Remover configurações CORS wildcard (`allow_origins=["*"]`) de 12 serviços para evitar ataques CSRF e acesso não autorizado cross-origin.

## Serviços Alvo

### 1. architect-agent
**Arquivo:** `services/architect-agent/src/api/app.py:28`
**Problema:** `allow_origins=["*"]` hardcoded
**Solução:** Usar `settings.CORS_ORIGINS`

```python
# ANTES (linha 28)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: configurar via settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DEPOIS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# src/config/settings.py - ADICIONAR
from neural_hive_security.cors import CORSConfig

class Settings(BaseSettings):
    IS_PUBLIC_API: bool = Field(default=True)

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return CORSConfig.get_origins_for_environment(
            self.ENVIRONMENT,
            is_public_api=self.IS_PUBLIC_API
        )
```

### 2. MCP Servers (5 serviços)
**Arquivos:** `services/mcp-servers/*/src/config/settings.py`
**Problema:** `cors_origins: str = "*"`
**Solução:** Aplicar padrão `CORSConfig`

**Serviços afetados:**
- scout-mcp-server
- optimizer-mcp-server
- trivy-mcp-server
- sonarqube-mcp-server
- ai-codegen-mcp-server

```python
# ANTES
cors_origins: str = Field(
    default="*",
    description="CORS origins"
)

# DEPOIS
from neural_hive_security.cors import CORSConfig

class Settings(BaseSettings):
    IS_PUBLIC_API: bool = Field(default=False)  # MCP servers são internos

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return CORSConfig.get_origins_for_environment(
            self.ENVIRONMENT,
            is_public_api=self.IS_PUBLIC_API
        )

# main.py - ATUALIZAR
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # Serviços internos não precisam
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 3. .env.example files (6 serviços)
**Arquivos:** `services/*/.env.example`
**Problema:** `CORS_ORIGINS=*` em exemplos
**Solução:** Remover ou adicionar comentário explicativo

**Arquivos a corrigir:**
- analyst-agents/.env.example
- mcp-tool-catalog/.env.example
- execution-ticket-service/.env.example
- semantic-translation-engine/.env.example
- orchestrator-dynamic/.env.example
- sla-management-system/.env.example

```bash
# REMOVER esta linha:
CORS_ORIGINS=*

# SUBSTITUIR por comentário:
# CORS_ORIGINS=http://localhost:3000,https://staging.neural-hive.local
# Adicione suas origens permitidas separadas por vírgula
# Para serviços internos, não defina CORS_ORIGINS
```

### 4. Validação de CORS em produção
**Arquivo:** `libraries/python/neural_hive_security/neural_hive_security/cors.py`
**Adicionar:** Validação no startup que avisa se CORS wildcard em produção

```python
def validate_cors_configuration(environment: str, cors_origins: list[str]) -> None:
    """
    Valida configuração de CORS e avisa sobre wildcards inseguros.

    Args:
        environment: Ambiente atual (dev, staging, production)
        cors_origins: Lista de origens permitidas
    """
    if environment == "production":
        if "*" in cors_origins:
            logger.error("⚠️  CRITICAL: CORS wildcard detected in production!")
            logger.error("⚠️  This is a security vulnerability. Fix immediately!")
            raise ValueError("CORS wildcard not allowed in production")

    if environment == "staging" and "*" in cors_origins:
        logger.warning("⚠️  CORS wildcard detected in staging. Consider using specific origins.")
```

## Verificação

```bash
# Verificar que wildcard foi removido
grep -r "allow_origins.*\*" services/ | grep -v ".env.example"
# Deve retornar vazio

# Verificar configuração segura
grep -r "CORSConfig.get_origins_for_environment" services/
# Deve retornar múltiplas ocorrências

# Verificar .env.example files
grep -r "CORS_ORIGINS=\*" services/*/.env.example
# Deve retornar vazio

# Testar CORS em desenvolvimento
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: X-Requested-With" \
     -X OPTIONS \
     http://localhost:8000/api/health
# Deve retornar headers CORS corretos

# Testar CORS wildcard negado em produção
# (simular ambiente production)
```

## Padrão de CORS Seguro

### Serviços Públicos (API REST com frontend)
```python
IS_PUBLIC_API: bool = True

@property
def CORS_ORIGINS(self) -> list[str]:
    return CORSConfig.get_origins_for_environment(
        self.ENVIRONMENT,
        is_public_api=True  # Habilita CORS
    )
```

### Serviços Internos (gRPC/Kafka apenas)
```python
IS_PUBLIC_API: bool = False

@property
def CORS_ORIGINS(self) -> list[str]:
    return CORSConfig.get_origins_for_environment(
        self.ENVIRONMENT,
        is_public_api=False  # Desabilita CORS (lista vazia)
    )
```

## Arquivos a Modificar

```
services/architect-agent/
├── src/api/app.py
└── src/config/settings.py

services/mcp-servers/scout-mcp-server/
├── src/config/settings.py
└── src/main.py

services/mcp-servers/optimizer-mcp-server/
├── src/config/settings.py
└── src/main.py

services/mcp-servers/trivy-mcp-server/
├── src/config/settings.py
└── src/main.py

services/mcp-servers/sonarqube-mcp-server/
├── src/config/settings.py
└── src/main.py

services/mcp-servers/ai-codegen-mcp-server/
├── src/config/settings.py
└── src/main.py

services/analyst-agents/.env.example
services/mcp-tool-catalog/.env.example
services/execution-ticket-service/.env.example
services/semantic-translation-engine/.env.example
services/orchestrator-dynamic/.env.example
services/sla-management-system/.env.example

libraries/python/neural_hive_security/neural_hive_security/cors.py
```
