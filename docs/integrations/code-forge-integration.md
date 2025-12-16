# CodeForge Integration Guide

## Overview
- Endpoints: `/api/v1/pipelines` (trigger), `/api/v1/pipelines/{id}` (status)
- Authentication: service token or mTLS (see Helm values)
- Supported stages: QUEUED → BUILDING → TESTING → PACKAGING → COMPLETED/FAILED

## Configuration
- Set `code_forge.enabled=true` and `code_forge.url` in `helm-charts/worker-agents/values.yaml`
- Provide credentials via Kubernetes Secret `codeforge-token`

## Tickets
```json
{
  "task_type": "BUILD",
  "parameters": {
    "artifact_id": "demo-service",
    "branch": "main",
    "commit_sha": "abc123",
    "build_args": {"TARGET": "prod"}
  }
}
```

## Troubleshooting
- Check CodeForge logs `/metrics` for errors
- Validate pipeline webhook delivery to Kafka `execution.pipeline.events`
