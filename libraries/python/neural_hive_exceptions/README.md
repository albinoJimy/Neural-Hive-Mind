# Neural Hive Exceptions

Biblioteca de exceções centralizada para consistent error handling em todos os serviços da plataforma Neural Hive-Mind.

## Instalação

```bash
pip install -e libraries/python/neural_hive_exceptions/
```

## Uso

```python
from neural_hive_exceptions import (
    NeuralHiveError,
    ValidationError,
    ConfigurationError,
    GRPCError,
    grpc_error_to_status
)

# Validação
raise ValidationError.missing_field("email")

# Configuração
raise ConfigurationError.missing_required("DATABASE_URL")

# gRPC
raise GRPCError(
    status_code=grpc.StatusCode.NOT_FOUND,
    detail="Resource not found"
)

# Conversão de erro
status = grpc_error_to_status(exception)
```

## Estrutura

- `base.py`: NeuralHiveError base class
- `validation.py`: ValidationError e ValidationErrorCode
- `configuration.py`: ConfigurationError e ConfigErrorCode
- `grpc.py`: GRPCError e utilitários para mapeamento HTTP/gRPC
