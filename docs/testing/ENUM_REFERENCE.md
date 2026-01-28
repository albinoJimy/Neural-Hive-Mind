# Referência de Enums - Neural Hive Mind

## Gateway de Intenções

### Campo: `priority`

| Valor Correto (lowercase) | ❌ Valor Incorreto (uppercase) |
|---------------------------|--------------------------------|
| `low`                     | `LOW`                          |
| `normal`                  | `NORMAL`                       |
| `high`                    | `HIGH`                         |
| `critical`                | `CRITICAL`                     |

### Campo: `security_level`

| Valor Correto (lowercase) | ❌ Valor Incorreto (uppercase) |
|---------------------------|--------------------------------|
| `public`                  | `PUBLIC`                       |
| `internal`                | `INTERNAL`                     |
| `confidential`            | `CONFIDENTIAL`                 |
| `restricted`              | `RESTRICTED`                   |

## Validação

O contrato Pydantic do `gateway-intencoes` valida estes campos usando enums em lowercase. Payloads com valores em uppercase retornarão:

```json
{
  "detail": [
    {
      "loc": ["body", "constraints", "priority"],
      "msg": "value is not a valid enumeration member; permitted: 'low', 'normal', 'high', 'critical'",
      "type": "type_error.enum"
    }
  ]
}
```

**Status HTTP:** 422 Unprocessable Entity
