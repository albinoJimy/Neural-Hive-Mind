"""
BackupManifest: Schema Pydantic para metadados de backup de disaster recovery.

Define estrutura de manifest salvo como metadata.json na raiz do backup .tar.gz.
"""

import os
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class ComponentMetadata(BaseModel):
    """Metadados de componente individual do backup."""

    included: bool = Field(description="Se componente foi incluído no backup")
    size_bytes: int = Field(default=0, description="Tamanho do componente em bytes")
    checksum: Optional[str] = Field(
        default=None, description="SHA-256 checksum do componente"
    )
    file_count: int = Field(default=0, description="Número de arquivos no componente")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadados específicos do componente"
    )


class BackupManifest(BaseModel):
    """
    Manifest de backup de disaster recovery.

    Estrutura:
    - backup_id: UUID único
    - specialist_type: Tipo do especialista
    - tenant_id: Tenant (se multi-tenancy habilitado)
    - backup_timestamp: Timestamp do backup
    - components: Metadados de cada componente (model, config, ledger, etc.)
    - checksums: SHA-256 checksums de todos os componentes
    - total_size_bytes: Tamanho total do backup
    - compression_level: Nível de compressão usado
    - created_by: Identificador de quem criou
    - metadata: Metadados adicionais
    """

    backup_id: str = Field(description="UUID único do backup")
    specialist_type: str = Field(
        description="Tipo do especialista (technical, business, etc.)"
    )
    tenant_id: Optional[str] = Field(
        default=None, description="Tenant ID (se multi-tenancy habilitado)"
    )
    backup_timestamp: datetime = Field(description="Timestamp do backup (UTC)")
    backup_version: str = Field(
        default="1.0.0", description="Versão do schema de backup"
    )

    # Componentes do backup
    components: Dict[str, ComponentMetadata] = Field(
        default_factory=dict,
        description="Componentes incluídos no backup (model, config, ledger, cache, features, metrics)",
    )

    # Checksums gerais
    checksums: Dict[str, str] = Field(
        default_factory=dict, description="SHA-256 checksums de cada componente"
    )

    total_size_bytes: int = Field(
        default=0, description="Tamanho total do backup em bytes"
    )
    compression_level: int = Field(
        default=6, description="Nível de compressão gzip usado (1-9)"
    )
    created_by: str = Field(
        default="neural-hive-disaster-recovery",
        description="Identificador de quem criou o backup",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais (ambiente, versão, etc.)",
    )

    def to_json(self) -> str:
        """
        Serializa manifest para JSON.

        Returns:
            String JSON formatada
        """
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "BackupManifest":
        """
        Deserializa manifest de JSON.

        Args:
            json_str: String JSON

        Returns:
            Instância de BackupManifest
        """
        return cls.model_validate_json(json_str)

    @classmethod
    def from_file(cls, file_path: str) -> "BackupManifest":
        """
        Carrega manifest de arquivo JSON.

        Args:
            file_path: Caminho do arquivo metadata.json

        Returns:
            Instância de BackupManifest
        """
        with open(file_path, "r") as f:
            return cls.from_json(f.read())

    def save_to_file(self, file_path: str) -> None:
        """
        Salva manifest em arquivo JSON.

        Args:
            file_path: Caminho de destino
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w") as f:
            f.write(self.to_json())

        logger.info("Manifest salvo", file_path=file_path, backup_id=self.backup_id)

    def validate_checksums(self, backup_dir: str) -> bool:
        """
        Valida checksums de todos os componentes.

        Args:
            backup_dir: Diretório raiz do backup extraído

        Returns:
            True se todos os checksums válidos, False caso contrário
        """
        logger.info(
            "Validando checksums do backup",
            backup_id=self.backup_id,
            backup_dir=backup_dir,
        )

        for component_name, component_meta in self.components.items():
            if not component_meta.included:
                continue

            component_path = self.get_component_path(component_name)
            full_path = os.path.join(backup_dir, component_path)

            if not os.path.exists(full_path):
                logger.error(
                    "Componente não encontrado",
                    component=component_name,
                    path=full_path,
                )
                return False

            # Calcular checksum
            expected_checksum = component_meta.checksum
            if expected_checksum:
                calculated_checksum = self._calculate_checksum(full_path)

                if calculated_checksum != expected_checksum:
                    logger.error(
                        "Checksum inválido",
                        component=component_name,
                        expected=expected_checksum,
                        calculated=calculated_checksum,
                    )
                    return False

                logger.debug("Checksum válido", component=component_name)

        logger.info(
            "Todos os checksums validados com sucesso", backup_id=self.backup_id
        )

        return True

    def get_component_path(self, component_name: str) -> str:
        """
        Retorna path relativo do componente no backup.

        Args:
            component_name: Nome do componente (model, config, ledger, etc.)

        Returns:
            Path relativo (ex: 'model/', 'config/')
        """
        # Convenção: cada componente em seu próprio diretório
        return f"{component_name}/"

    def _calculate_checksum(self, path: str) -> str:
        """
        Calcula SHA-256 checksum de arquivo ou diretório.

        Args:
            path: Caminho do arquivo ou diretório

        Returns:
            Checksum SHA-256
        """
        if os.path.isfile(path):
            # Arquivo único
            return self._calculate_file_checksum(path)
        elif os.path.isdir(path):
            # Diretório: calcular hash de todos os arquivos concatenados
            sha256_hash = hashlib.sha256()

            for root, dirs, files in sorted(os.walk(path)):
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    file_checksum = self._calculate_file_checksum(file_path)
                    sha256_hash.update(file_checksum.encode())

            return sha256_hash.hexdigest()
        else:
            return ""

    def _calculate_file_checksum(self, file_path: str) -> str:
        """
        Calcula SHA-256 checksum de arquivo único.

        Args:
            file_path: Caminho do arquivo

        Returns:
            Checksum SHA-256
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def get_summary(self) -> Dict[str, Any]:
        """
        Retorna resumo do backup.

        Returns:
            Dict com informações resumidas
        """
        included_components = [
            name for name, meta in self.components.items() if meta.included
        ]

        return {
            "backup_id": self.backup_id,
            "specialist_type": self.specialist_type,
            "tenant_id": self.tenant_id,
            "timestamp": self.backup_timestamp.isoformat(),
            "version": self.backup_version,
            "total_size_mb": round(self.total_size_bytes / (1024 * 1024), 2),
            "compression_level": self.compression_level,
            "components_included": included_components,
            "component_count": len(included_components),
        }

    def add_component(
        self,
        name: str,
        component_dir: str,
        included: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Adiciona componente ao manifest.

        Args:
            name: Nome do componente
            component_dir: Diretório do componente
            included: Se componente foi incluído
            metadata: Metadados específicos do componente
        """
        if not os.path.exists(component_dir):
            logger.warning(
                "Diretório de componente não encontrado",
                component=name,
                path=component_dir,
            )

            self.components[name] = ComponentMetadata(
                included=False, size_bytes=0, file_count=0, metadata=metadata or {}
            )
            return

        # Calcular tamanho e checksum
        size_bytes = 0
        file_count = 0

        if os.path.isfile(component_dir):
            size_bytes = os.path.getsize(component_dir)
            file_count = 1
        elif os.path.isdir(component_dir):
            for root, dirs, files in os.walk(component_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    size_bytes += os.path.getsize(file_path)
                    file_count += 1

        checksum = self._calculate_checksum(component_dir)

        self.components[name] = ComponentMetadata(
            included=included,
            size_bytes=size_bytes,
            checksum=checksum,
            file_count=file_count,
            metadata=metadata or {},
        )

        self.checksums[name] = checksum
        self.total_size_bytes += size_bytes

        logger.debug(
            "Componente adicionado ao manifest",
            component=name,
            size_bytes=size_bytes,
            file_count=file_count,
            checksum=checksum[:16] + "...",
        )
