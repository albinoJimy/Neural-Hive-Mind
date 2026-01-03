"""Settings configuration using Pydantic BaseSettings."""
from functools import lru_cache
from typing import Dict, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Service Identity
    SERVICE_NAME: str = "mcp-tool-catalog"
    SERVICE_VERSION: str = "1.0.0"
    HTTP_PORT: int = 8080
    GRPC_PORT: int = 9090
    METRICS_PORT: int = 9091

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="kafka-cluster-kafka-bootstrap:9092",
        description="Kafka bootstrap servers"
    )
    KAFKA_TOOL_SELECTION_REQUEST_TOPIC: str = "mcp.tool.selection.requests"
    KAFKA_TOOL_SELECTION_RESPONSE_TOPIC: str = "mcp.tool.selection.responses"
    KAFKA_CONSUMER_GROUP_ID: str = "mcp-tool-catalog-group"

    # MongoDB Configuration
    MONGODB_URL: str = Field(
        default="mongodb://mongodb-svc:27017",
        description="MongoDB connection URL"
    )
    MONGODB_DATABASE: str = "mcp_tool_catalog"
    MONGODB_TOOLS_COLLECTION: str = "tools"
    MONGODB_SELECTIONS_COLLECTION: str = "selections_history"

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://redis-cluster:6379",
        description="Redis connection URL"
    )
    CACHE_TTL_SECONDS: int = 3600
    CACHE_ENABLED: bool = True

    # Service Registry Configuration (use _GRPC_ to avoid Kubernetes service discovery collision)
    SERVICE_REGISTRY_GRPC_HOST: str = "service-registry.neural-hive.svc.cluster.local"
    SERVICE_REGISTRY_GRPC_PORT: int = 50051
    HEARTBEAT_INTERVAL_SECONDS: int = 30

    # Genetic Algorithm Configuration
    GA_POPULATION_SIZE: int = 50
    GA_MAX_GENERATIONS: int = 100
    GA_CROSSOVER_PROB: float = 0.7
    GA_MUTATION_PROB: float = 0.2
    GA_TOURNAMENT_SIZE: int = 3
    GA_CONVERGENCE_THRESHOLD: float = 0.01
    GA_TIMEOUT_SECONDS: int = 30

    # Tool Execution Configuration
    TOOL_EXECUTION_TIMEOUT_SECONDS: int = 300
    MAX_CONCURRENT_TOOL_EXECUTIONS: int = 10
    TOOL_RETRY_MAX_ATTEMPTS: int = 3

    # MCP Server Configuration
    MCP_SERVER_TIMEOUT_SECONDS: int = 30
    MCP_SERVER_MAX_RETRIES: int = 3
    MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD: int = 5
    MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = 60

    # Connection Timeouts
    MONGODB_CONNECT_TIMEOUT_MS: int = 10000
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000
    REDIS_CONNECT_TIMEOUT_SECONDS: int = 10
    REDIS_SOCKET_TIMEOUT_SECONDS: int = 10
    KAFKA_REQUEST_TIMEOUT_MS: int = 30000
    KAFKA_SESSION_TIMEOUT_MS: int = 30000
    SERVICE_REGISTRY_CONNECT_TIMEOUT_SECONDS: int = 10

    # Retry Configuration
    MAX_CONNECTION_RETRIES: int = 5
    INITIAL_RETRY_DELAY_SECONDS: float = 1.0

    MCP_SERVERS: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapeamento tool_id → MCP server URL (ex: {'trivy-001': 'http://trivy-mcp-server:3000'})"
    )

    @field_validator("MCP_SERVERS", mode="before")
    @classmethod
    def validate_mcp_servers(cls, v):
        """Valida que URLs em MCP_SERVERS são válidas."""
        if v is None:
            return {}
        if isinstance(v, str):
            import json
            v = json.loads(v)
        for tool_id, url in v.items():
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"URL inválida para {tool_id}: {url}. Deve começar com http:// ou https://")
        return v

    # Observability Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    OTEL_EXPORTER_ENDPOINT: Optional[str] = Field(
        default="http://otel-collector:4317",
        description="(Deprecated) OpenTelemetry collector endpoint"
    )
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(
        default="http://otel-collector:4317",
        description="OpenTelemetry OTLP collector endpoint"
    )

    @property
    def otel_endpoint(self) -> Optional[str]:
        """
        Compat helper to read OTLP endpoint.

        Prefers OTEL_EXPORTER_OTLP_ENDPOINT and falls back to legacy OTEL_EXPORTER_ENDPOINT.
        """
        return self.OTEL_EXPORTER_OTLP_ENDPOINT or self.OTEL_EXPORTER_ENDPOINT

    # Analyst Agents Integration (for RAG)
    # Use MCP_ prefix to avoid collision with Kubernetes service discovery env vars
    MCP_ANALYST_AGENTS_HOST: str = "analyst-agents"
    MCP_ANALYST_AGENTS_GRPC_PORT: int = 9090

    # ========================================
    # Tool Endpoints Configuration
    # ========================================

    # ANALYSIS Tools
    SONARQUBE_URL: str = Field(
        default="http://sonarqube:9000/api",
        description="SonarQube API endpoint"
    )
    CHECKMARX_URL: str = Field(
        default="https://checkmarx.example.com/api",
        description="Checkmarx API endpoint"
    )
    VERACODE_URL: str = Field(
        default="https://analysiscenter.veracode.com/api",
        description="Veracode API endpoint"
    )
    FORTIFY_URL: str = Field(
        default="https://fortify.example.com/api",
        description="Fortify API endpoint"
    )

    # GENERATION Tools
    GITHUB_COPILOT_URL: str = Field(
        default="https://api.github.com/copilot",
        description="GitHub Copilot API endpoint"
    )
    SPRING_INITIALIZR_URL: str = Field(
        default="https://start.spring.io",
        description="Spring Initializr API endpoint"
    )
    OPENAI_CODEX_URL: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI Codex API endpoint"
    )

    # VALIDATION Tools
    BURP_SUITE_URL: str = Field(
        default="http://burpsuite:8080",
        description="Burp Suite API endpoint"
    )

    # AUTOMATION Tools
    GITHUB_ACTIONS_URL: str = Field(
        default="https://api.github.com",
        description="GitHub Actions API endpoint"
    )
    ARGOCD_URL: str = Field(
        default="http://argocd-server:80/api",
        description="ArgoCD API endpoint"
    )
    GITLAB_CI_URL: str = Field(
        default="https://gitlab.com/api/v4",
        description="GitLab CI API endpoint"
    )
    JENKINS_URL: str = Field(
        default="http://jenkins:8080",
        description="Jenkins API endpoint"
    )
    CIRCLECI_URL: str = Field(
        default="https://circleci.com/api/v2",
        description="CircleCI API endpoint"
    )
    TRAVIS_CI_URL: str = Field(
        default="https://api.travis-ci.com",
        description="Travis CI API endpoint"
    )

    # INTEGRATION Tools
    KAFKA_CONNECT_URL: str = Field(
        default="http://kafka-connect:8083",
        description="Kafka Connect API endpoint"
    )
    AIRFLOW_URL: str = Field(
        default="http://airflow-webserver:8080/api/v1",
        description="Apache Airflow API endpoint"
    )
    MULESOFT_URL: str = Field(
        default="https://anypoint.mulesoft.com/api",
        description="MuleSoft API endpoint"
    )
    AWS_EVENTBRIDGE_URL: str = Field(
        default="https://events.amazonaws.com",
        description="AWS EventBridge endpoint"
    )
    AZURE_LOGIC_APPS_URL: str = Field(
        default="https://management.azure.com",
        description="Azure Logic Apps endpoint"
    )
    GOOGLE_WORKFLOWS_URL: str = Field(
        default="https://workflowexecutions.googleapis.com",
        description="Google Cloud Workflows endpoint"
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
