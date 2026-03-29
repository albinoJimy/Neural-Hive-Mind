# Neural Hive Security

Biblioteca centralizada para configurações de segurança em todos os serviços Neural Hive Mind.

## Instalação

```bash
pip install neural_hive_security
```

## CORS Configuration

A classe `CORSConfig` fornece configuração centralizada de CORS por ambiente.

### Uso Básico

```python
from neural_hive_security import CORSConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# API pública com CORS por ambiente
cors_config = CORSConfig.get_cors_middleware_config(
    environment="prod",
    is_public_api=True
)
app.add_middleware(CORSMiddleware, **cors_config)
```

### Serviço Interno (sem CORS)

```python
# Serviços internos (gRPC, Kafka) não usam CORS
cors_config = CORSConfig.get_cors_middleware_config(
    environment="prod",
    is_public_api=False
)
# allow_origins será [] - CORS desabilitado
```

### Origens por Ambiente

| Ambiente | Origens |
|----------|---------|
| **dev** | `localhost:3000`, `localhost:8000`, `127.0.0.1:*` |
| **staging** | `*.staging.neural-hive.local` |
| **prod** | `neural-hive.com`, `app.neural-hive.com` |

### Validação de Produção

```python
from neural_hive_security import CORSConfig

# Lança ValueError se usar "*" em produção
try:
    CORSConfig.validate_no_wildcard(["*"], environment="prod")
except ValueError as e:
    print(f"Security violation: {e}")
```

## Integração com Settings

```python
# src/config/settings.py
from pydantic_settings import BaseSettings
from neural_hive_security import CORSConfig

class Settings(BaseSettings):
    ENVIRONMENT: str = "dev"
    IS_PUBLIC_API: bool = False

    @property
    def cors_origins(self) -> list[str]:
        """CORS origins dinâmicas por ambiente."""
        return CORSConfig.get_origins_for_environment(
            self.ENVIRONMENT,
            self.is_public_api
        )

    @property
    def cors_config(self) -> dict:
        """Configuração completa para CORSMiddleware."""
        return CORSConfig.get_cors_middleware_config(
            self.ENVIRONMENT,
            self.is_public_api
        )
```

## Segurança

- ❌ **Wildcards (`*`) proibidos em produção**
- ✅ **Validação automática de ambiente**
- ✅ **Serviços internos sem CORS**
- ✅ **Origens específicas por ambiente**
