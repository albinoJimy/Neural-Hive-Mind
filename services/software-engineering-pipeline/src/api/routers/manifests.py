"""Router para manifests de pipeline."""

from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from src.models.pipeline import PipelineManifest
from src.models.schemas import PipelineProvider
from src.repositories.pipeline_repository import PipelineManifestRepository

router = APIRouter(prefix="/manifests", tags=["manifests"])
repo = PipelineManifestRepository()


class CreateManifestRequest(BaseModel):
    """Request para criar manifesto."""

    model_config = ConfigDict(extra="forbid")

    repo_url: str = Field(..., description="URL do repositório")
    branch: str = Field(default="main", description="Branch")
    provider: PipelineProvider = Field(..., description="Provider de CI/CD")
    content: str = Field(..., description="Conteúdo YAML do pipeline")
    stack: dict[str, str] = Field(
        default_factory=dict, description="Informações da stack"
    )


class ManifestResponse(BaseModel):
    """Response de manifesto."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    repo_url: str
    branch: str
    provider: str
    content: str
    stack: dict[str, str]
    created_at: str | None = None


@router.post("", response_model=ManifestResponse, status_code=201)
async def create_manifest(request: CreateManifestRequest) -> ManifestResponse:
    """Cria um novo manifesto de pipeline."""
    manifest_id = str(uuid.uuid4())

    manifest = PipelineManifest(
        manifest_id=manifest_id,
        repo_url=request.repo_url,
        branch=request.branch,
        provider=request.provider,
        content=request.content,
        stack=request.stack,
    )

    await repo.create(manifest)

    return _manifest_to_response(manifest)


@router.get("/repositories/{repo_url:path}", response_model=ManifestResponse)
async def get_manifest(
    repo_url: str,
    branch: str = Query("main", description="Branch"),
) -> ManifestResponse:
    """Obtém o manifesto de um repositório."""
    full_repo_url = (
        f"https://{repo_url}" if not repo_url.startswith("http") else repo_url
    )

    manifest = await repo.find_by_repo(full_repo_url, branch)

    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manifest not found for {full_repo_url} on branch {branch}",
        )

    return _manifest_to_response_from_dict(manifest)


@router.delete("/{manifest_id}", status_code=204)
async def delete_manifest(manifest_id: str) -> None:
    """Deleta um manifesto."""
    deleted = await repo.delete(manifest_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manifest {manifest_id} not found",
        )


def _manifest_to_response(manifest: PipelineManifest) -> ManifestResponse:
    """Converte um PipelineManifest para ManifestResponse."""
    return ManifestResponse(
        manifest_id=manifest.manifest_id,
        repo_url=manifest.repo_url,
        branch=manifest.branch,
        provider=manifest.provider.value,
        content=manifest.content,
        stack=manifest.stack,
        created_at=manifest.created_at.isoformat(),
    )


def _manifest_to_response_from_dict(manifest: dict) -> ManifestResponse:
    """Converte um dict para ManifestResponse."""
    return ManifestResponse(
        manifest_id=manifest.get("_id", manifest.get("manifest_id", "")),
        repo_url=manifest.get("repo_url", ""),
        branch=manifest.get("branch", "main"),
        provider=manifest.get("provider", "unknown"),
        content=manifest.get("content", ""),
        stack=manifest.get("stack", {}),
        created_at=manifest.get("created_at"),
    )
