#!/usr/bin/env python3
"""
test_database_connectivity.py - Database Connectivity Validation for Phase 2 Services

This script validates connectivity to all databases used by Phase 2 services:
- MongoDB (motor.motor_asyncio)
- PostgreSQL (asyncpg)
- Redis (redis.asyncio)
- Neo4j (neo4j.AsyncDriver)

Usage:
    python test_database_connectivity.py [--quiet] [--json] [--service SERVICE]
"""

import asyncio
import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Any
from datetime import datetime


# Color codes for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'
    BOLD = '\033[1m'


@dataclass
class ValidationResult:
    """Result of a database validation check"""
    service: str
    database_type: str
    connected: bool
    latency_ms: float
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# Configuration via environment variables
SERVICE_NAMESPACE = os.getenv("SERVICE_NAMESPACE", "neural-hive")
SERVICE_LABEL_KEY = os.getenv("SERVICE_LABEL_KEY", "app")


def get_default_namespace():
    """Get the default namespace from environment or fallback"""
    return SERVICE_NAMESPACE


# Database configurations per service
# Note: default_uri uses dynamic namespace resolution via get_mongodb_uri()
def get_mongodb_uri():
    """Get MongoDB URI with configurable namespace"""
    return os.getenv("MONGODB_URI", f"mongodb://mongodb.{SERVICE_NAMESPACE}:27017")


def get_postgresql_host():
    """Get PostgreSQL host with configurable namespace"""
    return os.getenv("POSTGRESQL_HOST", f"postgresql.{SERVICE_NAMESPACE}")


def get_redis_host():
    """Get Redis host with configurable namespace"""
    return os.getenv("REDIS_HOST", f"redis-master.{SERVICE_NAMESPACE}")


def get_neo4j_uri():
    """Get Neo4j URI with configurable namespace"""
    return os.getenv("NEO4J_URI", f"bolt://neo4j.{SERVICE_NAMESPACE}:7687")


MONGODB_SERVICES = {
    "orchestrator-dynamic": {
        "uri_env": "MONGODB_URI",
        "database": "orchestration_ledger",
        "collections": ["workflows", "decisions", "ml_feedback"]
    },
    "queen-agent": {
        "uri_env": "MONGODB_URI",
        "database": "strategic_decisions",
        "collections": ["decisions", "conflicts", "approvals"]
    },
    "analyst-agents": {
        "uri_env": "MONGODB_URI",
        "database": "analyst_insights",
        "collections": ["insights", "analysis_reports"]
    },
    "code-forge": {
        "uri_env": "MONGODB_URI",
        "database": "code_forge_db",
        "collections": ["pipelines", "artifacts", "validations"]
    },
    "guard-agents": {
        "uri_env": "MONGODB_URI",
        "database": "guard_audit",
        "collections": ["audit_logs", "security_events"]
    },
    "optimizer-agents": {
        "uri_env": "MONGODB_URI",
        "database": "optimizer_db",
        "collections": ["forecasts", "optimizations"]
    },
    "mcp-tool-catalog": {
        "uri_env": "MONGODB_URI",
        "database": "mcp_catalog",
        "collections": ["tools", "tool_usage"]
    },
    "execution-ticket-service": {
        "uri_env": "MONGODB_URI",
        "database": "execution_tickets",
        "collections": ["tickets", "ticket_lifecycle"]
    }
}

POSTGRESQL_SERVICES = {
    "execution-ticket-service": {
        "uri_env": "POSTGRESQL_URI",
        "default_port": 5432,
        "default_database": "tickets",
        "default_user": "tickets_user",
        "tables": ["execution_tickets", "ticket_lifecycle", "ticket_results"]
    },
    "sla-management-system": {
        "uri_env": "POSTGRESQL_URI",
        "default_port": 5432,
        "default_database": "sla_management",
        "default_user": "sla_user",
        "tables": ["sla_budgets", "sla_violations", "sla_metrics"]
    },
    "code-forge": {
        "uri_env": "POSTGRESQL_URI",
        "default_port": 5432,
        "default_database": "code_forge",
        "default_user": "code_forge_user",
        "tables": ["pipeline_runs", "validation_results"]
    }
}

REDIS_SERVICES = {
    "queen-agent": {
        "uri_env": "REDIS_URI",
        "default_port": 6379,
        "purpose": "pheromone_cache"
    },
    "orchestrator-dynamic": {
        "uri_env": "REDIS_URI",
        "default_port": 6379,
        "purpose": "workflow_cache"
    },
    "optimizer-agents": {
        "uri_env": "REDIS_URI",
        "default_port": 6379,
        "purpose": "forecast_cache"
    },
    "sla-management-system": {
        "uri_env": "REDIS_URI",
        "default_port": 6379,
        "purpose": "sla_cache"
    },
    "service-registry": {
        "uri_env": "REDIS_URI",
        "default_port": 6379,
        "purpose": "service_cache"
    }
}

NEO4J_SERVICES = {
    "queen-agent": {
        "uri_env": "NEO4J_URI",
        "default_user": "neo4j",
        "purpose": "intent_graph"
    },
    "analyst-agents": {
        "uri_env": "NEO4J_URI",
        "default_user": "neo4j",
        "purpose": "analysis_graph"
    }
}


class MongoDBValidator:
    """Validates MongoDB connectivity for services"""

    def __init__(self):
        self.results: List[ValidationResult] = []

    async def validate(self, service: str, config: Dict[str, Any]) -> ValidationResult:
        """Validate MongoDB connection for a specific service"""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError:
            return ValidationResult(
                service=service,
                database_type="mongodb",
                connected=False,
                latency_ms=0,
                error="motor library not installed"
            )

        uri = os.getenv(config["uri_env"], get_mongodb_uri())
        database_name = config["database"]
        collections = config.get("collections", [])

        start_time = time.time()
        try:
            client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)

            # Ping to verify connection
            await client.admin.command('ping')

            latency_ms = (time.time() - start_time) * 1000

            # Validate database access
            db = client[database_name]
            existing_collections = await db.list_collection_names()

            # Try to access collections
            accessible_collections = []
            for coll_name in collections:
                try:
                    coll = db[coll_name]
                    await coll.find_one()
                    accessible_collections.append(coll_name)
                except Exception:
                    pass

            client.close()

            return ValidationResult(
                service=service,
                database_type="mongodb",
                connected=True,
                latency_ms=round(latency_ms, 2),
                details={
                    "database": database_name,
                    "existing_collections": existing_collections,
                    "accessible_collections": accessible_collections
                }
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return ValidationResult(
                service=service,
                database_type="mongodb",
                connected=False,
                latency_ms=round(latency_ms, 2),
                error=str(e)
            )

    async def validate_all(self, services: Optional[Dict[str, Any]] = None) -> List[ValidationResult]:
        """Validate MongoDB connections for specified services"""
        target_services = services if services is not None else MONGODB_SERVICES
        if not target_services:
            return []
        tasks = [
            self.validate(service, config)
            for service, config in target_services.items()
        ]
        self.results = await asyncio.gather(*tasks)
        return self.results


class PostgreSQLValidator:
    """Validates PostgreSQL connectivity for services"""

    def __init__(self):
        self.results: List[ValidationResult] = []

    async def validate(self, service: str, config: Dict[str, Any]) -> ValidationResult:
        """Validate PostgreSQL connection for a specific service"""
        try:
            import asyncpg
        except ImportError:
            return ValidationResult(
                service=service,
                database_type="postgresql",
                connected=False,
                latency_ms=0,
                error="asyncpg library not installed"
            )

        host = os.getenv("POSTGRESQL_HOST", get_postgresql_host())
        port = int(os.getenv("POSTGRESQL_PORT", config["default_port"]))
        database = os.getenv("POSTGRESQL_DATABASE", config["default_database"])
        user = os.getenv("POSTGRESQL_USER", config["default_user"])
        password = os.getenv("POSTGRESQL_PASSWORD", "")

        start_time = time.time()
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                timeout=5
            )

            # Ping to verify connection
            await conn.execute("SELECT 1")

            latency_ms = (time.time() - start_time) * 1000

            # Check tables
            tables = config.get("tables", [])
            accessible_tables = []
            for table in tables:
                try:
                    result = await conn.fetchval(
                        f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = $1",
                        table
                    )
                    if result > 0:
                        accessible_tables.append(table)
                except Exception:
                    pass

            await conn.close()

            return ValidationResult(
                service=service,
                database_type="postgresql",
                connected=True,
                latency_ms=round(latency_ms, 2),
                details={
                    "host": host,
                    "database": database,
                    "accessible_tables": accessible_tables
                }
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return ValidationResult(
                service=service,
                database_type="postgresql",
                connected=False,
                latency_ms=round(latency_ms, 2),
                error=str(e)
            )

    async def validate_all(self, services: Optional[Dict[str, Any]] = None) -> List[ValidationResult]:
        """Validate PostgreSQL connections for specified services"""
        target_services = services if services is not None else POSTGRESQL_SERVICES
        if not target_services:
            return []
        tasks = [
            self.validate(service, config)
            for service, config in target_services.items()
        ]
        self.results = await asyncio.gather(*tasks)
        return self.results


class RedisValidator:
    """Validates Redis connectivity for services"""

    def __init__(self):
        self.results: List[ValidationResult] = []

    async def validate(self, service: str, config: Dict[str, Any]) -> ValidationResult:
        """Validate Redis connection for a specific service"""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            return ValidationResult(
                service=service,
                database_type="redis",
                connected=False,
                latency_ms=0,
                error="redis library not installed"
            )

        host = os.getenv("REDIS_HOST", get_redis_host())
        port = int(os.getenv("REDIS_PORT", config["default_port"]))
        password = os.getenv("REDIS_PASSWORD", None)

        start_time = time.time()
        try:
            redis_client = aioredis.Redis(
                host=host,
                port=port,
                password=password,
                socket_timeout=5
            )

            # Ping to verify connection
            await redis_client.ping()

            latency_ms = (time.time() - start_time) * 1000

            # Test set/get
            test_key = f"validation_test_{service}_{int(time.time())}"
            await redis_client.set(test_key, "test_value", ex=10)
            test_value = await redis_client.get(test_key)
            await redis_client.delete(test_key)

            # Check cluster mode
            cluster_mode = False
            try:
                info = await redis_client.info("cluster")
                cluster_mode = info.get("cluster_enabled", False)
            except Exception:
                pass

            await redis_client.close()

            return ValidationResult(
                service=service,
                database_type="redis",
                connected=True,
                latency_ms=round(latency_ms, 2),
                details={
                    "host": host,
                    "port": port,
                    "cluster_mode": cluster_mode,
                    "purpose": config.get("purpose", "unknown"),
                    "test_passed": test_value == b"test_value"
                }
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return ValidationResult(
                service=service,
                database_type="redis",
                connected=False,
                latency_ms=round(latency_ms, 2),
                error=str(e)
            )

    async def validate_all(self, services: Optional[Dict[str, Any]] = None) -> List[ValidationResult]:
        """Validate Redis connections for specified services"""
        target_services = services if services is not None else REDIS_SERVICES
        if not target_services:
            return []
        tasks = [
            self.validate(service, config)
            for service, config in target_services.items()
        ]
        self.results = await asyncio.gather(*tasks)
        return self.results


class Neo4jValidator:
    """Validates Neo4j connectivity for services"""

    def __init__(self):
        self.results: List[ValidationResult] = []

    async def validate(self, service: str, config: Dict[str, Any]) -> ValidationResult:
        """Validate Neo4j connection for a specific service"""
        try:
            from neo4j import AsyncGraphDatabase
        except ImportError:
            return ValidationResult(
                service=service,
                database_type="neo4j",
                connected=False,
                latency_ms=0,
                error="neo4j library not installed"
            )

        uri = os.getenv(config["uri_env"], get_neo4j_uri())
        user = os.getenv("NEO4J_USER", config["default_user"])
        password = os.getenv("NEO4J_PASSWORD", "")

        start_time = time.time()
        try:
            driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

            # Verify connectivity
            await driver.verify_connectivity()

            latency_ms = (time.time() - start_time) * 1000

            # Execute test query
            async with driver.session() as session:
                result = await session.run("MATCH (n) RETURN count(n) as count LIMIT 1")
                record = await result.single()
                nodes_count = record["count"] if record else 0

                # Get indexes
                indexes_result = await session.run("SHOW INDEXES")
                indexes = [r async for r in indexes_result]
                index_count = len(indexes)

            await driver.close()

            return ValidationResult(
                service=service,
                database_type="neo4j",
                connected=True,
                latency_ms=round(latency_ms, 2),
                details={
                    "uri": uri,
                    "purpose": config.get("purpose", "unknown"),
                    "nodes_count": nodes_count,
                    "index_count": index_count
                }
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return ValidationResult(
                service=service,
                database_type="neo4j",
                connected=False,
                latency_ms=round(latency_ms, 2),
                error=str(e)
            )

    async def validate_all(self, services: Optional[Dict[str, Any]] = None) -> List[ValidationResult]:
        """Validate Neo4j connections for specified services"""
        target_services = services if services is not None else NEO4J_SERVICES
        if not target_services:
            return []
        tasks = [
            self.validate(service, config)
            for service, config in target_services.items()
        ]
        self.results = await asyncio.gather(*tasks)
        return self.results


def print_result(result: ValidationResult, quiet: bool = False):
    """Print a single validation result with colors"""
    if quiet:
        return

    status = f"{Colors.GREEN}CONNECTED{Colors.NC}" if result.connected else f"{Colors.RED}FAILED{Colors.NC}"
    print(f"  [{status}] {result.service} ({result.database_type})")
    print(f"    Latency: {result.latency_ms}ms")

    if result.error:
        print(f"    {Colors.RED}Error: {result.error}{Colors.NC}")

    if result.details:
        for key, value in result.details.items():
            if isinstance(value, list):
                print(f"    {key}: {', '.join(str(v) for v in value[:5])}")
            else:
                print(f"    {key}: {value}")


def print_summary(all_results: List[ValidationResult], quiet: bool = False):
    """Print validation summary"""
    if quiet:
        return

    total = len(all_results)
    connected = sum(1 for r in all_results if r.connected)
    failed = total - connected

    print(f"\n{Colors.BOLD}{'='*60}{Colors.NC}")
    print(f"{Colors.BOLD}DATABASE CONNECTIVITY SUMMARY{Colors.NC}")
    print(f"{'='*60}")
    print(f"  Total Validations: {total}")
    print(f"  {Colors.GREEN}Connected: {connected}{Colors.NC}")
    print(f"  {Colors.RED}Failed: {failed}{Colors.NC}")

    if failed > 0:
        print(f"\n{Colors.RED}Failed Connections:{Colors.NC}")
        for r in all_results:
            if not r.connected:
                print(f"  - {r.service} ({r.database_type}): {r.error}")


def filter_services_by_name(
    service_name: str,
    mongodb: Dict[str, Any],
    postgresql: Dict[str, Any],
    redis: Dict[str, Any],
    neo4j: Dict[str, Any]
) -> tuple:
    """
    Filter service mappings to include only the specified service.

    Args:
        service_name: The service name to filter by
        mongodb: Full MongoDB services mapping
        postgresql: Full PostgreSQL services mapping
        redis: Full Redis services mapping
        neo4j: Full Neo4j services mapping

    Returns:
        Tuple of filtered dictionaries (mongodb, postgresql, redis, neo4j)
    """
    filtered_mongodb = {service_name: mongodb[service_name]} if service_name in mongodb else {}
    filtered_postgresql = {service_name: postgresql[service_name]} if service_name in postgresql else {}
    filtered_redis = {service_name: redis[service_name]} if service_name in redis else {}
    filtered_neo4j = {service_name: neo4j[service_name]} if service_name in neo4j else {}

    return filtered_mongodb, filtered_postgresql, filtered_redis, filtered_neo4j


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Validate database connectivity for Phase 2 services")
    parser.add_argument("--quiet", action="store_true", help="Suppress output, only return exit code")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--service", type=str, help="Validate only specific service")
    args = parser.parse_args()

    all_results: List[ValidationResult] = []

    # Filter services if --service is provided
    if args.service:
        mongodb_services, postgresql_services, redis_services, neo4j_services = filter_services_by_name(
            args.service,
            MONGODB_SERVICES,
            POSTGRESQL_SERVICES,
            REDIS_SERVICES,
            NEO4J_SERVICES
        )
        # Check if service exists in any mapping
        if not any([mongodb_services, postgresql_services, redis_services, neo4j_services]):
            if not args.quiet:
                print(f"{Colors.YELLOW}Warning: Service '{args.service}' not found in any database mapping{Colors.NC}")
                print(f"Available services:")
                all_services = set(MONGODB_SERVICES.keys()) | set(POSTGRESQL_SERVICES.keys()) | \
                              set(REDIS_SERVICES.keys()) | set(NEO4J_SERVICES.keys())
                for svc in sorted(all_services):
                    print(f"  - {svc}")
            sys.exit(1)
    else:
        mongodb_services = MONGODB_SERVICES
        postgresql_services = POSTGRESQL_SERVICES
        redis_services = REDIS_SERVICES
        neo4j_services = NEO4J_SERVICES

    if not args.quiet:
        print(f"\n{Colors.BOLD}{Colors.CYAN}DATABASE CONNECTIVITY VALIDATION{Colors.NC}")
        if args.service:
            print(f"{Colors.CYAN}Filtering by service: {args.service}{Colors.NC}")
        print(f"{Colors.CYAN}{'='*60}{Colors.NC}\n")

    # MongoDB validation
    if mongodb_services:
        if not args.quiet:
            print(f"{Colors.BOLD}MongoDB Connectivity:{Colors.NC}")
        mongodb_validator = MongoDBValidator()
        mongodb_results = await mongodb_validator.validate_all(mongodb_services)
        all_results.extend(mongodb_results)
        for result in mongodb_results:
            print_result(result, args.quiet)
    elif not args.quiet and not args.service:
        print(f"{Colors.BOLD}MongoDB Connectivity:{Colors.NC}")
        print(f"  {Colors.YELLOW}No MongoDB services to validate{Colors.NC}")

    # PostgreSQL validation
    if postgresql_services:
        if not args.quiet:
            print(f"\n{Colors.BOLD}PostgreSQL Connectivity:{Colors.NC}")
        postgresql_validator = PostgreSQLValidator()
        postgresql_results = await postgresql_validator.validate_all(postgresql_services)
        all_results.extend(postgresql_results)
        for result in postgresql_results:
            print_result(result, args.quiet)
    elif not args.quiet and not args.service:
        print(f"\n{Colors.BOLD}PostgreSQL Connectivity:{Colors.NC}")
        print(f"  {Colors.YELLOW}No PostgreSQL services to validate{Colors.NC}")

    # Redis validation
    if redis_services:
        if not args.quiet:
            print(f"\n{Colors.BOLD}Redis Connectivity:{Colors.NC}")
        redis_validator = RedisValidator()
        redis_results = await redis_validator.validate_all(redis_services)
        all_results.extend(redis_results)
        for result in redis_results:
            print_result(result, args.quiet)
    elif not args.quiet and not args.service:
        print(f"\n{Colors.BOLD}Redis Connectivity:{Colors.NC}")
        print(f"  {Colors.YELLOW}No Redis services to validate{Colors.NC}")

    # Neo4j validation
    if neo4j_services:
        if not args.quiet:
            print(f"\n{Colors.BOLD}Neo4j Connectivity:{Colors.NC}")
        neo4j_validator = Neo4jValidator()
        neo4j_results = await neo4j_validator.validate_all(neo4j_services)
        all_results.extend(neo4j_results)
        for result in neo4j_results:
            print_result(result, args.quiet)
    elif not args.quiet and not args.service:
        print(f"\n{Colors.BOLD}Neo4j Connectivity:{Colors.NC}")
        print(f"  {Colors.YELLOW}No Neo4j services to validate{Colors.NC}")

    # Print summary
    print_summary(all_results, args.quiet)

    # JSON output
    if args.json:
        report = {
            "timestamp": datetime.now().isoformat(),
            "service_filter": args.service,
            "results": [asdict(r) for r in all_results],
            "summary": {
                "total": len(all_results),
                "connected": sum(1 for r in all_results if r.connected),
                "failed": sum(1 for r in all_results if not r.connected)
            }
        }
        print(json.dumps(report, indent=2))

    # Return exit code
    failed_count = sum(1 for r in all_results if not r.connected)
    sys.exit(1 if failed_count > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
