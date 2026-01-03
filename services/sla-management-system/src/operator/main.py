"""
Kubernetes Operator for SLA Management System.

This operator reconciles SLODefinition and SLAPolicy custom resources,
synchronizing them with the PostgreSQL database and maintaining state.
"""

import asyncio
import os
import kopf
import structlog
from datetime import datetime
from typing import Dict, Any, Optional
from kubernetes import client, config

from src.services.slo_manager import SLOManager
from src.services.policy_enforcer import PolicyEnforcer
from src.clients.postgresql_client import PostgreSQLClient
from src.clients.prometheus_client import PrometheusClient
from src.clients.redis_client import RedisClient
from src.config.settings import Settings
from src.models.slo_definition import SLODefinition, SLOType
from src.models.freeze_policy import FreezePolicy, PolicyScope, PolicyAction
from src.observability.metrics import sla_metrics

# Initialize logger
logger = structlog.get_logger(__name__)

# Global clients - initialized in startup handler
postgresql_client: Optional[PostgreSQLClient] = None
prometheus_client: Optional[PrometheusClient] = None
redis_client: Optional[RedisClient] = None
slo_manager: Optional[SLOManager] = None
policy_enforcer: Optional[PolicyEnforcer] = None
settings: Optional[Settings] = None
reconciliation_interval: float = 300.0  # Default 5 minutes


@kopf.on.startup()
async def startup_handler(memo: kopf.Memo, **kwargs):
    """
    Initialize clients and services on operator startup.
    """
    global postgresql_client, prometheus_client, redis_client, slo_manager, policy_enforcer, settings, reconciliation_interval

    logger.info("Starting SLA Management System Operator")

    # Load configuration
    settings = Settings()

    # Load reconciliation interval from environment variable
    reconciliation_interval = float(os.getenv('RECONCILIATION_INTERVAL', '300'))
    logger.info(f"Reconciliation interval set to {reconciliation_interval} seconds")

    # Initialize Kubernetes client
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    # Initialize clients with their specific settings
    postgresql_client = PostgreSQLClient(settings.postgresql)
    await postgresql_client.connect()
    logger.info("PostgreSQL client connected")

    prometheus_client = PrometheusClient(settings.prometheus)
    logger.info("Prometheus client initialized")

    redis_client = RedisClient(settings.redis)
    await redis_client.connect()
    logger.info("Redis client connected")

    # Initialize services
    slo_manager = SLOManager(
        postgresql_client=postgresql_client,
        prometheus_client=prometheus_client
    )
    logger.info("SLO Manager initialized")

    # PolicyEnforcer requires kafka_producer - create a minimal one or skip for now
    # For now, skip PolicyEnforcer initialization in operator (not strictly needed for CRD sync)
    policy_enforcer = None
    logger.info("Policy Enforcer skipped (Kafka producer not configured for operator)")

    logger.info("SLA Management System Operator started successfully")


@kopf.on.cleanup()
async def cleanup_handler(**kwargs):
    """
    Cleanup resources on operator shutdown.
    """
    logger.info("Shutting down SLA Management System Operator")

    if postgresql_client:
        await postgresql_client.disconnect()
    if redis_client:
        await redis_client.disconnect()

    logger.info("SLA Management System Operator shutdown complete")


@kopf.on.create('neural-hive.io', 'v1', 'slodefinitions')
async def slo_create_handler(spec: Dict[str, Any], name: str, namespace: str, meta: Dict[str, Any], **kwargs):
    """
    Handle creation of SLODefinition CRD.
    """
    logger.info(f"Creating SLO: {name} in namespace {namespace}")

    try:
        # Convert CRD spec to SLODefinition model
        slo = SLODefinition(
            name=spec['name'],
            description=spec.get('description', ''),
            slo_type=SLOType(spec['sloType']),
            service_name=spec['serviceName'],
            component=spec.get('component'),
            layer=spec['layer'],
            target=spec['target'],
            window_days=spec.get('windowDays', 30),
            sli_query={
                'metric_name': spec['sliQuery']['metricName'],
                'query': spec['sliQuery']['query'],
                'aggregation': spec['sliQuery'].get('aggregation', 'avg'),
                'labels': spec['sliQuery'].get('labels', {})
            },
            enabled=spec.get('enabled', True),
            metadata=spec.get('metadata', {})
        )

        # Create SLO in database
        slo_id = await slo_manager.create_slo(slo)

        logger.info(f"SLO created in database with ID: {slo_id}")

        # Return status to update CRD
        return {
            'synced': True,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'sloId': str(slo_id),
            'conditions': [{
                'type': 'Synced',
                'status': 'True',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncSuccessful',
                'message': f'SLO created in database with ID {slo_id}'
            }]
        }

    except Exception as e:
        logger.error(f"Failed to create SLO {name}: {str(e)}", exc_info=True)
        sla_metrics.record_crd_sync_error(crd_type="slodefinition")
        return {
            'synced': False,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'conditions': [{
                'type': 'Synced',
                'status': 'False',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncFailed',
                'message': f'Failed to create SLO: {str(e)}'
            }]
        }


@kopf.on.update('neural-hive.io', 'v1', 'slodefinitions')
async def slo_update_handler(spec: Dict[str, Any], name: str, namespace: str, status: Dict[str, Any], **kwargs):
    """
    Handle updates to SLODefinition CRD.
    """
    logger.info(f"Updating SLO: {name} in namespace {namespace}")

    try:
        slo_id = status.get('sloId')

        # Auto-recovery: se não há sloId, tentar encontrar por nome ou criar novo
        if not slo_id:
            logger.warning(f"SLO ID not found in status for {name}, attempting auto-recovery")

            # Tentar encontrar SLO existente por nome e namespace
            existing_slo = await postgresql_client.find_slo_by_name(
                name=spec['name'],
                namespace=namespace
            )

            if existing_slo:
                # SLO encontrado, usar o ID existente
                slo_id = existing_slo.slo_id
                logger.info(f"Found existing SLO with ID: {slo_id}, will update it")
            else:
                # SLO não encontrado, criar novo
                logger.info(f"No existing SLO found, creating new one")
                slo = SLODefinition(
                    name=spec['name'],
                    description=spec.get('description', ''),
                    slo_type=SLOType(spec['sloType']),
                    service_name=spec['serviceName'],
                    component=spec.get('component'),
                    layer=spec['layer'],
                    target=spec['target'],
                    window_days=spec.get('windowDays', 30),
                    sli_query={
                        'metric_name': spec['sliQuery']['metricName'],
                        'query': spec['sliQuery']['query'],
                        'aggregation': spec['sliQuery'].get('aggregation', 'avg'),
                        'labels': spec['sliQuery'].get('labels', {})
                    },
                    enabled=spec.get('enabled', True),
                    metadata={'namespace': namespace, **(spec.get('metadata', {}))}
                )
                slo_id = await slo_manager.create_slo(slo)
                logger.info(f"Created new SLO with ID: {slo_id}")

                # Retornar status atualizado com o novo ID
                return {
                    'synced': True,
                    'lastSyncTime': datetime.utcnow().isoformat(),
                    'sloId': str(slo_id),
                    'conditions': [{
                        'type': 'Synced',
                        'status': 'True',
                        'lastTransitionTime': datetime.utcnow().isoformat(),
                        'reason': 'AutoRecoverySuccessful',
                        'message': f'SLO created via auto-recovery with ID {slo_id}'
                    }]
                }

        # Convert CRD spec to SLODefinition model
        slo_updates = {
            'name': spec['name'],
            'description': spec.get('description', ''),
            'slo_type': SLOType(spec['sloType']),
            'service_name': spec['serviceName'],
            'component': spec.get('component'),
            'layer': spec['layer'],
            'target': spec['target'],
            'window_days': spec.get('windowDays', 30),
            'sli_query': {
                'metric_name': spec['sliQuery']['metricName'],
                'query': spec['sliQuery']['query'],
                'aggregation': spec['sliQuery'].get('aggregation', 'avg'),
                'labels': spec['sliQuery'].get('labels', {})
            },
            'enabled': spec.get('enabled', True),
            'metadata': spec.get('metadata', {})
        }

        # Update SLO in database
        await slo_manager.update_slo(slo_id, slo_updates)

        logger.info(f"SLO updated in database: {slo_id}")

        return {
            'synced': True,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'sloId': slo_id,
            'conditions': [{
                'type': 'Synced',
                'status': 'True',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncSuccessful',
                'message': f'SLO updated in database'
            }]
        }

    except Exception as e:
        logger.error(f"Failed to update SLO {name}: {str(e)}", exc_info=True)
        sla_metrics.record_crd_sync_error(crd_type="slodefinition")
        return {
            'synced': False,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'conditions': [{
                'type': 'Synced',
                'status': 'False',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncFailed',
                'message': f'Failed to update SLO: {str(e)}'
            }]
        }


@kopf.on.delete('neural-hive.io', 'v1', 'slodefinitions')
async def slo_delete_handler(spec: Dict[str, Any], name: str, namespace: str, status: Dict[str, Any], **kwargs):
    """
    Handle deletion of SLODefinition CRD (soft delete).
    """
    logger.info(f"Deleting SLO: {name} in namespace {namespace}")

    try:
        slo_id = status.get('sloId')
        if not slo_id:
            logger.warning(f"SLO ID not found in status for {name} - skipping delete")
            return

        # Soft delete by disabling the SLO
        await slo_manager.update_slo(slo_id, {'enabled': False})

        logger.info(f"SLO soft-deleted (disabled) in database: {slo_id}")

    except Exception as e:
        logger.error(f"Failed to delete SLO {name}: {str(e)}", exc_info=True)
        raise kopf.PermanentError(f"Failed to delete SLO: {str(e)}")


@kopf.on.create('neural-hive.io', 'v1', 'slapolicies')
async def policy_create_handler(spec: Dict[str, Any], name: str, namespace: str, **kwargs):
    """
    Handle creation of SLAPolicy CRD.
    """
    logger.info(f"Creating SLA Policy: {name} in namespace {namespace}")

    try:
        # Convert CRD spec to FreezePolicy model
        policy = FreezePolicy(
            name=spec['name'],
            description=spec.get('description', ''),
            scope=PolicyScope(spec['scope']),
            target=spec['target'],
            actions=[PolicyAction(action) for action in spec['actions']],
            trigger_threshold_percent=spec.get('triggerThresholdPercent', 20),
            auto_unfreeze=spec.get('autoUnfreeze', True),
            unfreeze_threshold_percent=spec.get('unfreezeThresholdPercent', 50),
            enabled=spec.get('enabled', True),
            metadata=spec.get('metadata', {})
        )

        # Create policy in database
        policy_id = await postgresql_client.create_policy(policy)

        logger.info(f"SLA Policy created in database with ID: {policy_id}")

        return {
            'synced': True,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'policyId': str(policy_id),
            'activeFreezes': 0,
            'conditions': [{
                'type': 'Synced',
                'status': 'True',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncSuccessful',
                'message': f'Policy created in database with ID {policy_id}'
            }]
        }

    except Exception as e:
        logger.error(f"Failed to create SLA Policy {name}: {str(e)}", exc_info=True)
        sla_metrics.record_crd_sync_error(crd_type="slapolicy")
        return {
            'synced': False,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'conditions': [{
                'type': 'Synced',
                'status': 'False',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncFailed',
                'message': f'Failed to create policy: {str(e)}'
            }]
        }


@kopf.on.update('neural-hive.io', 'v1', 'slapolicies')
async def policy_update_handler(spec: Dict[str, Any], name: str, namespace: str, status: Dict[str, Any], **kwargs):
    """
    Handle updates to SLAPolicy CRD.
    """
    logger.info(f"Updating SLA Policy: {name} in namespace {namespace}")

    try:
        policy_id = status.get('policyId')

        # Auto-recovery: se não há policyId, tentar encontrar por nome ou criar novo
        if not policy_id:
            logger.warning(f"Policy ID not found in status for {name}, attempting auto-recovery")

            # Tentar encontrar Policy existente por nome e namespace
            existing_policy = await postgresql_client.find_policy_by_name(
                name=spec['name'],
                namespace=namespace
            )

            if existing_policy:
                # Policy encontrada, usar o ID existente
                policy_id = existing_policy.policy_id
                logger.info(f"Found existing Policy with ID: {policy_id}, will update it")
            else:
                # Policy não encontrada, criar nova
                logger.info(f"No existing Policy found, creating new one")
                policy = FreezePolicy(
                    name=spec['name'],
                    description=spec.get('description', ''),
                    scope=PolicyScope(spec['scope']),
                    target=spec['target'],
                    actions=[PolicyAction(action) for action in spec['actions']],
                    trigger_threshold_percent=spec.get('triggerThresholdPercent', 20),
                    auto_unfreeze=spec.get('autoUnfreeze', True),
                    unfreeze_threshold_percent=spec.get('unfreezeThresholdPercent', 50),
                    enabled=spec.get('enabled', True),
                    metadata={'namespace': namespace, **(spec.get('metadata', {}))}
                )
                policy_id = await postgresql_client.create_policy(policy)
                logger.info(f"Created new Policy with ID: {policy_id}")

                # Retornar status atualizado com o novo ID
                return {
                    'synced': True,
                    'lastSyncTime': datetime.utcnow().isoformat(),
                    'policyId': str(policy_id),
                    'activeFreezes': 0,
                    'conditions': [{
                        'type': 'Synced',
                        'status': 'True',
                        'lastTransitionTime': datetime.utcnow().isoformat(),
                        'reason': 'AutoRecoverySuccessful',
                        'message': f'Policy created via auto-recovery with ID {policy_id}'
                    }]
                }

        # Convert CRD spec to policy updates
        policy_updates = {
            'name': spec['name'],
            'description': spec.get('description', ''),
            'scope': PolicyScope(spec['scope']),
            'target': spec['target'],
            'actions': [PolicyAction(action) for action in spec['actions']],
            'trigger_threshold_percent': spec.get('triggerThresholdPercent', 20),
            'auto_unfreeze': spec.get('autoUnfreeze', True),
            'unfreeze_threshold_percent': spec.get('unfreezeThresholdPercent', 50),
            'enabled': spec.get('enabled', True),
            'metadata': spec.get('metadata', {})
        }

        # Update policy in database
        await postgresql_client.update_policy(policy_id, policy_updates)

        logger.info(f"SLA Policy updated in database: {policy_id}")

        return {
            'synced': True,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'policyId': policy_id,
            'conditions': [{
                'type': 'Synced',
                'status': 'True',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncSuccessful',
                'message': f'Policy updated in database'
            }]
        }

    except Exception as e:
        logger.error(f"Failed to update SLA Policy {name}: {str(e)}", exc_info=True)
        sla_metrics.record_crd_sync_error(crd_type="slapolicy")
        return {
            'synced': False,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'conditions': [{
                'type': 'Synced',
                'status': 'False',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'SyncFailed',
                'message': f'Failed to update policy: {str(e)}'
            }]
        }


@kopf.on.delete('neural-hive.io', 'v1', 'slapolicies')
async def policy_delete_handler(spec: Dict[str, Any], name: str, namespace: str, status: Dict[str, Any], **kwargs):
    """
    Handle deletion of SLAPolicy CRD (soft delete).
    """
    logger.info(f"Deleting SLA Policy: {name} in namespace {namespace}")

    try:
        policy_id = status.get('policyId')
        if not policy_id:
            logger.warning(f"Policy ID not found in status for {name} - skipping delete")
            return

        # Soft delete by disabling the policy
        await postgresql_client.update_policy(policy_id, {'enabled': False})

        logger.info(f"SLA Policy soft-deleted (disabled) in database: {policy_id}")

    except Exception as e:
        logger.error(f"Failed to delete SLA Policy {name}: {str(e)}", exc_info=True)
        raise kopf.PermanentError(f"Failed to delete policy: {str(e)}")


@kopf.timer('neural-hive.io', 'v1', 'slodefinitions', idle=1.0)
async def slo_reconciliation_timer(spec: Dict[str, Any], name: str, namespace: str, status: Dict[str, Any], **kwargs):
    """
    Periodic reconciliation of SLODefinition CRDs.
    Uses RECONCILIATION_INTERVAL environment variable for interval (default 300s).
    """
    global reconciliation_interval

    # Sleep for the configured interval
    await asyncio.sleep(reconciliation_interval)

    logger.debug(f"Reconciling SLO: {name} in namespace {namespace}")

    try:
        slo_id = status.get('sloId')

        # Auto-recovery: se não há sloId, tentar encontrar por nome
        if not slo_id:
            logger.warning(f"SLO ID not found for {name} during reconciliation, attempting auto-recovery")

            # Tentar encontrar SLO existente por nome e namespace
            existing_slo = await postgresql_client.find_slo_by_name(
                name=spec['name'],
                namespace=namespace
            )

            if existing_slo:
                # SLO encontrado, atualizar status com o ID
                slo_id = existing_slo.slo_id
                logger.info(f"Auto-recovery: Found existing SLO with ID: {slo_id}")

                return {
                    'synced': True,
                    'lastSyncTime': datetime.utcnow().isoformat(),
                    'sloId': str(slo_id),
                    'conditions': [{
                        'type': 'Synced',
                        'status': 'True',
                        'lastTransitionTime': datetime.utcnow().isoformat(),
                        'reason': 'AutoRecoverySuccessful',
                        'message': f'SLO ID recovered: {slo_id}'
                    }]
                }
            else:
                # Não foi possível recuperar, sinalizar para re-criação
                logger.error(f"Auto-recovery failed: SLO not found for {name}")
                return {
                    'synced': False,
                    'lastSyncTime': datetime.utcnow().isoformat(),
                    'conditions': [{
                        'type': 'Synced',
                        'status': 'False',
                        'lastTransitionTime': datetime.utcnow().isoformat(),
                        'reason': 'AutoRecoveryFailed',
                        'message': 'SLO ID not found and no matching SLO in database'
                    }]
                }

        # Verify SLO still exists in database
        slo = await slo_manager.get_slo(slo_id)
        if not slo:
            logger.warning(f"SLO {slo_id} not found in database - may need re-sync")
            return {
                'synced': False,
                'lastSyncTime': datetime.utcnow().isoformat(),
                'conditions': [{
                    'type': 'Synced',
                    'status': 'False',
                    'lastTransitionTime': datetime.utcnow().isoformat(),
                    'reason': 'NotFoundInDatabase',
                    'message': 'SLO not found in database'
                }]
            }

        # Get current budget status
        budget = await slo_manager.get_budget(slo_id)

        # Update status with current values
        return {
            'synced': True,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'sloId': slo_id,
            'currentSLI': budget.current_sli if budget else None,
            'budgetRemaining': budget.remaining_percent if budget else None,
            'budgetStatus': budget.status.value if budget else None,
            'conditions': [{
                'type': 'Synced',
                'status': 'True',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'ReconciliationSuccessful',
                'message': 'Periodic reconciliation completed'
            }]
        }

    except Exception as e:
        logger.error(f"Failed to reconcile SLO {name}: {str(e)}", exc_info=True)
        # Don't update status on reconciliation errors to avoid flapping


@kopf.timer('neural-hive.io', 'v1', 'slapolicies', idle=1.0)
async def policy_reconciliation_timer(spec: Dict[str, Any], name: str, namespace: str, status: Dict[str, Any], **kwargs):
    """
    Periodic reconciliation of SLAPolicy CRDs.
    Uses RECONCILIATION_INTERVAL environment variable for interval (default 300s).
    """
    global reconciliation_interval

    # Sleep for the configured interval
    await asyncio.sleep(reconciliation_interval)

    logger.debug(f"Reconciling SLA Policy: {name} in namespace {namespace}")

    try:
        policy_id = status.get('policyId')

        # Auto-recovery: se não há policyId, tentar encontrar por nome
        if not policy_id:
            logger.warning(f"Policy ID not found for {name} during reconciliation, attempting auto-recovery")

            # Tentar encontrar Policy existente por nome e namespace
            existing_policy = await postgresql_client.find_policy_by_name(
                name=spec['name'],
                namespace=namespace
            )

            if existing_policy:
                # Policy encontrada, atualizar status com o ID
                policy_id = existing_policy.policy_id
                logger.info(f"Auto-recovery: Found existing Policy with ID: {policy_id}")

                return {
                    'synced': True,
                    'lastSyncTime': datetime.utcnow().isoformat(),
                    'policyId': str(policy_id),
                    'activeFreezes': 0,
                    'conditions': [{
                        'type': 'Synced',
                        'status': 'True',
                        'lastTransitionTime': datetime.utcnow().isoformat(),
                        'reason': 'AutoRecoverySuccessful',
                        'message': f'Policy ID recovered: {policy_id}'
                    }]
                }
            else:
                # Não foi possível recuperar, sinalizar para re-criação
                logger.error(f"Auto-recovery failed: Policy not found for {name}")
                return {
                    'synced': False,
                    'lastSyncTime': datetime.utcnow().isoformat(),
                    'conditions': [{
                        'type': 'Synced',
                        'status': 'False',
                        'lastTransitionTime': datetime.utcnow().isoformat(),
                        'reason': 'AutoRecoveryFailed',
                        'message': 'Policy ID not found and no matching Policy in database'
                    }]
                }

        # Verify policy still exists in database
        policy = await postgresql_client.get_policy(policy_id)
        if not policy:
            logger.warning(f"Policy {policy_id} not found in database - may need re-sync")
            return {
                'synced': False,
                'lastSyncTime': datetime.utcnow().isoformat(),
                'conditions': [{
                    'type': 'Synced',
                    'status': 'False',
                    'lastTransitionTime': datetime.utcnow().isoformat(),
                    'reason': 'NotFoundInDatabase',
                    'message': 'Policy not found in database'
                }]
            }

        # Get active freezes for this policy (if policy_enforcer is available)
        active_freezes = []
        if policy_enforcer:
            active_freezes = await policy_enforcer.get_active_freezes(policy_id=policy_id)

        # Update status with current values
        return {
            'synced': True,
            'lastSyncTime': datetime.utcnow().isoformat(),
            'policyId': policy_id,
            'activeFreezes': len(active_freezes) if active_freezes else 0,
            'lastTriggeredAt': max([f.triggered_at for f in active_freezes]).isoformat() if active_freezes else None,
            'conditions': [{
                'type': 'Synced',
                'status': 'True',
                'lastTransitionTime': datetime.utcnow().isoformat(),
                'reason': 'ReconciliationSuccessful',
                'message': 'Periodic reconciliation completed'
            }]
        }

    except Exception as e:
        logger.error(f"Failed to reconcile SLA Policy {name}: {str(e)}", exc_info=True)
        # Don't update status on reconciliation errors to avoid flapping


if __name__ == '__main__':
    # Run the operator
    kopf.run()
