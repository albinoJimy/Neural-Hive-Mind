# Phase 2 Production Checklist

## Pre-Deployment
- [ ] All 13 services built and pushed to ECR
- [ ] Helm charts validated with `helm lint`
- [ ] Resource limits reviewed and approved
- [ ] Secrets created in AWS Secrets Manager
- [ ] Vault HA cluster provisioned and initialized
- [ ] SPIFFE/SPIRE deployed and workload entries created
- [ ] PostgreSQL backups configured and tested
- [ ] MongoDB backups configured and tested
- [ ] Circuit breakers enabled and tested
- [ ] Dashboards imported to Grafana
- [ ] Alerts configured in Prometheus
- [ ] Runbooks reviewed by on-call team

## Deployment
- [ ] Deploy in dependency order (Service Registry → Orchestrator → Workers → ...)
- [ ] Validate each service health before proceeding
- [ ] Run smoke tests after each service
- [ ] Monitor metrics during rollout
- [ ] Validate mTLS connectivity between services

## Post-Deployment
- [ ] Run E2E test suite (`tests/phase2-end-to-end-test.sh`)
- [ ] Validate SLO targets (Intent-to-Deploy < 4h, SLA compliance > 99%)
- [ ] Verify backup CronJobs executed successfully
- [ ] Confirm circuit breakers in closed state
- [ ] Review Grafana dashboards for anomalies
- [ ] Execute disaster recovery test
- [ ] Document lessons learned

## Rollback Criteria
- E2E test failure rate > 5%
- SLA compliance < 95%
- Circuit breakers open for > 5 minutes
- Critical alerts firing for > 10 minutes
- Database connection pool exhaustion
