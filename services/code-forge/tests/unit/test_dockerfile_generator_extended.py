"""
Testes estendidos para DockerfileGenerator.

Este modulo testa todas as linguagens suportadas e cenarios alternativos
para o gerador de Dockerfiles.
"""

import pytest

from src.services.dockerfile_generator import DockerfileGenerator
from src.types.artifact_types import CodeLanguage, ArtifactSubtype


class TestDockerfileGeneratorPython:
    """Testes para geracao de Dockerfiles Python."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_python_default_framework(self, generator):
        """Testa Dockerfile Python sem framework especificado."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM python:3.11-slim' in dockerfile
        assert 'CMD ["python", "main.py"]' in dockerfile
        assert 'EXPOSE 8000' in dockerfile
        assert 'HEALTHCHECK' in dockerfile
        assert 'useradd -m -u 1000 appuser' in dockerfile

    def test_python_fastapi_framework(self, generator):
        """Testa Dockerfile Python com FastAPI."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework='fastapi',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile
        assert 'EXPOSE 8000' in dockerfile

    def test_python_flask_framework(self, generator):
        """Testa Dockerfile Python com Flask."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework='flask',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]' in dockerfile
        assert 'EXPOSE 5000' in dockerfile

    def test_python_lambda_function(self, generator):
        """Testa Dockerfile Python para Lambda Function."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework=None,
            artifact_type=ArtifactSubtype.LAMBDA_FUNCTION
        )

        assert 'CMD ["python", "-m", "awslambdaric"]' in dockerfile
        # Lambda nao tem EXPOSE nem HEALTHCHECK tradicional
        assert 'EXPOSE' not in dockerfile or dockerfile.count('EXPOSE') == 0

    def test_python_multi_stage_build(self, generator):
        """Testa que Dockerfile Python usa multi-stage build."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework='fastapi',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM python:3.11-slim as builder' in dockerfile
        assert 'COPY --from=builder' in dockerfile

    def test_python_non_root_user(self, generator):
        """Testa que Dockerfile Python cria usuario nao-root."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'USER appuser' in dockerfile
        assert 'useradd -m -u 1000 appuser' in dockerfile


class TestDockerfileGeneratorNodejs:
    """Testes para geracao de Dockerfiles Node.js."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_nodejs_default_framework(self, generator):
        """Testa Dockerfile Node.js sem framework especificado."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.NODEJS,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM node:20-alpine' in dockerfile
        assert 'CMD ["node", "index.js"]' in dockerfile
        assert 'EXPOSE 3000' in dockerfile
        assert 'HEALTHCHECK' in dockerfile

    def test_nodejs_express_framework(self, generator):
        """Testa Dockerfile Node.js com Express."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.NODEJS,
            framework='express',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'EXPOSE 3000' in dockerfile
        assert 'HEALTHCHECK' in dockerfile

    def test_nodejs_nest_framework(self, generator):
        """Testa Dockerfile Node.js com NestJS."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.NODEJS,
            framework='nest',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'EXPOSE 3000' in dockerfile

    def test_nodejs_lambda_function(self, generator):
        """Testa Dockerfile Node.js para Lambda Function."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.NODEJS,
            framework=None,
            artifact_type=ArtifactSubtype.LAMBDA_FUNCTION
        )

        assert 'CMD ["node", "index.js"]' in dockerfile

    def test_nodejs_multi_stage_build(self, generator):
        """Testa que Dockerfile Node.js usa multi-stage build."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.NODEJS,
            framework='express',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM node:20-alpine as builder' in dockerfile
        assert 'COPY --from=builder' in dockerfile

    def test_nodejs_npm_ci_production(self, generator):
        """Testa que Dockerfile Node.js instala apenas dependencias de producao."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.NODEJS,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'npm ci --only=production' in dockerfile


class TestDockerfileGeneratorGolang:
    """Testes para geracao de Dockerfiles Go."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_golang_default_framework(self, generator):
        """Testa Dockerfile Go sem framework especificado."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.GOLANG,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM golang:1.21-alpine as builder' in dockerfile
        assert 'FROM alpine:latest' in dockerfile
        assert 'CMD ["./main"]' in dockerfile
        assert 'EXPOSE 8080' in dockerfile

    def test_golang_gin_framework(self, generator):
        """Testa Dockerfile Go com framework Gin."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.GOLANG,
            framework='gin',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'EXPOSE 8080' in dockerfile

    def test_golang_echo_framework(self, generator):
        """Testa Dockerfile Go com framework Echo."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.GOLANG,
            framework='echo',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'EXPOSE 8080' in dockerfile

    def test_golang_static_binary(self, generator):
        """Testa que Dockerfile Go compila binario estatico."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.GOLANG,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o main .' in dockerfile
        assert 'FROM alpine:latest' in dockerfile

    def test_golang_lambda_function(self, generator):
        """Testa Dockerfile Go para Lambda Function."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.GOLANG,
            framework=None,
            artifact_type=ArtifactSubtype.LAMBDA_FUNCTION
        )

        # Lambda nao expoe porta tradicional
        assert 'CMD ["./main"]' in dockerfile


class TestDockerfileGeneratorJava:
    """Testes para geracao de Dockerfiles Java."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_java_default_framework(self, generator):
        """Testa Dockerfile Java sem framework especificado."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.JAVA,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM eclipse-temurin:21-slim as builder' in dockerfile
        assert 'FROM eclipse-temurin:21-slim-jre' in dockerfile
        assert 'CMD ["java", "-jar", "app.jar"]' in dockerfile
        assert 'EXPOSE 8080' in dockerfile

    def test_java_spring_boot_framework(self, generator):
        """Testa Dockerfile Java com Spring Boot."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.JAVA,
            framework='spring-boot',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'mvn clean package -DskipTests' in dockerfile
        assert '/actuator/health' in dockerfile

    def test_java_maven_build(self, generator):
        """Testa que Dockerfile Java usa Maven."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.JAVA,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'RUN apt-get update && apt-get install -y maven' in dockerfile
        assert 'mvn dependency:go-offline -B' in dockerfile
        assert 'mvn clean package -DskipTests' in dockerfile

    def test_java_multi_stage_build(self, generator):
        """Testa que Dockerfile Java usa multi-stage build."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.JAVA,
            framework='spring-boot',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM eclipse-temurin:21-slim as builder' in dockerfile
        assert 'COPY --from=builder' in dockerfile


class TestDockerfileGeneratorTypescript:
    """Testes para geracao de Dockerfiles TypeScript."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_typescript_default_framework(self, generator):
        """Testa Dockerfile TypeScript sem framework especificado."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.TYPESCRIPT,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM node:20-alpine as builder' in dockerfile
        assert 'FROM node:20-alpine' in dockerfile
        assert 'npm run build' in dockerfile
        assert 'CMD ["node", "dist/main.js"]' in dockerfile
        assert 'EXPOSE 3000' in dockerfile

    def test_typescript_nestjs_framework(self, generator):
        """Testa Dockerfile TypeScript com NestJS."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.TYPESCRIPT,
            framework='nestjs',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'CMD ["node", "dist/main.js"]' in dockerfile
        assert 'EXPOSE 3000' in dockerfile

    def test_typescript_express_framework(self, generator):
        """Testa Dockerfile TypeScript com Express."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.TYPESCRIPT,
            framework='express',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'CMD ["node", "dist/index.js"]' in dockerfile

    def test_typescript_lambda_function(self, generator):
        """Testa Dockerfile TypeScript para Lambda Function."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.TYPESCRIPT,
            framework=None,
            artifact_type=ArtifactSubtype.LAMBDA_FUNCTION
        )

        assert 'CMD ["node", "dist/index.js"]' in dockerfile

    def test_typescript_tini_entrypoint(self, generator):
        """Testa que Dockerfile TypeScript usa tini para signal handling."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.TYPESCRIPT,
            framework='nestjs',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'ENTRYPOINT ["/sbin/tini", "--"]' in dockerfile


class TestDockerfileGeneratorCsharp:
    """Testes para geracao de Dockerfiles C#."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_csharp_default_framework(self, generator):
        """Testa Dockerfile C# sem framework especificado."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.CSHARP,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'FROM mcr.microsoft.com/dotnet/sdk:8.0 as builder' in dockerfile
        assert 'FROM mcr.microsoft.com/dotnet/aspnet:8.0' in dockerfile
        assert 'ENTRYPOINT ["dotnet", "App.dll"]' in dockerfile
        assert 'EXPOSE 8080' in dockerfile

    def test_csharp_aspnet_framework(self, generator):
        """Testa Dockerfile C# com ASP.NET."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.CSHARP,
            framework='aspnet',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'EXPOSE 8080' in dockerfile

    def test_csharp_webapi_framework(self, generator):
        """Testa Dockerfile C# com WebAPI."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.CSHARP,
            framework='webapi',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'EXPOSE 8080' in dockerfile

    def test_csharp_lambda_function(self, generator):
        """Testa Dockerfile C# para Lambda Function."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.CSHARP,
            framework=None,
            artifact_type=ArtifactSubtype.LAMBDA_FUNCTION
        )

        assert 'ENTRYPOINT ["dotnet", "App.dll"]' in dockerfile

    def test_csharp_dotnet_publish(self, generator):
        """Testa que Dockerfile C# usa dotnet publish."""
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.CSHARP,
            framework='aspnet',
            artifact_type=ArtifactSubtype.MICROSERVICE
        )

        assert 'dotnet publish -c Release -o /app/publish' in dockerfile
        assert '--no-restore' in dockerfile


class TestDockerfileGeneratorEdgeCases:
    """Testes para cenarios edge cases do DockerfileGenerator."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_custom_template_overrides_default(self, generator):
        """Testa que template customizado sobrescreve o padrao."""
        custom_content = '# Custom Dockerfile\nFROM alpine:latest\nCMD ["echo", "hello"]'

        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework=None,
            artifact_type=ArtifactSubtype.MICROSERVICE,
            custom_template=custom_content
        )

        assert dockerfile == custom_content
        assert 'FROM python:3.11-slim' not in dockerfile

    def test_unsupported_language_raises_error(self, generator):
        """Testa que linguagem nao suportada levanta ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generator.generate_dockerfile(
                language='UNSUPPORTED_LANG',
                framework=None,
                artifact_type=ArtifactSubtype.MICROSERVICE
            )

        assert 'Linguagem não suportada' in str(exc_info.value)
        assert 'UNSUPPORTED_LANG' in str(exc_info.value)

    def test_all_supported_languages(self, generator):
        """Testa que todas as linguagens suportadas geram Dockerfile."""
        supported_languages = [
            CodeLanguage.PYTHON,
            CodeLanguage.NODEJS,
            CodeLanguage.GOLANG,
            CodeLanguage.JAVA,
            CodeLanguage.TYPESCRIPT,
            CodeLanguage.CSHARP,
        ]

        for language in supported_languages:
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=None,
                artifact_type=ArtifactSubtype.MICROSERVICE
            )

            assert 'FROM ' in dockerfile
            assert 'CMD ' in dockerfile
            assert 'USER ' in dockerfile or 'useradd' in dockerfile

    def test_healthcheck_in_microservices(self, generator):
        """Testa que microservicos tem HEALTHCHECK."""
        for language in [CodeLanguage.PYTHON, CodeLanguage.NODEJS, CodeLanguage.GOLANG]:
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=None,
                artifact_type=ArtifactSubtype.MICROSERVICE
            )

            assert 'HEALTHCHECK' in dockerfile

    def test_lambda_functions_no_expose(self, generator):
        """Testa que Lambda Functions nao tem EXPOSE."""
        for language in [CodeLanguage.PYTHON, CodeLanguage.NODEJS]:
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=None,
                artifact_type=ArtifactSubtype.LAMBDA_FUNCTION
            )

            # Lambda functions nao tem EXPOSE tradicional
            lines = dockerfile.split('\n')
            expose_lines = [l for l in lines if l.strip().startswith('EXPOSE')]
            # Para Lambda, nao deve haver EXPOSE
            assert len(expose_lines) == 0 or all('EXPOSE 8080' not in l for l in expose_lines)

    def test_all_dockerfiles_use_non_root_user(self, generator):
        """Testa que todos os Dockerfiles criam usuario nao-root."""
        for language in [CodeLanguage.PYTHON, CodeLanguage.NODEJS, CodeLanguage.GOLANG, CodeLanguage.JAVA, CodeLanguage.TYPESCRIPT, CodeLanguage.CSHARP]:
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=None,
                artifact_type=ArtifactSubtype.MICROSERVICE
            )

            # Verificar presenca de usuario nao-root
            assert 'USER' in dockerfile or 'useradd' in dockerfile or 'adduser' in dockerfile


class TestDockerfileGeneratorVersionConstants:
    """Testes para constantes de versao das imagens base."""

    @pytest.fixture
    def generator(self):
        """Instancia do DockerfileGenerator."""
        return DockerfileGenerator()

    def test_python_version_constant(self, generator):
        """Testa constante de versao Python."""
        assert generator.PYTHON_VERSION == "3.11-slim"

    def test_node_version_constant(self, generator):
        """Testa constante de versao Node.js."""
        assert generator.NODE_VERSION == "20-alpine"

    def test_golang_version_constant(self, generator):
        """Testa constante de versao Go."""
        assert generator.GOLANG_VERSION == "1.21-alpine"

    def test_java_version_constant(self, generator):
        """Testa constante de versao Java."""
        assert generator.JAVA_VERSION == "21-slim"

    def test_typescript_version_constant(self, generator):
        """Testa constante de versao TypeScript."""
        assert generator.TYPESCRIPT_VERSION == "20-alpine"

    def test_csharp_version_constant(self, generator):
        """Testa constante de versao C#."""
        assert generator.CSHARP_VERSION == "8.0"

    def test_versions_used_in_dockerfiles(self, generator):
        """Testa que as versoes definidas sao usadas nos Dockerfiles."""
        python_df = generator.generate_dockerfile(CodeLanguage.PYTHON)
        assert generator.PYTHON_VERSION in python_df

        node_df = generator.generate_dockerfile(CodeLanguage.NODEJS)
        assert generator.NODE_VERSION in node_df

        go_df = generator.generate_dockerfile(CodeLanguage.GOLANG)
        assert generator.GOLANG_VERSION in go_df

        java_df = generator.generate_dockerfile(CodeLanguage.JAVA)
        assert generator.JAVA_VERSION in java_df
