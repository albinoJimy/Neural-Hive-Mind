"""Cliente para interagir com a API do GitLab."""

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import settings


class PipelineTriggerRequest(BaseModel):
    """Requisição para disparar um pipeline do GitLab."""

    model_config = ConfigDict(extra="forbid")

    project_id: int | str = Field(..., description="ID ou path do projeto")
    ref: str = Field(default="main", description="Branch ou tag")
    variables: dict[str, str] = Field(default_factory=dict, description="Variáveis do pipeline")


class PipelineTriggerResponse(BaseModel):
    """Resposta do disparo de pipeline."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    pipeline_id: int | None = None
    web_url: str | None = None
    status: str | None = None
    message: str


class GitLabClient:
    """Cliente para interagir com a API do GitLab."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """
        Inicializa o cliente do GitLab.

        Args:
            token: Token de acesso pessoal do GitLab
            base_url: URL base da API do GitLab
        """
        self.token = token or settings.gitlab_token
        self.base_url = (base_url or settings.gitlab_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP, criando se necessário."""
        if self._client is None:
            headers = {}
            if self.token:
                headers["PRIVATE-TOKEN"] = self.token

            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/api/v4",
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def trigger_pipeline(self, request: PipelineTriggerRequest) -> PipelineTriggerResponse:
        """
        Dispara um pipeline do GitLab CI.

        Args:
            request: Dados da requisição de disparo

        Returns:
            PipelineTriggerResponse com o resultado
        """
        client = await self._get_client()

        url = f"/projects/{request.project_id}/pipeline"

        payload = {"ref": request.ref}

        if request.variables:
            payload["variables"] = [{"key": k, "value": v} for k, v in request.variables.items()]

        response = await client.post(url, json=payload)

        if response.status_code == 201:
            data = response.json()
            return PipelineTriggerResponse(
                success=True,
                pipeline_id=data.get("id"),
                web_url=data.get("web_url"),
                status=data.get("status"),
                message="Pipeline triggered successfully",
            )

        error_msg = response.text
        try:
            error_data = response.json()
            error_msg = error_data.get("message", error_msg)
        except Exception:
            pass

        return PipelineTriggerResponse(
            success=False,
            message=f"Failed to trigger pipeline: {error_msg}",
        )

    async def get_pipeline_status(
        self, project_id: int | str, pipeline_id: int
    ) -> dict[str, str | bool] | None:
        """
        Obtém o status de um pipeline.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            Dict com status, estágio e URL se encontrado
        """
        client = await self._get_client()

        url = f"/projects/{project_id}/pipelines/{pipeline_id}"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            return {
                "id": data.get("id"),
                "status": data.get("status"),
                "stage": data.get("stage"),
                "web_url": data.get("web_url"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "finished_at": data.get("finished_at"),
            }

        return None

    async def list_pipelines(
        self,
        project_id: int | str,
        ref: str | None = None,
        status: str | None = None,
        per_page: int = 20,
    ) -> list[dict[str, str | int]]:
        """
        Lista os pipelines de um projeto.

        Args:
            project_id: ID ou path do projeto
            ref: Filtrar por branch/tag
            status: Filtrar por status
            per_page: Itens por página

        Returns:
            Lista de pipelines
        """
        client = await self._get_client()

        url = f"/projects/{project_id}/pipelines"

        params = {"per_page": per_page}
        if ref:
            params["ref"] = ref
        if status:
            params["status"] = status

        response = await client.get(url, params=params)

        if response.status_code == 200:
            return response.json()

        return []

    async def get_pipeline_jobs(
        self, project_id: int | str, pipeline_id: int
    ) -> list[dict[str, str | int]]:
        """
        Obtém os jobs de um pipeline.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            Lista de jobs
        """
        client = await self._get_client()

        url = f"/projects/{project_id}/pipelines/{pipeline_id}/jobs"

        response = await client.get(url)

        if response.status_code == 200:
            return response.json()

        return []

    async def retry_pipeline_job(self, project_id: int | str, job_id: int) -> dict | None:
        """
        Retenta um job de pipeline.

        Args:
            project_id: ID ou path do projeto
            job_id: ID do job

        Returns:
            Dict com o job retornado
        """
        client = await self._get_client()

        url = f"/projects/{project_id}/jobs/{job_id}/retry"

        response = await client.post(url)

        if response.status_code == 201:
            return response.json()

        return None

    async def get_project_info(self, project_id: int | str) -> dict | None:
        """
        Obtém informações sobre um projeto.

        Args:
            project_id: ID ou path do projeto

        Returns:
            Dict com informações do projeto
        """
        client = await self._get_client()

        url = f"/projects/{project_id}"

        response = await client.get(url)

        if response.status_code == 200:
            return response.json()

        return None

    async def get_file(
        self,
        project_id: int | str,
        file_path: str,
        ref: str = "main",
    ) -> dict[str, str] | None:
        """
        Obtém um arquivo do repositório.

        Args:
            project_id: ID ou path do projeto
            file_path: Caminho do arquivo
            ref: Branch ou tag

        Returns:
            Dict com file_name, content, size, ref
        """
        client = await self._get_client()

        url = f"/projects/{project_id}/repository/files/{file_path}"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            import base64

            content = base64.b64decode(data.get("content", "")).decode("utf-8")
            return {
                "file_name": data.get("file_name"),
                "file_path": data.get("file_path"),
                "content": content,
                "size": data.get("size"),
                "ref": data.get("ref"),
                "sha": data.get("commit_id"),
            }

        return None

    async def create_file(
        self,
        project_id: int | str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str = "main",
    ) -> bool:
        """
        Cria um arquivo no repositório.

        Args:
            project_id: ID ou path do projeto
            file_path: Caminho do arquivo
            content: Conteúdo do arquivo
            commit_message: Mensagem de commit
            branch: Branch

        Returns:
            True se bem-sucedido
        """
        client = await self._get_client()

        import base64

        url = f"/projects/{project_id}/repository/files/{file_path}"

        payload = {
            "file_path": file_path,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "commit_message": commit_message,
            "branch": branch,
        }

        response = await client.post(url, json=payload)

        return response.status_code == 201

    async def update_file(
        self,
        project_id: int | str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str = "main",
    ) -> bool:
        """
        Atualiza um arquivo no repositório.

        Args:
            project_id: ID ou path do projeto
            file_path: Caminho do arquivo
            content: Conteúdo do arquivo
            commit_message: Mensagem de commit
            branch: Branch

        Returns:
            True se bem-sucedido
        """
        client = await self._get_client()

        import base64

        url = f"/projects/{project_id}/repository/files/{file_path}"

        payload = {
            "file_path": file_path,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "commit_message": commit_message,
            "branch": branch,
        }

        response = await client.put(url, json=payload)

        return response.status_code == 200

    async def list_branches(self, project_id: int | str) -> list[dict[str, str | bool]]:
        """
        Lista os branches de um projeto.

        Args:
            project_id: ID ou path do projeto

        Returns:
            Lista de branches com name, protected, default
        """
        client = await self._get_client()

        url = f"/projects/{project_id}/repository/branches"

        response = await client.get(url)

        if response.status_code == 200:
            return [
                {
                    "name": b.get("name"),
                    "protected": b.get("protected", False),
                    "default": b.get("default", False),
                    "web_url": b.get("web_url"),
                }
                for b in response.json()
            ]

        return []
