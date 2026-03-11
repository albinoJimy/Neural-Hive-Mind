# Spec Requirements Document

> Spec: Code Forge - Correções de Completude
> Created: 2026-03-11
> Status: Planning

## Overview

Implementar correções e melhorias identificadas na análise de completude do Code Forge para atingir 98%+ de completude, focando principalmente no Approval Gate (commit + push + MR), validações precisas e cleanup de workspace.

## User Stories

### História 1: Approval Gate Completo

Como **desenvolvedor**, quero que o Approval Gate commit e push o código gerado antes de criar o Merge Request, para que o MR contenha os artefatos gerados para revisão.

**Fluxo esperado:**
1. Code Composer gera código e salva no MongoDB
2. Approval Gate recupera código do MongoDB
3. GitClient cria branch e commita os arquivos
4. GitClient faz push do branch
5. GitClient cria MR/PR com os arquivos

### História 2: Medição Precisa de Tempo

Como **engenheiro de observabilidade**, quero que o Validator meça o tempo real de execução de cada ferramenta de validação, para métricas precisas de performance.

### História 3: Cleanup de Workspace

Como **administrador de infraestrutura**, quero que o Test Runner limpe os workspaces após a execução, para evitar vazamento de disco no servidor.

## Spec Scope

1. **Completar Approval Gate** - Implementar commit + push + MR com arquivos reais
2. **Corrigir TODO validator.py** - Medir execution_time_ms real
3. **Habilitar workspace cleanup** - Ativar limpeza após testes
4. **Validação de licenças** - Adicionar verificação de licenças de dependências
5. **Expandir Test Runner** - Suportar testes em JavaScript/TypeScript
6. **Cache de templates versionados** - Usar Git tags para versionamento

## Out of Scope

- Reescrever Code Composer para usar Jinja2 (futuro refactoring)
- Autenticação/OAuth2 nas APIs (fase 2)
- Rate limiting (fase 2)
- Testes E2E completos (fase 2)

## Expected Deliverable

1. Approval Gate cria MR com código commitado
2. Validator registra tempo real de execução
3. Workspaces são limpos após testes
4. Validação de licenças detecta problemas
5. Testes executam para JavaScript/TypeScript
6. Templates são versionados por Git tags
