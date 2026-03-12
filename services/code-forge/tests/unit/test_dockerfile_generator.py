"""
Testes unitarios para DockerfileGenerator.
"""

import pytest

from src.services.dockerfile_generator import (
    DockerfileGenerator,
    SupportedLanguage,
    ArtifactType,
)


class TestDockerfileGenerator:
    """Testes para geração de Dockerfiles."""

    def test_generate_python_fastapi_dockerfile(self):
        """Testa geração de Dockerfile Python/FastAPI."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.PYTHON,
            framework="fastapi",
            artifact_type=ArtifactType.MICROSERVICE,
        )

        # Verifica componentes essenciais
        assert "FROM python:3.11-slim" in dockerfile
        assert "builder" in dockerfile.lower()
        assert "HEALTHCHECK" in dockerfile
        assert "appuser" in dockerfile
        assert "uvicorn" in dockerfile
        assert "EXPOSE 8000" in dockerfile

    def test_generate_python_flask_dockerfile(self):
        """Testa geração de Dockerfile Python/Flask."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.PYTHON,
            framework="flask",
            artifact_type=ArtifactType.MICROSERVICE,
        )

        assert "FROM python:3.11-slim" in dockerfile
        assert "gunicorn" in dockerfile
        assert "EXPOSE 5000" in dockerfile
        assert "appuser" in dockerfile

    def test_generate_python_lambda_dockerfile(self):
        """Testa geração de Dockerfile Python para Lambda."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.PYTHON,
            artifact_type=ArtifactType.LAMBDA_FUNCTION,
        )

        assert "FROM python:3.11-slim" in dockerfile
        assert "awslambdaric" in dockerfile
        # Lambda não expõe porta tradicional
        assert "EXPOSE" not in dockerfile or "EXPOSE 8080" not in dockerfile

    def test_generate_nodejs_express_dockerfile(self):
        """Testa geração de Dockerfile Node.js/Express."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.NODEJS,
            framework="express",
            artifact_type=ArtifactType.MICROSERVICE,
        )

        assert "FROM node:20-alpine" in dockerfile
        assert "builder" in dockerfile.lower()
        assert "HEALTHCHECK" in dockerfile
        assert "nodejs" in dockerfile  # usuário não-root
        assert "EXPOSE 3000" in dockerfile
        assert "npm ci" in dockerfile

    def test_generate_nodejs_nestjs_dockerfile(self):
        """Testa geração de Dockerfile Node.js/NestJS."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.NODEJS,
            framework="nest",
        )

        assert "FROM node:20-alpine" in dockerfile
        assert "EXPOSE 3000" in dockerfile

    def test_generate_nodejs_lambda_dockerfile(self):
        """Testa geração de Dockerfile Node.js para Lambda."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.NODEJS,
            artifact_type=ArtifactType.LAMBDA_FUNCTION,
        )

        assert "FROM node:20-alpine" in dockerfile
        # Lambda não tem HEALTHCHECK tradicional
        assert "curl" in dockerfile

    def test_generate_golang_dockerfile(self):
        """Testa geração de Dockerfile Go."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.GOLANG,
            artifact_type=ArtifactType.MICROSERVICE,
        )

        assert "FROM golang:1.21-alpine" in dockerfile
        assert "builder" in dockerfile.lower()
        assert "FROM alpine:latest" in dockerfile
        assert "HEALTHCHECK" in dockerfile
        assert "appuser" in dockerfile
        assert "CGO_ENABLED=0" in dockerfile
        assert "EXPOSE 8080" in dockerfile

    def test_generate_golang_gin_dockerfile(self):
        """Testa geração de Dockerfile Go com Gin framework."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.GOLANG,
            framework="gin",
        )

        assert "FROM golang:1.21-alpine" in dockerfile
        assert "EXPOSE 8080" in dockerfile

    def test_generate_java_spring_boot_dockerfile(self):
        """Testa geração de Dockerfile Java/Spring Boot."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.JAVA,
            framework="spring-boot",
            artifact_type=ArtifactType.MICROSERVICE,
        )

        assert "FROM eclipse-temurin:21-slim" in dockerfile
        assert "builder" in dockerfile.lower()
        assert "mvn clean package" in dockerfile
        assert "HEALTHCHECK" in dockerfile
        assert "appuser" in dockerfile
        assert "EXPOSE 8080" in dockerfile
        assert "actuator/health" in dockerfile

    def test_generate_java_maven_dockerfile(self):
        """Testa geração de Dockerfile Java com Maven padrão."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.JAVA,
        )

        assert "FROM eclipse-temurin:21-slim" in dockerfile
        assert "mvn clean package" in dockerfile
        # CMD usa formato JSON com aspas duplas
        assert '"java"' in dockerfile and '"app.jar"' in dockerfile

    def test_generate_typescript_nestjs_dockerfile(self):
        """Testa geração de Dockerfile TypeScript/NestJS."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.TYPESCRIPT,
            framework="nestjs",
            artifact_type=ArtifactType.MICROSERVICE,
        )

        assert "FROM node:20-alpine" in dockerfile
        assert "builder" in dockerfile.lower()
        assert "npm run build" in dockerfile
        assert "HEALTHCHECK" in dockerfile
        assert "nodejs" in dockerfile  # usuário não-root
        assert "dist/main.js" in dockerfile

    def test_generate_typescript_express_dockerfile(self):
        """Testa geração de Dockerfile TypeScript/Express."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.TYPESCRIPT,
            framework="express",
        )

        assert "FROM node:20-alpine" in dockerfile
        assert "npm run build" in dockerfile
        assert "dist/index.js" in dockerfile

    def test_generate_csharp_aspnet_dockerfile(self):
        """Testa geração de Dockerfile C#/ASP.NET."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.CSHARP,
            framework="aspnet",
            artifact_type=ArtifactType.MICROSERVICE,
        )

        assert "mcr.microsoft.com/dotnet/sdk:8.0" in dockerfile
        assert "builder" in dockerfile.lower()
        assert "dotnet publish" in dockerfile
        assert "HEALTHCHECK" in dockerfile
        assert "appuser" in dockerfile
        assert "EXPOSE 8080" in dockerfile

    def test_generate_csharp_lambda_dockerfile(self):
        """Testa geração de Dockerfile C# para Lambda."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.CSHARP,
            artifact_type=ArtifactType.LAMBDA_FUNCTION,
        )

        assert "mcr.microsoft.com/dotnet/sdk:8.0" in dockerfile
        assert "dotnet publish" in dockerfile
        # Lambda não expõe porta tradicionalmente

    def test_custom_template_overrides(self):
        """Testa que template customizado sobrescreve padrão."""
        generator = DockerfileGenerator()
        custom = "FROM alpine:latest\nCMD ['sh']"
        dockerfile = generator.generate_dockerfile(
            language=SupportedLanguage.PYTHON,
            custom_template=custom,
        )

        assert dockerfile == custom

    def test_unsupported_language_raises(self):
        """Testa que linguagem não suportada levanta ValueError."""
        generator = DockerfileGenerator()

        with pytest.raises(ValueError, match="Linguagem não suportada"):
            generator.generate_dockerfile(language="rust")

    def test_all_templates_have_non_root_user(self):
        """Testa que todos os templates têm usuário não-root."""
        generator = DockerfileGenerator()
        languages = [
            (SupportedLanguage.PYTHON, "fastapi"),
            (SupportedLanguage.NODEJS, "express"),
            (SupportedLanguage.GOLANG, None),
            (SupportedLanguage.JAVA, "spring-boot"),
            (SupportedLanguage.TYPESCRIPT, "nestjs"),
            (SupportedLanguage.CSHARP, "aspnet"),
        ]

        for language, framework in languages:
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=framework,
                artifact_type=ArtifactType.MICROSERVICE,
            )
            # Verifica presença de usuário não-root
            assert "USER" in dockerfile or "adduser" in dockerfile or "useradd" in dockerfile

    def test_all_templates_have_healthcheck(self):
        """Testa que todos os templates têm HEALTHCHECK (exceto Lambda)."""
        generator = DockerfileGenerator()
        languages = [
            (SupportedLanguage.PYTHON, "fastapi"),
            (SupportedLanguage.NODEJS, "express"),
            (SupportedLanguage.GOLANG, None),
            (SupportedLanguage.JAVA, "spring-boot"),
            (SupportedLanguage.TYPESCRIPT, "nestjs"),
            (SupportedLanguage.CSHARP, "aspnet"),
        ]

        for language, framework in languages:
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=framework,
                artifact_type=ArtifactType.MICROSERVICE,
            )
            assert "HEALTHCHECK" in dockerfile

    def test_all_templates_are_multistage(self):
        """Testa que templates usam multi-stage build."""
        generator = DockerfileGenerator()

        # Python
        python_df = generator.generate_dockerfile(SupportedLanguage.PYTHON)
        assert "as builder" in python_df.lower()

        # Node.js
        node_df = generator.generate_dockerfile(SupportedLanguage.NODEJS)
        assert "as builder" in node_df.lower()

        # Java
        java_df = generator.generate_dockerfile(SupportedLanguage.JAVA)
        assert "as builder" in java_df.lower()

        # Go também tem builder stage
        go_df = generator.generate_dockerfile(SupportedLanguage.GOLANG)
        assert "as builder" in go_df.lower()

        # TypeScript
        ts_df = generator.generate_dockerfile(SupportedLanguage.TYPESCRIPT)
        assert "as builder" in ts_df.lower()

        # C#
        csharp_df = generator.generate_dockerfile(SupportedLanguage.CSHARP)
        assert "as builder" in csharp_df.lower()
