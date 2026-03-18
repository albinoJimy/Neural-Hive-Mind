"""Testes unitários para analyzers multi-database."""
import pytest
import asyncio
from src.analyzers.factory import AnalyzerFactory, AnalyzerType
from src.analyzers.mongodb_analyzer import MongoDBAnalyzer
from src.analyzers.postgresql_analyzer import PostgreSQLAnalyzer
from src.analyzers.code_analyzer import CodeAnalyzer


class TestAnalyzerFactory:
    """Testes para AnalyzerFactory."""

    def test_create_mongodb_analyzer(self):
        analyzer = AnalyzerFactory.create(AnalyzerType.MONGODB)
        assert isinstance(analyzer, MongoDBAnalyzer)

    def test_create_from_string(self):
        analyzer = AnalyzerFactory.create("mongodb")
        assert isinstance(analyzer, MongoDBAnalyzer)

    def test_create_for_database(self):
        analyzer = AnalyzerFactory.create_for_database("mongodb")
        assert isinstance(analyzer, MongoDBAnalyzer)


@pytest.mark.asyncio
class TestMongoDBAnalyzer:
    """Testes para MongoDBAnalyzer."""

    async def test_analyze_pipeline(self):
        analyzer = MongoDBAnalyzer()
        pipeline = [{"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id"}}]
        result = await analyzer.analyze({"pipeline": pipeline, "collection": "orders"})
        assert len(result.issues) >= 1


@pytest.mark.asyncio
class TestPostgreSQLAnalyzer:
    """Testes para PostgreSQLAnalyzer."""

    async def test_select_star(self):
        analyzer = PostgreSQLAnalyzer()
        result = await analyzer.analyze({"query": "SELECT * FROM users"})
        assert len(result.issues) >= 1


@pytest.mark.asyncio
class TestCodeAnalyzer:
    """Testes para CodeAnalyzer."""

    async def test_simple_function(self):
        analyzer = CodeAnalyzer()
        code = "def f(x): return x * 2"
        result = await analyzer.analyze({"code": code})
        assert result.metrics["analyzed_functions"] == 1
        assert len(result.issues) == 0  # Função simples, sem issues
