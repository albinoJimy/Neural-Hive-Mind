# Spec Requirements Document

> Spec: P04 — Operacional
> Created: 2026-03-27
> Status: Planning
> Priority: MODERADA

---

## Overview

Higiene de repositório e otimização de build. Remover arquivos órfãos, reorganizar documentação histórica, fazer pinning completo de dependências e otimizar Docker build do Gateway.

---

## User Stories

### Como desenvolvedor
Eu quero um repositório limpo e organizado
Para que navegação seja eficiente

**Workflow:**
1. Arquivos órfãos são removidos
2. Documentos históricos são arquivados
3. Estrutura de diretórios é clara

### Como engenheiro de DevOps
Eu quero dependências completamente versionadas
Para que builds sejam reprodutíveis

**Workflow:**
1. requirements.txt usa versões exatas
2. requirements.frozen é gerado
3. CI valida dependências

### Como SRE
Eu quero Docker images otimizadas
Para que deploys sejam rápidos e seguros

**Workflow:**
1. Multi-stage build reduz tamanho
2. Apenas runtime dependencies na imagem final
3. Security scanning passa

---

## Spec Scope

1. **Limpeza de repositório** — Remover arquivos órfãos e binários
2. **Arquivamento de docs** — Mover relatórios históricos para archive/
3. **Pinning de dependências** — Versões exatas em requirements.txt
4. **Multi-stage build** — Otimizar Dockerfile do Gateway

---

## Out of Scope

- Migration para poetry/pipenv (futuro)
- Renomear diretórios de serviços (fora de escopo)
- CI/CD refactoring (já existe)

---

## Expected Deliverable

1. Repositório sem arquivos órfãos
2. Documentos históricos em docs/archive/
3. requirements.frozen em todos os serviços
4. Multi-stage Dockerfile no gateway
5. README atualizado com estrutura
