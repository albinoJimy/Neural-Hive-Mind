"""Cliente para interagir com a API do GitHub."""

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import settings


class WorkflowDispatchRequest(BaseModel):
    """Requisição para disparar um workflow do GitHub."""

    model_config = ConfigDict(extra="forbid")

    owner: str = Field(..., description="Proprietário do repositório")
    repo: str = Field(..., description="Nome do repositório")
    workflow_id: str = Field(..., description="ID ou nome do arquivo do workflow")
    branch: str = Field(default="main", description="Branch para executar")
    inputs: dict[str, str | int | bool] = Field(
        default_factory=dict, description="Inputs do workflow"
    )


class WorkflowDispatchResponse(BaseModel):
    """Resposta do disparo de workflow."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    workflow_run_id: int | None = None
    status_url: str | None = None
    message: str


class GitHubFile(BaseModel):
    """Arquivo no GitHub."""

    model_config = ConfigDict(extra="forbid")

    path: str
    content: str
    sha: str | None = None


class GitHubClient:
    """Cliente para interagir com a API do GitHub."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        """
        Inicializa o cliente do GitHub.

        Args:
            token: Token de autenticação do GitHub (PAT ou App token)
            base_url: URL base da API do GitHub
        """
        self.token = token or settings.github_token
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP, criando se necessário."""
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def trigger_workflow(
        self, request: WorkflowDispatchRequest
    ) -> WorkflowDispatchResponse:
        """
        Dispara um workflow do GitHub Actions.

        Args:
            request: Dados da requisição de disparo

        Returns:
            WorkflowDispatchResponse com o resultado
        """
        client = await self._get_client()

        url = (
            f"/repos/{request.owner}/{request.repo}"
            f"/actions/workflows/{request.workflow_id}/dispatches"
        )

        payload = {
            "ref": request.branch,
        }

        if request.inputs:
            payload["inputs"] = {
                k: str(v) if not isinstance(v, bool) else v
                for k, v in request.inputs.items()
            }

        response = await client.post(url, json=payload)

        if response.status_code == 204:
            # Buscar a run mais recente para obter o ID
            run_url = (
                f"/repos/{request.owner}/{request.repo}"
                f"/actions/runs?branch={request.branch}&per_page=1"
            )
            run_response = await client.get(run_url)

            if run_response.status_code == 200:
                data = run_response.json()
                if data.get("workflow_runs"):
                    run = data["workflow_runs"][0]
                    return WorkflowDispatchResponse(
                        success=True,
                        workflow_run_id=run.get("id"),
                        status_url=run.get("html_url"),
                        message="Workflow dispatched successfully",
                    )

            return WorkflowDispatchResponse(
                success=True,
                message="Workflow dispatched successfully",
            )

        error_msg = response.text
        try:
            error_data = response.json()
            error_msg = error_data.get("message", error_msg)
        except Exception:
            pass

        return WorkflowDispatchResponse(
            success=False,
            message=f"Failed to dispatch workflow: {error_msg}",
        )

    async def get_file(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> GitHubFile | None:
        """
        Obtém um arquivo do repositório.

        Args:
            owner: Proprietário do repositório
            repo: Nome do repositório
            path: Caminho do arquivo
            branch: Branch (default: main)

        Returns:
            GitHubFile se encontrado, None caso contrário
        """
        client = await self._get_client()

        url = f"/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": branch}

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            import base64

            content = base64.b64decode(data.get("content", "")).decode("utf-8")
            return GitHubFile(
                path=path,
                content=content,
                sha=data.get("sha"),
            )

        return None

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
        sha: str | None = None,
    ) -> bool:
        """
        Cria ou atualiza um arquivo no repositório.

        Args:
            owner: Proprietário do repositório
            repo: Nome do repositório
            path: Caminho do arquivo
            content: Conteúdo do arquivo
            message: Mensagem de commit
            branch: Branch (default: main)
            sha: SHA do arquivo para atualização (None para criação)

        Returns:
            True se bem-sucedido, False caso contrário
        """
        client = await self._get_client()

        import base64

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        url = f"/repos/{owner}/{repo}/contents/{path}"

        payload = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }

        if sha:
            payload["sha"] = sha

        response = await client.put(url, json=payload)

        return response.status_code in (200, 201)

    async def get_workflow_run_status(
        self, owner: str, repo: str, run_id: int
    ) -> dict[str, str | bool] | None:
        """
        Obtém o status de uma execução de workflow.

        Args:
            owner: Proprietário do repositório
            repo: Nome do repositório
            run_id: ID da execução

        Returns:
            Dict com status, conclusão e URL se encontrado
        """
        client = await self._get_client()

        url = f"/repos/{owner}/{repo}/actions/runs/{run_id}"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            return {
                "status": data.get("status"),
                "conclusion": data.get("conclusion"),
                "url": data.get("html_url"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            }

        return None

    async def list_workflows(self, owner: str, repo: str) -> list[dict[str, str | int]]:
        """
        Lista os workflows do repositório.

        Args:
            owner: Proprietário do repositório
            repo: Nome do repositório

        Returns:
            Lista de workflows com id, name, path, state
        """
        client = await self._get_client()

        url = f"/repos/{owner}/{repo}/actions/workflows"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            return [
                {
                    "id": w.get("id"),
                    "name": w.get("name"),
                    "path": w.get("path"),
                    "state": w.get("state"),
                }
                for w in data.get("workflows", [])
            ]

        return []

    async def get_repo_info(self, owner: str, repo: str) -> dict | None:
        """
        Obtém informações sobre um repositório.

        Args:
            owner: Proprietário do repositório
            repo: Nome do repositório

        Returns:
            Dict com informações do repositório
        """
        client = await self._get_client()

        url = f"/repos/{owner}/{repo}"

        response = await client.get(url)

        if response.status_code == 200:
            return response.json()

        return None
