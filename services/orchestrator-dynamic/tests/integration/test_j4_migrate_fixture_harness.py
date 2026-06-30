"""Testes Fase 0 / Task 1.1 do gate "J4/MIGRATE fiável".

Cobre os três artefactos da Fase 0 (DEFINE e testa em bloco; a execução real do
fixture é Fase 4):

1. Oráculo de contagens determinístico (derivado de scripts/init-legacy-db.sql).
2. Harness de injeção: constrói plano direto J4_MIGRATE (sem decision_id),
   pronto a produzir no topic plans.consensus.
3. Baseline: J4_MIGRATE -> OrchestrationWorkflow genérica (reusa a função já
   testada em tests/consumers/test_decision_consumer_journey_routing.py:74 — não
   a duplica, liga-a ao harness).
"""

from __future__ import annotations

from src.consumers.decision_consumer import (
    _deserialize_avro_or_json,
    _get_journey_from_plan,
    _select_workflow_class_by_journey,
)
from src.workflows.orchestration_workflow import OrchestrationWorkflow

from tests.integration.j4_migrate_fixture import (
    EXPECTED_LEGACY_COUNTS,
    LEGACY_SEED_PATH,
    MIGRATION_TABLES,
    build_j4_migrate_plan_message,
    expected_legacy_counts,
    legacy_row_count,
    parse_legacy_seed_counts,
    serialize_plan_message,
)

# =============================================================================
# Oráculo de contagens — determinístico, bate com o seed legacy
# =============================================================================


class TestLegacyCountOracle:
    """O oráculo expõe N linhas conhecidas (contagem determinística da origem)."""

    def test_seed_file_exists(self):
        assert LEGACY_SEED_PATH.is_file(), f"seed legacy ausente: {LEGACY_SEED_PATH}"

    def test_known_counts_are_explicit(self):
        """Contagens-oráculo explícitas (referência a init-legacy-db.sql)."""
        assert {
            "users": 5,
            "orders": 5,
            "products": 5,
            "order_items": 9,
        } == EXPECTED_LEGACY_COUNTS

    def test_parse_matches_known_constants(self):
        """Parse do ficheiro real bate com as constantes (anti-drift)."""
        assert parse_legacy_seed_counts() == EXPECTED_LEGACY_COUNTS

    def test_parse_is_deterministic(self):
        """Duas leituras consecutivas produzem o mesmo resultado."""
        assert parse_legacy_seed_counts() == parse_legacy_seed_counts()

    def test_expected_legacy_counts_helper(self):
        assert expected_legacy_counts() == EXPECTED_LEGACY_COUNTS

    def test_legacy_row_count_per_table(self):
        assert legacy_row_count("users") == 5
        assert legacy_row_count("order_items") == 9

    def test_oracle_covers_all_migration_tables(self):
        for table in MIGRATION_TABLES:
            assert table in EXPECTED_LEGACY_COUNTS


# =============================================================================
# Harness de injeção J4 — constrói mensagem de plano direto válida
# =============================================================================


class TestJ4MigratePlanHarness:
    """O harness constrói uma mensagem J4 válida (plan direto sem decision_id)."""

    def test_journey_is_j4_migrate(self):
        msg = build_j4_migrate_plan_message()
        assert msg["journey"] == "J4_MIGRATE"

    def test_context_source_is_doc_ingestion(self):
        """Sinal estruturado que o STE usa para classificar J4_MIGRATE."""
        msg = build_j4_migrate_plan_message()
        assert msg["context"]["source"] == "doc-ingestion"

    def test_is_direct_plan_no_decision_id(self):
        """is_direct_plan no consumer: tem 'tasks' e NÃO tem 'decision_id'."""
        msg = build_j4_migrate_plan_message()
        assert "tasks" in msg
        assert "decision_id" not in msg

    def test_has_required_plan_fields(self):
        """Campos obrigatórios do Cognitive Plan no consumer."""
        msg = build_j4_migrate_plan_message()
        for field in ("tasks", "execution_order", "risk_band"):
            assert field in msg

    def test_migration_config_present_and_complete(self):
        msg = build_j4_migrate_plan_message()
        cfg = msg["migration_config"]
        assert cfg["legacy_connection_id"] == "postgres-legacy"
        assert cfg["modern_connection_id"] == "postgres-modern"
        assert cfg["tables"] == MIGRATION_TABLES

    def test_tables_override_is_respected(self):
        msg = build_j4_migrate_plan_message(tables=["users"])
        assert msg["migration_config"]["tables"] == ["users"]

    def test_execution_order_matches_tasks(self):
        msg = build_j4_migrate_plan_message()
        task_ids = [t["task_id"] for t in msg["tasks"]]
        assert msg["execution_order"] == task_ids

    def test_journey_extraction_via_consumer_helper(self):
        """O consumer extrai a journey correta da mensagem do harness."""
        msg = build_j4_migrate_plan_message()
        assert _get_journey_from_plan(msg) == "J4_MIGRATE"

    def test_message_roundtrips_through_consumer_deserializer(self):
        """Serializa -> _deserialize_avro_or_json preserva journey + config.

        Prova que a mensagem está 'pronta a produzir' no topic plans.consensus
        (o consumer aceita JSON puro).
        """
        msg = build_j4_migrate_plan_message()
        decoded = _deserialize_avro_or_json(serialize_plan_message(msg))
        assert decoded["journey"] == "J4_MIGRATE"
        assert decoded["migration_config"]["tables"] == MIGRATION_TABLES
        assert "decision_id" not in decoded


# =============================================================================
# Baseline do gap — J4_MIGRATE roteia para a OrchestrationWorkflow genérica
# =============================================================================


class TestJ4BaselineRoutingGap:
    """Baseline (o gap): J4 cai na OrchestrationWorkflow genérica (=J2).

    Reusa _select_workflow_class_by_journey (já testada com mocks na suite de
    routing congelada); aqui valida a CLASSE REAL e liga-a ao harness — não
    duplica o teste existente.
    """

    def test_j4_migrate_routes_to_orchestration_real_class(self):
        assert _select_workflow_class_by_journey("J4_MIGRATE") is OrchestrationWorkflow

    def test_baseline_from_harness_message(self):
        """Da mensagem do harness ao workflow: J4 -> OrchestrationWorkflow."""
        msg = build_j4_migrate_plan_message()
        journey = _get_journey_from_plan(msg)
        assert _select_workflow_class_by_journey(journey) is OrchestrationWorkflow
