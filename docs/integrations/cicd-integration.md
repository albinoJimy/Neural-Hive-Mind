# CI/CD Integration Guide

## GitHub Actions
- Configure `github_actions_enabled=true`, `github_token` secret, `github_api_url`
- Supported operations: trigger workflow, poll status, download artifacts (planned)

## Jenkins
- Set `jenkins_url`, `jenkins_user`, `jenkins_token`
- Methods: trigger job, fetch build status, fetch test report

## Ticket Parameters
- `provider`: `github_actions` or `jenkins`
- `workflow_id` / `job_name`, `ref`, `inputs`

## Troubleshooting
- Check API rate limits and credentials validity
- Use Prometheus metrics `worker_agent_github_actions_api_calls_total`
