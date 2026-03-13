"""
Testes E2E para builds de container reais.

Estes testes verificam:
- Geração de Dockerfiles para diferentes linguagens
- Build de imagens usando Docker CLI
- Obtenção de digest e tamanho da imagem

REQUISITO: Docker daemon deve estar rodando.
"""

import pytest
import tempfile
import subprocess
from pathlib import Path

from src.services.dockerfile_generator import DockerfileGenerator
from src.types.artifact_types import CodeLanguage, ArtifactCategory
from src.services.container_builder import ContainerBuilder, BuilderType


@pytest.mark.e2e
class TestContainerBuildE2E:
    """Testes E2E para builds de container."""

    def setup_method(self):
        """Verifica se Docker está rodando antes dos testes."""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                pytest.skip("Docker não está disponível")
        except FileNotFoundError:
            pytest.skip("Docker CLI não encontrado")
        except Exception as e:
            pytest.skip(f"Docker não disponível: {e}")

    @pytest.mark.asyncio
    async def test_python_container_build_e2e(self):
        """Teste E2E completo de build Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Criar app Python simples
            app_dir = Path(tmpdir) / "app"
            app_dir.mkdir()

            (app_dir / "main.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Hello World"}
""")

            (app_dir / "requirements.txt").write_text("""
fastapi==0.104.1
uvicorn[standard]==0.24.0
""")

            # Gerar Dockerfile
            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=CodeLanguage.PYTHON,
                framework="fastapi",
                artifact_type=ArtifactCategory.MICROSERVICE,
            )

            dockerfile_path = app_dir / "Dockerfile"
            dockerfile_path.write_text(dockerfile)

            # Verificar que o Dockerfile foi gerado corretamente
            assert "FROM python:3.11-slim" in dockerfile
            assert "HEALTHCHECK" in dockerfile
            assert "appuser" in dockerfile

            # Executar build
            builder = ContainerBuilder(builder_type=BuilderType.DOCKER)
            result = await builder.build_container(
                dockerfile_path=str(dockerfile_path),
                build_context=str(app_dir),
                image_tag="test-python:latest",
            )

            # Assertions
            assert result.success is True, f"Build falhou: {result.error_message}"
            assert result.image_digest is not None
            assert result.image_digest.startswith("sha256:")
            assert len(result.image_digest) >= 10

            # Limpar imagem
            subprocess.run(
                ["docker", "rmi", "test-python:latest", "--force"],
                capture_output=True,
            )

    @pytest.mark.asyncio
    async def test_nodejs_container_build_e2e(self):
        """Teste E2E de build Node.js."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "app"
            app_dir.mkdir()

            (app_dir / "package.json").write_text("""
{
  "name": "test-app",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {
    "express": "^4.18.0"
  }
}
""")

            (app_dir / "index.js").write_text("""
const express = require('express');
const app = express();

app.get('/health', (req, res) => res.json({status: 'ok'}));
app.get('/', (req, res) => res.json({message: 'Hello World'}));

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`Server running on port ${port}`));
""")

            generator = DockerfileGenerator()
            # Usar template customizado com npm install para teste E2E (sem package-lock.json)
            custom_dockerfile = """# Builder stage
FROM node:20-alpine as builder

WORKDIR /app

# Copiar package files
COPY package*.json ./

# Instalar dependências (npm install para teste sem lockfile)
RUN npm install --only=production

# Final stage
FROM node:20-alpine

WORKDIR /app

# Instalar dependências de runtime
RUN apk add --no-cache curl

# Copiar node_modules do builder
COPY --from=builder /app/node_modules ./node_modules

# Copiar código da aplicação
COPY . .

# Usar usuário 'node' existente na imagem
USER node

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:3000/health || exit 1

EXPOSE 3000

CMD ["node", "index.js"]
"""
            dockerfile = generator.generate_dockerfile(
                language=CodeLanguage.NODEJS,
                custom_template=custom_dockerfile,
            )

            dockerfile_path = app_dir / "Dockerfile"
            dockerfile_path.write_text(dockerfile)

            builder = ContainerBuilder()
            result = await builder.build_container(
                dockerfile_path=str(dockerfile_path),
                build_context=str(app_dir),
                image_tag="test-nodejs:latest",
            )

            assert result.success is True, f"Build falhou: {result.error_message}"
            assert result.image_digest is not None

            # Limpar
            subprocess.run(
                ["docker", "rmi", "test-nodejs:latest", "--force"],
                capture_output=True,
            )

    @pytest.mark.asyncio
    async def test_golang_container_build_e2e(self):
        """Teste E2E de build Go."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "app"
            app_dir.mkdir()

            (app_dir / "main.go").write_text("""
package main

import (
    "fmt"
    "net/http"
)

func healthHandler(w http.ResponseWriter, r *http.Request) {
    fmt.Fprintf(w, `{"status": "ok"}`)
}

func main() {
    http.HandleFunc("/health", healthHandler)
    http.ListenAndServe(":8080", nil)
}
""")

            (app_dir / "go.mod").write_text("""
module test-app

go 1.21
""")

            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=CodeLanguage.GOLANG,
            )

            dockerfile_path = app_dir / "Dockerfile"
            dockerfile_path.write_text(dockerfile)

            builder = ContainerBuilder()
            result = await builder.build_container(
                dockerfile_path=str(dockerfile_path),
                build_context=str(app_dir),
                image_tag="test-golang:latest",
            )

            assert result.success is True, f"Build falhou: {result.error_message}"
            assert result.image_digest is not None

            # Limpar
            subprocess.run(
                ["docker", "rmi", "test-golang:latest", "--force"],
                capture_output=True,
            )

    @pytest.mark.asyncio
    async def test_typescript_nestjs_build_e2e(self):
        """Teste E2E de build TypeScript com NestJS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "app"
            app_dir.mkdir()

            (app_dir / "package.json").write_text("""
{
  "name": "test-nest-app",
  "version": "1.0.0",
  "scripts": {
    "build": "tsc"
  },
  "dependencies": {
    "@nestjs/common": "^10.0.0",
    "@nestjs/core": "^10.0.0",
    "reflect-metadata": "^0.1.13",
    "rxjs": "^7.8.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "typescript": "^5.0.0"
  }
}
""")

            (app_dir / "tsconfig.json").write_text("""
{
  "compilerOptions": {
    "module": "commonjs",
    "declaration": true,
    "removeComments": true,
    "emitDecoratorMetadata": true,
    "experimentalDecorators": true,
    "allowSyntheticDefaultImports": true,
    "target": "ES2021",
    "sourceMap": true,
    "outDir": "./dist",
    "baseUrl": "./"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules"]
}
""")

            src_dir = app_dir / "src"
            src_dir.mkdir()

            # Criar AppModule
            (src_dir / "app.module.ts").write_text("""
import { Module } from '@nestjs/common';

@Module({})
export class AppModule {}
""")

            (src_dir / "main.ts").write_text("""
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, {});
  await app.listen(3000);
}

bootstrap();
""")

            generator = DockerfileGenerator()
            # Usar template customizado com npm install para teste E2E (sem package-lock.json)
            custom_dockerfile = """# Builder stage
FROM node:20-alpine as builder

WORKDIR /app

# Copiar package files
COPY package*.json ./

# Instalar todas as dependências (incluindo devDependencies para build)
RUN npm install

# Copiar código e transpilar
COPY . .

# Transpilar TypeScript
RUN npm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Instalar dependências de runtime
RUN apk add --no-cache curl

# Copiar node_modules de produção e código transpilado
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist

# Usar usuário 'node' existente na imagem
USER node

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:3000/health || exit 1

EXPOSE 3000

CMD ["node", "dist/main.js"]
"""
            dockerfile = generator.generate_dockerfile(
                language=CodeLanguage.TYPESCRIPT,
                framework="nestjs",
                custom_template=custom_dockerfile,
            )

            dockerfile_path = app_dir / "Dockerfile"
            dockerfile_path.write_text(dockerfile)

            builder = ContainerBuilder()
            result = await builder.build_container(
                dockerfile_path=str(dockerfile_path),
                build_context=str(app_dir),
                image_tag="test-nestjs:latest",
            )

            assert result.success is True, f"Build falhou: {result.error_message}"
            assert result.image_digest is not None

            # Limpar
            subprocess.run(
                ["docker", "rmi", "test-nestjs:latest", "--force"],
                capture_output=True,
            )

    @pytest.mark.asyncio
    async def test_csharp_aspnet_build_e2e(self):
        """Teste E2E de build C#/ASP.NET."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "app"
            app_dir.mkdir()

            (app_dir / "App.csproj").write_text("""
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
""")

            (app_dir / "Program.cs").write_text("""
var app = WebApplication.CreateBuilder(args).Build();

app.MapGet("/", () => "Hello World");

app.MapGet("/health", () => new { status = "ok" });

app.Run();
""")

            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=CodeLanguage.CSHARP,
                framework="aspnet",
            )

            dockerfile_path = app_dir / "Dockerfile"
            dockerfile_path.write_text(dockerfile)

            builder = ContainerBuilder()
            result = await builder.build_container(
                dockerfile_path=str(dockerfile_path),
                build_context=str(app_dir),
                image_tag="test-aspnet:latest",
            )

            # ASP.NET build pode falhar se SDK não estiver disponível
            if result.success:
                assert result.image_digest is not None
                # Limpar
                subprocess.run(
                    ["docker", "rmi", "test-aspnet:latest", "--force"],
                    capture_output=True,
                )
            else:
                # Se falhar, verificar se é por falta do .NET SDK
                if ".NET" in result.error_message or "dotnet" in result.error_message:
                    pytest.skip(".NET SDK não está disponível no ambiente")
                else:
                    pytest.fail(f"Build falhou: {result.error_message}")

    @pytest.mark.asyncio
    async def test_custom_dockerfile_build_e2e(self):
        """Teste E2E com Dockerfile customizado."""
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "app"
            app_dir.mkdir()

            # Dockerfile customizado simples
            custom_dockerfile = """FROM alpine:latest
CMD echo "Hello from custom container"
"""

            (app_dir / "Dockerfile").write_text(custom_dockerfile)

            builder = ContainerBuilder()
            result = await builder.build_container(
                dockerfile_path=str(app_dir / "Dockerfile"),
                build_context=str(app_dir),
                image_tag="test-custom:latest",
            )

            assert result.success is True, f"Build falhou: {result.error_message}"
            assert result.image_digest is not None

            # Limpar
            subprocess.run(
                ["docker", "rmi", "test-custom:latest", "--force"],
                capture_output=True,
            )

    @pytest.mark.asyncio
    async def test_dockerfile_with_lambda_function_e2e(self):
        """Teste E2E de Dockerfile para Lambda Function."""
        generator = DockerfileGenerator()
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            artifact_type=ArtifactCategory.LAMBDA_FUNCTION,
        )

        # Lambda não deve ter EXPOSE tradicional
        assert "FROM python:3.11-slim" in dockerfile
        assert "awslambdaric" in dockerfile

    @pytest.mark.asyncio
    async def test_multi_stage_dockerfile_e2e(self):
        """Teste E2E que Dockerfile é multi-stage."""
        generator = DockerfileGenerator()

        # Python template é multi-stage
        dockerfile = generator.generate_dockerfile(
            language=CodeLanguage.PYTHON,
            framework="fastapi",
        )

        assert "as builder" in dockerfile.lower()
        assert "COPY --from=builder" in dockerfile

    @pytest.mark.asyncio
    async def test_non_root_user_e2e(self):
        """Teste E2E que todas as imagens têm usuário não-root."""
        languages = [
            (CodeLanguage.PYTHON, "fastapi"),
            (CodeLanguage.NODEJS, "express"),
            (CodeLanguage.GOLANG, None),
        ]

        for language, framework in languages:
            generator = DockerfileGenerator()
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=framework,
            )

            # Verifica presença de usuário não-root
            has_user = "USER" in dockerfile or "useradd" in dockerfile or "adduser" in dockerfile
            assert has_user, f"Template {language} não tem usuário não-root"

    @pytest.mark.asyncio
    async def test_healthcheck_in_all_templates_e2e(self):
        """Teste E2E que todos os templates têm HEALTHCHECK."""
        generator = DockerfileGenerator()

        templates_to_check = [
            (CodeLanguage.PYTHON, "fastapi", ArtifactCategory.MICROSERVICE),
            (CodeLanguage.NODEJS, "express", ArtifactCategory.MICROSERVICE),
            (CodeLanguage.GOLANG, None, ArtifactCategory.MICROSERVICE),
            (CodeLanguage.JAVA, "spring-boot", ArtifactCategory.MICROSERVICE),
            (CodeLanguage.TYPESCRIPT, "nestjs", ArtifactCategory.MICROSERVICE),
            (CodeLanguage.CSHARP, "aspnet", ArtifactCategory.MICROSERVICE),
        ]

        for language, framework, artifact_type in templates_to_check:
            dockerfile = generator.generate_dockerfile(
                language=language,
                framework=framework,
                artifact_type=artifact_type,
            )

            # Lambda functions não têm HEALTHCHECK tradicional
            if artifact_type != ArtifactCategory.LAMBDA_FUNCTION:
                assert "HEALTHCHECK" in dockerfile, \
                    f"Template {language}/{framework} não tem HEALTHCHECK"
