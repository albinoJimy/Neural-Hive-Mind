"""Cliente para interagir com a API do ArgoCD."""

from datetime import UTC

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import settings


class ApplicationSyncRequest(BaseModel):
    """Requisição para sincronizar uma aplicação ArgoCD."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Nome da aplicação")
    namespace: str = Field(default="argocd", description="Namespace da aplicação")
    revision: str | None = Field(None, description="Revision específica para sync")
    prune: bool = Field(default=False, description="Remover recursos que não existem no Git")
    dry_run: bool = Field(default=False, description="Simular sync sem aplicar")


class ApplicationSyncResponse(BaseModel):
    """Resposta do sync de aplicação."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    sync_started_at: str | None = None
    operation_id: str | None = None


class ApplicationRollbackRequest(BaseModel):
    """Requisição para rollback de aplicação."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Nome da aplicação")
    namespace: str = Field(default="argocd", description="Namespace da aplicação")
    revision: str = Field(..., description="Revision para rollback")
    dry_run: bool = Field(default=False, description="Simular rollback sem aplicar")


class ApplicationRollbackResponse(BaseModel):
    """Resposta do rollback."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    operation_id: str | None = None


class ArgoCDClient:
    """Cliente para interagir com a API do ArgoCD."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        namespace: str | None = None,
    ) -> None:
        """
        Inicializa o cliente do ArgoCD.

        Args:
            token: Token de autenticação do ArgoCD
            base_url: URL base da API do ArgoCD
            namespace: Namespace padrão para operações
        """
        self.token = token or settings.argocd_token
        self.base_url = (base_url or settings.argocd_url).rstrip("/")
        self.namespace = namespace or settings.argocd_namespace
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP, criando se necessário."""
        if self._client is None:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
                verify=False,  # ArgoCD frequentemente usa certificados self-signed
            )
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def sync_application(self, request: ApplicationSyncRequest) -> ApplicationSyncResponse:
        """
        Sincroniza uma aplicação ArgoCD.

        Args:
            request: Dados da requisição de sync

        Returns:
            ApplicationSyncResponse com o resultado
        """
        from datetime import datetime

        client = await self._get_client()

        url = f"/api/v1/applications/{request.name}/sync"

        payload = {}
        if request.revision:
            payload["revision"] = request.revision
        payload["prune"] = request.prune
        payload["dryRun"] = request.dry_run

        response = await client.post(url, json=payload)

        if response.status_code == 200:
            data = response.json()
            return ApplicationSyncResponse(
                success=True,
                message="Application sync started",
                sync_started_at=datetime.now(UTC).isoformat(),
                operation_id=data.get("uid"),
            )

        error_msg = response.text
        try:
            error_data = response.json()
            error_msg = error_data.get("message", error_msg)
        except Exception:
            pass

        return ApplicationSyncResponse(
            success=False,
            message=f"Failed to sync application: {error_msg}",
        )

    async def rollback_application(
        self, request: ApplicationRollbackRequest
    ) -> ApplicationRollbackResponse:
        """
        Realiza rollback de uma aplicação.

        Args:
            request: Dados da requisição de rollback

        Returns:
            ApplicationRollbackResponse com o resultado
        """
        client = await self._get_client()

        url = f"/api/v1/applications/{request.name}/rollback"

        payload = {
            "revision": request.revision,
            "dryRun": request.dry_run,
        }

        response = await client.post(url, json=payload)

        if response.status_code == 200:
            data = response.json()
            return ApplicationRollbackResponse(
                success=True,
                message="Rollback started",
                operation_id=data.get("uid"),
            )

        error_msg = response.text
        try:
            error_data = response.json()
            error_msg = error_data.get("message", error_msg)
        except Exception:
            pass

        return ApplicationRollbackResponse(
            success=False,
            message=f"Failed to rollback: {error_msg}",
        )

    async def get_application(self, name: str, namespace: str | None = None) -> dict | None:
        """
        Obtém informações de uma aplicação.

        Args:
            name: Nome da aplicação
            namespace: Namespace (usa default se não especificado)

        Returns:
            Dict com informações da aplicação
        """
        client = await self._get_client()

        ns = namespace or self.namespace
        url = f"/api/v1/applications/{name}?appNamespace={ns}"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            return {
                "name": data.get("name"),
                "namespace": data.get("spec", {}).get("destination", {}).get("namespace"),
                "project": data.get("spec", {}).get("project"),
                "sync_status": data.get("status", {}).get("sync", {}).get("status"),
                "health_status": data.get("status", {}).get("health", {}).get("status"),
                "revision": data.get("status", {}).get("sync", {}).get("revision"),
                "url": data.get("spec", {}).get("source", {}).get("repoURL"),
                "path": data.get("spec", {}).get("source", {}).get("path"),
                "operation": data.get("status", {}).get("operation"),
            }

        return None

    async def list_applications(
        self,
        project: str | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, str]]:
        """
        Lista as aplicações do ArgoCD.

        Args:
            project: Filtrar por projeto
            namespace: Filtrar por namespace

        Returns:
            Lista de aplicações com name, namespace, sync_status, health_status
        """
        client = await self._get_client()

        url = "/api/v1/applications"

        params = {}
        if project:
            params["project"] = project
        if namespace:
            params["appNamespace"] = namespace

        response = await client.get(url, params=params)

        if response.status_code == 200:
            data = response.json()
            return [
                {
                    "name": app.get("name"),
                    "namespace": app.get("spec", {}).get("destination", {}).get("namespace"),
                    "project": app.get("spec", {}).get("project"),
                    "sync_status": app.get("status", {}).get("sync", {}).get("status"),
                    "health_status": app.get("status", {}).get("health", {}).get("status"),
                    "synced_at": app.get("status", {}).get("sync", {}).get("startedAt"),
                }
                for app in data.get("items", [])
            ]

        return []

    async def get_application_health(
        self, name: str, namespace: str | None = None
    ) -> dict[str, str | bool] | None:
        """
        Obtém o status de saúde de uma aplicação.

        Args:
            name: Nome da aplicação
            namespace: Namespace

        Returns:
            Dict com status, healthy, message
        """
        client = await self._get_client()

        ns = namespace or self.namespace
        url = f"/api/v1/applications/{name}?appNamespace={ns}"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            health = data.get("status", {}).get("health", {})
            return {
                "status": health.get("status"),
                "healthy": health.get("status") == "Healthy",
                "message": health.get("message", ""),
            }

        return None

    async def get_application_sync_status(
        self, name: str, namespace: str | None = None
    ) -> dict[str, str | bool] | None:
        """
        Obtém o status de sync de uma aplicação.

        Args:
            name: Nome da aplicação
            namespace: Namespace

        Returns:
            Dict com status, synced, revision, compared_to
        """
        client = await self._get_client()

        ns = namespace or self.namespace
        url = f"/api/v1/applications/{name}?appNamespace={ns}"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            sync = data.get("status", {}).get("sync", {})
            return {
                "status": sync.get("status"),
                "synced": sync.get("status") == "Synced",
                "revision": sync.get("revision"),
                "compared_to": sync.get("comparedTo", {}).get("revision"),
            }

        return None

    async def get_application_operations(
        self, name: str, namespace: str | None = None
    ) -> list[dict[str, str | bool]]:
        """
        Obtém as operações de uma aplicação.

        Args:
            name: Nome da aplicação
            namespace: Namespace

        Returns:
            Lista de operações
        """
        app = await self.get_application(name, namespace)
        if not app:
            return []

        operation = app.get("operation")
        if not operation:
            return []

        return [
            {
                "type": operation.get("type"),
                "state": operation.get("state", "Running"),
                "phase": operation.get("phase"),
                "message": operation.get("message", ""),
                "started_at": operation.get("startedAt"),
                "finished_at": operation.get("finishedAt"),
            }
        ]

    async def delete_application(
        self,
        name: str,
        namespace: str | None = None,
        cascade: bool = False,
    ) -> bool:
        """
        Deleta uma aplicação do ArgoCD.

        Args:
            name: Nome da aplicação
            namespace: Namespace
            cascade: Se True, remove recursos do Kubernetes

        Returns:
            True se bem-sucedido
        """
        client = await self._get_client()

        ns = namespace or self.namespace
        url = f"/api/v1/applications/{name}?appNamespace={ns}&cascade={str(cascade).lower()}"

        response = await client.delete(url)

        return response.status_code == 200

    async def create_application(
        self,
        name: str,
        project: str,
        repo_url: str,
        path: str,
        destination_namespace: str,
        destination_cluster: str = "https://kubernetes.default.svc",
        sync_policy: str | None = None,
    ) -> bool:
        """
        Cria uma nova aplicação ArgoCD.

        Args:
            name: Nome da aplicação
            project: Projeto do ArgoCD
            repo_url: URL do repositório Git
            path: Caminho do manifesto no repo
            destination_namespace: Namespace de destino
            destination_cluster: URL do cluster de destino
            sync_policy: Política de sync (automatic, manual)

        Returns:
            True se bem-sucedido
        """
        client = await self._get_client()

        url = "/api/v1/applications"

        payload = {
            "metadata": {"name": name},
            "spec": {
                "project": project,
                "source": {
                    "repoURL": repo_url,
                    "path": path,
                },
                "destination": {
                    "server": destination_cluster,
                    "namespace": destination_namespace,
                },
            },
        }

        if sync_policy == "automatic":
            payload["spec"]["syncPolicy"] = {
                "automated": {
                    "prune": True,
                    "selfHeal": True,
                }
            }

        response = await client.post(url, json=payload)

        return response.status_code in (200, 201)

    async def get_repository_list(self) -> list[dict[str, str]]:
        """
        Obtém a lista de repositórios configurados.

        Returns:
            Lista de repositórios
        """
        client = await self._get_client()

        url = "/api/v1/repositories"

        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            return [
                {
                    "url": repo.get("repoURL"),
                    "connection_status": repo.get("connectionState", {}).get("status"),
                    "insecure": repo.get("insecure", False),
                }
                for repo in data
            ]

        return []
