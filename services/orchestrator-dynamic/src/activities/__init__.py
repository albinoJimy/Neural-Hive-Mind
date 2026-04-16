# CI/CD Cache Fix - Force rebuild
# This comment triggers a new commit to invalidate CI/CD cache

"""
Atividades Temporal para Orchestrator Dynamic.

Este pacote contém as atividades chamadas pelos workflows Temporal.
"""

from .cutover import (
    configure_canary_traffic,
    configure_full_cutover,
    execute_rollback as cutover_execute_rollback,
    finalize_shadow_mode,
    initialize_shadow_mode,
    monitor_canary_metrics,
    monitor_stabilization,
    validate_canary_stage,
    validate_shadow_metrics,
    verify_full_cutover,
)
from .data_migration import (
    analyze_legacy_schema,
    approve_mapping,
    cleanup_snapshot,
    create_snapshot,
    execute_rollback as migration_execute_rollback,
    generate_schema_mapping,
    run_batch_migration,
    start_cdc,
    validate_data,
)

__all__ = [
    # Cutover activities
    "configure_canary_traffic",
    "configure_full_cutover",
    "cutover_execute_rollback",
    "finalize_shadow_mode",
    "initialize_shadow_mode",
    "monitor_canary_metrics",
    "monitor_stabilization",
    "validate_canary_stage",
    "validate_shadow_metrics",
    "verify_full_cutover",
    # Data Migration activities
    "analyze_legacy_schema",
    "approve_mapping",
    "cleanup_snapshot",
    "create_snapshot",
    "migration_execute_rollback",
    "generate_schema_mapping",
    "run_batch_migration",
    "start_cdc",
    "validate_data",
]
