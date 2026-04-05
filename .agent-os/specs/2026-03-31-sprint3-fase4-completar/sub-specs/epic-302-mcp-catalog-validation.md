# EPIC-302: MCP Tool Catalog Schema Validation

**ID:** EPIC-302
**Priority:** P1 - Alta
**Effort:** M (2 semanas)
**Service:** mcp-tool-catalog

## Resumo

Implementar schema validation completo para ferramentas MCP. Atualmente catálogo existe mas sem validação de schemas. Precisa: validação JSON Schema, validação de segurança, teste de conectividade.

## Arquivos a Criar/Modificar

### Novos:
- `src/validators/schema_validator.py` - Valida JSON Schema
- `src/validators/security_validator.py` - Valida segurança
- `src/services/connectivity_tester.py` - Testa conectividade
- `src/models/validated_tool.py` - Tool validado

### Modificar:
- `src/services/catalog_service.py` - Integrar validação
- `src/api/catalog.py` - Endpoints de validação

## Critérios
- [ ] JSON Schema validação
- [ ] Validação de segurança (perigos)
- [ ] Teste de conectividade
- [ ] Relatório de validação
- [ ] Endpoint POST /tools/validate
