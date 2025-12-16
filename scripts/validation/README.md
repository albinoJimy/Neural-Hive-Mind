# Scripts de Validação - Neural Hive-Mind

## CLI Unificado (novo)

- **Use:** `./scripts/validate.sh --target <TARGET>`
- **Documentação:** `docs/scripts/VALIDATION_CLI.md`
- **Alvos principais:** `infrastructure`, `services`, `specialists`, `security`, `observability`, `performance`, `phase`, `e2e`, `all`
- **Flags úteis:** `--namespace`, `--component`, `--phase`, `--report (console|json|html|all)`, `--report-file`, `--quick`, `--verbose`
- **Exemplos rápidos:**
  - `./scripts/validate.sh --target all`
  - `./scripts/validate.sh --target observability --report html --report-file /tmp/obs.html`
  - `./scripts/validate.sh --target specialists --component business --quick`

## Scripts legados (deprecados)

Todos os scripts individuais anteriores (ex.: `validate-all-specialists.sh`, `validate-observability.sh`, `validate-infrastructure-local.sh`) foram consolidados no CLI acima. Eles permanecem apenas por compatibilidade e imprimem aviso de deprecação ao serem executados. Prefira sempre `scripts/validate.sh`.
