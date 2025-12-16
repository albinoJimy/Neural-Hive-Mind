# Worker Agents Troubleshooting Runbook

- **CodeForge down**: switch feature flag `codeForge.enabled=false` to simulate, check `worker_agent_code_forge_api_calls_total`.
- **ArgoCD unreachable**: validate ServiceAccount token, namespace `argocd`, check `/healthz`.
- **High retry rate**: inspect Kafka connectivity, backoff settings, external API saturation.
- **Validation failures**: inspect violations payload, rerun with `validation_type=policy` and verbose logging.
- **Metrics missing**: ensure Prometheus scraping `/metrics` on worker-agents and dependencies.
