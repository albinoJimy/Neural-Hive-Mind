"""
Gerenciador de PVC para builds Kaniko com contextos grandes.

Quando o contexto de build excede ~1MB (limite do ConfigMap),
o PVCManager cria dinamicamente um PersistentVolumeClaim para armazenar o contexto.
"""

import logging
from datetime import UTC

UTC = UTC  # type: ignore
from uuid import uuid4

from kubernetes import client, config
from kubernetes.client import ApiException, V1PersistentVolumeClaim

logger = logging.getLogger(__name__)

# Tamanho máximo aproximado para ConfigMap em bytes (base64)
# Kubernetes tem limites de 1MB para ConfigMap, mas o overhead base64
# significa que o contexto real deve ser menor (~700-800KB)
CONFIGMAP_MAX_BYTES = 800 * 1024  # ~800KB após compressão


class PVCManager:
    """
    Gerencia criação e cleanup de PVCs para builds Kaniko.

    Fluxo:
    1. Detecta contexto >1MB
    2. Cria PVC com tamanho apropriado
    3. Substitui ConfigMap por volume PVC
    4. Limpa PVC após build
    """

    def __init__(self, namespace: str = "default", storage_class: str = None):
        """
        Inicializa o PVCManager.

        Args:
            namespace: Namespace Kubernetes para recursos
            storage_class: StorageClass para PVCs (default: standard)
        """
        self.namespace = namespace
        self.storage_class = storage_class or "standard"

        # Lazy load do client Kubernetes
        self._k8s_client: client.CoreV1Api | None = None

    def _get_k8s_client(self) -> client.CoreV1Api:
        """Obtém ou cria cliente Kubernetes."""
        if self._k8s_client is None:
            try:
                config.load_kube_config()
                self._k8s_client = client.CoreV1Api()
                logger.info(f"k8s_client_initialized, namespace: {self.namespace}")
            except Exception as e:
                logger.error(f"k8s_client_init_failed: {e}")
                raise

        return self._k8s_client

    def detect_context_size(self, dockerfile_path: str, build_context: str) -> int:
        """
        Detecta o tamanho do contexto de build em bytes.

        Args:
            dockerfile_path: Caminho para o Dockerfile
            build_context: Diretório de contexto

        Returns:
            Tamanho em bytes do contexto comprimido
        """
        import os

        # Calcular tamanho do contexto
        context_size = 0

        # Adicionar tamanho do Dockerfile
        if os.path.exists(dockerfile_path):
            context_size += os.path.getsize(dockerfile_path)

        # Adicionar arquivos no contexto
        for root, dirs, files in os.walk(build_context):
            for file in files:
                file_path = os.path.join(root, file)
                context_size += os.path.getsize(file_path)

        logger.info(
            f"context_size_detected: dockerfile={dockerfile_path}, "
            f"size_bytes={context_size}, size_mb={context_size / (1024 * 1024):.2f}"
        )

        return context_size

    def should_use_pvc(self, context_size_bytes: int) -> bool:
        """
        Decide se deve usar PVC baseado no tamanho do contexto.

        Args:
            context_size_bytes: Tamanho do contexto em bytes

        Returns:
            True se contexto > CONFIGMAP_MAX_BYTES
        """
        return context_size_bytes > CONFIGMAP_MAX_BYTES

    def calculate_pvc_size_gb(self, context_size_bytes: int, margin_multiplier: float = 1.5) -> int:
        """
        Calcula tamanho do PVC necessário com margem.

        Args:
            context_size_bytes: Tamanho do contexto
            margin_multiplier: Multiplicador de margem de segurança (default 1.5x)

        Returns:
            Tamanho do PVC em GB (arredondado para cima)
        """
        # Converter para GB e adicionar margem
        size_gb = (context_size_bytes * margin_multiplier) / (1024**3)

        # Arredondar para cima próximo GB inteiro, mínimo 1GB
        return max(1, int(size_gb) + 1)

    def get_pvc_name(self, build_id: str = None) -> str:
        """
        Gera nome único para PVC.

        Args:
            build_id: ID do build (opcional, para tracking)

        Returns:
            Nome do PVC no formato kaniko-build-{id}
        """
        if build_id:
            return f"kaniko-build-{build_id}"
        return f"kaniko-build-{uuid4().hex[:8]}"

    def create_pvc_for_build(
        self, build_id: str, size_gb: int, access_mode: str = "ReadWriteOnce"
    ) -> V1PersistentVolumeClaim:
        """
        Cria PVC para armazenar contexto de build.

        Args:
            build_id: ID único do build
            size_gb: Tamanho do PVC em GB
            access_mode: Modo de acesso (default: ReadWriteOnce)

        Returns:
            Objeto PersistentVolumeClaim criado

        Raises:
            ApiException: Se falha ao criar PVC
        """
        pvc_name = self.get_pvc_name(build_id)

        pvc_spec = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": pvc_name,
                "namespace": self.namespace,
                "labels": {"app": "kaniko", "build-id": build_id, "temporary": "true"},
                "annotations": {"cleanup-after": "build-complete"},
            },
            "spec": {
                "accessModes": [access_mode],
                "resources": {"requests": {"storage": f"{size_gb}Gi"}},
                "storageClassName": self.storage_class if self.storage_class else None,
            },
        }

        client = self._get_k8s_client()

        try:
            pvc = client.create_namespaced_persistent_volume_claim(
                namespace=self.namespace, body=pvc_spec
            )
            logger.info(f"pvc_created: {pvc_name}, size_gb={size_gb}, access_mode={access_mode}")
            return pvc
        except ApiException as e:
            logger.error(f"pvc_creation_failed: {pvc_name}, error: {e}")
            raise

    def get_pvc_mount_path(self, pvc_name: str) -> str:
        """
        Retorna caminho de mount do PVC no container.

        Args:
            pvc_name: Nome do PVC

        Returns:
            Caminho para mount do volume
        """
        return "/workspace-pvc"

    def cleanup_pvc(self, pvc_name: str, ignore_if_not_found: bool = True) -> bool:
        """
        Limpa PVC após build.

        Args:
            pvc_name: Nome do PVC para remover
            ignore_if_not_found: Não levantar erro se PVC não existir

        Returns:
            True se PVC foi removido (ou não existia e ignore_if_not_find=True)
        """
        client = self._get_k8s_client()

        try:
            # Primeiro, tentar deletar o PVC
            policy = {"foregroundPolicy": "Foreground"}
            client.delete_namespaced_persistent_volume_claim(
                namespace=self.namespace, name=pvc_name, body=policy
            )
            logger.info(f"pvc_deleted: {pvc_name}")
            return True
        except ApiException as e:
            if e.status == 404 and ignore_if_not_found:
                logger.info(f"pvc_not_found: {pvc_name}")
                return True
            logger.error(f"pvc_deletion_failed: {pvc_name}, error: {e}")
            return False

    def list_pvcs_for_build(self, build_id: str | None = None) -> list[V1PersistentVolumeClaim]:
        """
        Lista PVCs temporários de build.

        Args:
            build_id: Filtrar por build_id específico (opcional)

        Returns:
            Lista de PVCs encontrados
        """
        client = self._get_k8s_client()

        try:
            label_selector = "app=kaniko,temporary=true"
            if build_id:
                label_selector += f",build-id={build_id}"

            pvcs = client.list_namespaced_persistent_volume_claim(
                namespace=self.namespace, label_selector=label_selector
            )

            logger.info("pvcs_listed", count=len(pvcs.items), build_id=build_id or "all")
            return pvcs.items
        except ApiException as e:
            logger.error(f"pvc_list_failed: {e}")
            return []

    def cleanup_all_build_pvcs(self, older_than_hours: int = 24) -> int:
        """
        Limpa todos os PVCs de build antigos.

        Útil para cleanup periódico de PVCs órfãos.

        Args:
            older_than_hours: Remover PVCs criados há X horas atrás

        Returns:
            Número de PVCs removidos
        """
        from datetime import datetime, timedelta

        client = self._get_k8s_client()
        cutoff_time = datetime.now(UTC) - timedelta(hours=older_than_hours)

        try:
            label_selector = "app=kaniko,temporary=true"
            pvcs = client.list_namespaced_persistent_volume_claim(
                namespace=self.namespace, label_selector=label_selector
            )

            deleted_count = 0
            for pvc in pvcs.items:
                # Verificar idade do PVC pela criação
                creation_timestamp = pvc.metadata.creation_timestamp
                if creation_timestamp and creation_timestamp < cutoff_time:
                    # Deletar PVC
                    policy = {"foregroundPolicy": "Foreground"}
                    try:
                        client.delete_namespaced_persistent_volume_claim(
                            namespace=self.namespace, name=pvc.metadata.name, body=policy
                        )
                        deleted_count += 1
                        logger.info(f"old_pvc_deleted: {pvc.metadata.name}")
                    except ApiException as e:
                        logger.warning(f"old_pvc_deletion_failed: {pvc.metadata.name}, error: {e}")

            logger.info(
                f"build_pvcs_cleanup_complete: deleted={deleted_count}, older_than_hours={older_than_hours}"
            )
            return deleted_count
        except ApiException as e:
            logger.error(f"cleanup_pvcs_failed: {e}")
            return 0


def detect_large_context_and_create_pvc(
    dockerfile_path: str,
    build_context: str,
    build_id: str,
    namespace: str = "default",
    storage_class: str | None = None,
) -> tuple[bool, str | None, int | None]:
    """
    Detecta contexto grande e cria PVC se necessário.

    Função de conveniência para uso em pipelines.

    Args:
        dockerfile_path: Caminho do Dockerfile
        build_context: Diretório de contexto
        build_id: ID único do build
        namespace: Namespace Kubernetes
        storage_class: StorageClass para PVC

    Returns:
        Tuple (needs_pvc, pvc_name, pvc_size_gb)
        - needs_pvc: True se contexto precisa de PVC
        - pvc_name: Nome do PVC criado (se aplicável)
        - pvc_size_gb: Tamanho do PVC em GB (se aplicável)
    """
    manager = PVCManager(namespace=namespace, storage_class=storage_class)

    # Detectar tamanho do contexto
    context_size = manager.detect_context_size(dockerfile_path, build_context)

    # Verificar se precisa de PVC
    if manager.should_use_pvc(context_size):
        pvc_size_gb = manager.calculate_pvc_size_gb(context_size)

        try:
            pvc = manager.create_pvc_for_build(build_id, pvc_size_gb)
            pvc_name = pvc.metadata.name

            logger.info(
                f"pvc_created_for_large_context: build_id={build_id}, "
                f"pvc_name={pvc_name}, pvc_size_gb={pvc_size_gb}, "
                f"context_mb={context_size / (1024 * 1024):.2f}"
            )

            return True, pvc_name, pvc_size_gb
        except Exception as e:
            logger.error(f"pvc_creation_for_large_context_failed: build_id={build_id}, error: {e}")
            return False, None, None
    else:
        logger.info(f"context_fits_in_configmap: size_mb={context_size / (1024 * 1024):.2f}")
        return False, None, None


def cleanup_build_pvc(pvc_name: str, namespace: str = "default") -> bool:
    """
    Limpa PVC de build após conclusão.

    Função de conveniência para uso em finally blocks.

    Args:
        pvc_name: Nome do PVC para limpar
        namespace: Namespace Kubernetes

    Returns:
        True se PVC foi removido (ou não existia)
    """
    manager = PVCManager(namespace=namespace)
    return manager.cleanup_pvc(pvc_name)


def get_pvc_mount_spec(pvc_name: str) -> dict:
    """
    Retorna especificação de mount do PVC para pod Kaniko.

    Args:
        pvc_name: Nome do PVC

    Returns:
    Dicionário com volumeMount para PVC
    """
    manager = PVCManager()
    mount_path = manager.get_pvc_mount_path(pvc_name)

    return {"name": pvc_name, "mountPath": mount_path}
