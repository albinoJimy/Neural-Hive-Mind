"""Router para operações de parsing e extração de entidades."""

import time
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from src.clients.s3_client import get_s3_client
from src.dependencies import get_doc_producer
from src.models.document import DocumentStatus
from src.repositories.document_repository import DocumentRepository
from src.services.entity_extractor import EntityExtractor
from src.services.parsers.pdf_parser import PDFParser
from src.services.parsers.postman_parser import PostmanParser
from src.services.parsers.visio_parser import VisioParser
from src.services.parsers.word_parser import WordParser

router = APIRouter(prefix="/documents", tags=["parsing"])
logger = structlog.get_logger(__name__)


def get_repository() -> DocumentRepository:
    """Retorna instância do repositório."""
    return DocumentRepository()


async def get_parser_for_format(format_type: str):
    """Retorna parser apropriado para o formato.

    Args:
        format_type: Formato do documento.

    Returns:
        Instância do parser apropriado.
    """
    parsers = {
        "pdf": PDFParser(),
        "docx": WordParser(),
        "vsd": VisioParser(),
        "vsdx": VisioParser(),
        "postman": PostmanParser(),
    }

    parser = parsers.get(format_type.lower())
    if not parser:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No parser available for format: {format_type}",
        )

    return parser


@router.post("/{document_id}/parse", status_code=status.HTTP_202_ACCEPTED)
async def parse_document(
    document_id: str,
    repository: DocumentRepository = Depends(get_repository),
):
    """Iniciar parsing de documento já carregado.

    Args:
        document_id: ID do documento.
        repository: Instância do repositório (injetado).

    Returns:
        Job ID para acompanhamento do parsing.
    """
    job_id = str(uuid.uuid4())

    try:
        # Buscar documento
        document = await repository.get_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        # Atualizar status para parsing
        await repository.update_status(document_id, DocumentStatus.PARSING)

        # Download do arquivo do S3
        s3_client = await get_s3_client()
        file_content = await s3_client.download_file(document.s3_key)

        logger.info(
            "parsing_started",
            document_id=document_id,
            job_id=job_id,
            format=document.format.value,
        )

        start_time = time.time()
        parsing_error = None
        parsed_text = None

        try:
            # Obter parser para o formato
            parser = await get_parser_for_format(document.format.value)

            # Parse do documento
            parsed_text = await parser.parse(file_content)

            # Atualizar com conteúdo parseado
            await repository.update_parsed_content(document_id, parsed_text)

            logger.info(
                "parsing_completed",
                document_id=document_id,
                job_id=job_id,
                text_length=len(parsed_text) if parsed_text else 0,
            )

        except Exception as e:
            parsing_error = str(e)
            logger.error(
                "parsing_failed",
                document_id=document_id,
                job_id=job_id,
                error=parsing_error,
            )
            await repository.update_status(
                document_id, DocumentStatus.FAILED, error=parsing_error
            )

        duration_ms = int((time.time() - start_time) * 1000)

        # Publicar evento Kafka
        producer = get_doc_producer()
        if producer:
            try:
                await producer.publish_doc_parsed(
                    document_id=document_id,
                    parsed_text_length=len(parsed_text) if parsed_text else 0,
                    parsing_duration_ms=duration_ms,
                    has_error=parsing_error is not None,
                    error_message=parsing_error,
                )
            except Exception as e:
                logger.warning("failed_to_publish_parsed_event", error=str(e))

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "job_id": job_id,
                "document_id": document_id,
                "status": "completed" if not parsing_error else "failed",
                "parsed_text_length": len(parsed_text) if parsed_text else 0,
                "duration_ms": duration_ms,
                "error": parsing_error,
                "message": "Document parsing completed"
                if not parsing_error
                else "Document parsing failed",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("parse_document_error", id=document_id, error=str(e), exc_info=True)
        await repository.update_status(document_id, DocumentStatus.FAILED, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse document: {str(e)}",
        )


@router.post("/{document_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract_entities(
    document_id: str,
    min_confidence: float = Query(0.7, ge=0.0, le=1.0, description="Confiança mínima"),
    repository: DocumentRepository = Depends(get_repository),
):
    """Extrair entidades de documento já parseado.

    Args:
        document_id: ID do documento.
        min_confidence: Confiança mínima para entidades (0.0 a 1.0).
        repository: Instância do repositório (injetado).

    Returns:
        Resultado da extração.
    """
    job_id = str(uuid.uuid4())

    try:
        # Buscar documento
        document = await repository.get_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        # Verificar se documento foi parseado
        if not document.parsed_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document must be parsed before entity extraction. Call /parse first.",
            )

        # Atualizar status para extraction
        await repository.update_status(document_id, DocumentStatus.EXTRACTION)

        logger.info(
            "entity_extraction_started",
            document_id=document_id,
            job_id=job_id,
            text_length=len(document.parsed_text),
        )

        start_time = time.time()

        try:
            # Extrair entidades usando LLM
            extractor = EntityExtractor(min_confidence=min_confidence)
            entities = await extractor.extract(
                document_id=document_id,
                text=document.parsed_text,
                context={
                    "filename": document.filename,
                    "format": document.format.value,
                    "title": document.title,
                },
            )

            # Calcular tipos extraídos
            entity_types_set = {e.type.value for e in entities}
            entity_types_list = list(entity_types_set)

            # Atualizar documento com resultados
            await repository.update_extraction_results(
                document_id=document_id,
                entity_count=len(entities),
                extracted_entity_types=entity_types_list,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Publicar evento Kafka
            producer = get_doc_producer()
            if producer:
                try:
                    await producer.publish_doc_entities_extracted(
                        document_id=document_id,
                        entity_count=len(entities),
                        entity_types=entity_types_list,
                        extraction_duration_ms=duration_ms,
                    )
                except Exception as e:
                    logger.warning("failed_to_publish_entities_event", error=str(e))

            logger.info(
                "entity_extraction_completed",
                document_id=document_id,
                job_id=job_id,
                entity_count=len(entities),
                entity_types=entity_types_list,
            )

            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "job_id": job_id,
                    "document_id": document_id,
                    "entity_count": len(entities),
                    "entity_types": entity_types_list,
                    "duration_ms": duration_ms,
                    "entities": [e.model_dump() for e in entities],
                    "message": "Entity extraction completed",
                },
            )

        except Exception as e:
            logger.error(
                "entity_extraction_failed",
                document_id=document_id,
                job_id=job_id,
                error=str(e),
            )
            await repository.update_status(
                document_id, DocumentStatus.PARSED, error=f"Extraction failed: {str(e)}"
            )
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error("extract_entities_error", id=document_id, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract entities: {str(e)}",
        )


@router.get("/jobs/{job_id}")
async def get_parsing_job(job_id: str):
    """Obter status de job de parsing.

    Args:
        job_id: ID do job de parsing.

    Returns:
        Status do job.
    """
    # Em uma implementação real, buscaríamos o job em um banco de dados
    # Por enquanto, retornamos um placeholder
    return {
        "job_id": job_id,
        "status": "completed",
        "message": "Job status tracking not yet implemented",
    }


@router.get("/{document_id}/entities")
async def list_document_entities(
    document_id: str,
    entity_type: Optional[str] = Query(None, description="Filtrar por tipo de entidade"),
    repository: DocumentRepository = Depends(get_repository),
):
    """Listar entidades extraídas de um documento.

    Args:
        document_id: ID do documento.
        entity_type: Filtro por tipo de entidade.
        repository: Instância do repositório (injetado).

    Returns:
        Lista de entidades extraídas.
    """
    try:
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        if document.status != DocumentStatus.EXTRACTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document entities not extracted yet. Current status: {document.status.value}",
            )

        # Em uma implementação real, buscaríamos as entidades da coleção entities
        # Por enquanto, retornamos informações do documento
        return {
            "document_id": document_id,
            "entity_count": document.entity_count,
            "extracted_entity_types": document.extracted_entity_types,
            "extracted_at": document.extracted_at.isoformat()
            if document.extracted_at
            else None,
            "message": "Entity details not yet persisted",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_entities_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/{document_id}/approve")
async def approve_document(
    document_id: str,
    approved_by: str = Query(..., description="Usuário que está aprovando"),
    notes: Optional[str] = Query(None, description="Notas da aprovação"),
    repository: DocumentRepository = Depends(get_repository),
):
    """Aprovar documento processado.

    Args:
        document_id: ID do documento.
        approved_by: Usuário que está aprovando.
        notes: Notas da aprovação.
        repository: Instância do repositório (injetado).

    Returns:
        Confirmação da aprovação.
    """
    try:
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        if document.status not in [DocumentStatus.PARSED, DocumentStatus.EXTRACTED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document must be parsed or extracted before approval. Current status: {document.status.value}",
            )

        # Atualizar status para approved
        await repository.update_status(document_id, DocumentStatus.APPROVED)

        # Publicar evento Kafka
        producer = get_doc_producer()
        if producer:
            try:
                await producer.publish_doc_approved(
                    document_id=document_id,
                    approved_by=approved_by,
                    approval_notes=notes,
                )
            except Exception as e:
                logger.warning("failed_to_publish_approved_event", error=str(e))

        logger.info(
            "document_approved",
            document_id=document_id,
            approved_by=approved_by,
        )

        # Buscar documento atualizado para retornar o updated_at
        updated_doc = await repository.get_by_id(document_id)

        return {
            "document_id": document_id,
            "status": DocumentStatus.APPROVED.value,
            "approved_by": approved_by,
            "approved_at": updated_doc.updated_at.isoformat()
            if updated_doc and updated_doc.updated_at
            else None,
            "message": "Document approved successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("approve_document_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
