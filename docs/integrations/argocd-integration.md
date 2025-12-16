# ArgoCD Integration Guide

## Setup
- Deploy manifests at `k8s/infrastructure/argocd/argocd-install.yaml`
- Create token secret `argocd-token` in namespace `argocd`
- Enable via Helm `argocd.enabled=true` and `argocd.url`

## Deployment Tickets
- Parameters: `deployment_name`, `namespace`, `repo_url`, `chart_path`, `revision`, `image`, `replicas`, `sync_strategy`

## Health / Rollback
- Poll sync + health; rollback to previous revision on `Degraded`
- Metrics: `worker_agent_deploy_tasks_executed_total`, `worker_agent_argocd_api_calls_total`

## Troubleshooting
- Check ArgoCD API `/api/v1/applications/{app}`
- Verify RBAC for worker-agent ServiceAccount
