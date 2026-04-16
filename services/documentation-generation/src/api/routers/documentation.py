"""Router para endpoints de documentação."""

from fastapi import APIRouter, HTTPException, status

from src.models import ReadmeRequest, APIDocsRequest, DocType
from src.services.readme_generator import ReadmeGenerator
from src.services.diagram_generator import DiagramGenerator

router = APIRouter(prefix="/docs", tags=["documentation"])

# Singleton instances
_readme_generator = None
_diagram_generator = None


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


@router.post("/readme", status_code=status.HTTP_200_OK)
async def generate_readme(request: ReadmeRequest):
    """Gera documentação README."""
    try:
        generator = get_readme_generator()
        document = await generator.generate(request)

        return {
            "document_id": document.id,
            "doc_type": document.doc_type,
            "title": document.title,
            "content": document.content,
            "file_path": document.file_path
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/diagram", status_code=status.HTTP_200_OK)
async def generate_diagram(
    description: str,
    diagram_type: str = "sequence"
):
    """Gera diagrama Mermaid."""
    try:
        generator = get_diagram_generator()
        document = await generator.generate(
            description=description,
            diagram_type=diagram_type
        )

        return {
            "document_id": document.id,
            "doc_type": document.doc_type,
            "title": document.title,
            "content": document.content,
            "format": document.format
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/api-docs", status_code=status.HTTP_200_OK)
async def generate_api_docs(request: APIDocsRequest):
    """Gera documentação de API."""
    try:
        # Simular geração de documentação de API
        # Em produção, usaria LLM para gerar documentação mais detalhada

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
            doc_content += f"\n### {method} {path}\n\n{summary}\n\n"

        return {
            "document_id": f"DOC-API-{request.service_name.lower()}",
            "doc_type": "api_docs",
            "title": f"{request.service_name} API Documentation",
            "content": doc_content,
            "file_path": "API.md"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/health")
async def health_check():
    """Health check do serviço."""
    return {"status": "healthy"}
