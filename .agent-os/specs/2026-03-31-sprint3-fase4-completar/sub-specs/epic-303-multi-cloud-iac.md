# EPIC-303: Multi-Cloud IaC Generation - code-forge

**ID:** EPIC-303
**Priority:** P1 - Alta
**Effort:** XL (4 semanas)
**Service:** code-forge

## Resumo

Expandir IaC generation para suportar AWS, Azure e GCP. Atualmente apenas AWS suportado. Precisa: templates Terraform multi-cloud, abstração de recursos, code splitting.

## Arquivos a Criar/Modificar

### Novos:
- `src/generators/azure_generator.py` - Gera ARM templates
- `src/generators/gcp_generator.py` - Gera GCP Deployment Manager
- `src/abstractions/resource_abstraction.py` - Abstrai recursos
- `src/mappers/cloud_mapper.py` - Mapeia recursos entre clouds
- `src/validators/multi_cloud_validator.py` - Valida IaC multi-cloud

### Modificar:
- `src/services/code_forge_service.py` - Suporte multi-cloud
- `src/api/iac.py` - Endpoints multi-cloud

## Critérios
- [ ] Azure ARM templates
- [ ] GCP Deployment Manager
- [ ] Abstração de recursos (db, storage, compute)
- [ ] Mapeamento entre clouds
- [ ] Validação multi-cloud
- [ ] Testes E2E para cada cloud
