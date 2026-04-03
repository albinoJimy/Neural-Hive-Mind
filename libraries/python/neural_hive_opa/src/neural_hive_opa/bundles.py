"""
Policy Bundle Management para OPA.

Este módulo fornece funcionalidades para:
- Download de policy bundles do OPA
- Reload de políticas em runtime
- Versionamento de políticas
- Validação de sintaxe OPA

Uso:
    from neural_hive_opa.bundles import PolicyBundleManager

    manager = PolicyBundleManager(opa_url="http://opa:8181")
    await manager.download_bundle()
    await manager.reload_policies()
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel, Field

from neural_hive_opa.config import OPAConfig
from neural_hive_opa.client import OPAClient

logger = structlog.get_logger(__name__)


class PolicyStatus(str, Enum):
    """Status de uma política OPA."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    ERROR = "error"


@dataclass
class PolicyBundle:
    """
    Representa um bundle de políticas OPA.

    Attributes:
        name: Nome do bundle
        version: Versão do bundle
        policies: Dict com nome → conteúdo da política
        created_at: Timestamp de criação
        status: Status do bundle
    """

    name: str
    version: str
    policies: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: PolicyStatus = PolicyStatus.PENDING

    def hash(self) -> str:
        """
        Calcula hash do bundle baseado no conteúdo das políticas.

        Returns:
            String hexadecimal do hash
        """
        content = json.dumps(self.policies, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


class PolicyBundleInfo(BaseModel):
    """Informações sobre um bundle de políticas."""

    name: str = Field(description="Nome do bundle")
    version: str = Field(description="Versão do bundle")
    policy_count: int = Field(description="Número de políticas no bundle")
    hash: str = Field(description="Hash do conteúdo do bundle")
    created_at: str = Field(description="Timestamp de criação (ISO)")
    status: PolicyStatus = Field(description="Status do bundle")


class PolicyBundleManager:
    """
    Gerenciador de bundles de políticas OPA.

    Permite download, reload e versionamento de políticas.
    """

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        bundle_path: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        """
        Inicializa gerenciador de bundles.

        Args:
            opa_url: URL do servidor OPA
            bundle_path: Caminho local para armazenar bundles
            timeout_seconds: Timeout para operações HTTP
        """
        self.opa_url = opa_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.bundle_path = Path(bundle_path) if bundle_path else Path("/tmp/opa_bundles")
        self.bundle_path.mkdir(parents=True, exist_ok=True)

        self._bundles: dict[str, PolicyBundle] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def close(self) -> None:
        """Fecha cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def download_bundle(
        self,
        bundle_url: str,
        name: str,
        version: str = "latest",
    ) -> PolicyBundleInfo:
        """
        Download de policy bundle de uma URL externa.

        Args:
            bundle_url: URL do bundle (tar.gz, zip, ou diretório)
            name: Nome do bundle
            version: Versão do bundle

        Returns:
            PolicyBundleInfo com informações do bundle baixado

        Raises:
            httpx.HTTPStatusError: Se download falhar
        """
        client = await self._get_client()

        logger.info("downloading_bundle", name=name, version=version, url=bundle_url)

        try:
            response = await client.get(bundle_url, follow_redirects=True)
            response.raise_for_status()

            # Salvar bundle localmente
            bundle_file = self.bundle_path / f"{name}-{version}.tar.gz"
            bundle_file.write_bytes(response.content)

            # Extrair se for tar.gz
            if bundle_url.endswith(".tar.gz"):
                await self._extract_bundle(bundle_file, name)

            logger.info("bundle_downloaded", name=name, version=version)

            return await self.load_bundle(name, version)

        except httpx.HTTPStatusError as e:
            logger.error("bundle_download_failed", name=name, error=str(e))
            raise

    async def _extract_bundle(self, bundle_file: Path, name: str) -> None:
        """
        Extrai bundle tar.gz para diretório de políticas.

        Args:
            bundle_file: Caminho do arquivo bundle
            name: Nome do bundle
        """
        import tarfile

        extract_dir = self.bundle_path / name
        extract_dir.mkdir(exist_ok=True)

        with tarfile.open(bundle_file) as tar:
            tar.extractall(path=extract_dir)

        logger.info("bundle_extracted", name=name, path=str(extract_dir))

    async def create_bundle(
        self,
        name: str,
        version: str,
        policies: dict[str, str],
        activate: bool = True,
    ) -> PolicyBundleInfo:
        """
        Cria um novo bundle de políticas.

        Args:
            name: Nome do bundle
            version: Versão do bundle
            policies: Dict com policy_name → policy_content
            activate: Se True, ativa o bundle imediatamente

        Returns:
            PolicyBundleInfo com informações do bundle criado
        """
        bundle = PolicyBundle(
            name=name,
            version=version,
            policies=policies,
            status=PolicyStatus.ACTIVE if activate else PolicyStatus.PENDING,
        )

        self._bundles[f"{name}:{version}"] = bundle

        # Salvar políticas em arquivos
        bundle_dir = self.bundle_path / name / version
        bundle_dir.mkdir(parents=True, exist_ok=True)

        for policy_name, policy_content in policies.items():
            policy_file = bundle_dir / f"{policy_name}.rego"
            policy_file.write_text(policy_content)

        logger.info("bundle_created", name=name, version=version, policy_count=len(policies))

        if activate:
            await self.activate_bundle(name, version)

        return self._get_bundle_info(bundle)

    async def load_bundle(
        self,
        name: str,
        version: str = "latest",
    ) -> PolicyBundleInfo:
        """
        Carrega bundle do disco.

        Args:
            name: Nome do bundle
            version: Versão do bundle

        Returns:
            PolicyBundleInfo
        """
        bundle_dir = self.bundle_path / name
        if version == "latest":
            # Encontrar versão mais recente
            versions = [d.name for d in bundle_dir.iterdir() if d.is_dir()]
            version = sorted(versions)[-1] if versions else "1.0.0"

        bundle_path = bundle_dir / version
        if not bundle_path.exists():
            raise FileNotFoundError(f"Bundle not found: {name}:{version}")

        # Carregar políticas
        policies = {}
        for policy_file in bundle_path.glob("*.rego"):
            policy_name = policy_file.stem
            policies[policy_name] = policy_file.read_text()

        bundle = PolicyBundle(
            name=name,
            version=version,
            policies=policies,
            status=PolicyStatus.ACTIVE,
        )

        self._bundles[f"{name}:{version}"] = bundle

        logger.info("bundle_loaded", name=name, version=version, policy_count=len(policies))

        return self._get_bundle_info(bundle)

    async def activate_bundle(
        self,
        name: str,
        version: str,
    ) -> None:
        """
        Ativa um bundle de políticas no OPA.

        Args:
            name: Nome do bundle
            version: Versão do bundle
        """
        client = await self._get_client()

        bundle_key = f"{name}:{version}"
        if bundle_key not in self._bundles:
            raise ValueError(f"Bundle not loaded: {bundle_key}")

        bundle = self._bundles[bundle_key]

        # Upload políticas para OPA via API
        opa_policies_url = f"{self.opa_url}/v1/policies"

        for policy_name, policy_content in bundle.policies.items():
            policy_data = {
                "id": f"{name}/{policy_name}",
                "name": policy_name,
                "module": policy_content,
                "rego": policy_content,
            }

            try:
                response = await client.put(
                    f"{opa_policies_url}/{name}/{policy_name}",
                    json=policy_data,
                )
                response.raise_for_status()
                logger.info("policy_uploaded", name=name, policy=policy_name)
            except httpx.HTTPStatusError as e:
                logger.error("policy_upload_failed", name=name, policy=policy_name, error=str(e))
                raise

        bundle.status = PolicyStatus.ACTIVE
        logger.info("bundle_activated", name=name, version=version)

    async def reload_policies(self, bundle_name: str | None = None) -> dict[str, str]:
        """
        Recarrega políticas no OPA.

        Args:
            bundle_name: Nome do bundle específico, ou None para todos

        Returns:
            Dict com status de cada política recarregada
        """
        client = await self._get_client()

        if bundle_name:
            bundles_to_reload = [bundle_name]
        else:
            bundles_to_reload = list(set(b.split(":")[0] for b in self._bundles.keys()))

        results: dict[str, str] = {}

        for name in bundles_to_reload:
            try:
                # Trigger reload via OPA API
                response = await client.post(
                    f"{self.opa_url}/v1/policies/{name}/reload",
                    json={"import": f"base.{name}"},
                )
                response.raise_for_status()

                results[name] = "reloaded"
                logger.info("policy_reloaded", name=name)

            except httpx.HTTPStatusError as e:
                results[name] = f"failed: {e}"
                logger.error("policy_reload_failed", name=name, error=str(e))

        return results

    async def list_bundles(self) -> list[PolicyBundleInfo]:
        """
        Lista todos os bundles carregados.

        Returns:
            Lista de PolicyBundleInfo
        """
        return [
            self._get_bundle_info(bundle)
            for bundle in self._bundles.values()
        ]

    async def get_bundle(self, name: str, version: str = "latest") -> PolicyBundleInfo | None:
        """
        Retorna informações de um bundle específico.

        Args:
            name: Nome do bundle
            version: Versão do bundle

        Returns:
            PolicyBundleInfo ou None se não encontrado
        """
        if version == "latest":
            # Encontrar versão mais recente
            versions = [
                b.version for b in self._bundles.values()
                if b.name == name
            ]
            if not versions:
                return None
            version = sorted(versions)[-1]

        bundle_key = f"{name}:{version}"
        bundle = self._bundles.get(bundle_key)

        if bundle:
            return self._get_bundle_info(bundle)

        return None

    async def validate_policy(self, policy_content: str) -> dict[str, Any]:
        """
        Valida sintaxe de uma política OPA.

        Args:
            policy_content: Conteúdo da política Rego

        Returns:
            Dict com resultado da validação
        """
        client = await self._get_client()

        try:
            response = await client.post(
                f"{self.opa_url}/v1/compile",
                json={"query": policy_content, "input": {}},
            )

            if response.status_code == 200:
                return {"valid": True, "errors": []}

            result = response.json()
            return {
                "valid": False,
                "errors": result.get("errors", []),
            }

        except Exception as e:
            logger.error("policy_validation_failed", error=str(e))
            return {"valid": False, "errors": [str(e)]}

    def _get_bundle_info(self, bundle: PolicyBundle) -> PolicyBundleInfo:
        """Converte PolicyBundle para PolicyBundleInfo."""
        return PolicyBundleInfo(
            name=bundle.name,
            version=bundle.version,
            policy_count=len(bundle.policies),
            hash=bundle.hash(),
            created_at=bundle.created_at.isoformat(),
            status=bundle.status,
        )

    async def cleanup_old_bundles(
        self,
        name: str,
        keep_versions: int = 3,
    ) -> list[str]:
        """
        Remove versões antigas de um bundle.

        Args:
            name: Nome do bundle
            keep_versions: Quantidade de versões para manter

        Returns:
            Lista de versões removidas
        """
        bundle_dir = self.bundle_path / name
        if not bundle_dir.exists():
            return []

        versions = sorted(
            [d.name for d in bundle_dir.iterdir() if d.is_dir()],
            reverse=True,
        )

        to_remove = versions[keep_versions:]
        removed = []

        for version in to_remove:
            version_dir = bundle_dir / version
            try:
                # Remover arquivos e diretório
                for file in version_dir.glob("*"):
                    file.unlink()
                version_dir.rmdir()
                removed.append(version)
                logger.info("old_bundle_removed", name=name, version=version)
            except Exception as e:
                logger.warning("failed_to_remove_bundle", name=name, version=version, error=str(e))

        return removed


__all__ = [
    "PolicyStatus",
    "PolicyBundle",
    "PolicyBundleInfo",
    "PolicyBundleManager",
]
