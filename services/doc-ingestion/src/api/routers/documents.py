"""Router para manipulação de documentos."""

import hashlib
import uuid
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from src.clients.s3_client import get_s3_client
from src.dependencies import get_doc_producer
from src.models.document import (
    Document,
    DocumentFormat,
    DocumentList,
    DocumentStatus,
)
from src.repositories.document_repository import DocumentRepository

router = APIRouter(prefix="/documents", tags=["documents"])
logger = structlog.get_logger(__name__)


def get_repository() -> DocumentRepository:
    """Retorna instância do repositório."""
    return DocumentRepository()


def get_file_extension(filename: str) -> str:
    """Extrai extensão do arquivo.

    Args:
        filename: Nome do arquivo.

    Returns:
        Extensão do arquivo com ponto.
    """
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def detect_document_format(filename: str, extension: str) -> DocumentFormat:
    """Detecta formato do documento baseado no nome/extensão.

    Args:
        filename: Nome do arquivo.
        extension: Extensão do arquivo.

    Returns:
        DocumentFormat detectado.

    Raises:
        HTTPException: Se formato não suportado.
    """
    ext_lower = extension.lower()
    filename_lower = filename.lower()

    if ext_lower in [".pdf"]:
        return DocumentFormat.PDF
    elif ext_lower in [".docx", ".doc"]:
        return DocumentFormat.DOCX
    elif ext_lower in [".vsd", ".vsdx"]:
        if filename_lower.endswith(".vsdx"):
            return DocumentFormat.VSDX
        return DocumentFormat.VSD
    elif ext_lower in [".json"]:
        # Postman collections são JSON
        if "postman" in filename_lower:
            return DocumentFormat.POSTMAN
        # Tentar detectar pelo conteúdo depois
        return DocumentFormat.POSTMAN
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {extension}. Supported: PDF, DOCX, VSD, VSDX, Postman JSON",
        )


async def calculate_checksum(content: bytes) -> str:
    """Calcula checksum SHA256 do conteúdo.

    Args:
        content: Conteúdo do arquivo.

    Returns:
        Checksum em hexadecimal.
    """
    return hashlib.sha256(content).hexdigest()


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(..., description="Arquivo do documento"),
    title: Optional[str] = Form(None, description="Título do documento"),
    description: Optional[str] = Form(None, description="Descrição do documento"),
    project_id: Optional[str] = Form(None, description="ID do projeto"),
    tags: Optional[str] = Form(None, description="Tags separadas por vírgula"),
    uploaded_by: str = Form(..., description="Usuário que está fazendo upload"),
    repository: DocumentRepository = Depends(get_repository),
):
    """Upload de novo documento para processamento.

    Args:
        file: Arquivo para upload.
        title: Título opcional do documento.
        description: Descrição opcional do documento.
        project_id: ID do projeto relacionado.
        tags: Tags separadas por vírgula.
        uploaded_by: Usuário que está fazendo upload (obrigatório).
        repository: Instância do repositório (injetado).

    Returns:
        Documento criado com metadados.
    """
    try:
        # Ler conteúdo do arquivo
        content = await file.read()
        file_size = len(content)

        # Validar tamanho do arquivo
        from src.config.settings import get_settings
        settings = get_settings()
        max_size = settings.max_file_size_mb * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {settings.max_file_size_mb}MB",
            )

        # Detectar formato
        extension = get_file_extension(file.filename)
        doc_format = detect_document_format(file.filename, extension)

        # Calcular checksum
        checksum = await calculate_checksum(content)

        # Gerar ingestion_id (UUID para agrupar arquivos da mesma ingestão)
        ingestion_id = str(uuid.uuid4())

        # Upload para S3
        s3_client = await get_s3_client()
        s3_key = await s3_client.upload_file(
            ingestion_id=ingestion_id,
            filename=file.filename,
            content=content,
            metadata={
                "original_filename": file.filename,
                "content_type": file.content_type or "application/octet-stream",
                "checksum": checksum,
                "uploaded_by": uploaded_by,
            },
        )

        # Parse tags
        tags_list = []
        if tags:
            tags_list = [t.strip() for t in tags.split(",") if t.strip()]

        # Criar registro no banco
        from src.models.document import DocumentCreate
        document_create = DocumentCreate(
            filename=file.filename,
            format=doc_format,
            file_size_bytes=file_size,
            s3_key=s3_key,
            uploaded_by=uploaded_by,
            title=title,
            description=description,
            project_id=project_id,
            tags=tags_list,
            metadata={
                "checksum": checksum,
                "ingestion_id": ingestion_id,
                "content_type": file.content_type,
            },
        )

        document = await repository.create(document_create)

        # Publicar evento Kafka
        producer = get_doc_producer()
        if producer:
            try:
                await producer.publish_doc_uploaded(
                    document_id=document.id,
                    filename=document.filename,
                    format_type=document.format.value,
                    file_size_bytes=document.file_size_bytes,
                    uploaded_by=document.uploaded_by,
                    s3_key=document.s3_key,
                    project_id=document.project_id,
                )
            except Exception as e:
                logger.warning("failed_to_publish_upload_event", error=str(e))

        logger.info(
            "document_uploaded",
            document_id=document.id,
            filename=file.filename,
            size_bytes=file_size,
            format=doc_format,
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "id": document.id,
                "filename": document.filename,
                "format": document.format.value,
                "status": document.status.value,
                "file_size_bytes": document.file_size_bytes,
                "uploaded_by": document.uploaded_by,
                "title": document.title,
                "description": document.description,
                "project_id": document.project_id,
                "tags": document.tags,
                "created_at": document.created_at.isoformat(),
                "checksum": checksum,
                "s3_key": s3_key,
                "message": "Document uploaded successfully",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("upload_document_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}",
        )


@router.get("", response_model=DocumentList)
async def list_documents(
    status_filter: Optional[DocumentStatus] = Query(None, alias="status"),
    format_filter: Optional[str] = Query(None, alias="format"),
    project_id: Optional[str] = Query(None, alias="project_id"),
    uploaded_by: Optional[str] = Query(None, alias="uploaded_by"),
    tags: Optional[str] = Query(None, alias="tags"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    repository: DocumentRepository = Depends(get_repository),
):
    """Listar todos os documentos processados com filtros.

    Args:
        status_filter: Filtrar por status do documento.
        format_filter: Filtrar por formato do documento.
        project_id: Filtrar por ID do projeto.
        uploaded_by: Filtrar por usuário que fez upload.
        tags: Filtrar por tags (separadas por vírgula, qualquer uma).
        limit: Limite de resultados.
        skip: Quantidade de resultados a pular.
        repository: Instância do repositório (injetado).

    Returns:
        Lista de documentos com contagem total.
    """
    try:
        tags_list = None
        if tags:
            tags_list = [t.strip() for t in tags.split(",") if t.strip()]

        documents, total = await repository.list(
            status_filter=status_filter,
            format_filter=format_filter,
            project_id=project_id,
            uploaded_by=uploaded_by,
            tags=tags_list,
            limit=limit,
            skip=skip,
        )

        return DocumentList(
            total=total,
            items=documents,
            filters={
                "status": status_filter.value if status_filter else None,
                "format": format_filter,
                "project_id": project_id,
                "uploaded_by": uploaded_by,
                "tags": tags_list,
            },
        )

    except Exception as e:
        logger.error("list_documents_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    repository: DocumentRepository = Depends(get_repository),
):
    """Obter detalhes de um documento.

    Args:
        document_id: ID do documento.
        repository: Instância do repositório (injetado).

    Returns:
        Detalhes do documento.
    """
    try:
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        return {
            "id": document.id,
            "filename": document.filename,
            "format": document.format.value,
            "status": document.status.value,
            "file_size_bytes": document.file_size_bytes,
            "s3_key": document.s3_key,
            "uploaded_by": document.uploaded_by,
            "title": document.title,
            "description": document.description,
            "project_id": document.project_id,
            "tags": document.tags,
            "metadata": document.metadata,
            "parsed_text": document.parsed_text,
            "entity_count": document.entity_count,
            "extracted_entity_types": document.extracted_entity_types,
            "parsing_error": document.parsing_error,
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
            "parsed_at": document.parsed_at.isoformat() if document.parsed_at else None,
            "extracted_at": document.extracted_at.isoformat() if document.extracted_at else None,
            "version": document.version,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_document_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    repository: DocumentRepository = Depends(get_repository),
):
    """Obter status de processamento de um documento.

    Args:
        document_id: ID do documento.
        repository: Instância do repositório (injetado).

    Returns:
        Status atual do documento.
    """
    try:
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        return {
            "id": document.id,
            "filename": document.filename,
            "status": document.status.value,
            "parsing_error": document.parsing_error,
            "entity_count": document.entity_count,
            "created_at": document.created_at.isoformat(),
            "parsed_at": document.parsed_at.isoformat() if document.parsed_at else None,
            "extracted_at": document.extracted_at.isoformat() if document.extracted_at else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_document_status_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    repository: DocumentRepository = Depends(get_repository),
):
    """Deleta um documento.

    Args:
        document_id: ID do documento.
        repository: Instância do repositório (injetado).
    """
    try:
        deleted = await repository.delete(document_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        logger.info("document_deleted", id=document_id)

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_document_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
