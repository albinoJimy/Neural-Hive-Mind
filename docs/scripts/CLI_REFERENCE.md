# Referencia dos CLIs Unificados

## 1. Introducao
- 6 CLIs com convencao consistente; todas suportam `--help`.
- Flags comuns: `--help`, `--verbose`, `--dry-run` (quando aplicavel).

## 2. scripts/build.sh
### Sintaxe
```
./scripts/build.sh [OPTIONS]
```
### Opcoes
- `--target <local|ecr|registry|all>` (default: local)
- `--version <ver>` (default: 1.0.7)
- `--parallel <n>` (default: 4)
- `--services <list>` (comma-separated)
- `--no-cache`
- `--skip-base-images`
- `--push`
- `--env <env>`
- `--region <region>`
- `--registry <url>`
- `--help`
### Exemplos
```
./scripts/build.sh --target local
./scripts/build.sh --target ecr --version 1.0.8 --push
./scripts/build.sh --target ecr --services "gateway-intencoes,consensus-engine" --push
./scripts/build.sh --target local --parallel 8 --no-cache
```
### Scripts Consolidados
15 (build-local-parallel.sh, build-and-push-images.sh, push-to-ecr.sh, ...)

## 3. scripts/deploy.sh
### Sintaxe
```
./scripts/deploy.sh [OPTIONS]
```
### Opcoes
- `-e, --env <local|eks|minikube>` (default: local)
- `-p, --phase <foundation|1|2|all>` (default: 1)
- `-s, --services <LIST>`
- `-v, --version <VERSION>` (default: latest)
- `-d, --dry-run`
- `--skip-validation`
- `-h, --help`
### Ambientes/Fases
- Ambientes: local (Minikube), eks, minikube.
- Fases: foundation, 1, 2, all.
### Exemplos
```
./scripts/deploy.sh --env local --phase 1
./scripts/deploy.sh --env eks --services gateway
./scripts/deploy.sh --env eks --phase 2 --version 1.0.8
./scripts/deploy.sh --env eks --phase all --dry-run
```
### Scripts Consolidados
38 (deploy-eks-complete.sh, deploy-gateway.sh, ...)

## 4. tests/run-tests.sh
### Sintaxe
```
./tests/run-tests.sh [OPTIONS]
```
### Opcoes
- `--type <unit|integration|e2e|all>` (default: all)
- `--phase <1|2|all>`
- `--component <NAME>`
- `--coverage`
- `--report <console|json|html|all>`
- `--parallel`
- `--parallel-jobs <n>` (default: 4)
- `--dry-run`
- `--verbose`
- `--help`
### Exemplos
```
./tests/run-tests.sh --type all
./tests/run-tests.sh --type e2e --phase 1
./tests/run-tests.sh --type integration --component specialists
./tests/run-tests.sh --type all --coverage
./tests/run-tests.sh --type e2e --parallel --parallel-jobs 8
```
### Scripts Consolidados
45 (phase1-end-to-end-test.sh, integration-test.sh, ...)

## 5. scripts/validate.sh
### Sintaxe
```
./scripts/validate.sh [OPTIONS]
```
### Opcoes
- `--target <infrastructure|services|specialists|security|observability|performance|phase|e2e|all>`
- `--phase <1|2|all>`
- `--component <NAME>`
- `--namespace <NS>`
- `--report <console|json|html|all>`
- `--report-file <FILE>`
- `--fix`
- `--verbose`
- `--quick`
- `--help`
### Exemplos
```
./scripts/validate.sh --target all
./scripts/validate.sh --target specialists
./scripts/validate.sh --target observability --report html --report-file /tmp/report.html
./scripts/validate.sh --target phase --phase 2
```
### Scripts Consolidados
75 (validate-all-specialists.sh, validate-observability.sh, ...)

## 6. scripts/security.sh
### Sintaxe
```
./scripts/security.sh <COMMAND> <SUBCOMMAND> [OPTIONS]
```
### Comandos Principais
- vault, spire, certs, secrets, policies, validate, audit
### Exemplos
```
./scripts/security.sh vault init
./scripts/security.sh spire deploy --namespace spire-system
./scripts/security.sh certs validate --check-expiry --days 30
./scripts/security.sh secrets create --phase 2 --mode static
./scripts/security.sh validate all
./scripts/security.sh audit report --output /reports/security-audit.html
```
### Scripts Consolidados
23 (vault-init.sh, deploy-spire.sh, create-phase2-secrets.sh, ...)

## 7. ml_pipelines/ml.sh
### Sintaxe
```
./ml_pipelines/ml.sh <COMMAND> [OPTIONS]
```
### Comandos Principais
- train, validate, promote, retrain, rollback, generate-dataset, status, business-metrics, anomaly-detector, feedback, disaster-recovery
### Opcoes Comuns
- `--specialist <TYPE>`
- `--model <NAME>`
- `--version <N>`
- `--stage <STAGE>`
- `--all`
- `--hyperparameter-tuning`
- `--num-samples <N>`
- `--llm-provider <PROVIDER>`
- `--verbose`
- `--help`
### Exemplos
```
./ml_pipelines/ml.sh train --specialist technical
./ml_pipelines/ml.sh train --all --hyperparameter-tuning
./ml_pipelines/ml.sh validate --all
./ml_pipelines/ml.sh promote --model technical-evaluator --version 3 --stage Production
./ml_pipelines/ml.sh retrain --specialist business --hyperparameter-tuning
./ml_pipelines/ml.sh generate-dataset --all --llm-provider openai
./ml_pipelines/ml.sh status --all --verbose
```
### Variaveis de Ambiente
- MLFLOW_URI, MONGODB_URI, DATASET_DIR, K8S_NAMESPACE, LLM_PROVIDER, LLM_MODEL, LLM_API_KEY
### Scripts Consolidados
25 (train_all_specialists.sh, retrain_specialist.sh, promote_model.py, ...)

## 8. Integracao com Makefile
```
make build-local      # ./scripts/build.sh --target local
make deploy-eks       # ./scripts/deploy.sh --env eks --phase all
make test             # ./tests/run-tests.sh --type all
make validate         # ./scripts/validate.sh --target all
make security-init    # ./scripts/security.sh vault init && spire deploy
make ml-train         # ./ml_pipelines/ml.sh train --all
```

## 9. Integracao CI/CD
Exemplo:
```yaml
- name: Build and Push Images
  run: ./scripts/build.sh --target ecr --push --parallel 8
- name: Deploy to EKS
  run: ./scripts/deploy.sh --env eks --phase all --version ${{ github.sha }}
- name: Validate Deployment
  run: ./scripts/validate.sh --target all --report json --report-file validation.json
- name: Security Validation
  run: ./scripts/security.sh validate all
- name: Train Models
  run: ./ml_pipelines/ml.sh train --all
```
