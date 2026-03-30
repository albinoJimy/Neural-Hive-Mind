# Spec Requirements Document

> Spec: Completude Gap Correction
> Created: 2026-03-30
> Status: Planning

## Overview

Corrigir gaps críticos identificados na análise profunda de completude do Neural-Hive-Mind, elevando a completude global de 83.5% para ~90%. Foco em vulnerabilidades de segurança, documentação ausente e infraestrutura de deploy.

## Contexto

A análise profunda revelou:
- **Completude global: 83.5%**
- **Vulnerabilidade crítica:** `allowed_hosts: ["*"]` em gateway-intencoes
- **7 serviços sem README**
- **2 Helm charts ausentes**
- **Cobertura de testes: 14%** (fora do scope desta spec)

## User Stories

### Como DevOps Engineer
Eu quero corrigir a vulnerabilidade de `allowed_hosts: ["*"]`, para que o gateway não aceite requests de qualquer origem maliciosa.

**Workflow:**
1. Identificar services/gateway-intencoes/src/config/settings.py linha 217-220
2. Substituir `default=["*"]` por hosts específicos por ambiente
3. Adicionar validação de ambiente (produção exige hosts específicos)
4. Testar que requests de hosts não autorizados são rejeitados

### Como Desenvolvedor Novo
Eu quero READMEs em todos os serviços, para que eu possa entender rapidamente a arquitetura, configuração e operação de cada componente.

**Workflow:**
1. Navegar para service/
2. Encontrar README.md com seções padronizadas
3. Ler descrição, arquitetura, API, configuração e troubleshooting
4. Conseguir rodar o serviço localmente em 5 minutos

### Como Platform Engineer
Eu quero Helm charts para todos os serviços, para que o deploy seja consistente e automatizado via GitOps.

**Workflow:**
1. Chart segue estrutura padrão (Deployment, Service, HPA, PDB, NetworkPolicy)
2. `helm install` funciona sem erros
3. Values.yaml permitem customização por ambiente
4. Service mesh e observability integrados

## Spec Scope

1. **Correção de Segurança Crítica** - Substituir wildcard em allowed_hosts
2. **Criação de 2 READMEs** - Para feature-store e software-engineering-pipeline
3. **Criação de 2 Helm Charts** - feature-store e software-engineering-pipeline

## Out of Scope

- Aumento de cobertura de testes (spec separada)
- Refatoração de neural_hive_ml (estrutura já está adequada)
- Deep learning support (PyTorch/TensorFlow)
- Canary deployments

## Expected Deliverable

1. Gateway com `allowed_hosts` configurado por ambiente (sem wildcards em produção)
2. 2 novos ficheiros README.md following template padronizado
3. 2 novos Helm charts funcionalmente completos
4. Completude global elevada de 83.5% para ~88%

## Success Criteria

- [ ] `grep -r 'allowed_hosts.*\*"' services/` retorna 0 resultados
- [ ] Todos os serviços principais têm README.md
- [ ] `helm lint` passa para os 2 novos charts
- [ ] `helm template` gera manifests válidos
- [ ] Score de segurança elevado de 83% para 90%+
