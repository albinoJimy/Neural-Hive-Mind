"""Learning Documentation Generator - Main Application"""

import asyncio

import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from src.api import v1
from src.api.v1.docs import AppState, set_state
from src.clients import KafkaLearningDocProducer
from src.config import get_settings
from src.consumers import LearningEventConsumer
from src.scheduler import DocumentScheduler
from src.services import (
    DocumentRepository,
    ExperimentInsightExtractor,
    MarkdownReportGenerator,
    PDFGenerator,
    PlotGenerator,
)

from neural_hive_observability import init_observability
from neural_hive_observability.health import HealthChecker, HealthStatus

logger = structlog.get_logger()

# Configurações
settings = get_settings()

# Aplicação FastAPI
app = FastAPI(
    title="Learning Documentation Generator",
    version="1.0.0",
    description="Geração automática de documentação de aprendizado para Neural Hive-Mind",
    docs_url="/docs",
    redoc_url="/redoc",
)


# Estado global
class GlobalState:
    """Estado global da aplicação"""

    repository: DocumentRepository = None
    insight_extractor: ExperimentInsightExtractor = None
    report_generator: MarkdownReportGenerator = None
    plot_generator: PlotGenerator = None
    pdf_generator: PDFGenerator = None
    health_checker: HealthChecker = None
    scheduler: DocumentScheduler = None
    kafka_consumer: LearningEventConsumer = None
    kafka_producer: KafkaLearningDocProducer = None


state = GlobalState()


@app.on_event("startup")
async def startup_event():
    """Inicialização da aplicação"""
    logger.info("Iniciando Learning Documentation Generator", environment=settings.environment)

    # Inicializar observabilidade
    init_observability(
        service_name="learning-doc-generator",
        service_version="1.0.0",
        neural_hive_component="learning-doc-generator",
        neural_hive_layer="observability",
        neural_hive_domain="learning",
        otel_endpoint=settings.otel_endpoint,
        prometheus_port=settings.prometheus_port,
    )

    # Inicializar HealthChecker
    from neural_hive_observability.config import ObservabilityConfig
    from neural_hive_observability.health_checks.otel import OTELPipelineHealthCheck

    observability_config = ObservabilityConfig(
        service_name="learning-doc-generator",
        service_version="1.0.0",
        neural_hive_component="learning-doc-generator",
        neural_hive_layer="observability",
    )
    state.health_checker = HealthChecker(config=observability_config)

    otel_health_check = OTELPipelineHealthCheck(
        otel_endpoint=settings.otel_endpoint,
        service_name="learning-doc-generator",
        name="otel_pipeline",
        timeout_seconds=5.0,
        verify_trace_export=True,
    )
    state.health_checker.register_check(otel_health_check)
    logger.info("otel_pipeline_health_check_registered")

    try:
        # Inicializar repositório MongoDB
        state.repository = DocumentRepository()
        await state.repository.initialize()
        logger.info("MongoDB inicializado")

        # Inicializar extractor de insights
        state.insight_extractor = ExperimentInsightExtractor()
        await state.insight_extractor.initialize()
        logger.info("MLflow client inicializado")

        # Inicializar gerador de relatórios
        state.report_generator = MarkdownReportGenerator()
        await state.report_generator.initialize()
        logger.info("Report generator inicializado")

        # Inicializar gerador de plots
        state.plot_generator = PlotGenerator()
        logger.info("Plot generator inicializado")

        # Inicializar gerador de PDF (opcional)
        state.pdf_generator = PDFGenerator()
        if state.pdf_generator.is_available():
            logger.info("PDF generator inicializado")
        else:
            logger.warning(
                "PDF generator não disponível - WeasyPrint não instalado",
                hint="Instale com: pip install weasyprint",
            )

        # Inicializar Kafka Producer
        state.kafka_producer = KafkaLearningDocProducer()
        await state.kafka_producer.start()
        logger.info("Kafka producer inicializado")

        # Inicializar Scheduler
        state.scheduler = DocumentScheduler(
            repository=state.repository,
            insight_extractor=state.insight_extractor,
            report_generator=state.report_generator,
        )
        await state.scheduler.start()
        logger.info("Scheduler iniciado")

        # Inicializar Kafka Consumer em background
        state.kafka_consumer = LearningEventConsumer(
            repository=state.repository,
            insight_extractor=state.insight_extractor,
            report_generator=state.report_generator,
            kafka_producer=state.kafka_producer,
        )
        asyncio.create_task(state.kafka_consumer.start())
        logger.info("Kafka consumer iniciado em background")

        # Configurar estado para API
        api_state = AppState()
        api_state.repository = state.repository
        api_state.insight_extractor = state.insight_extractor
        api_state.report_generator = state.report_generator
        api_state.plot_generator = state.plot_generator
        api_state.pdf_generator = state.pdf_generator
        set_state(api_state)

        # Registrar routers
        app.include_router(v1.router, prefix="/api/v1")

        logger.info("Learning Documentation Generator iniciado com sucesso")

    except Exception as e:
        logger.error("Erro na inicialização", error=str(e), exc_info=True)
        # Cleanup
        if state.scheduler:
            await state.scheduler.stop()
        if state.kafka_consumer:
            await state.kafka_consumer.stop()
        if state.kafka_producer:
            await state.kafka_producer.stop()
        if state.repository:
            try:
                await state.repository.close()
            except Exception:
                pass
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Encerramento graceful"""
    logger.info("Encerrando Learning Documentation Generator")

    # Parar scheduler
    if state.scheduler:
        await state.scheduler.stop()
        logger.info("Scheduler parado")

    # Parar Kafka consumer
    if state.kafka_consumer:
        await state.kafka_consumer.stop()
        logger.info("Kafka consumer parado")

    # Parar Kafka producer
    if state.kafka_producer:
        await state.kafka_producer.stop()
        logger.info("Kafka producer parado")

    # Fechar serviços
    if state.insight_extractor:
        await state.insight_extractor.close()

    if state.repository:
        await state.repository.close()

    if state.plot_generator:
        await state.plot_generator.close()

    if state.pdf_generator:
        await state.pdf_generator.close()

    logger.info("Learning Documentation Generator encerrado")


@app.get("/health")
async def health():
    """Health check básico"""
    return {"status": "healthy", "service": "learning-doc-generator"}


@app.get("/ready")
async def readiness():
    """Readiness check"""
    checks = {
        "mongodb": False,
        "mlflow": False,
        "otel_pipeline": True,
        "scheduler": False,
        "kafka_producer": False,
    }

    try:
        # Verificar MongoDB
        if state.repository and state.repository._client:
            await state.repository._client.admin.command("ping")
            checks["mongodb"] = True

        # Verificar MLflow (básico)
        if state.insight_extractor and state.insight_extractor._mlflow_client:
            checks["mlflow"] = True

        # Verificar OTEL pipeline
        if state.health_checker:
            try:
                otel_result = await state.health_checker.check_single("otel_pipeline")
                if otel_result:
                    checks["otel_pipeline"] = otel_result.status in (
                        HealthStatus.HEALTHY,
                        HealthStatus.DEGRADED,
                    )
            except Exception:
                checks["otel_pipeline"] = False

        # Verificar Scheduler
        if state.scheduler and state.scheduler.is_running():
            checks["scheduler"] = True

        # Verificar Kafka Producer
        if state.kafka_producer and await state.kafka_producer.health_check():
            checks["kafka_producer"] = True

        # Kafka consumer é opcional para readiness (roda em background)
        all_ready = all(checks.values())
        if not all_ready:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=503, content={"ready": False, "checks": checks})

        return {"ready": True, "checks": checks}

    except Exception as e:
        logger.error("Erro no readiness check", error=str(e))
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503, content={"ready": False, "checks": checks, "error": str(e)}
        )


@app.get("/metrics")
async def metrics():
    """Endpoint métricas Prometheus (compatibilidade)"""
    from fastapi.responses import Response

    # O endpoint principal está montado abaixo, este é apenas para compatibilidade
    return Response(content="Prometheus metrics disponíveis em /metrics", media_type="text/plain")


@app.get("/scheduler/status")
async def scheduler_status():
    """Status do scheduler e próximos runs"""
    if not state.scheduler:
        return {"running": False, "next_runs": {}}

    return {
        "running": state.scheduler.is_running(),
        "next_runs": state.scheduler.get_next_run_times(),
    }


# Montar métricas Prometheus
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=settings.debug,
    )
