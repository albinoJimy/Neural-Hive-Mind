# Phase 2 Disaster Recovery Playbook

## 1) PostgreSQL Temporal Complete Loss
1. Identify last successful backup in S3: `aws s3 ls s3://neural-hive-backups-prod/temporal/backups/`.
2. Scale Temporal frontend to 0: `kubectl scale deployment temporal-frontend --replicas=0 -n temporal`.
3. Restore: `scripts/maintenance/restore-postgres-temporal.sh <backup_file>`.
4. Replay WAL to point-in-time: `aws s3 cp s3://neural-hive-backups-prod/temporal/wal/ /tmp/wal/ --recursive` and configure `restore_command`.
5. Scale frontend to 3 replicas and run smoke test workflows.

## 2) MongoDB Orchestration Cluster Failure
1. Promote DR snapshot and rebuild replica set.
2. Restore data: `mongorestore --uri $MONGODB_URI --drop /backups/orchestration`.
3. Reindex critical collections (`execution_tickets`, `validation_audit`, `workflow_results`).
4. Validate integrity via hash comparison of `validation_audit` entries.

## 3) Kafka Cluster Failure
1. Restore topics from MirrorMaker backup or tiered storage.
2. Replay messages: reset consumer offsets to last checkpoint for `plans.consensus`, `execution.tickets`, and SLA topics.
3. Monitor lag with `kafka-consumer-groups.sh --describe` until caught up.

## 4) Complete Phase 2 Outage
1. Execute emergency deploy script: `scripts/deploy/deploy-phase2-emergency.sh`.
2. Restore databases in parallel (PostgreSQL, MongoDB, Kafka topics).
3. Deploy services in dependency order: Service Registry → Orchestrator → Workers/Agents → Queen/Optimizers → Observability.
4. Run E2E validation suite: `tests/phase2-end-to-end-test.sh`.
5. Confirm alerts clear and circuit breakers return to closed state.
