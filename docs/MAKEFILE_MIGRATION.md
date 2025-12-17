# Makefile Migration Guide

This guide summarizes the simplified Makefile (v2.0) and how to transition from older targets and scripts to the unified CLIs.

## Quick Changes
- Makefile shrunk from ~850 lines to ~200 with thin wrappers over CLIs.
- Deprecated targets removed: `test-specialists-unit`, `test-phase1-pre-validate`.
- New helper: `scripts/makefile-migration-helper.sh` to route deprecated commands.

## Target Mapping
| Old Command | New Command |
| --- | --- |
| `make test-specialists-unit` | `make test-unit` |
| `make test-phase1-pre-validate` | `make test-phase1` |

## New CLIs
- `./scripts/observability.sh` — dashboards, validation, SLO/correlation tests.
- `./scripts/setup.sh` — minikube, eks (with `--auto`), backend setup.
- `./scripts/maintenance.sh` — backup/restore, cluster and cost optimization, disaster recovery.

## Common Recipes
- Validate everything: `make validate`
- Build locally: `make build-local`
- Deploy to EKS: `make deploy-eks`
- Run all tests: `make test`
- Observability dashboards: `make observability-dashboards`

## Migration Tips
- Keep using existing target names; behavior now delegates to CLIs for consistency.
- If you hit a missing target, check `make help` or the CLI `--help` commands.
- Use the migration helper when invoking deprecated targets from automation.
