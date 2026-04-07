"""Testes de integração para otimizações multi-database."""

import pytest
import asyncio
from datetime import datetime

from src.analyzers.factory import AnalyzerFactory, AnalyzerType
from src.analyzers.mongodb_analyzer import MongoDBAnalyzer
from src.analyzers.postgresql_analyzer import PostgreSQLAnalyzer
from src.analyzers.code_analyzer import CodeAnalyzer


@pytest.mark.asyncio
class TestMultiDatabaseAnalyzers:
    """Testes de analyzers multi-database."""

    async def test_mongodb_analyzer_pipeline(self):
        """Testa análise de pipeline MongoDB."""
        analyzer = MongoDBAnalyzer()
        pipeline = [
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "_id",
                    "as": "user",
                }
            },
            {"$sort": {"created_at": -1}},
            {"$limit": 100},
        ]
        result = await analyzer.analyze({"pipeline": pipeline, "collection": "orders"})

        assert len(result.issues) >= 1
        assert any("INDEX_SUGGESTION" in str(issue.get("type", "")) for issue in result.issues)

    async def test_postgresql_analyzer_select_star(self):
        """Testa detecção de SELECT *."""
        analyzer = PostgreSQLAnalyzer()
        query = "SELECT * FROM users WHERE status = 'active' ORDER BY created_at"
        result = await analyzer.analyze({"query": query})

        assert len(result.issues) >= 2  # SELECT * e ORDER BY sem LIMIT

    async def test_code_analyzer_complexity(self):
        """Testa análise de complexidade."""
        analyzer = CodeAnalyzer()

        # Função com complexidade alta (>15) para trigger de recomendação
        # Complexidade = 1 + (for * 5) + (if * 12) + (while * 1) = 19+
        code = """
def complex_function(data, options):
    results = []
    for item in data:
        if item.get('status') == 'active':
            if item.get('type') == 'premium':
                if item.get('verified'):
                    results.append(process_premium(item))
                else:
                    results.append(queue_verification(item))
            elif item.get('type') == 'standard':
                if item.get('priority') > 5:
                    results.append(process_priority(item))
                else:
                    results.append(process_normal(item))
            elif item.get('type') == 'vip':
                if item.get('expires'):
                    results.append(process_vip(item))
            elif item.get('type') == 'trial':
                if item.get('days_left', 0) < 3:
                    results.append(expire_trial(item))
            elif item.get('type') == 'enterprise':
                for contract in item.get('contracts', []):
                    if contract.get('active'):
                        results.append(process_contract(contract))
            else:
                for tag in item.get('tags', []):
                    if tag.startswith('special'):
                        results.append(process_special(item, tag))
        elif item.get('status') == 'pending':
            for attempt in range(3):
                if attempt == 0:
                    results.append(first_attempt(item))
                elif attempt == 1:
                    results.append(second_attempt(item))
        elif item.get('status') == 'failed':
            if item.get('retry'):
                results.append(schedule_retry(item))
        else:
            if options.get('include_archived'):
                results.append(archive_item(item))
    while len(results) < 100:
        if options.get('fill_results'):
            results.append(default_result())
        else:
            break
    return results
"""
        result = await analyzer.analyze({"code": code, "file_path": "test.py"})

        assert result.metrics["analyzed_functions"] == 1
        # Complexidade >> 15 deve gerar pelo menos uma recomendação
        assert len(result.issues) >= 1
        assert result.issues[0]["type"] == "reduce_complexity"

    async def test_factory_creates_correct_analyzer(self):
        """Testa factory cria analyzer correto."""
        mongo_analyzer = AnalyzerFactory.create_for_database("mongodb")
        assert isinstance(mongo_analyzer, MongoDBAnalyzer)

        pg_analyzer = AnalyzerFactory.create_for_database("postgresql")
        assert isinstance(pg_analyzer, PostgreSQLAnalyzer)

        code_analyzer = AnalyzerFactory.create_for_database("unknown")
        assert isinstance(code_analyzer, CodeAnalyzer)


class TestRecommendationModels:
    """Testes dos modelos de recomendação."""

    def test_recommendation_creation(self):
        """Testa criação de recomendação."""
        from src.analyzers.base import (
            RecommendationType,
            Severity,
            TargetType,
        )

        rec = {
            "type": RecommendationType.REDUCE_COMPLEXITY,
            "severity": Severity.HIGH,
            "description": "Função muito complexa",
            "estimated_improvement_pct": 40.0,
            "target_type": TargetType.CODE,
            "file_path": "test.py",
            "line_number": 42,
        }

        assert rec["type"] == RecommendationType.REDUCE_COMPLEXITY
        assert rec["severity"] == Severity.HIGH
        assert rec["target_type"] == TargetType.CODE

    def test_all_target_types(self):
        """Testa todos os tipos de target suportados."""
        from src.analyzers.base import TargetType

        assert TargetType.CODE.value == "code"
        assert TargetType.MONGODB.value == "mongodb"
        assert TargetType.POSTGRESQL.value == "postgresql"
        assert TargetType.NEO4J.value == "neo4j"
        assert TargetType.REDIS.value == "redis"
        assert TargetType.CLICKHOUSE.value == "clickhouse"


@pytest.mark.asyncio
class TestWorkflowIntegration:
    """Testes de integração do workflow de otimização."""

    async def test_full_workflow_mongodb(self):
        """Testa workflow completo para MongoDB."""
        analyzer = AnalyzerFactory.create_for_database("mongodb")

        # Simular contexto de ticket
        context = {
            "query": '{"status": "active", "created_at": {"$gt": "2024-01-01"}}',
            "collection": "users",
        }

        result = await analyzer.analyze(context)

        assert result is not None
        assert "issues" in result.__dict__ or "issues" in dir(result)

    async def test_full_workflow_postgresql(self):
        """Testa workflow completo para PostgreSQL."""
        analyzer = AnalyzerFactory.create_for_database("postgresql")

        context = {
            "query": "SELECT * FROM orders JOIN users ON orders.user_id = users.id WHERE users.status = 'active'",
        }

        result = await analyzer.analyze(context)

        assert result is not None
        # Deve detectar SELECT *
        issues = result.issues
        assert len(issues) >= 1

    async def test_full_workflow_code(self):
        """Testa workflow completo para código Python."""
        analyzer = AnalyzerFactory.create_for_database("code")

        context = {
            "code": """
def process_batch(items):
    results = []
    for item in items:
        if item.status == "pending":
            for sub in item.subtasks:
                if sub.needs_processing:
                    result = process(sub)
                    results.append(result)
    return results
""",
            "file_path": "services/worker/src/processor.py",
        }

        result = await analyzer.analyze(context)

        assert result.metrics["analyzed_functions"] >= 1
