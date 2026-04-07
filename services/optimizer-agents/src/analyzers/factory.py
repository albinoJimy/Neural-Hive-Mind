"""Factory para criar analyzers apropriados."""

from enum import Enum

from .base import BaseAnalyzer
from .clickhouse_analyzer import ClickHouseAnalyzer
from .code_analyzer import CodeAnalyzer
from .mongodb_analyzer import MongoDBAnalyzer
from .neo4j_analyzer import Neo4jAnalyzer
from .postgresql_analyzer import PostgreSQLAnalyzer
from .redis_analyzer import RedisAnalyzer


class AnalyzerType(str, Enum):
    """Tipos de analyzer suportados."""

    CODE = "code"
    MONGODB = "mongodb"
    POSTGRESQL = "postgresql"
    NEO4J = "neo4j"
    REDIS = "redis"
    CLICKHOUSE = "clickhouse"


class AnalyzerFactory:
    """Factory para criar analyzers."""

    _analyzers: dict[AnalyzerType, type[BaseAnalyzer]] = {
        AnalyzerType.CODE: CodeAnalyzer,
        AnalyzerType.MONGODB: MongoDBAnalyzer,
        AnalyzerType.POSTGRESQL: PostgreSQLAnalyzer,
        AnalyzerType.NEO4J: Neo4jAnalyzer,
        AnalyzerType.REDIS: RedisAnalyzer,
        AnalyzerType.CLICKHOUSE: ClickHouseAnalyzer,
    }

    @classmethod
    def create(cls, analyzer_type: AnalyzerType | str) -> BaseAnalyzer:
        """Cria instância de analyzer."""
        if isinstance(analyzer_type, str):
            try:
                analyzer_type = AnalyzerType(analyzer_type.lower())
            except ValueError:
                raise ValueError(f"Unsupported analyzer type: {analyzer_type}")

        analyzer_class = cls._analyzers.get(analyzer_type)
        if not analyzer_class:
            raise ValueError(f"No analyzer registered for type: {analyzer_type}")

        return analyzer_class()

    @classmethod
    def create_for_database(cls, database_type: str) -> BaseAnalyzer:
        """Cria analyzer baseado no tipo de banco de dados."""
        db_mapping = {
            "mongodb": AnalyzerType.MONGODB,
            "postgresql": AnalyzerType.POSTGRESQL,
            "postgres": AnalyzerType.POSTGRESQL,
            "neo4j": AnalyzerType.NEO4J,
            "redis": AnalyzerType.REDIS,
            "clickhouse": AnalyzerType.CLICKHOUSE,
        }

        analyzer_type = db_mapping.get(database_type.lower())
        if not analyzer_type:
            analyzer_type = AnalyzerType.CODE

        return cls.create(analyzer_type)
