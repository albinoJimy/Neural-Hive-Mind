# Estratégia de Branching — [Project Name]

## Branches Principais

- `main` — Produção (push directo bloqueado)
- `staging` — Pré-produção
- `develop` — Desenvolvimento activo

## Convenção de Nomes

```
feat/TICKET-ID-descricao-curta
fix/TICKET-ID-descricao-curta
refactor/TICKET-ID-descricao-curta
hotfix/XXX-descricao-curta
```

## Fluxo

1. Criar branch a partir de `develop`
2. Desenvolver e committar
3. Push e criar PR
4. Review e correcções
5. Merge para `develop` (squash and merge)
6. Apagar branch

## Hotfixes

1. Criar branch a partir de `main`
2. Merge para `main`
3. Cherry-pick para `develop`
