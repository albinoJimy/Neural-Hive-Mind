"""Router para manipulação de documentos."""

from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document():
    """Upload de novo documento para processamento."""
    # TODO: Implementar upload de documento
    return {"status": "pending", "message": "Endpoint em desenvolvimento"}


@router.get("/{document_id}")
async def get_document(document_id: str):
    """Obter detalhes de um documento."""
    # TODO: Implementar busca de documento
    return {"document_id": document_id, "status": "pending"}


@router.get("/")
async def list_documents():
    """Listar todos os documentos processados."""
    # TODO: Implementar listagem de documentos
    return {"documents": [], "status": "pending"}
