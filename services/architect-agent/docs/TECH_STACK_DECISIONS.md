# Technical Stack Decisions - Architect Agent

> Documentação das decisões técnicas que divergem da spec original e suas justificativas.

---

## Decisão: pip vs Poetry

**Data:** 2026-04-17
**Status:** Decisão tomada e implementada

### Contexto

A spec original (`docs/superpowers/plans/2026-04-16-fluxo-g-fase1-foundation.md`) especifica o uso de Poetry para gestão de dependências (linhas 124-158).

### Decisão Tomada

**Optámos por pip em vez de Poetry** para gestão de dependências do architect-agent.

### Justificativa

1. **Consistência com o restante do projeto**
   - Outros serviços no Neural-Hive-Mind usam pip + requirements.txt
   - Manter consistência reduz complexidade operacional

2. **Simplicidade de setup**
   - pip é pré-instalado com Python
   - Poetry requer instalação adicional e curva de aprendizado

3. **Ferramentas de CI/CD existentes**
   - Pipelines GitHub Actions já configurados para pip
   - Cache de dependências funcionando corretamente

4. **Interoperabilidade**
   - requirements.txt é universalmente compreendido
   - Facilita integração com ferramentas de scanning de segurança

### Especificação Final

**Ficheiros:**
- `requirements.txt` - Dependências de produção
- `requirements-dev.txt` - Dependências de desenvolvimento

**Versão Python:** 3.12+ (conforme spec)

**CI/CD:** GitHub Actions com cache pip

### Impacto

**Positivo:**
- ✅ Setup mais simples para novos developers
- ✅ Menos ferramentas para aprender
- ✅ Consistência com restante do projeto

**Negativo:**
- ⚠️ Perdemos funcionalidades Poetry (lock file detalhado, dependency groups)

### Mitigação

Para mitigar a perda de funcionalidades do Poetry:

1. **Version pinning** - requirements.txt usa versões fixas
2. **Separate dev requirements** - requirements-dev.txt para dependências de desenvolvimento
3. **CI/CD validation** - pipeline valida instalação e testes

---

## Decisão: Python 3.12 vs 3.10

**Data:** 2026-04-17
**Status:** Implementado

### Decisão

**Python 3.12** para todas as componentes (conforme spec).

### Implementação

- `requirements.txt`: `python_version >= "3.12"`
- `Dockerfile`: `FROM python:3.12-slim`
- CI/CD: `python-version: '3.12'`

### Justificativa

A spec requere Python 3.12+ para suportar funcionalidades modernas:
- Type hints melhorados
- Performance gains
- Novas features de linguagem

---

## Revisão e Atualização

**Próxima revisão:** 2026-05-17
**Responsável:** Tech Lead

Este documento deve ser revisto se:
- Mudarmos para Poetry no futuro
- Novas versões Python forem lançadas
- Problemas de dependência surgirem
