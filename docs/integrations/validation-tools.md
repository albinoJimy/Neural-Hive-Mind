# Validation Tools Guide

## Tools
- OPA (policy): `opa_url`, `policy_path`, `input_data`
- Trivy (SAST): `trivy_enabled`, `trivy_timeout_seconds`
- SonarQube: `sonarqube_enabled`, `sonarqube_url`, `sonarqube_token`
- Snyk: `snyk_enabled`, `snyk_token`
- Checkov: `checkov_enabled`

## Ticket Parameters
- `validation_type`: `policy`, `sast`, `sonarqube`, `snyk`, `iac`
- `working_dir` or `manifest_path`

## Metrics
- `worker_agent_validate_tasks_executed_total{status,tool}`
- `worker_agent_validate_violations_total{severity,tool}`

## Troubleshooting
- Validate tool endpoints; enable debug logs; review violations payload
