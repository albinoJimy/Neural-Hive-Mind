# Worker Agents Rollback Runbook

1. Set executor feature flags to simulation in `helm-charts/worker-agents/values.yaml` (`codeForge.enabled=false`, `argocd.enabled=false`, `githubActions.enabled=false`, validation tools disabled).
2. Redeploy chart: `helm upgrade worker-agents ./helm-charts/worker-agents -f values.yaml`.
3. Validate rollback: tickets processed in simulated mode, metrics show `stage=simulated`.
4. Monitor alerts for failure rate decrease before closing incident.
