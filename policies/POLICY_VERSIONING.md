# Policy Versioning Guide

Guia para uso do sistema de versionamento avançado de políticas OPA.

## Visão Geral

O sistema de versionamento permite gerenciar múltiplas versões de políticas OPA, suportando:

- **Versionamento Semântico** (major.minor.patch)
- **Multi-versioning** - múltiplas versões ativas simultaneamente
- **Compatibilidade** - especificação de ranges de versão suportados
- **Depreciação** - marcação e migração de versões antigas
- **Validação** - verificação automática de formato e compatibilidade

## Estrutura de Versão

### Formato Semântico

```
major.minor.patch

ex: 2.1.3
- major: 2 (mudanças incompatíveis na API)
- minor: 1 (funcionalidades backwards-compatible)
- patch: 3 (correções de bugs backwards-compatible)
```

### Estados de Política

| Estado | Descrição |
|--------|-----------|
| `active` | Política em uso ativo |
| `deprecated` | Política obsoleta (será removida) |
| `experimental` | Política em teste |
| `retired` | Política removida (não mais usada) |

## Uso em Políticas

### Importar Biblioteca de Versionamento

```rego
package neuralhive.my_policy

import future.keywords.in
import future.keywords.if
import data.neuralhive.policy.versioning

# Usar função de versionamento
default allow := false
```

### Definir Metadados de Política

```rego
# Metadados no início da política
metadata := {
    "version": "2.0.0",
    "created_at": "2026-04-07",
    "updated_at": "2026-04-07",
    "author": "Team Name",
    "status": "active",
    "compatibility": {
        "min_version": "1.0.0",
        "max_version": "2.x",
    },
}
```

### Verificar Compatibilidade

```rego
# Permitir apenas se versão do cliente é compatível
allow if {
    input.client_version
    versioning.version_in_range(
        input.client_version,
        metadata.compatibility.min_version,
        metadata.compatibility.max_version
    )
}
```

### Tratar Versão Depreciada

```rego
# Adicionar warning se versão está depreciada
warnings contains warning if {
    versioning.is_policy_deprecated("my_policy", input.policy_version)
    warning := {
        "severity": "WARNING",
        "message": "Policy version is deprecated",
        "migration_guide": versioning.get_migration_guide("my_policy", input.policy_version),
    }
}
```

## Multi-Versioning

### Estrutura com Múltiplas Versões

```rego
# Em data.policies:
{
    "security_policies": {
        "versions": {
            "1.0.0": {
                "metadata": {"status": "deprecated"},
                "rules": {...}
            },
            "2.0.0": {
                "metadata": {"status": "active"},
                "rules": {...}
            },
        }
    }
}
```

### Obter Versão Específica

```rego
# Obter política na versão solicitada
policy_data := versioning.get_policy_version("security_policies", "2.0.0")

# Obter versão mais recente
latest := versioning.get_latest_version("security_policies")

# Obter versão compatível com cliente
compatible := versioning.get_compatible_version("security_policies", client_version)
```

## Funções Disponíveis

### Parse e Validação

| Função | Descrição |
|--------|-----------|
| `parse_version(string)` | Parse versão semântica |
| `is_valid_version(version)` | Valida formato |
| `validate_policy_version(policy_id)` | Valida versão da política |

### Comparação

| Função | Descrição |
|--------|-----------|
| `compare_versions(v1, v2)` | Compara duas versões (-1, 0, 1) |
| `version_meets_min_required(v, min)` | Verifica mínimo |
| `version_in_range(v, min, max)` | Verifica range |

### Multi-Versioning

| Função | Descrição |
|--------|-----------|
| `get_all_versions(policy_id)` | Lista todas versões |
| `get_active_version(policy_id)` | Versão ativa |
| `get_latest_version(policy_id)` | Versão mais recente |
| `get_policy_version(policy_id, v)` | Versão específica |

### Metadados

| Função | Descrição |
|--------|-----------|
| `policy_metadata(policy_id)` | Metadados da política |
| `get_policy_metadata(policy_id, v)` | Metadados da versão |
| `get_deprecation_info(policy_id, v)` | Info de depreciação |
| `get_migration_guide(policy_id, v)` | Guia de migração |

### Utilitários

| Função | Descrição |
|--------|-----------|
| `version_key(policy_id, v)` | Chave única (cache) |
| `version_hash(policy_id, v)` | Hash para validação |
| `format_version_for_logging(p)` | Formata para logs |
| `version_stats` | Estatísticas globais |

## Boas Práticas

### 1. Sempre Especificar Versão

```rego
# Ruim - usa versão padrão
metadata := {"status": "active"}

# Bom - versão explícita
metadata := {
    "version": "1.0.0",
    "status": "active",
}
```

### 2. Usar Ranges de Compatibilidade

```rego
metadata := {
    "compatibility": {
        "min_version": "1.0.0",
        "max_version": "2.x",  # Suporta qualquer 2.x
    },
}
```

### 3. Documentar Mudanças de Major

```rego
# v2.0.0 - BREAKING CHANGE
# - Renomeado 'allow' para 'permit' no resultado
# - Removido campo 'legacy_mode'
metadata := {
    "version": "2.0.0",
    "breaking_changes": [
        "allow -> permit",
        "removed legacy_mode",
    ],
}
```

### 4. Usar Changelog em Metadados

```rego
metadata := {
    "version": "1.1.0",
    "changelog": [
        "Added support for new resource types",
        "Fixed false positives in validation",
    ],
}
```

## Testando Políticas com Versionamento

```bash
# Testar versão específica
opa test policies/rego/lib/versioning_test.rego

# Testar com input de versão
opa eval -d policies/rego/lib/versioning.rego -i '{
    "policies": {
        "test_policy": {
            "metadata": {"version": "1.0.0"}
        }
    }
}' 'data.neuralhive.policy.versioning.policy_metadata("test_policy")'
```

## Exemplo Completo

```rego
package neuralhive.guard.security

import future.keywords.in
import future.keywords.if
import data.neuralhive.policy.versioning

# Metadados da política
metadata := {
    "version": "2.1.0",
    "created_at": "2026-04-07",
    "updated_at": "2026-04-07",
    "author": "Security Team",
    "status": "active",
    "compatibility": {
        "min_version": "2.0.0",
        "max_version": "3.x",
    },
}

# Resultado com informação de versão
result := {
    "allow": allow,
    "violations": violations,
    "policy_version": metadata.version,
    "warnings": get_version_warnings(),
}

# Regras principais
allow if {
    count(violations) == 0
}

violations contains violation if {
    some i, input.resources[i]
    is_dangerous_capability(input.resources[i].capability)
    violation := {
        "severity": "CRITICAL",
        "message": "Dangerous capability not allowed",
        "resource": input.resources[i].name,
    }
}

# Warnings para versões depreciadas
get_version_warnings() := warnings if {
    versioning.is_policy_deprecated("security", metadata.version)
    warnings := ["This policy version is deprecated, upgrade to 3.0.0"]
}

get_version_warnings() := [] if {
    not versioning.is_policy_deprecated("security", metadata.version)
}

is_dangerous_capability(cap) {
    dangerous_capabilities[cap]
}

dangerous_capabilities := {
    "SYS_ADMIN",
    "NET_ADMIN",
}
```
