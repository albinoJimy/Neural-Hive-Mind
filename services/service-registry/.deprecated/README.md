# Deprecated Code

Este diretório contém código obsoleto mantido para referência histórica.

## Arquivos

### `etcd_client.py.deprecated`

**Status:** Movido em v1.3.0 (OPS-003)

**Motivo:**
- Usava biblioteca `etcd3` incompatível com protobuf >= 4.0
- Substituído por `RedisRegistryClient`
- Causava confusão operacional (nome "etcd" mas usava Redis)

**Alternativa:**
- Use `src/clients/redis_registry_client.py`

**Nota:** Este arquivo NÃO deve ser usado em produção. Mantido apenas para:
1. Referência histórica do design original
2. Debugging de issues legados
3. Comparação de implementação

## Política de Retenção

Arquivos neste diretório serão removidos após:
1. 6 meses desde a deprecation
2. Confirmação que não há referências em produção
3. Aprovação do tech lead

Para v1.6.0, todo este diretório será removido.
