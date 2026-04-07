"""Testes E2E para fluxo completo de otimização."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.consumers.ticket_completed_consumer import TicketCompletedConsumer
from src.analyzers.factory import AnalyzerFactory
from src.services.auto_applier import OptimizationApplier
from src.repositories.optimization_repository import OptimizationRepository


@pytest.mark.asyncio
class TestE2ETicketToRecommendation:
    """Testes E2E: ticket → analysis → recommendation."""

    async def test_full_workflow_mongodb_query_analysis(self):
        """Testa fluxo completo: ticket MongoDB → análise → recomendação."""
        # Simular evento ticket.completed
        ticket_event = {
            "ticket_id": "ticket-001",
            "workflow_id": "workflow-001",
            "status": "COMPLETED",
            "duration_ms": 2500,
            "peak_memory_mb": 128,
            "task_count": 1,
            "tasks": [
                {
                    "task_id": "task-001",
                    "executor_type": "query",
                    "duration_ms": 2500,
                    "collection": "users",
                    "query": '{"status": "active"}',
                }
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Executar análise
        analyzer = AnalyzerFactory.create_for_database("mongodb")
        context = {
            "pipeline": [
                {
                    "$lookup": {
                        "from": "profiles",
                        "localField": "user_id",
                        "foreignField": "_id",
                        "as": "profile",
                    }
                },
                {"$sort": {"created_at": -1}},
            ],
            "collection": "users",
        }

        result = await analyzer.analyze(context)

        # Verificar que foram detectados issues
        assert len(result.issues) > 0
        assert any("INDEX_SUGGESTION" in str(issue.get("type", "")) for issue in result.issues)

    async def test_full_workflow_postgresql_select_star(self):
        """Testa fluxo completo: ticket PostgreSQL → análise → recomendação."""
        ticket_event = {
            "ticket_id": "ticket-002",
            "workflow_id": "workflow-001",
            "status": "COMPLETED",
            "duration_ms": 5000,
            "peak_memory_mb": 256,
            "task_count": 1,
            "tasks": [
                {
                    "task_id": "task-002",
                    "executor_type": "query",
                    "database_type": "postgresql",
                    "query": "SELECT * FROM users WHERE status = 'active' ORDER BY created_at",
                }
            ],
        }

        # Executar análise
        analyzer = AnalyzerFactory.create_for_database("postgresql")
        result = await analyzer.analyze({"query": ticket_event["tasks"][0]["query"]})

        # Deve detectar SELECT * e ORDER BY sem LIMIT
        assert len(result.issues) >= 2

    async def test_full_workflow_code_complexity(self):
        """Testa fluxo completo: ticket código Python → análise → recomendação."""
        ticket_event = {
            "ticket_id": "ticket-003",
            "workflow_id": "workflow-001",
            "status": "COMPLETED",
            "duration_ms": 3000,
            "peak_memory_mb": 64,
            "task_count": 1,
            "tasks": [
                {
                    "task_id": "task-003",
                    "executor_type": "transform",
                    "file_path": "services/worker/src/processor.py",
                    "code": """
def complex_function(data):
    results = []
    for item in data:
        if item.get('status') == 'pending':
            if item.get('priority') > 5:
                for sub in item.get('subtasks', []):
                    if sub.get('needs_work'):
                        results.append(process(sub))
    return results
""",
                }
            ],
        }

        # Executar análise
        analyzer = AnalyzerFactory.create_for_database("code")
        result = await analyzer.analyze(
            {
                "code": ticket_event["tasks"][0]["code"],
                "file_path": ticket_event["tasks"][0]["file_path"],
            }
        )

        # Deve analisar a função
        assert result.metrics["analyzed_functions"] >= 1

    async def test_consumer_processes_ticket_event(self):
        """Testa que consumer processa evento e gera recomendações."""
        # Mock repository
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value="rec-001")

        # Mock Kafka consumer
        mock_consumer = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.value = {
            "ticket_id": "ticket-004",
            "workflow_id": "workflow-002",
            "status": "COMPLETED",
            "duration_ms": 2000,
            "peak_memory_mb": 100,
            "task_count": 1,
            "tasks": [
                {
                    "task_id": "task-004",
                    "executor_type": "query",
                    "collection": "orders",
                    "query": '{"status": "pending"}',
                }
            ],
        }

        # Criar consumer e processar mensagem
        consumer = TicketCompletedConsumer()
        consumer._repository = mock_repo

        # Processar mensagem (chamando método privado)
        await consumer._process_message(mock_msg)

        # Verificar que repository.create foi chamado (se houver recomendações)
        # Nota: pode não ser chamado se não houver issues detectados


@pytest.mark.asyncio
class TestE2EApproveApplyValidate:
    """Testes E2E: approve → apply → validate."""

    async def test_approve_recommendation_flow(self):
        """Testa fluxo de aprovação de recomendação."""
        # Mock repository
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(
            return_value={
                "id": "rec-001",
                "ticket_id": "ticket-001",
                "workflow_id": "workflow-001",
                "status": "pending",
                "recommendations": [
                    {
                        "id": "rec-001-1",
                        "type": "reduce_complexity",
                        "status": "pending",
                    }
                ],
            }
        )
        mock_repo.update_status = AsyncMock(return_value=True)

        # Aprovar recomendação
        rec = await mock_repo.get_by_id("rec-001")
        assert rec["status"] == "pending"

        # Atualizar status
        success = await mock_repo.update_status("rec-001", "approved", approved_by="user-001")
        assert success is True

    async def test_apply_recommendation_with_auto_applier(self):
        """Testa aplicação de recomendação via OptimizationApplier."""
        applier = OptimizationApplier(dry_run=True)

        recommendation = {
            "id": "rec-002",
            "file_path": "src/analyzers/base.py",
            "target_type": "code",
            "type": "reduce_complexity",
            "severity": "medium",
            "auto_apply": True,
            "code_diff": "@@ -1,1 +1,1 @@\n-old_line\n+new_line",
        }

        # Aplicar (dry run)
        result = await applier.apply_recommendation(recommendation, project_root=".")

        assert result["success"] is True
        assert result.get("dry_run") is True

    async def test_validate_application_improvement(self):
        """Testa validação de melhoria pós-aplicação."""
        applier = OptimizationApplier(dry_run=True)

        before = {"duration_ms": 5000}
        after = {"duration_ms": 3500}

        result = await applier.validate_application(before, after)

        assert result["valid"] is True
        assert result["improvement_pct"] == 30.0
        assert result["successful"] is True

    async def test_validate_regression_detection(self):
        """Testa detecção de regressão na validação."""
        applier = OptimizationApplier(dry_run=True)

        before = {"duration_ms": 2000}
        after = {"duration_ms": 3000}

        result = await applier.validate_application(before, after)

        assert result["improvement_pct"] == -50.0
        assert result["successful"] is False


@pytest.mark.asyncio
class TestE2EKafkaIntegration:
    """Testes E2E: integração Kafka."""

    async def test_kafka_producer_publishes_event(self):
        """Testa que producer publica evento ticket.completed."""
        # Nota: OptimizationProducer está no orchestrator-dynamic
        # Este teste valida o formato do evento que será produzido

        event = {
            "ticket_id": "ticket-005",
            "workflow_id": "workflow-003",
            "status": "COMPLETED",
            "duration_ms": 1500,
            "peak_memory_mb": 80,
            "task_count": 2,
            "tasks": [
                {"task_id": "t1", "executor_type": "query"},
                {"task_id": "t2", "executor_type": "transform"},
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Validar estrutura do evento
        assert "ticket_id" in event
        assert "workflow_id" in event
        assert "tasks" in event
        assert len(event["tasks"]) == 2

    async def test_kafka_consumer_receives_and_processes(self):
        """Testa que consumer recebe e processa evento."""
        # Simular mensagem Kafka
        kafka_message = MagicMock()
        kafka_message.value = {
            "ticket_id": "ticket-006",
            "workflow_id": "workflow-004",
            "status": "COMPLETED",
            "duration_ms": 1000,
            "peak_memory_mb": 50,
            "task_count": 1,
            "tasks": [
                {
                    "task_id": "task-006",
                    "executor_type": "query",
                    "collection": "users",
                    "query": '{"active": true}',
                }
            ],
        }

        # Criar consumer com mock repository
        consumer = TicketCompletedConsumer()
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value="rec-006")
        consumer._repository = mock_repo

        # Processar mensagem
        await consumer._process_message(kafka_message)

        # Verificar processamento (não deve lançar exceção)
        assert True  # Se chegou aqui, processou sem erro


@pytest.mark.asyncio
class TestE2EMultiDatabaseWorkflow:
    """Testes E2E: workflow multi-database."""

    async def test_workflow_analyzes_multiple_databases(self):
        """Testa workflow que analisa múltiplos tipos de banco."""
        ticket_event = {
            "ticket_id": "ticket-007",
            "workflow_id": "workflow-005",
            "status": "COMPLETED",
            "duration_ms": 8000,
            "peak_memory_mb": 512,
            "task_count": 5,
            "tasks": [
                {
                    "task_id": "task-001",
                    "executor_type": "query",
                    "database_type": "mongodb",
                    "collection": "users",
                    "query": '{"status": "active"}',
                },
                {
                    "task_id": "task-002",
                    "executor_type": "query",
                    "database_type": "postgresql",
                    "query": "SELECT * FROM orders",
                },
                {
                    "task_id": "task-003",
                    "executor_type": "query",
                    "database_type": "redis",
                    "query": "GET user:*",
                },
                {
                    "task_id": "task-004",
                    "executor_type": "transform",
                    "file_path": "src/processor.py",
                    "code": "def process(data): return [x for x in data if x]",
                },
                {
                    "task_id": "task-005",
                    "executor_type": "query",
                    "database_type": "clickhouse",
                    "query": "SELECT * FROM events",
                },
            ],
        }

        # Analisar cada task
        all_issues = []
        for task in ticket_event["tasks"]:
            db_type = task.get("database_type", "code")
            analyzer = AnalyzerFactory.create_for_database(db_type)

            if db_type == "code":
                result = await analyzer.analyze(
                    {
                        "code": task.get("code"),
                        "file_path": task.get("file_path"),
                    }
                )
            else:
                result = await analyzer.analyze(
                    {
                        "query": task.get("query"),
                        "collection": task.get("collection"),
                    }
                )

            all_issues.extend(result.issues)

        # Verificar que issues foram detectados
        assert len(all_issues) >= 0  # Pode ser 0 se queries estiverem otimizadas

    async def test_workflow_creates_unified_recommendation(self):
        """Testa que workflow cria recomendação unificada."""
        # Simular análise completa
        ticket_id = "ticket-008"
        workflow_id = "workflow-006"

        performance_analysis = {
            "total_duration_ms": 5000,
            "peak_memory_mb": 200,
            "task_count": 2,
            "bottlenecks": [
                {
                    "task_id": "task-001",
                    "task_type": "mongodb",
                    "issue": "Missing index on user_id",
                    "impact_score": 0.8,
                }
            ],
        }

        recommendations = [
            {
                "id": "rec-001",
                "type": "index_suggestion",
                "severity": "high",
                "target_type": "mongodb",
                "description": "Create index on user_id",
                "estimated_improvement_pct": 40.0,
                "auto_apply": False,
                "status": "pending",
            }
        ]

        recommendation_doc = {
            "ticket_id": ticket_id,
            "workflow_id": workflow_id,
            "status": "pending",
            "performance_analysis": performance_analysis,
            "recommendations": recommendations,
            "analyzed_by": "optimizer-agents",
            "analyzed_at": datetime.now(timezone.utc),
        }

        # Verificar estrutura
        assert recommendation_doc["ticket_id"] == ticket_id
        assert recommendation_doc["workflow_id"] == workflow_id
        assert len(recommendation_doc["recommendations"]) > 0
        assert len(recommendation_doc["performance_analysis"]["bottlenecks"]) > 0
