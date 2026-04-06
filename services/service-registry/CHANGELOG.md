# Changelog - Service Registry

## [1.3.0] - 2025-04-05

### Changed - Migração etcd→Redis (OPS-003)

**Resumo:** Clarificação de nomes de configuração para eliminar confusão operacional.

- **Configurações:**
  - Novas variáveis `REGISTRY_REDIS_*` substituem `ETCD_*`
  - `ETCD_ENDPOINTS` → `REGISTRY_REDIS_ENDPOINTS`
  - `ETCD_PREFIX` → `REGISTRY_REDIS_PREFIX`
  - `ETCD_TIMEOUT_SECONDS` → `REGISTRY_REDIS_TIMEOUT_SECONDS`
  - Nomes antigos mantidos com deprecation warning (removidos em v1.6.0)

- **Código:**
  - `main.py`: Usa `RedisRegistryClient` diretamente (removido alias `EtcdClient`)
  - `src/clients/__init__.py`: Exporta `RedisRegistryClient` em vez de `EtcdClient`
  - `src/clients/redis_registry_client.py`: Removido alias `EtcdClient`
  - `src/clients/etcd_client.py`: Movido para `.deprecated/` (código obsoleto)
  - `src/config/settings.py`: Propriedades `registry_redis_*` para migração transparente

- **Documentação:**
  - `docs/service-registry/MIGRATION_ETCD_TO_REDIS.md`: Guia completo de migração
  - `docs/service-registry/ROLLBACK_ETCD_TO_REDIS.md`: Plano de rollback
  - `docs/service-registry/VALIDATION_CHECKLIST.md`: Checklist de validação
  - `scripts/validate_migration.sh`: Script de validação automatizada

### Deprecations

- `ETCD_ENDPOINTS` - Use `REGISTRY_REDIS_ENDPOINTS` (removido em v1.6.0)
- `ETCD_PREFIX` - Use `REGISTRY_REDIS_PREFIX` (removido em v1.6.0)
- `ETCD_TIMEOUT_SECONDS` - Use `REGISTRY_REDIS_TIMEOUT_SECONDS` (removido em v1.6.0)

### Migration Guide

Ver `docs/service-registry/MIGRATION_ETCD_TO_REDIS.md` para instruções completas.

**Estratégia de 3 fases:**
- **Fase 1 (v1.3.0):** Backward compatibility - suporta ambos os nomes
- **Fase 2 (v1.4.0):** Migration - atualizar Helm charts
- **Fase 3 (v1.6.0):** Cleanup - remover `ETCD_*` deprecated

---

## [1.2.0] - Anterior

- Implementação inicial de Redis como backend
- Alias `EtcdClient` para `RedisRegistryClient`
- Configurações com nomes `ETCD_*` (confusion point)

---

## Formato de Versão

- **Major (X.0.0):** Mudanças breaking
- **Minor (x.Y.0):** Novas funcionalidades, deprecations
- **Patch (x.y.Z):** Bug fixes
