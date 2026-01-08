from functools import lru_cache
from typing import Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações do Code Forge via variáveis de ambiente"""

    # Identificação do Serviço
    SERVICE_NAME: str = Field(default='code-forge', description='Nome do serviço')
    NAMESPACE: str = Field(default='neural-hive-execution', description='Namespace Kubernetes')
    CLUSTER: str = Field(default='production', description='Cluster de execução')

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(..., description='Servidores Kafka (host:port,host:port)')
    KAFKA_TICKETS_TOPIC: str = Field(default='execution.tickets', description='Tópico de Execution Tickets')
    KAFKA_RESULTS_TOPIC: str = Field(default='code-forge.results', description='Tópico de resultados do Code Forge')
    KAFKA_CONSUMER_GROUP_ID: str = Field(default='code-forge', description='Consumer group ID')
    KAFKA_AUTO_OFFSET_RESET: str = Field(default='earliest', description='Offset reset strategy')
    KAFKA_ENABLE_AUTO_COMMIT: bool = Field(default=False, description='Auto commit offsets')

    # Database - PostgreSQL
    POSTGRES_HOST: str = Field(..., description='PostgreSQL host')
    POSTGRES_PORT: int = Field(default=5432, description='PostgreSQL port')
    POSTGRES_DB: str = Field(..., description='PostgreSQL database')
    POSTGRES_USER: str = Field(..., description='PostgreSQL user')
    POSTGRES_PASSWORD: str = Field(..., description='PostgreSQL password')

    @property
    def POSTGRES_URL(self) -> str:
        return f'postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}'

    # Database - MongoDB
    MONGODB_HOST: str = Field(..., description='MongoDB host')
    MONGODB_PORT: int = Field(default=27017, description='MongoDB port')
    MONGODB_DB: str = Field(default='code_forge', description='MongoDB database')
    MONGODB_USER: str = Field(default='', description='MongoDB user')
    MONGODB_PASSWORD: str = Field(default='', description='MongoDB password')

    @property
    def MONGODB_URL(self) -> str:
        if self.MONGODB_USER and self.MONGODB_PASSWORD:
            return f'mongodb://{self.MONGODB_USER}:{self.MONGODB_PASSWORD}@{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DB}'
        return f'mongodb://{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DB}'

    # Database - Redis
    REDIS_HOST: str = Field(..., description='Redis host')
    REDIS_PORT: int = Field(default=6379, description='Redis port')
    REDIS_DB: int = Field(default=0, description='Redis database')
    REDIS_PASSWORD: str = Field(default='', description='Redis password')

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f'redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'
        return f'redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'

    # Service Registry
    SERVICE_REGISTRY_HOST: str = Field(..., description='Service Registry host')
    SERVICE_REGISTRY_PORT: int = Field(default=50051, description='Service Registry gRPC port')
    HEARTBEAT_INTERVAL_SECONDS: int = Field(default=30, description='Intervalo de heartbeat (segundos)')

    # Execution Ticket Service
    EXECUTION_TICKET_SERVICE_URL: str = Field(..., description='URL do Execution Ticket Service')

    # Templates Configuration
    TEMPLATES_GIT_REPO: str = Field(..., description='Repositório Git de templates')
    TEMPLATES_GIT_BRANCH: str = Field(default='main', description='Branch do repositório de templates')
    TEMPLATES_LOCAL_PATH: str = Field(default='/app/templates', description='Caminho local para templates')
    TEMPLATES_CACHE_TTL_SECONDS: int = Field(default=3600, description='TTL do cache de templates')

    # Ferramentas Externas - SonarQube
    SONARQUBE_URL: str = Field(default='', description='URL do SonarQube')
    SONARQUBE_TOKEN: str = Field(default='', description='Token de autenticação SonarQube')
    SONARQUBE_ENABLED: bool = Field(default=True, description='Habilitar validação SonarQube')
    SONARQUBE_SCANNER_TIMEOUT: int = Field(default=900, description='Timeout do scanner SonarQube (segundos)')
    SONARQUBE_POLL_INTERVAL: int = Field(default=5, description='Intervalo de polling SonarQube (segundos)')
    SONARQUBE_POLL_TIMEOUT: int = Field(default=300, description='Timeout de polling SonarQube (segundos)')

    # Ferramentas Externas - Snyk
    SNYK_TOKEN: str = Field(default='', description='Token de autenticação Snyk')
    SNYK_ENABLED: bool = Field(default=True, description='Habilitar validação Snyk')
    SNYK_TIMEOUT: int = Field(default=300, description='Timeout do scan Snyk (segundos)')

    # Ferramentas Externas - Trivy
    TRIVY_ENABLED: bool = Field(default=True, description='Habilitar validação Trivy')
    TRIVY_SEVERITY: str = Field(default='CRITICAL,HIGH', description='Severidades Trivy')
    TRIVY_TIMEOUT: int = Field(default=600, description='Timeout do scan Trivy (segundos)')

    # Ferramentas Externas - GitLab
    GITLAB_URL: str = Field(default='https://gitlab.com', description='URL do GitLab')
    GITLAB_TOKEN: str = Field(default='', description='Token de autenticação GitLab')

    # Ferramentas Externas - Sigstore
    SIGSTORE_FULCIO_URL: str = Field(default='https://fulcio.sigstore.dev', description='URL Fulcio')
    SIGSTORE_REKOR_URL: str = Field(default='https://rekor.sigstore.dev', description='URL Rekor')
    SIGSTORE_ENABLED: bool = Field(default=True, description='Habilitar assinatura Sigstore')

    # Artifact Storage
    ARTIFACTS_S3_BUCKET: str = Field(default='', description='Bucket S3 para artefatos')
    ARTIFACTS_S3_REGION: str = Field(default='us-east-1', description='Região AWS S3')
    ARTIFACTS_S3_ENDPOINT: str = Field(default='', description='Endpoint S3 customizado')
    OCI_REGISTRY_URL: str = Field(default='', description='URL do OCI Registry')

    # Pipeline Configuration
    MAX_CONCURRENT_PIPELINES: int = Field(default=3, description='Máximo de pipelines concorrentes')
    PIPELINE_TIMEOUT_SECONDS: int = Field(default=3600, description='Timeout de pipeline (segundos)')
    AUTO_APPROVAL_THRESHOLD: float = Field(default=0.9, description='Threshold para aprovação automática')
    MIN_QUALITY_SCORE: float = Field(default=0.5, description='Score mínimo de qualidade')
    MIN_TEST_COVERAGE: float = Field(default=0.8, description='Cobertura mínima de testes')

    # Observability - OpenTelemetry
    OTEL_EXPORTER_ENDPOINT: str = Field(default='https://opentelemetry-collector.observability.svc.cluster.local:4317', description='Endpoint OpenTelemetry')
    OTEL_TLS_VERIFY: bool = Field(default=True, description='Verificar certificado TLS do OTEL Collector')
    OTEL_CA_BUNDLE: Optional[str] = Field(default=None, description='Caminho para CA bundle do OTEL Collector')
    OTEL_SERVICE_NAME: str = Field(default='code-forge', description='Nome do serviço OpenTelemetry')

    # Observability - Prometheus
    PROMETHEUS_PORT: int = Field(default=9090, description='Porta Prometheus metrics')

    # Observability - HTTP/gRPC
    HTTP_PORT: int = Field(default=8080, description='Porta HTTP API')
    GRPC_PORT: int = Field(default=50051, description='Porta gRPC')

    # Logging
    LOG_LEVEL: str = Field(default='INFO', description='Nível de log (DEBUG, INFO, WARNING, ERROR)')
    LOG_FORMAT: str = Field(default='json', description='Formato de log (json, text)')

    # MCP Tool Catalog Integration
    MCP_TOOL_CATALOG_HOST: str = Field(default='mcp-tool-catalog', description='MCP Tool Catalog host')
    MCP_TOOL_CATALOG_PORT: int = Field(default=8080, description='MCP Tool Catalog port')

    @property
    def MCP_TOOL_CATALOG_URL(self) -> str:
        return f'http://{self.MCP_TOOL_CATALOG_HOST}:{self.MCP_TOOL_CATALOG_PORT}'

    # LLM Integration (Optional)
    LLM_PROVIDER: str = Field(default='', description='LLM provider (openai, anthropic, local)')
    LLM_API_KEY: str = Field(default='', description='LLM API key (for OpenAI/Anthropic)')
    LLM_MODEL: str = Field(default='gpt-4', description='LLM model name')
    LLM_BASE_URL: str = Field(default='', description='LLM base URL (for local/custom endpoints)')
    LLM_ENABLED: bool = Field(default=False, description='Enable LLM-based code generation')

    # Analyst Agents Integration (Optional)
    ANALYST_AGENTS_HOST: str = Field(default='analyst-agents', description='Analyst Agents host')
    ANALYST_AGENTS_PORT: int = Field(default=8000, description='Analyst Agents port')

    @property
    def ANALYST_AGENTS_URL(self) -> str:
        return f'http://{self.ANALYST_AGENTS_HOST}:{self.ANALYST_AGENTS_PORT}'

    # Ambiente
    ENVIRONMENT: str = Field(default='development', description='Ambiente de execução')

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: OTEL Collector.
        """
        is_prod_staging = self.ENVIRONMENT.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.OTEL_EXPORTER_ENDPOINT.startswith('http://'):
            http_endpoints.append(('OTEL_EXPORTER_ENDPOINT', self.OTEL_EXPORTER_ENDPOINT))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.ENVIRONMENT}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Retorna singleton de Settings"""
    return Settings()
