# Exemplos Praticos de Uso dos CLIs

## 1. Workflows Comuns

### Desenvolvimento Local
```bash
./scripts/build.sh --target local --parallel 8
./scripts/deploy.sh --env local --phase 1
./scripts/validate.sh --target all --quick
./tests/run-tests.sh --type integration
```

### Deploy em Producao
```bash
./scripts/build.sh --target ecr --version 1.0.8 --push
./scripts/deploy.sh --env eks --phase foundation
./scripts/deploy.sh --env eks --phase 1 --version 1.0.8
./scripts/validate.sh --target all --report html
./tests/run-tests.sh --type e2e --report json
```

### Continuous Learning
```bash
./ml_pipelines/ml.sh generate-dataset --all --num-samples 1000
./ml_pipelines/ml.sh train --all --hyperparameter-tuning
./ml_pipelines/ml.sh validate --all
./ml_pipelines/ml.sh promote --model technical-evaluator --version 3 --stage Staging
./tests/run-tests.sh --type e2e --component specialists
./ml_pipelines/ml.sh promote --model technical-evaluator --version 3 --stage Production
```

### Troubleshooting
```bash
./scripts/validate.sh --target all --quick
kubectl logs -n neural-hive -l app=gateway --tail=100
./scripts/security.sh validate all
./ml_pipelines/ml.sh rollback --specialist technical --reason "Performance degradation"
./scripts/validate.sh --target specialists --verbose
```

## 2. Integracao CI/CD (GitHub Actions)
```yaml
name: CI/CD Pipeline
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build Images
        run: ./scripts/build.sh --target ecr --push --version ${{ github.sha }}

  test:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Tests
        run: ./tests/run-tests.sh --type all --coverage --report json
      - name: Upload Coverage
        uses: codecov/codecov-action@v3

  deploy-staging:
    needs: test
    if: github.ref == 'refs/heads/develop'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Staging
        run: ./scripts/deploy.sh --env eks --phase all --version ${{ github.sha }}
      - name: Validate Deployment
        run: ./scripts/validate.sh --target all --report json

  deploy-production:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Production
        run: ./scripts/deploy.sh --env eks --phase all --version ${{ github.sha }}
      - name: Validate Deployment
        run: ./scripts/validate.sh --target all --report html
      - name: Security Audit
        run: ./scripts/security.sh audit report --output audit.html
```

## 3. Scripts de Automacao (exemplos)

### Backup Completo
```bash
#!/bin/bash
./scripts/security.sh vault backup --output /backup/vault-$(date +%Y%m%d).tar.gz
./scripts/security.sh secrets backup --output /backup/secrets-$(date +%Y%m%d).yaml
kubectl exec -n neural-hive mongodb-0 -- mongodump --archive=/tmp/backup.archive
kubectl cp neural-hive/mongodb-0:/tmp/backup.archive /backup/mongodb-$(date +%Y%m%d).archive
```

### Health Check Completo
```bash
#!/bin/bash
./scripts/validate.sh --target all --report json --report-file /tmp/validation.json
./scripts/security.sh validate all
./ml_pipelines/ml.sh status --all --format json > /tmp/ml-status.json
cat /tmp/validation.json /tmp/ml-status.json | jq -s '.[0] + .[1]' > /tmp/health-report.json
```
