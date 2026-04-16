"""Router para endpoints de documentação."""

import structlog
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, status, Depends, Query, UploadFile, File

from src.models import (
    ReadmeRequest,
    APIDocsRequest,
    DocType,
    DocFormat,
    Document
)
from src.services.readme_generator import ReadmeGenerator
from src.services.diagram_generator import DiagramGenerator
from src.services.code_doc_generator import CodeDocGenerator
from src.repositories.documents_repository import DocumentsRepository

router = APIRouter(prefix="/docs", tags=["documentation"])
logger = structlog.get_logger(__name__)

# Singleton instances
_readme_generator = None
_diagram_generator = None
_code_doc_generator = None


def get_readme_generator() -> ReadmeGenerator:
    """Retorna instância singleton do ReadmeGenerator."""
    global _readme_generator
    if _readme_generator is None:
        _readme_generator = ReadmeGenerator()
    return _readme_generator


def get_diagram_generator() -> DiagramGenerator:
    """Retorna instância singleton do DiagramGenerator."""
    global _diagram_generator
    if _diagram_generator is None:
        _diagram_generator = DiagramGenerator()
    return _diagram_generator


def get_code_doc_generator() -> CodeDocGenerator:
    """Retorna instância singleton do CodeDocGenerator."""
    global _code_doc_generator
    if _code_doc_generator is None:
        _code_doc_generator = CodeDocGenerator()
    return _code_doc_generator


def get_repository() -> DocumentsRepository:
    """Retorna instância do repositório."""
    return DocumentsRepository()


@router.post("/readme", status_code=status.HTTP_200_OK)
async def generate_readme(
    request: ReadmeRequest,
    repository: DocumentsRepository = Depends(get_repository)
):
    """Gera documentação README."""
    try:
        generator = get_readme_generator()
        document = await generator.generate(request)

        # Salvar no MongoDB
        await repository.save(document)

        return {
            "document_id": document.id,
            "doc_type": document.doc_type,
            "title": document.title,
            "content": document.content,
            "file_path": document.file_path
        }

    except Exception as e:
        logger.error("generate_readme_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/diagram", status_code=status.HTTP_200_OK)
async def generate_diagram(
    description: str = Query(..., description="Descrição do diagrama"),
    diagram_type: str = Query("sequence", description="Tipo: sequence, flowchart, er, class"),
    repository: DocumentsRepository = Depends(get_repository)
):
    """Gera diagrama Mermaid."""
    try:
        generator = get_diagram_generator()
        document = await generator.generate(
            description=description,
            diagram_type=diagram_type
        )

        # Salvar no MongoDB
        await repository.save(document)

        return {
            "document_id": document.id,
            "doc_type": document.doc_type,
            "title": document.title,
            "content": document.content,
            "format": document.format
        }

    except Exception as e:
        logger.error("generate_diagram_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/api-docs", status_code=status.HTTP_200_OK)
async def generate_api_docs(request: APIDocsRequest):
    """Gera documentação de API."""
    try:
        # Gerar documentação de API estruturada
        doc_content = f"""# {request.service_name} API Documentation

## Base URL
{request.base_url}

## Description
{request.description or "API service for Neural Hive-Mind"}

## Endpoints

"""

        for endpoint in request.endpoints:
            method = endpoint.get("method", "GET")
            path = endpoint.get("path", "/")
            summary = endpoint.get("summary", "")
            description = endpoint.get("description", "")
            params = endpoint.get("parameters", [])
            responses = endpoint.get("responses", {})

            doc_content += f"\n### {method} {path}\n\n"
            doc_content += f"**{summary}**\n\n" if summary else ""
            doc_content += f"{description}\n\n" if description else ""

            if params:
                doc_content += "**Parameters:**\n\n"
                for param in params:
                    param_name = param.get("name", "")
                    param_type = param.get("type", "string")
                    param_desc = param.get("description", "")
                    doc_content += f"- `{param_name}` ({param_type}): {param_desc}\n"
                doc_content += "\n"

            if responses:
                doc_content += "**Responses:**\n\n"
                for status_code, response_desc in responses.items():
                    doc_content += f"- `{status_code}`: {response_desc}\n"
                doc_content += "\n"

        document = Document(
            id=f"DOC-API-{request.service_name.lower().replace(' ', '-')}",
            doc_type=DocType.API_DOCS,
            format=DocFormat.MARKDOWN,
            title=f"{request.service_name} API Documentation",
            content=doc_content,
            file_path="API.md"
        )

        repository = get_repository()
        await repository.save(document)

        return {
            "document_id": document.id,
            "doc_type": document.doc_type,
            "title": document.title,
            "content": document.content,
            "file_path": document.file_path
        }

    except Exception as e:
        logger.error("generate_api_docs_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/code", status_code=status.HTTP_200_OK)
async def generate_code_docs(
    code: str = Query(..., description="Código fonte"),
    file_path: str = Query(..., description="Caminho do arquivo"),
    language: str = Query("python", description="Linguagem de programação"),
    repository: DocumentsRepository = Depends(get_repository)
):
    """Gera documentação a partir de código fonte."""
    try:
        generator = get_code_doc_generator()
        document = await generator.generate_from_code(
            code=code,
            file_path=file_path,
            language=language
        )

        # Salvar no MongoDB
        await repository.save(document)

        return {
            "document_id": document.id,
            "doc_type": document.doc_type,
            "title": document.title,
            "content": document.content,
            "metadata": document.metadata
        }

    except Exception as e:
        logger.error("generate_code_docs_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/project", status_code=status.HTTP_200_OK)
async def generate_project_docs(
    files: List[Dict[str, str]],
    project_name: str = Query(..., description="Nome do projeto"),
    repository: DocumentsRepository = Depends(get_repository)
):
    """Gera documentação completa para um projeto."""
    try:
        generator = get_code_doc_generator()
        document = await generator.generate_for_project(
            files=files,
            project_name=project_name
        )

        # Salvar no MongoDB
        await repository.save(document)

        return {
            "document_id": document.id,
            "doc_type": document.doc_type,
            "title": document.title,
            "content": document.content,
            "file_path": document.file_path,
            "metadata": document.metadata
        }

    except Exception as e:
        logger.error("generate_project_docs_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", status_code=status.HTTP_200_OK)
async def list_documents(
    doc_type: Optional[str] = Query(None, description="Filtro por tipo de documento"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    repository: DocumentsRepository = Depends(get_repository)
):
    """Lista documentos gerados."""
    try:
        documents, total = await repository.list(
            doc_type=doc_type,
            limit=limit,
            skip=skip
        )

        return {
            "total": total,
            "items": documents,
            "filters": {"doc_type": doc_type}
        }

    except Exception as e:
        logger.error("list_documents_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{document_id}", status_code=status.HTTP_200_OK)
async def get_document(
    document_id: str,
    repository: DocumentsRepository = Depends(get_repository)
):
    """Obtém documento por ID."""
    try:
        document = await repository.get_by_id(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_document_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: str,
    repository: DocumentsRepository = Depends(get_repository)
):
    """Deleta um documento."""
    try:
        deleted = await repository.delete(document_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )

        return {"message": f"Document {document_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_document_error", id=document_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/search/{query}", status_code=status.HTTP_200_OK)
async def search_documents(
    query: str,
    limit: int = Query(20, ge=1, le=100),
    repository: DocumentsRepository = Depends(get_repository)
):
    """Busca documentos por texto."""
    try:
        documents = await repository.search(query, limit)

        return {
            "query": query,
            "total": len(documents),
            "results": documents
        }

    except Exception as e:
        logger.error("search_documents_error", query=query, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
