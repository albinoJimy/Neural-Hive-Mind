"""
Gerador de Dockerfiles otimizados baseado em linguagem e framework.

Suporta multi-stage builds para Python, Node.js, Go, Java, TypeScript e C# com
foco em segurança (usuário não-root), tamanho mínimo e health checks.
"""

from typing import Optional
import structlog

# Importar tipos centralizados
from ..types.artifact_types import CodeLanguage, ArtifactSubtype


logger = structlog.get_logger()


class DockerfileGenerator:
    """
    Gera Dockerfiles otimizados baseado em linguagem e framework.

    Todos os templates seguem as melhores práticas:
    - Multi-stage build (quando aplicável)
    - Usuário não-root
    - HEALTHCHECK
    - Imagens base mínimas
    """

    # Versões das imagens base
    PYTHON_VERSION = "3.11-slim"
    NODE_VERSION = "20-alpine"
    GOLANG_VERSION = "1.21-alpine"
    JAVA_VERSION = "21-slim"
    TYPESCRIPT_VERSION = "20-alpine"
    CSHARP_VERSION = "8.0"

    def __init__(self):
        self._templates = {
            CodeLanguage.PYTHON: self._get_python_template,
            CodeLanguage.NODEJS: self._get_nodejs_template,
            CodeLanguage.GOLANG: self._get_golang_template,
            CodeLanguage.JAVA: self._get_java_template,
            CodeLanguage.TYPESCRIPT: self._get_typescript_template,
            CodeLanguage.CSHARP: self._get_csharp_template,
        }

    def generate_dockerfile(
        self,
        language: CodeLanguage,
        framework: Optional[str] = None,
        artifact_type: ArtifactSubtype = ArtifactSubtype.MICROSERVICE,
        custom_template: Optional[str] = None,
    ) -> str:
        """
        Gera um Dockerfile multi-stage otimizado.

        Args:
            language: Linguagem de programação
            framework: Framework específico (ex: fastapi, express, spring-boot)
            artifact_type: Tipo do artefato a ser buildado
            custom_template: Template customizado (sobrescreve padrão)

        Returns:
            Conteúdo do Dockerfile como string

        Raises:
            ValueError: Se linguagem não é suportada e não há custom template
        """
        if custom_template:
            logger.info("using_custom_dockerfile_template")
            return custom_template

        if language not in self._templates:
            raise ValueError(
                f"Linguagem não suportada: {language}. "
                f"Suportadas: {list(self._templates.keys())}"
            )

        template_func = self._templates[language]
        dockerfile = template_func(framework, artifact_type)

        logger.info(
            "dockerfile_generated",
            language=language,
            framework=framework,
            artifact_type=artifact_type,
        )

        return dockerfile

    def _get_python_template(
        self,
        framework: Optional[str],
        artifact_type: ArtifactSubtype,
    ) -> str:
        """
        Retorna template Python multi-stage.

        Suporta FastAPI, Flask e aplicações Python genéricas.
        """
        # Detectar command baseado no framework
        if framework == "fastapi":
            cmd = 'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]'
            port = 8000
        elif framework == "flask":
            cmd = 'CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]'
            port = 5000
        elif artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            cmd = 'CMD ["python", "-m", "awslambdaric"]'
            port = 8080
        else:
            # Default Python
            cmd = 'CMD ["python", "main.py"]'
            port = 8000

        if artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            # Lambda não usa expor porta tradicional
            expose = ""
            healthcheck = ""
        else:
            expose = f"EXPOSE {port}"
            healthcheck = (
                f"HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\\n"
                f'    CMD python -c "import urllib.request; '
                f'urllib.request.urlopen(\'http://localhost:{port}/health\')" || exit 1'
            )

        return f"""# Builder stage
FROM python:{self.PYTHON_VERSION} as builder

WORKDIR /app

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:{self.PYTHON_VERSION}

WORKDIR /app

# Instalar dependências de runtime
RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copiar pacotes instalados
COPY --from=builder /root/.local /root/.local

# Copiar código da aplicação
COPY . .

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

{healthcheck}

{expose}

{cmd}
"""

    def _get_nodejs_template(
        self,
        framework: Optional[str],
        artifact_type: ArtifactSubtype,
    ) -> str:
        """
        Retorna template Node.js multi-stage.

        Suporta Express, NestJS e aplicações Node genéricas.
        """
        # Detectar porta e command baseado no framework
        if framework == "express" or framework == "nest":
            port = 3000
        elif artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            port = 8080
        else:
            port = 3000

        if artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            expose = ""
            healthcheck = ""
            cmd = 'CMD ["node", "index.js"]'  # Lambda adapter
        else:
            expose = f"EXPOSE {port}"
            healthcheck = (
                f"HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\\n"
                f'    CMD curl -f http://localhost:{port}/health || exit 1'
            )
            cmd = 'CMD ["node", "index.js"]'

        return f"""# Builder stage
FROM node:{self.NODE_VERSION} as builder

WORKDIR /app

# Copiar package files
COPY package*.json ./

# Instalar dependências
RUN npm ci --only=production

# Final stage
FROM node:{self.NODE_VERSION}

WORKDIR /app

# Instalar dependências de runtime
RUN apk add --no-cache curl

# Copiar node_modules do builder
COPY --from=builder /app/node_modules ./node_modules

# Copiar código da aplicação
COPY . .

# Criar usuário não-root
RUN addgroup -g 1000 -S nodejs && \\
    adduser -S nodejs -u 1000 && \\
    chown -R nodejs:nodejs /app
USER nodejs

{healthcheck}

{expose}

{cmd}
"""

    def _get_golang_template(
        self,
        framework: Optional[str],
        artifact_type: ArtifactSubtype,
    ) -> str:
        """
        Retorna template Go (single stage com build estático).

        Go compila para binário estático, então não precisa de multi-stage.
        """
        # Detectar porta baseado no framework
        if framework == "gin" or framework == "echo":
            port = 8080
        else:
            port = 8080

        if artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            expose = ""
            healthcheck = ""
        else:
            expose = f"EXPOSE {port}"
            healthcheck = (
                f"HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\\n"
                f'    CMD wget -q -O /dev/null http://localhost:{port}/health || exit 1'
            )

        return f"""# Builder stage
FROM golang:{self.GOLANG_VERSION} as builder

WORKDIR /app

# Copiar go mod files
COPY go.* ./
RUN go mod download

# Copiar código e build
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o main .

# Final stage (scratch - mínimo)
FROM alpine:latest

WORKDIR /app

# Instalar certificados CA e wget para healthcheck
RUN apk --no-cache add ca-certificates wget

# Copiar binário do builder
COPY --from=builder /app/main .

# Criar usuário não-root
RUN addgroup -g 1000 -S appuser && \\
    adduser -S appuser -u 1000 && \\
    chown -R appuser:appuser /app
USER appuser

{healthcheck}

{expose}

CMD ["./main"]
"""

    def _get_java_template(
        self,
        framework: Optional[str],
        artifact_type: ArtifactSubtype,
    ) -> str:
        """
        Retorna template Java/Spring Boot multi-stage.

        Suporta Spring Boot e aplicações Java genéricas com Maven/Gradle.
        """
        # Detectar porta para Spring Boot
        port = 8080

        # Detectar build tool
        if framework == "spring-boot":
            build_cmd = "RUN mvn clean package -DskipTests"
            jar_path = "target/*.jar"
        else:
            # Default Maven
            build_cmd = "RUN mvn clean package -DskipTests"
            jar_path = "target/*.jar"

        return f"""# Builder stage
FROM eclipse-temurin:{self.JAVA_VERSION} as builder

WORKDIR /app

# Instalar build tools
RUN apt-get update && apt-get install -y maven \\
    && rm -rf /var/lib/apt/lists/*

# Copiar pom.xml e download dependencies (cache layer)
COPY pom.xml .
RUN mvn dependency:go-offline -B

# Copiar código e build
COPY . .
{build_cmd}

# Final stage
FROM eclipse-temurin:{self.JAVA_VERSION}-jre

WORKDIR /app

# Instalar dependências de runtime
RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copiar JAR do builder
COPY --from=builder /app/{jar_path} app.jar

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \\
    CMD curl -f http://localhost:8080/actuator/health || exit 1

EXPOSE {port}

CMD ["java", "-jar", "app.jar"]
"""

    def _get_typescript_template(
        self,
        framework: Optional[str],
        artifact_type: ArtifactSubtype,
    ) -> str:
        """
        Retorna template TypeScript multi-stage.

        TypeScript é transpilado para JavaScript, então usa base Node.js.
        Suporta NestJS, Express e aplicações TypeScript genéricas.
        """
        # Detectar porta baseado no framework
        if framework == "nestjs" or framework == "nest":
            port = 3000
            build_cmd = "RUN npm run build"
            start_cmd = 'CMD ["node", "dist/main.js"]'
        elif framework == "express":
            port = 3000
            build_cmd = "RUN npm run build"
            start_cmd = 'CMD ["node", "dist/index.js"]'
        elif artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            port = 8080
            build_cmd = "RUN npm run build"
            start_cmd = 'CMD ["node", "dist/index.js"]'
        else:
            port = 3000
            build_cmd = "RUN npm run build"
            start_cmd = 'CMD ["node", "dist/main.js"]'

        if artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            expose = ""
            healthcheck = ""
        else:
            expose = f"EXPOSE {port}"
            healthcheck = (
                f"HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\\n"
                f'    CMD curl -f http://localhost:{port}/health || exit 1'
            )

        return f"""# Builder stage
FROM node:{self.TYPESCRIPT_VERSION} as builder

WORKDIR /app

# Copiar package files
COPY package*.json ./

# Instalar todas as dependências (incluindo devDependencies para build)
RUN npm ci

# Copiar código e transpilar
COPY . .
{build_cmd}

# Production stage
FROM node:{self.TYPESCRIPT_VERSION}

WORKDIR /app

# Instalar dependências de runtime
RUN apk add --no-cache curl tini

# Copiar package files e instalar apenas produção
COPY package*.json ./
RUN npm ci --only=production

# Copiar código transpilado do builder
COPY --from=builder /app/dist ./dist

# Criar usuário não-root
RUN addgroup -g 1000 -S nodejs && \\
    adduser -S nodejs -u 1000 && \\
    chown -R nodejs:nodejs /app
USER nodejs

# Use tini for proper signal handling
ENTRYPOINT ["/sbin/tini", "--"]

{healthcheck}

{expose}

{start_cmd}
"""

    def _get_csharp_template(
        self,
        framework: Optional[str],
        artifact_type: ArtifactSubtype,
    ) -> str:
        """
        Retorna template C#/.NET multi-stage.

        Suporta ASP.NET Core, APIs genéricas e Lambda Functions.
        """
        # Detectar porta e configuração baseado no framework
        if framework == "aspnet" or framework == "webapi":
            port = 8080
        elif artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            port = 8080
        else:
            port = 8080

        if artifact_type == ArtifactSubtype.LAMBDA_FUNCTION:
            expose = ""
            healthcheck = ""
        else:
            expose = f"EXPOSE {port}"
            healthcheck = (
                f"HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \\\n"
                f'    CMD curl -f http://localhost:{port}/health || exit 1'
            )

        return f"""# Builder stage
FROM mcr.microsoft.com/dotnet/sdk:{self.CSHARP_VERSION} as builder

WORKDIR /src

# Copiar csproj e restaurar dependências
COPY *.csproj ./
RUN dotnet restore --use-current-runtime

# Copiar código e build
COPY . .
WORKDIR /src
RUN dotnet publish -c Release -o /app/publish \\
    --self-contained false \\
    --no-restore

# Final stage
FROM mcr.microsoft.com/dotnet/aspnet:{self.CSHARP_VERSION}

WORKDIR /app

# Instalar dependências de runtime para healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copiar aplicação publicada
COPY --from=builder /app/publish .

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

{healthcheck}

{expose}

ASPNETCORE_URLS=http://+:{port}
ENTRYPOINT ["dotnet", "App.dll"]
"""
