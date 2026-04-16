"""Router para operações de parsing e extração de entidades."""

from fastapi import APIRouter

router = APIRouter(prefix="/parsing", tags=["parsing"])


@router.post("/parse")
async def parse_document():
    """Iniciar parsing de documento já carregado."""
    # TODO: Implementar parse de documento
    return {"status": "pending", "message": "Endpoint em desenvolvimento"}


@router.get("/jobs/{job_id}")
async def get_parsing_job(job_id: str):
    """Obter status de job de parsing."""
    # TODO: Implementar busca de job
    return {"job_id": job_id, "status": "pending"}


@router.get("/entities")
async def list_entities():
    """Listar todas as entidades extraídas."""
    # TODO: Implementar listagem de entidades
    return {"entities": [], "status": "pending"}
