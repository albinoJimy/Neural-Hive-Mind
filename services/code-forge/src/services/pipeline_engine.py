import asyncio
import uuid
import os
from datetime import datetime
from typing import Dict, Any, Optional, TYPE_CHECKING
import structlog

from ..models.execution_ticket import ExecutionTicket, TicketStatus
from ..models.pipeline_context import PipelineContext
from ..models.artifact import PipelineResult, PipelineStage, StageStatus
from ..clients.kafka_result_producer import KafkaResultProducer
from ..clients.execution_ticket_client import ExecutionTicketClient
from ..clients.postgres_client import PostgresClient
from ..clients.mongodb_client import MongoDBClient
from ..types.artifact_types import CodeLanguage, ArtifactSubtype, ArtifactCategory
from .dockerfile_generator import DockerfileGenerator
from .container_builder import ContainerBuilder, BuilderType

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class PipelineEngine:
    """
    Orquestrador principal que coordena execução dos pipelines.

    Stages do pipeline:
    1. template_selection - Seleção de template baseado no ticket
    2. code_composition - Geração do código fonte
    3. dockerfile_generation - Geração do Dockerfile otimizado
    4. container_build - Build da imagem de container
    5. validation - Validação de qualidade e segurança
    6. testing - Execução de testes
    7. packaging - Empacotamento e geração de SBOM
    8. approval_gate - Gate de aprovação manual/automática
    """

    def __init__(
        self,
        template_selector,
        code_composer,
        validator,
        test_runner,
        packager,
        approval_gate,
        kafka_producer: KafkaResultProducer,
        ticket_client: ExecutionTicketClient,
        postgres_client: PostgresClient,
        mongodb_client: MongoDBClient,
        max_concurrent: int = 3,
        pipeline_timeout: int = 3600,
        auto_approval_threshold: float = 0.9,
        min_quality_score: float = 0.5,
        metrics: Optional['CodeForgeMetrics'] = None,
        build_timeout: int = 3600,
        enable_container_build: bool = True,
    ):
        self.template_selector = template_selector
        self.code_composer = code_composer
        self.validator = validator
        self.test_runner = test_runner
        self.packager = packager
        self.approval_gate = approval_gate

        self.kafka_producer = kafka_producer
        self.ticket_client = ticket_client
        self.postgres_client = postgres_client
        self.mongodb_client = mongodb_client

        # Novos serviços para builds de container reais
        self.dockerfile_generator = DockerfileGenerator()
        self.container_builder = ContainerBuilder(
            builder_type=BuilderType.DOCKER,
            timeout_seconds=build_timeout,
        )
        self.enable_container_build = enable_container_build

        self.max_concurrent = max_concurrent
        self.pipeline_timeout = pipeline_timeout
        self.auto_approval_threshold = auto_approval_threshold
        self.min_quality_score = min_quality_score
        self.metrics = metrics

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_pipelines: Dict[str, PipelineContext] = {}

    async def execute_pipeline(self, ticket: ExecutionTicket) -> PipelineResult:
        """
        Executa pipeline completo para um Execution Ticket

        Args:
            ticket: Execution Ticket do tipo BUILD

        Returns:
            PipelineResult com status e artefatos gerados
        """
        async with self._semaphore:
            pipeline_id = str(uuid.uuid4())
            trace_id = ticket.trace_id or str(uuid.uuid4())
            span_id = ticket.span_id or str(uuid.uuid4())

            # Criar contexto do pipeline
            # Extrair generation_method dos parâmetros do ticket se presente
            generation_method = ticket.parameters.get('generation_method') if ticket.parameters else None

            context = PipelineContext(
                pipeline_id=pipeline_id,
                ticket=ticket,
                trace_id=trace_id,
                span_id=span_id,
                generation_method=generation_method
            )

            self._active_pipelines[pipeline_id] = context

            try:
                logger.info(
                    'pipeline_started',
                    pipeline_id=pipeline_id,
                    ticket_id=ticket.ticket_id,
                    trace_id=trace_id
                )

                # Validar ticket
                if not ticket.is_build_task():
                    raise ValueError(f'Ticket não é do tipo BUILD: {ticket.task_type}')

                # Atualizar status do ticket para RUNNING
                await self.ticket_client.update_status(
                    ticket.ticket_id,
                    TicketStatus.RUNNING,
                    {'pipeline_id': pipeline_id}
                )

                # Executar 8 subpipelines sequencialmente
                await self._execute_stage(context, 'template_selection', self.template_selector.select)
                await self._execute_stage(context, 'code_composition', self.code_composer.compose)

                # Novos stages para builds de container reais
                if self.enable_container_build:
                    await self._execute_stage(
                        context,
                        'dockerfile_generation',
                        self._generate_dockerfile
                    )
                    await self._execute_stage(
                        context,
                        'container_build',
                        self._build_container
                    )

                await self._execute_stage(context, 'validation', self.validator.validate)
                await self._execute_stage(context, 'testing', self.test_runner.run_tests)
                await self._execute_stage(context, 'packaging', self.packager.package)
                await self._execute_stage(context, 'approval_gate', self.approval_gate.check_approval)

                # Pipeline completado
                context.completed_at = datetime.now()

                # Converter para PipelineResult
                pipeline_result = context.to_pipeline_result(
                    self.auto_approval_threshold,
                    self.min_quality_score
                )

                # Persistir resultado
                await self.postgres_client.save_pipeline(pipeline_result)

                # Publicar resultado no Kafka
                await self.kafka_producer.publish_result(pipeline_result)

                # Atualizar status do ticket baseado no status do pipeline
                if pipeline_result.status == 'COMPLETED':
                    final_status = TicketStatus.COMPLETED
                elif pipeline_result.status in ('REQUIRES_REVIEW', 'PARTIAL'):
                    # Tickets que requerem revisão permanecem em RUNNING
                    final_status = TicketStatus.RUNNING
                else:
                    final_status = TicketStatus.FAILED

                await self.ticket_client.update_status(
                    ticket.ticket_id,
                    final_status,
                    {'pipeline_id': pipeline_id, 'status': pipeline_result.status}
                )

                logger.info(
                    'pipeline_completed',
                    pipeline_id=pipeline_id,
                    status=pipeline_result.status,
                    duration_ms=pipeline_result.total_duration_ms
                )

                return pipeline_result

            except Exception as e:
                logger.error(
                    'pipeline_failed',
                    pipeline_id=pipeline_id,
                    error=str(e),
                    exc_info=True
                )

                context.error = e
                context.completed_at = datetime.now()

                # Criar ticket de compensação
                try:
                    await self.ticket_client.create_compensation_ticket(
                        ticket.ticket_id,
                        f'Pipeline falhou: {str(e)}'
                    )
                except Exception as comp_error:
                    logger.error('compensation_ticket_failed', error=str(comp_error))

                # Atualizar status do ticket
                await self.ticket_client.update_status(
                    ticket.ticket_id,
                    TicketStatus.FAILED,
                    {'pipeline_id': pipeline_id, 'error': str(e)}
                )

                # Criar PipelineResult com erro
                pipeline_result = context.to_pipeline_result(
                    self.auto_approval_threshold,
                    self.min_quality_score
                )

                # Publicar resultado de falha
                await self.kafka_producer.publish_result(pipeline_result)

                return pipeline_result

            finally:
                # Remover do tracking de pipelines ativos
                self._active_pipelines.pop(pipeline_id, None)

    async def _execute_stage(self, context: PipelineContext, stage_name: str, stage_func):
        """
        Executa um stage do pipeline

        Args:
            context: Contexto do pipeline
            stage_name: Nome do stage
            stage_func: Função assíncrona do stage
        """
        stage = PipelineStage(
            stage_name=stage_name,
            status=StageStatus.RUNNING,
            started_at=datetime.now(),
            duration_ms=0
        )
        context.add_stage(stage)

        start_time = datetime.now()

        try:
            logger.info('stage_started', stage=stage_name, pipeline_id=context.pipeline_id)

            # Executar stage com timeout
            await asyncio.wait_for(
                stage_func(context),
                timeout=self.pipeline_timeout
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            context.mark_stage_completed(stage_name, duration_ms)

            # Emitir métrica de duração do stage
            if self.metrics:
                self.metrics.stage_duration_seconds.labels(stage=stage_name).observe(duration_ms / 1000.0)

            logger.info('stage_completed', stage=stage_name, duration_ms=duration_ms)

        except asyncio.TimeoutError:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = f'Stage {stage_name} timeout após {self.pipeline_timeout}s'
            context.mark_stage_failed(stage_name, error_msg, duration_ms)

            # Emitir métricas de falha
            if self.metrics:
                self.metrics.stage_duration_seconds.labels(stage=stage_name).observe(duration_ms / 1000.0)
                self.metrics.stage_failures_total.labels(stage=stage_name, error_type='TimeoutError').inc()

            logger.error('stage_timeout', stage=stage_name)
            raise

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            context.mark_stage_failed(stage_name, str(e), duration_ms)

            # Emitir métricas de falha
            if self.metrics:
                self.metrics.stage_duration_seconds.labels(stage=stage_name).observe(duration_ms / 1000.0)
                self.metrics.stage_failures_total.labels(stage=stage_name, error_type=type(e).__name__).inc()

            logger.error('stage_failed', stage=stage_name, error=str(e))
            raise

    async def _generate_dockerfile(self, context: PipelineContext) -> PipelineContext:
        """
        Stage: Gera Dockerfile otimizado para o código.

        Gera um Dockerfile multi-stage baseado na linguagem detectada,
        com foco em segurança (usuário não-root) e tamanho mínimo.
        """
        try:
            # Detectar linguagem a partir dos parâmetros do ticket
            language = self._detect_language(context)
            framework = context.ticket.parameters.get("framework", "fastapi")
            artifact_type = self._map_artifact_type(context)

            logger.info(
                "generating_dockerfile",
                pipeline_id=context.pipeline_id,
                language=language,
                framework=framework,
                artifact_type=artifact_type,
            )

            # Gerar Dockerfile usando o DockerfileGenerator
            dockerfile_content = self.dockerfile_generator.generate_dockerfile(
                language=language,
                framework=framework,
                artifact_type=artifact_type,
            )

            # Armazenar no contexto (reutilizar no build stage)
            context.metadata["dockerfile"] = {
                "language": language,
                "framework": framework,
                "content": dockerfile_content,  # Cache para reutilizar
                "generated": True,
            }

            logger.info(
                "dockerfile_generated",
                pipeline_id=context.pipeline_id,
                language=language,
            )

            return context

        except Exception as e:
            logger.error(
                "dockerfile_generation_failed",
                pipeline_id=context.pipeline_id,
                error=str(e),
            )
            context.error = e
            raise

    async def _build_container(self, context: PipelineContext) -> PipelineContext:
        """
        Stage: Executa build da imagem de container.

        Salva o Dockerfile gerado em disco e executa o build
        usando Docker CLI.
        """
        try:
            # O workdir deve ter sido criado nos stages anteriores
            workdir = context.code_workspace_path or f"/tmp/{context.pipeline_id}"
            os.makedirs(workdir, exist_ok=True)

            # Salvar Dockerfile em disco (reutilizar cached se disponível)
            dockerfile_path = os.path.join(workdir, "Dockerfile")

            # Reutilizar Dockerfile do cache se disponível
            if "dockerfile" in context.metadata and "content" in context.metadata["dockerfile"]:
                dockerfile_content = context.metadata["dockerfile"]["content"]
                logger.debug("reusing_cached_dockerfile", pipeline_id=context.pipeline_id)
            else:
                # Fallback: gerar novamente
                dockerfile_content = self.dockerfile_generator.generate_dockerfile(
                    language=self._detect_language(context),
                    framework=context.ticket.parameters.get("framework"),
                    artifact_type=self._map_artifact_type(context),
                )

            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)

            # Preparar arquivos de código no workspace para o build
            language = self._detect_language(context)
            await self._prepare_build_workspace(context, workdir, language)

            # Definir tag da imagem
            artifact_name = context.ticket.parameters.get(
                "service_name",
                f"service-{context.ticket.ticket_id[:8]}"
            )
            version = context.ticket.parameters.get("version", "latest")
            image_tag = f"{artifact_name}:{version}"

            logger.info(
                "building_container_image",
                pipeline_id=context.pipeline_id,
                image_tag=image_tag,
            )

            # Executar build
            result = await self.container_builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=workdir,
                image_tag=image_tag,
            )

            if result.success:
                context.metadata["container_image"] = {
                    "digest": result.image_digest,
                    "tag": image_tag,
                    "size_bytes": result.size_bytes,
                }

                logger.info(
                    "container_build_success",
                    pipeline_id=context.pipeline_id,
                    image_tag=image_tag,
                    digest=result.image_digest,
                )

                return context
            else:
                logger.error(
                    "container_build_failed",
                    pipeline_id=context.pipeline_id,
                    error=result.error_message,
                )
                raise RuntimeError(f"Build failed: {result.error_message}")

        except Exception as e:
            logger.error(
                "container_build_exception",
                pipeline_id=context.pipeline_id,
                error=str(e),
            )
            context.error = e
            raise

    def _detect_language(self, context: PipelineContext) -> CodeLanguage:
        """Detecta a linguagem a partir dos parâmetros do ticket."""
        language_str = context.ticket.parameters.get("language", "python").lower()

        language_map = {
            "python": CodeLanguage.PYTHON,
            "py": CodeLanguage.PYTHON,
            "nodejs": CodeLanguage.NODEJS,
            "node": CodeLanguage.NODEJS,
            "javascript": CodeLanguage.NODEJS,  # Mapear javascript para NODEJS
            "js": CodeLanguage.NODEJS,
            "typescript": CodeLanguage.TYPESCRIPT,
            "ts": CodeLanguage.TYPESCRIPT,
            "go": CodeLanguage.GOLANG,  # Mapear go para GOLANG
            "golang": CodeLanguage.GOLANG,
            "java": CodeLanguage.JAVA,
            "c#": CodeLanguage.CSHARP,
            "csharp": CodeLanguage.CSHARP,
        }

        return language_map.get(language_str, CodeLanguage.PYTHON)

    def _map_artifact_type(self, context: PipelineContext) -> ArtifactSubtype:
        """Mapeia o tipo de artefato do ticket para ArtifactSubtype."""
        artifact_type_str = context.ticket.parameters.get(
            "artifact_type",
            "microservice"
        ).lower()

        type_map = {
            "microservice": ArtifactSubtype.MICROSERVICE,
            "lambda_function": ArtifactSubtype.LAMBDA_FUNCTION,
            "lambda": ArtifactSubtype.LAMBDA_FUNCTION,
            "cli_tool": ArtifactSubtype.CLI_TOOL,
            "cli": ArtifactSubtype.CLI_TOOL,
            "library": ArtifactSubtype.LIBRARY,
        }

        return type_map.get(artifact_type_str, ArtifactSubtype.MICROSERVICE)

    async def _prepare_build_workspace(
        self,
        context: PipelineContext,
        workdir: str,
        language: CodeLanguage,
    ) -> None:
        """
        Prepara o workspace de build com arquivos necessários.

        Cria requirements.txt, main.py, package.json, go.mod, etc.
        baseado na linguagem e nos artefatos gerados.
        """
        # Obter código gerado dos artefatos (se disponível)
        generated_code = self._extract_generated_code(context)

        if language == CodeLanguage.PYTHON:
            # Criar requirements.txt
            requirements = self._get_python_requirements(context)
            requirements_path = os.path.join(workdir, "requirements.txt")
            with open(requirements_path, "w") as f:
                f.write(requirements)

            # Criar main.py com código gerado ou padrão
            main_py_path = os.path.join(workdir, "main.py")
            with open(main_py_path, "w") as f:
                f.write(generated_code or self._get_default_python_code(context))

            logger.debug(
                "python_workspace_prepared",
                pipeline_id=context.pipeline_id,
                files=["requirements.txt", "main.py"],
            )

        elif language == CodeLanguage.NODEJS:
            # Criar package.json
            package_json = self._get_nodejs_package_json(context)
            package_path = os.path.join(workdir, "package.json")
            with open(package_path, "w") as f:
                f.write(package_json)

            # Criar index.js
            index_js_path = os.path.join(workdir, "index.js")
            with open(index_js_path, "w") as f:
                f.write(generated_code or self._get_default_nodejs_code(context))

            logger.debug(
                "nodejs_workspace_prepared",
                pipeline_id=context.pipeline_id,
                files=["package.json", "index.js"],
            )

        elif language == CodeLanguage.TYPESCRIPT:
            # Criar package.json
            package_json = self._get_typescript_package_json(context)
            package_path = os.path.join(workdir, "package.json")
            with open(package_path, "w") as f:
                f.write(package_json)

            # Criar tsconfig.json
            tsconfig = self._get_tsconfig_json()
            tsconfig_path = os.path.join(workdir, "tsconfig.json")
            with open(tsconfig_path, "w") as f:
                f.write(tsconfig)

            # Criar index.ts
            index_ts_path = os.path.join(workdir, "index.ts")
            with open(index_ts_path, "w") as f:
                f.write(generated_code or self._get_default_typescript_code(context))

            logger.debug(
                "typescript_workspace_prepared",
                pipeline_id=context.pipeline_id,
                files=["package.json", "tsconfig.json", "index.ts"],
            )

        elif language == CodeLanguage.GOLANG:
            # Criar go.mod
            go_mod = self._get_go_mod(context)
            go_mod_path = os.path.join(workdir, "go.mod")
            with open(go_mod_path, "w") as f:
                f.write(go_mod)

            # Criar main.go
            main_go_path = os.path.join(workdir, "main.go")
            with open(main_go_path, "w") as f:
                f.write(generated_code or self._get_default_go_code(context))

            logger.debug(
                "go_workspace_prepared",
                pipeline_id=context.pipeline_id,
                files=["go.mod", "main.go"],
            )

        elif language == CodeLanguage.JAVA:
            # Criar pom.xml (Maven)
            pom_xml = self._get_maven_pom(context)
            pom_path = os.path.join(workdir, "pom.xml")
            with open(pom_path, "w") as f:
                f.write(pom_xml)

            # Criar src/main/java/Main.java
            java_dir = os.path.join(workdir, "src", "main", "java")
            os.makedirs(java_dir, exist_ok=True)
            main_java_path = os.path.join(java_dir, "Main.java")
            with open(main_java_path, "w") as f:
                f.write(generated_code or self._get_default_java_code(context))

            logger.debug(
                "java_workspace_prepared",
                pipeline_id=context.pipeline_id,
                files=["pom.xml", "src/main/java/Main.java"],
            )

    def _extract_generated_code(self, context: PipelineContext) -> str:
        """Extrai código gerado dos artefatos no contexto."""
        # Buscar artefato de código gerado
        for artifact in context.generated_artifacts:
            if artifact.artifact_type == ArtifactCategory.CODE:
                # Se tivermos o código em cache (gerado por CodeComposer)
                if hasattr(artifact, "content") and artifact.content:
                    return artifact.content

                # TODO: Buscar do MongoDB se necessário
                # Por enquanto retornar vazio para usar código padrão
                break
        return ""

    def _get_python_requirements(self, context: PipelineContext) -> str:
        """Retorna requirements.txt baseado no framework."""
        framework = context.ticket.parameters.get("framework", "fastapi")

        base_requirements = [
            "fastapi>=0.104.0",
            "uvicorn[standard]>=0.24.0",
            "pydantic>=2.5.0",
            "structlog>=23.2.0",
            "python-multipart>=0.0.6",
        ]

        if framework == "fastapi":
            return "\n".join(base_requirements)
        elif framework == "flask":
            return "\n".join([
                "Flask>=3.0.0",
                "gunicorn>=21.2.0",
                "structlog>=23.2.0",
            ])
        else:
            return "\n".join(base_requirements)

    def _get_default_python_code(self, context: PipelineContext) -> str:
        """Retorna código Python padrão se nenhum foi gerado."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        framework = context.ticket.parameters.get("framework", "fastapi")

        if framework == "fastapi":
            return f'''from fastapi import FastAPI
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)
app = FastAPI(title="{service_name}")


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/health")
async def health():
    return HealthResponse(status="healthy", service="{service_name}")


@app.get("/")
async def root():
    return {{"message": "Welcome to {service_name}"}}
'''
        else:
            return f'''#!/usr/bin/env python3
"""
{service_name} - Generated by Neural Code Forge
"""

import structlog

logger = structlog.get_logger(__name__)


def main():
    logger.info("Starting {service_name}...")
    # Add your logic here


if __name__ == "__main__":
    main()
'''

    def _get_nodejs_package_json(self, context: PipelineContext) -> str:
        """Retorna package.json para Node.js."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        return f'''{{
  "name": "{service_name}",
  "version": "1.0.0",
  "description": "Generated by Neural Code Forge",
  "main": "index.js",
  "scripts": {{
    "start": "node index.js",
    "test": "echo \\"Error: no test specified\\" && exit 1"
  }},
  "dependencies": {{
    "express": "^4.18.2",
    "helmet": "^7.1.0"
  }}
}}
'''

    def _get_default_nodejs_code(self, context: PipelineContext) -> str:
        """Retorna código Node.js padrão."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        return f'''const express = require('express');
const helmet = require('helmet');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(express.json());

app.get('/health', (req, res) => {{
  res.json({{ status: 'healthy', service: '{service_name}' }});
}});

app.get('/', (req, res) => {{
  res.json({{ message: 'Welcome to {service_name}' }});
}});

if (require.main === module) {{
  app.listen(PORT, () => {{
    console.log(`{service_name} listening on port ${{PORT}}`);
  }});
}}

module.exports = app;
'''

    def _get_typescript_package_json(self, context: PipelineContext) -> str:
        """Retorna package.json para TypeScript."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        return f'''{{
  "name": "{service_name}",
  "version": "1.0.0",
  "description": "Generated by Neural Code Forge",
  "main": "dist/index.js",
  "scripts": {{
    "build": "tsc",
    "start": "node dist/index.js",
    "dev": "ts-node src/index.ts"
  }},
  "dependencies": {{
    "express": "^4.18.2",
    "helmet": "^7.1.0"
  }},
  "devDependencies": {{
    "@types/express": "^4.17.21",
    "@types/node": "^20.10.0",
    "typescript": "^5.3.3",
    "ts-node": "^10.9.2"
  }}
}}
'''

    def _get_tsconfig_json(self) -> str:
        """Retorna tsconfig.json padrão."""
        return '''{{
  "compilerOptions": {{
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "moduleResolution": "node"
  }},
  "include": ["*.ts"],
  "exclude": ["node_modules"]
}}
'''

    def _get_default_typescript_code(self, context: PipelineContext) -> str:
        """Retorna código TypeScript padrão."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        return f'''import express, {{ Request, Response, Application }} from 'express';
import helmet from 'helmet';

const PORT = process.env.PORT || 3000;

interface HealthResponse {{
  status: string;
  service: string;
}}

const app: Application = express();

app.use(helmet());
app.use(express.json());

app.get('/health', (req: Request, res: Response) => {{
  const response: HealthResponse = {{
    status: 'healthy',
    service: '{service_name}"
  }};
  res.json(response);
}});

app.get('/', (req: Request, res: Response) => {{
  res.json({{ message: 'Welcome to {service_name}' }});
}});

if (require.main === module) {{
  app.listen(PORT, () => {{
    console.log(`{service_name} listening on port ${{PORT}}`);
  }});
}}

export default app;
'''

    def _get_go_mod(self, context: PipelineContext) -> str:
        """Retorna go.mod."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        module_name = service_name.replace("-", "_")
        return f'''module {module_name}

go 1.21

require (
    github.com/gorilla/mux v1.8.1
)
'''

    def _get_default_go_code(self, context: PipelineContext) -> str:
        """Retorna código Go padrão."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        return f'''// Package main - {service_name}
// Generated by Neural Code Forge

package main

import (
    "encoding/json"
    "log"
    "net/http"
    "os"
)

type HealthResponse struct {{
    Status  string `json:"status"`
    Service string `json:"service"`
}}

func healthHandler(w http.ResponseWriter, r *http.Request) {{
    w.Header().Set("Content-Type", "application/json")
    resp := HealthResponse{{
        Status:  "healthy",
        Service: "{service_name}",
    }}
    json.NewEncoder(w).Encode(resp)
}}

func rootHandler(w http.ResponseWriter, r *http.Request) {{
    w.Header().Set("Content-Type", "application/json")
    resp := map[string]string{{
        "message": "Welcome to {service_name}",
    }}
    json.NewEncoder(w).Encode(resp)
}}

func main() {{
    port := os.Getenv("PORT")
    if port == "" {{
        port = "8080"
    }}

    http.HandleFunc("/health", healthHandler)
    http.HandleFunc("/", rootHandler)

    log.Printf("{service_name} listening on port %s", port)
    if err := http.ListenAndServe(":"+port, nil); err != nil {{
        log.Fatalf("Failed to start server: %v", err)
    }}
}}
'''

    def _get_maven_pom(self, context: PipelineContext) -> str:
        """Retorna pom.xml para Maven."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        artifact_id = service_name.replace("-", "")
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.neuralhive</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>{service_name}</name>
    <description>Generated by Neural Code Forge</description>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
'''

    def _get_default_java_code(self, context: PipelineContext) -> str:
        """Retorna código Java padrão."""
        service_name = context.ticket.parameters.get("service_name", "my-service")
        class_name = "".join(word.title() for word in service_name.replace("-", " ").split())
        return f'''package com.neuralhive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;

import java.util.HashMap;
import java.util.Map;

@SpringBootApplication
@RestController
public class {class_name}Application {{

    public static void main(String[] args) {{
        SpringApplication.run({class_name}Application.class, args);
    }}

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {{
        Map<String, Object> response = new HashMap<>();
        response.put("status", "healthy");
        response.put("service", "{service_name}");
        return ResponseEntity.ok(response);
    }}

    @GetMapping("/")
    public ResponseEntity<Map<String, String>> root() {{
        Map<String, String> response = new HashMap<>();
        response.put("message", "Welcome to {service_name}");
        return ResponseEntity.ok(response);
    }}
}}
'''

    def get_active_pipelines_count(self) -> int:
        """Retorna número de pipelines ativos"""
        return len(self._active_pipelines)

    def get_pipeline_context(self, pipeline_id: str) -> PipelineContext:
        """Retorna contexto de um pipeline ativo"""
        return self._active_pipelines.get(pipeline_id)
