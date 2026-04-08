"""API REST para documentos de aprendizado"""

import asyncio
from datetime import datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response
from fastapi.responses import FileResponse

from src.config import get_settings
from src.models import (
    DocumentFormat,
    DocumentGenerationRequest,
    DocumentGenerationResponse,
    DocumentListResponse,
    DocumentStatus,
    DocumentType,
    LearningDocument,
)
from src.services import (
    DocumentRepository,
    ExperimentInsightExtractor,
    MarkdownReportGenerator,
    PlotGenerator,
)

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter()

# Estado global (será inicializado no main.py)
class AppState:
    """Estado global da aplicação"""

    repository: Optional[DocumentRepository] = None
    insight_extractor: Optional[ExperimentInsightExtractor] = None
    report_generator: Optional[MarkdownReportGenerator] = None
    plot_generator: Optional[PlotGenerator] = None


_state: Optional[AppState] = None


def get_state() -> AppState:
    """Obtém estado global"""
    global _state
    if _state is None:
        _state = AppState()
    return _state


def set_state(state: AppState) -> None:
    """Define estado global"""
    global _state
    _state = state


async def generate_document_task(
    doc_id: str,
    request: DocumentGenerationRequest,
    state: AppState,
) -> None:
    """Task em background para geração de documento

    Args:
        doc_id: ID do documento
        request: Request de geração
        state: Estado global
    """
    try:
        logger.info("Iniciando geração de documento", doc_id=doc_id, type=request.type)

        # Atualizar status para generating
        await state.repository.update_status(doc_id, DocumentStatus.GENERATING)

        # Buscar experiment runs
        runs = await state.insight_extractor.fetch_experiment_runs(
            experiment_ids=request.experiment_ids,
            period_start=request.period_start,
            period_end=request.period_end,
            max_runs=settings.max_experiments_per_doc,
        )

        if not runs:
            await state.repository.update_status(
                doc_id, DocumentStatus.FAILED, "Nenhum experimento encontrado"
            )
            logger.warning("Nenhum experimento encontrado", doc_id=doc_id)
            return

        # Extrair insights
        insights = await state.insight_extractor.extract_insights(runs)

        # Gerar resumo
        summary = await state.insight_extractor.generate_summary(runs)

        # Gerar recomendações
        recommendations = await state.insight_extractor.generate_recommendations(insights, runs)

        # Gerar gráficos se solicitado
        plots = []
        if request.include_plots and state.plot_generator:
            plots = await state.plot_generator.generate_all_plots(
                runs, format_type=request.plot_format
            )

        # Buscar documento atualizado
        document = await state.repository.get_by_id(doc_id)
        if not document:
            logger.error("Documento não encontrado", doc_id=doc_id)
            return

        # Atualizar documento
        document.experiment_runs = runs
        document.insights = insights
        document.summary = summary
        document.recommendations = recommendations
        document.plots = plots
        document.period_start = request.period_start or min(
            (r.start_time for r in runs if r.start_time), default=datetime.utcnow()
        )
        document.period_end = request.period_end or datetime.utcnow()
        document.generated_at = datetime.utcnow()

        # Gerar Markdown
        markdown_content = await state.report_generator.generate(document)
        document.markdown_content = markdown_content

        # Salvar arquivo
        file_path = await state.report_generator.save_to_file(document, markdown_content)
        document.metadata["file_path"] = file_path

        # Atualizar no repositório
        await state.repository.update(doc_id, document)

        # Atualizar status para completed
        await state.repository.update_status(doc_id, DocumentStatus.COMPLETED)

        logger.info(
            "Documento gerado com sucesso",
            doc_id=doc_id,
            runs=len(runs),
            insights=len(insights),
        )

    except Exception as e:
        logger.error("Erro na geração de documento", doc_id=doc_id, error=str(e), exc_info=True)
        await state.repository.update_status(doc_id, DocumentStatus.FAILED, str(e))


@router.post("/generate", response_model=DocumentGenerationResponse)
async def generate_document(
    request: DocumentGenerationRequest,
    background_tasks: BackgroundTasks,
) -> DocumentGenerationResponse:
    """Gera um novo documento de aprendizado

    Args:
        request: Request de geração
        background_tasks: Tasks em background

    Returns:
        Response com ID do documento
    """
    state = get_state()

    if not state.repository:
        raise HTTPException(status_code=503, detail="Serviço indisponível - repositório não inicializado")

    try:
        # Criar documento inicial
        document = LearningDocument(
            title=request.title or f"Relatório {request.type.value}",
            type=request.type,
            format=request.format,
            period_start=request.period_start,
            period_end=request.period_end,
            status=DocumentStatus.PENDING,
            metadata=request.metadata,
        )

        # Salvar documento
        doc_id = await state.repository.save(document)

        # Adicionar task em background
        background_tasks.add_task(generate_document_task, doc_id, request, state)

        return DocumentGenerationResponse(
            document_id=doc_id,
            status=DocumentStatus.PENDING,
            message="Documento em geração",
        )

    except Exception as e:
        logger.error("Erro ao iniciar geração", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    type: Optional[DocumentType] = Query(None, description="Filtrar por tipo"),
    status: Optional[DocumentStatus] = Query(None, description="Filtrar por status"),
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(20, ge=1, le=100, description="Tamanho da página"),
    sort_by: str = Query("created_at", description="Campo para ordenação"),
    sort_order: int = Query(-1, ge=-1, le=1, description="Ordem (-1=DESC, 1=ASC)"),
) -> DocumentListResponse:
    """Lista documentos de aprendizado

    Args:
        type: Filtrar por tipo
        status: Filtrar por status
        page: Página
        page_size: Tamanho da página
        sort_by: Campo para ordenação
        sort_order: Ordem (-1=DESC, 1=ASC)

    Returns:
        Lista de documentos
    """
    state = get_state()

    if not state.repository:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    try:
        documents, total = await state.repository.list_documents(
            doc_type=type,
            status=status,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return DocumentListResponse(
            total=total,
            page=page,
            page_size=page_size,
            documents=documents,
        )

    except Exception as e:
        logger.error("Erro ao listar documentos", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}", response_model=LearningDocument)
async def get_document(doc_id: str) -> LearningDocument:
    """Obtém um documento por ID

    Args:
        doc_id: ID do documento

    Returns:
        Documento
    """
    state = get_state()

    if not state.repository:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    document = await state.repository.get_by_id(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    return document


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    format: DocumentFormat = Query(DocumentFormat.MARKDOWN, description="Formato"),
) -> Response:
    """Download de documento

    Args:
        doc_id: ID do documento
        format: Formato desejado

    Returns:
        Arquivo para download
    """
    state = get_state()

    if not state.repository:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    document = await state.repository.get_by_id(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if document.status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=400, detail="Documento ainda não foi gerado completamente"
        )

    if format == DocumentFormat.MARKDOWN:
        if not document.markdown_content:
            raise HTTPException(status_code=404, detail="Conteúdo Markdown não disponível")

        return Response(
            content=document.markdown_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{doc_id}.md"',
            },
        )
    else:
        raise HTTPException(status_code=400, detail=f"Formato {format} não implementado ainda")


@router.delete("/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    """Deleta um documento

    Args:
        doc_id: ID do documento

    Returns:
        Confirmação
    """
    state = get_state()

    if not state.repository:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    deleted = await state.repository.delete(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    return {"deleted": True, "doc_id": doc_id}


@router.post("/{doc_id}/regenerate")
async def regenerate_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
) -> DocumentGenerationResponse:
    """Regenera um documento existente

    Args:
        doc_id: ID do documento
        background_tasks: Tasks em background

    Returns:
        Response de regeneração
    """
    state = get_state()

    if not state.repository:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    document = await state.repository.get_by_id(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Criar request de regeneração
    request = DocumentGenerationRequest(
        type=document.type,
        title=document.title,
        period_start=document.period_start,
        period_end=document.period_end,
        format=document.format,
        include_plots=True,
        plot_format="png",
        metadata=document.metadata,
    )

    # Resetar status
    await state.repository.update_status(doc_id, DocumentStatus.PENDING)

    # Adicionar task
    background_tasks.add_task(generate_document_task, doc_id, request, state)

    return DocumentGenerationResponse(
        document_id=doc_id,
        status=DocumentStatus.PENDING,
        message="Documento em regeração",
    )
