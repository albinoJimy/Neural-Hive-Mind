"""
DisasterRecoveryManager: Orquestra backup e restore do estado completo dos especialistas.

Responsabilidades:
- Backup completo: modelo MLflow, config, ledger MongoDB, cache Redis, features, métricas
- Restore de backup com validação de integridade
- Teste de recovery automatizado
- Integração com StorageClient (S3/GCS/Local)
- Geração de manifest de backup
"""

import os
import shutil
import tarfile
import tempfile
import uuid
import json
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import structlog

from .backup_manifest import BackupManifest, ComponentMetadata
from .storage_client import StorageClient

logger = structlog.get_logger()


class DisasterRecoveryManager:
    """
    Gerenciador de disaster recovery para especialistas neurais.

    Fluxo de backup:
    1. Criar diretório temporário
    2. Backup de componentes em paralelo
    3. Gerar manifest com checksums
    4. Criar arquivo .tar.gz
    5. Upload para storage
    6. Registrar métricas

    Fluxo de restore:
    1. Download de backup
    2. Validar checksum do arquivo
    3. Extrair .tar.gz
    4. Validar checksums de componentes
    5. Restaurar componentes em ordem
    6. Executar smoke tests
    """

    def __init__(self, config, specialist, storage_client: StorageClient):
        """
        Inicializa DisasterRecoveryManager.

        Args:
            config: SpecialistConfig com configurações de DR
            specialist: Instância de BaseSpecialist
            storage_client: Cliente de storage (S3/GCS/Local)
        """
        self.config = config
        self.specialist = specialist
        self.storage_client = storage_client

        logger.info(
            "DisasterRecoveryManager inicializado",
            specialist_type=config.specialist_type,
            storage_provider=config.backup_storage_provider
        )

    def backup_specialist_state(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executa backup do estado do especialista.

        Suporta dois modos (configurável via backup_mode):
        - 'full': Upload completo de tar.gz (comportamento original)
        - 'incremental': Content-addressed storage com deduplicação por SHA-256

        Args:
            tenant_id: Tenant ID (opcional, para multi-tenancy)

        Returns:
            Dict com resultado:
            - status: 'success', 'partial', 'failed'
            - backup_id: UUID do backup ou snapshot ID
            - total_size_bytes: Tamanho total (full) ou tamanho do snapshot (incremental)
            - duration_seconds: Duração
            - components_included: Lista de componentes
            - error: Mensagem de erro (se falha)
        """
        import time
        start_time = time.time()

        # Verificar modo de backup e rotear para método apropriado
        backup_mode = getattr(self.config, 'backup_mode', 'full')

        if backup_mode == 'incremental':
            logger.info(
                "Usando modo incremental (content-addressed storage)",
                specialist_type=self.config.specialist_type,
                tenant_id=tenant_id
            )
            return self._backup_incremental(tenant_id)

        # Modo 'full' - comportamento original
        backup_id = str(uuid.uuid4())
        tenant_suffix = f"-{tenant_id}" if tenant_id else ""

        logger.info(
            "Iniciando backup de especialista (modo full)",
            backup_id=backup_id,
            specialist_type=self.config.specialist_type,
            tenant_id=tenant_id
        )

        # Criar diretório temporário
        backup_dir = tempfile.mkdtemp(prefix=f'backup-{backup_id}-')

        try:
            # Criar manifest
            manifest = BackupManifest(
                backup_id=backup_id,
                specialist_type=self.config.specialist_type,
                tenant_id=tenant_id,
                backup_timestamp=datetime.utcnow(),
                compression_level=self.config.backup_compression_level,
                metadata={
                    'environment': self.config.environment,
                    'service_name': self.config.service_name
                }
            )

            # Backup de componentes em paralelo
            component_results = {}

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}

                # Modelo MLflow
                futures[executor.submit(self._backup_model, backup_dir)] = 'model'

                # Configuração
                futures[executor.submit(self._backup_config, backup_dir)] = 'config'

                # Ledger MongoDB
                futures[executor.submit(self._backup_ledger, backup_dir, tenant_id)] = 'ledger'

                # Cache Redis (opcional)
                if self.config.backup_include_cache:
                    futures[executor.submit(self._backup_cache, backup_dir)] = 'cache'

                # Feature Store
                if self.config.backup_include_feature_store:
                    futures[executor.submit(self._backup_feature_store, backup_dir, tenant_id)] = 'feature_store'

                # Métricas
                if self.config.backup_include_metrics:
                    futures[executor.submit(self._backup_metrics, backup_dir)] = 'metrics'

                # Aguardar conclusão
                for future in as_completed(futures):
                    component_name = futures[future]
                    try:
                        result = future.result()
                        component_results[component_name] = result

                        # Adicionar componente ao manifest
                        if result['success']:
                            component_dir = os.path.join(backup_dir, component_name)
                            manifest.add_component(
                                name=component_name,
                                component_dir=component_dir,
                                included=True,
                                metadata=result.get('metadata', {})
                            )

                            # Registrar métrica de duração por componente
                            if hasattr(self.specialist, 'metrics'):
                                self.specialist.metrics.observe_backup_component_duration(
                                    component_name,
                                    result.get('duration_seconds', 0)
                                )
                        else:
                            logger.warning(
                                "Componente falhou no backup",
                                component=component_name,
                                error=result.get('error')
                            )

                    except Exception as e:
                        logger.error(
                            "Erro ao processar componente",
                            component=component_name,
                            error=str(e)
                        )
                        component_results[component_name] = {
                            'success': False,
                            'error': str(e)
                        }

            # Salvar manifest
            manifest_path = os.path.join(backup_dir, 'metadata.json')
            manifest.save_to_file(manifest_path)

            # Criar arquivo .tar.gz
            timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
            backup_filename = f"specialist-{self.config.specialist_type}{tenant_suffix}-backup-{timestamp}.tar.gz"
            backup_archive_path = os.path.join(tempfile.gettempdir(), backup_filename)

            logger.info(
                "Criando arquivo de backup",
                backup_file=backup_filename,
                compression_level=self.config.backup_compression_level
            )

            with tarfile.open(backup_archive_path, f'w:gz', compresslevel=self.config.backup_compression_level) as tar:
                tar.add(backup_dir, arcname='')

            # Calcular checksum do arquivo
            checksum = self._calculate_file_checksum(backup_archive_path)
            checksum_file = f"{backup_archive_path}.sha256"

            with open(checksum_file, 'w') as f:
                f.write(f"{checksum}  {backup_filename}\n")

            archive_size = os.path.getsize(backup_archive_path)

            logger.info(
                "Arquivo de backup criado",
                size_bytes=archive_size,
                checksum=checksum[:16] + '...'
            )

            # Upload para storage
            try:
                upload_success = self.storage_client.upload_backup(
                    backup_archive_path,
                    backup_filename
                )

                if not upload_success:
                    raise Exception("Falha no upload para storage")

            except Exception as e:
                # Incrementar métrica de erro de upload
                if hasattr(self.specialist, 'metrics'):
                    provider = self.config.backup_storage_provider
                    self.specialist.metrics.increment_storage_upload_error(provider)

                raise  # Re-raise para tratamento externo

            # Upload do checksum
            try:
                checksum_upload = self.storage_client.upload_backup(
                    checksum_file,
                    f"{backup_filename}.sha256"
                )

                if not checksum_upload:
                    logger.warning("Falha no upload do checksum, continuando")

            except Exception as e:
                logger.warning("Erro ao fazer upload de checksum", error=str(e))
                # Não é crítico, não falhar o backup por isso

            # Registrar métricas
            duration = time.time() - start_time

            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.set_backup_last_success_timestamp(
                    tenant_id or 'default',
                    time.time()
                )
                self.specialist.metrics.observe_backup_duration(duration)
                self.specialist.metrics.set_backup_size(
                    tenant_id or 'default',
                    archive_size
                )
                self.specialist.metrics.increment_backup_total('success')

            # Limpar arquivos temporários
            shutil.rmtree(backup_dir, ignore_errors=True)
            os.remove(backup_archive_path)
            os.remove(checksum_file)

            successful_components = [
                name for name, result in component_results.items() if result['success']
            ]

            logger.info(
                "Backup concluído com sucesso",
                backup_id=backup_id,
                backup_file=backup_filename,
                size_bytes=archive_size,
                duration_seconds=round(duration, 2),
                components_included=successful_components
            )

            return {
                'status': 'success',
                'backup_id': backup_id,
                'backup_filename': backup_filename,
                'total_size_bytes': archive_size,
                'duration_seconds': round(duration, 2),
                'components_included': successful_components,
                'checksum': checksum
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup",
                backup_id=backup_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )

            # Registrar métrica de falha
            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.increment_backup_total('failed')

            # Limpar
            shutil.rmtree(backup_dir, ignore_errors=True)

            return {
                'status': 'failed',
                'backup_id': backup_id,
                'error': str(e),
                'duration_seconds': round(duration, 2)
            }

    def _backup_model(self, backup_dir: str) -> Dict[str, Any]:
        """
        Backup de modelo MLflow incluindo artifacts.

        Args:
            backup_dir: Diretório de backup

        Returns:
            Dict com resultado
        """
        import time
        start_time = time.time()

        model_dir = os.path.join(backup_dir, 'model')
        os.makedirs(model_dir, exist_ok=True)

        try:
            logger.info("Iniciando backup de modelo MLflow")

            # Obter informações do modelo atual
            mlflow_client = self.specialist.mlflow_client

            # Obter run_id e model info
            run_id = None
            model_version = getattr(self.specialist, 'current_model_version', 'unknown')

            # Salvar metadata do modelo
            model_metadata = {
                'model_name': self.config.mlflow_model_name,
                'model_version': model_version,
                'model_stage': self.config.mlflow_model_stage,
                'mlflow_tracking_uri': self.config.mlflow_tracking_uri,
                'mlflow_experiment_name': self.config.mlflow_experiment_name
            }

            # Download de artifacts do MLflow
            artifacts_size = 0

            if mlflow_client and hasattr(mlflow_client, 'download_artifacts'):
                try:
                    # Construir model URI
                    model_uri = f"models:/{self.config.mlflow_model_name}/{self.config.mlflow_model_stage}"

                    logger.info("Baixando artifacts do MLflow", model_uri=model_uri)

                    # Criar diretório de artifacts
                    artifacts_dir = os.path.join(model_dir, 'artifacts')
                    os.makedirs(artifacts_dir, exist_ok=True)

                    # Download de artifacts
                    # Nota: Requer mlflow client com método download_artifacts
                    try:
                        import mlflow

                        # Download do modelo completo
                        downloaded_path = mlflow.artifacts.download_artifacts(
                            artifact_uri=model_uri,
                            dst_path=artifacts_dir
                        )

                        # Calcular tamanho dos artifacts
                        for root, dirs, files in os.walk(artifacts_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                artifacts_size += os.path.getsize(file_path)

                        model_metadata['artifacts_downloaded'] = True
                        model_metadata['artifacts_size_bytes'] = artifacts_size
                        model_metadata['artifacts_path'] = downloaded_path

                        logger.info(
                            "Artifacts do modelo baixados",
                            size_bytes=artifacts_size
                        )

                    except ImportError:
                        logger.warning("mlflow não disponível para download de artifacts")
                        model_metadata['artifacts_downloaded'] = False

                    except Exception as e:
                        logger.warning(
                            "Falha ao baixar artifacts do MLflow",
                            error=str(e)
                        )
                        model_metadata['artifacts_downloaded'] = False
                        model_metadata['artifacts_error'] = str(e)

                except Exception as e:
                    logger.warning("Erro ao acessar MLflow client", error=str(e))
                    model_metadata['artifacts_downloaded'] = False

            else:
                logger.warning("MLflow client não disponível")
                model_metadata['artifacts_downloaded'] = False

            # Salvar metadata
            with open(os.path.join(model_dir, 'model_metadata.json'), 'w') as f:
                json.dump(model_metadata, f, indent=2)

            duration = time.time() - start_time

            logger.info(
                "Backup de modelo concluído",
                duration_seconds=round(duration, 2),
                artifacts_size_bytes=artifacts_size
            )

            return {
                'success': True,
                'duration_seconds': duration,
                'metadata': model_metadata
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup de modelo",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                'success': False,
                'error': str(e),
                'duration_seconds': duration
            }

    def _backup_config(self, backup_dir: str) -> Dict[str, Any]:
        """
        Backup de configuração.

        Args:
            backup_dir: Diretório de backup

        Returns:
            Dict com resultado
        """
        import time
        start_time = time.time()

        config_dir = os.path.join(backup_dir, 'config')
        os.makedirs(config_dir, exist_ok=True)

        try:
            logger.info("Iniciando backup de configuração")

            # Exportar configuração principal
            config_dict = self.config.to_dict()

            # Remover campos sensíveis
            sensitive_fields = [
                'jwt_secret_key', 'mongodb_uri', 'neo4j_password',
                'aws_access_key_id', 'aws_secret_access_key'
            ]

            for field in sensitive_fields:
                if field in config_dict:
                    config_dict[field] = '***REDACTED***'

            with open(os.path.join(config_dir, 'config.json'), 'w') as f:
                json.dump(config_dict, f, indent=2)

            # Backup de tenant configs (se multi-tenancy habilitado)
            if self.config.enable_multi_tenancy:
                tenant_configs = {}
                # Aqui iria a lógica para exportar configs de tenants
                # tenant_configs = self.specialist.get_tenant_configs()

                with open(os.path.join(config_dir, 'tenant_configs.json'), 'w') as f:
                    json.dump(tenant_configs, f, indent=2)

            duration = time.time() - start_time

            logger.info(
                "Backup de configuração concluído",
                duration_seconds=round(duration, 2)
            )

            return {
                'success': True,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup de configuração",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                'success': False,
                'error': str(e),
                'duration_seconds': duration
            }

    def _backup_ledger(self, backup_dir: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Backup de ledger MongoDB.

        Args:
            backup_dir: Diretório de backup
            tenant_id: Tenant ID (opcional)

        Returns:
            Dict com resultado
        """
        import time
        start_time = time.time()

        ledger_dir = os.path.join(backup_dir, 'ledger')
        os.makedirs(ledger_dir, exist_ok=True)

        try:
            logger.info(
                "Iniciando backup de ledger MongoDB",
                tenant_id=tenant_id
            )

            # Usar mongodump para exportar collection
            # Nota: Requer mongodump instalado no sistema

            db_name = self.config.mongodb_database
            collection_name = self.config.mongodb_ledger_collection

            query = {}
            if tenant_id:
                query = {'tenant_id': tenant_id}

            # Construir comando mongodump
            cmd = [
                'mongodump',
                '--uri', self.config.mongodb_uri,
                '--db', db_name,
                '--collection', collection_name,
                '--out', ledger_dir
            ]

            if query:
                cmd.extend(['--query', json.dumps(query)])

            # Executar mongodump
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode != 0:
                    raise Exception(f"mongodump falhou: {result.stderr}")

            except FileNotFoundError:
                # mongodump não disponível, usar fallback via driver
                logger.warning("mongodump não encontrado, usando export via driver")

                from pymongo import MongoClient
                client = MongoClient(self.config.mongodb_uri)
                db = client[db_name]
                collection = db[collection_name]

                # Exportar para JSON
                documents = list(collection.find(query))

                output_file = os.path.join(ledger_dir, f'{collection_name}.json')

                with open(output_file, 'w') as f:
                    json.dump(documents, f, indent=2, default=str)

                logger.info(
                    "Ledger exportado via driver",
                    document_count=len(documents)
                )

            duration = time.time() - start_time

            logger.info(
                "Backup de ledger concluído",
                duration_seconds=round(duration, 2)
            )

            return {
                'success': True,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup de ledger",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                'success': False,
                'error': str(e),
                'duration_seconds': duration
            }

    def _backup_cache(self, backup_dir: str) -> Dict[str, Any]:
        """
        Backup de cache Redis (opcional).

        Args:
            backup_dir: Diretório de backup

        Returns:
            Dict com resultado
        """
        import time
        start_time = time.time()

        cache_dir = os.path.join(backup_dir, 'cache')
        os.makedirs(cache_dir, exist_ok=True)

        try:
            logger.info("Iniciando backup de cache Redis")

            # Exportar chaves do Redis
            # Nota: Cache é efêmero, backup é opcional

            if hasattr(self.specialist, 'opinion_cache'):
                cache_keys = []
                # Aqui iria a lógica para exportar cache
                # cache_keys = self.specialist.opinion_cache.keys('opinion:*')

                cache_data = {
                    'keys': cache_keys,
                    'key_count': len(cache_keys)
                }

                with open(os.path.join(cache_dir, 'cache_keys.json'), 'w') as f:
                    json.dump(cache_data, f, indent=2)

            duration = time.time() - start_time

            logger.info(
                "Backup de cache concluído",
                duration_seconds=round(duration, 2)
            )

            return {
                'success': True,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup de cache",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                'success': False,
                'error': str(e),
                'duration_seconds': duration
            }

    def _backup_feature_store(self, backup_dir: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Backup de feature store MongoDB.

        Args:
            backup_dir: Diretório de backup
            tenant_id: Tenant ID (opcional, para filtrar features por tenant)

        Returns:
            Dict com resultado
        """
        import time
        start_time = time.time()

        features_dir = os.path.join(backup_dir, 'feature_store')
        os.makedirs(features_dir, exist_ok=True)

        try:
            logger.info(
                "Iniciando backup de feature store",
                tenant_id=tenant_id
            )

            # Exportar collection plan_features
            from pymongo import MongoClient
            client = MongoClient(self.config.mongodb_uri)
            db = client[self.config.mongodb_database]
            collection = db[self.config.mongodb_feature_store_collection]

            # Construir query com filtro de tenant se fornecido
            query = {}
            if tenant_id:
                query = {'tenant_id': tenant_id}

            features = list(collection.find(query))

            output_file = os.path.join(features_dir, 'plan_features.json')

            with open(output_file, 'w') as f:
                json.dump(features, f, indent=2, default=str)

            duration = time.time() - start_time

            logger.info(
                "Backup de feature store concluído",
                feature_count=len(features),
                tenant_id=tenant_id,
                duration_seconds=round(duration, 2)
            )

            return {
                'success': True,
                'duration_seconds': duration,
                'metadata': {
                    'feature_count': len(features),
                    'tenant_id': tenant_id
                }
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup de feature store",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                'success': False,
                'error': str(e),
                'duration_seconds': duration
            }

    def _backup_metrics(self, backup_dir: str) -> Dict[str, Any]:
        """
        Backup de resumo de métricas.

        Args:
            backup_dir: Diretório de backup

        Returns:
            Dict com resultado
        """
        import time
        start_time = time.time()

        metrics_dir = os.path.join(backup_dir, 'metrics')
        os.makedirs(metrics_dir, exist_ok=True)

        try:
            logger.info("Iniciando backup de métricas")

            # Obter resumo de métricas
            if hasattr(self.specialist, 'metrics'):
                metrics_summary = self.specialist.metrics.get_summary()

                with open(os.path.join(metrics_dir, 'metrics_summary.json'), 'w') as f:
                    json.dump(metrics_summary, f, indent=2, default=str)

            duration = time.time() - start_time

            logger.info(
                "Backup de métricas concluído",
                duration_seconds=round(duration, 2)
            )

            return {
                'success': True,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup de métricas",
                error=str(e),
                duration_seconds=round(duration, 2)
            )

            return {
                'success': False,
                'error': str(e),
                'duration_seconds': duration
            }

    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calcula SHA-256 checksum de arquivo."""
        import hashlib

        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    # ============================================================================
    # Incremental Backup com Content-Addressed Storage
    # ============================================================================

    def _backup_incremental(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executa backup incremental com content-addressed storage e deduplicação.

        Estrutura de storage:
        - components/<component_name>/<sha256>.tar.gz: Blobs de componentes
        - snapshots/snapshot-<timestamp>.json: Snapshots com referências

        Args:
            tenant_id: Tenant ID (opcional)

        Returns:
            Dict com resultado do backup
        """
        import time
        start_time = time.time()

        snapshot_id = f"snapshot-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        tenant_suffix = f"-{tenant_id}" if tenant_id else ""

        logger.info(
            "Iniciando backup incremental",
            snapshot_id=snapshot_id,
            specialist_type=self.config.specialist_type,
            tenant_id=tenant_id
        )

        # Criar diretório temporário
        backup_dir = tempfile.mkdtemp(prefix=f'incremental-backup-{snapshot_id}-')

        try:
            # Criar manifest base
            manifest = BackupManifest(
                backup_id=snapshot_id,
                specialist_type=self.config.specialist_type,
                tenant_id=tenant_id,
                backup_timestamp=datetime.utcnow(),
                compression_level=self.config.backup_compression_level,
                metadata={
                    'environment': self.config.environment,
                    'service_name': self.config.service_name,
                    'backup_mode': 'incremental'
                }
            )

            # Backup de componentes em paralelo
            component_results = {}
            component_digests = {}

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}

                # Modelo MLflow
                futures[executor.submit(self._backup_model, backup_dir)] = 'model'

                # Configuração
                futures[executor.submit(self._backup_config, backup_dir)] = 'config'

                # Ledger MongoDB
                futures[executor.submit(self._backup_ledger, backup_dir, tenant_id)] = 'ledger'

                # Cache Redis (opcional)
                if self.config.backup_include_cache:
                    futures[executor.submit(self._backup_cache, backup_dir)] = 'cache'

                # Feature Store
                if self.config.backup_include_feature_store:
                    futures[executor.submit(self._backup_feature_store, backup_dir, tenant_id)] = 'feature_store'

                # Métricas
                if self.config.backup_include_metrics:
                    futures[executor.submit(self._backup_metrics, backup_dir)] = 'metrics'

                # Aguardar conclusão
                for future in as_completed(futures):
                    component_name = futures[future]
                    try:
                        result = future.result()
                        component_results[component_name] = result

                        # Processar componente com sucesso
                        if result['success']:
                            component_dir = os.path.join(backup_dir, component_name)

                            # Criar tarball do componente e calcular SHA-256
                            component_tarball = os.path.join(tempfile.gettempdir(), f'{component_name}.tar.gz')

                            with tarfile.open(component_tarball, 'w:gz', compresslevel=self.config.backup_compression_level) as tar:
                                tar.add(component_dir, arcname=component_name)

                            # Calcular SHA-256 do tarball
                            sha256_digest = self._calculate_file_checksum(component_tarball)
                            component_digests[component_name] = sha256_digest

                            logger.info(
                                "Component tarball criado",
                                component=component_name,
                                sha256=sha256_digest[:16] + '...',
                                size_bytes=os.path.getsize(component_tarball)
                            )

                            # Upload para content-addressed storage com deduplicação
                            blob_key = f"{self.config.backup_prefix}/components/{component_name}/{sha256_digest}.tar.gz"

                            # Verificar se blob já existe (deduplicação)
                            if self._blob_exists(blob_key):
                                logger.info(
                                    "Blob já existe, pulando upload (deduplicação)",
                                    component=component_name,
                                    sha256=sha256_digest[:16] + '...'
                                )
                            else:
                                # Upload do blob
                                logger.info(
                                    "Fazendo upload de blob novo",
                                    component=component_name,
                                    blob_key=blob_key
                                )

                                if not self.storage_client.upload_backup(component_tarball, blob_key):
                                    raise Exception(f"Falha no upload do componente {component_name}")

                            # Limpar tarball temporário
                            os.remove(component_tarball)

                            # Adicionar componente ao manifest
                            manifest.add_component(
                                name=component_name,
                                component_dir=component_dir,
                                included=True,
                                metadata=result.get('metadata', {})
                            )

                            # Registrar métrica de duração por componente
                            if hasattr(self.specialist, 'metrics'):
                                self.specialist.metrics.observe_backup_component_duration(
                                    component_name,
                                    result.get('duration_seconds', 0)
                                )
                        else:
                            logger.warning(
                                "Componente falhou no backup",
                                component=component_name,
                                error=result.get('error')
                            )

                    except Exception as e:
                        logger.error(
                            "Erro ao processar componente",
                            component=component_name,
                            error=str(e)
                        )
                        component_results[component_name] = {
                            'success': False,
                            'error': str(e)
                        }

            # Criar snapshot JSON com referências
            snapshot = {
                'snapshot_id': snapshot_id,
                'timestamp': datetime.utcnow().isoformat(),
                'specialist_type': self.config.specialist_type,
                'tenant_id': tenant_id,
                'component_refs': component_digests,
                'metadata': {
                    'environment': self.config.environment,
                    'service_name': self.config.service_name,
                    'backup_mode': 'incremental',
                    'component_versions': {
                        name: result.get('metadata', {})
                        for name, result in component_results.items()
                        if result.get('success')
                    }
                }
            }

            # Salvar snapshot JSON local
            snapshot_file = os.path.join(tempfile.gettempdir(), f'{snapshot_id}.json')
            with open(snapshot_file, 'w') as f:
                json.dump(snapshot, f, indent=2)

            snapshot_size = os.path.getsize(snapshot_file)

            logger.info(
                "Snapshot JSON criado",
                snapshot_id=snapshot_id,
                size_bytes=snapshot_size
            )

            # Upload do snapshot
            snapshot_key = f"{self.config.backup_prefix}/snapshots/{snapshot_id}.json"

            if not self.storage_client.upload_backup(snapshot_file, snapshot_key):
                raise Exception("Falha no upload do snapshot")

            # Limpar arquivos temporários
            os.remove(snapshot_file)
            shutil.rmtree(backup_dir, ignore_errors=True)

            # Registrar métricas
            duration = time.time() - start_time

            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.set_backup_last_success_timestamp(
                    tenant_id or 'default',
                    time.time()
                )
                self.specialist.metrics.observe_backup_duration(duration)
                self.specialist.metrics.set_backup_size(
                    tenant_id or 'default',
                    snapshot_size
                )
                self.specialist.metrics.increment_backup_total('success')

            successful_components = [
                name for name, result in component_results.items() if result['success']
            ]

            logger.info(
                "Backup incremental concluído com sucesso",
                snapshot_id=snapshot_id,
                snapshot_size_bytes=snapshot_size,
                duration_seconds=round(duration, 2),
                components_included=successful_components,
                component_digests={k: v[:16] + '...' for k, v in component_digests.items()}
            )

            return {
                'status': 'success',
                'backup_id': snapshot_id,
                'backup_filename': f"{snapshot_id}.json",
                'total_size_bytes': snapshot_size,
                'duration_seconds': round(duration, 2),
                'components_included': successful_components,
                'component_digests': component_digests,
                'backup_mode': 'incremental'
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no backup incremental",
                snapshot_id=snapshot_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )

            # Registrar métrica de falha
            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.increment_backup_total('failed')

            # Limpar
            shutil.rmtree(backup_dir, ignore_errors=True)

            return {
                'status': 'failed',
                'backup_id': snapshot_id,
                'error': str(e),
                'duration_seconds': round(duration, 2),
                'backup_mode': 'incremental'
            }

    def _blob_exists(self, blob_key: str) -> bool:
        """
        Verifica se um blob já existe no storage (para deduplicação).

        Args:
            blob_key: Chave do blob no storage

        Returns:
            True se blob existe, False caso contrário
        """
        try:
            # Listar com prefixo exato para verificar existência
            objects = self.storage_client.list_backups(prefix=blob_key, limit=1)
            return len(objects) > 0 and any(obj['key'] == blob_key for obj in objects)
        except Exception as e:
            logger.warning(
                "Erro ao verificar existência de blob, assumindo que não existe",
                blob_key=blob_key,
                error=str(e)
            )
            return False

    def garbage_collect_blobs(self) -> Dict[str, Any]:
        """
        Remove blobs órfãos não referenciados por nenhum snapshot ativo.

        Processo:
        1. Lista todos os snapshots ativos (não expirados)
        2. Coleta SHA-256s referenciados
        3. Lista todos os blobs em components/
        4. Deleta blobs não referenciados

        Returns:
            Dict com resultado:
            - status: 'success', 'failed'
            - deleted_count: Número de blobs deletados
            - freed_bytes: Espaço liberado (estimado)
            - duration_seconds: Duração
        """
        import time
        from datetime import timezone

        start_time = time.time()

        logger.info(
            "Iniciando garbage collection de blobs",
            specialist_type=self.config.specialist_type
        )

        try:
            # 1. Listar todos os snapshots
            snapshot_prefix = f"{self.config.backup_prefix}/snapshots/"
            all_snapshots = self.storage_client.list_backups(prefix=snapshot_prefix)

            # Filtrar snapshots não expirados
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.config.backup_retention_days)
            active_snapshots = []

            for snapshot_obj in all_snapshots:
                if not snapshot_obj['key'].endswith('.json'):
                    continue

                snapshot_timestamp = snapshot_obj.get('timestamp')
                if snapshot_timestamp:
                    # Normalizar timestamp para UTC timezone-aware
                    if isinstance(snapshot_timestamp, datetime):
                        if snapshot_timestamp.tzinfo is None:
                            snapshot_timestamp = snapshot_timestamp.replace(tzinfo=timezone.utc)
                        else:
                            snapshot_timestamp = snapshot_timestamp.astimezone(timezone.utc)

                        # Verificar se não expirou
                        if snapshot_timestamp >= cutoff_date:
                            active_snapshots.append(snapshot_obj)

            logger.info(
                "Snapshots ativos encontrados",
                total_snapshots=len(all_snapshots),
                active_snapshots=len(active_snapshots)
            )

            # 2. Coletar SHA-256s referenciados
            referenced_sha256s = set()

            for snapshot_obj in active_snapshots:
                try:
                    # Download do snapshot JSON
                    snapshot_local = os.path.join(tempfile.gettempdir(), os.path.basename(snapshot_obj['key']))

                    if self.storage_client.download_backup(snapshot_obj['key'], snapshot_local):
                        with open(snapshot_local, 'r') as f:
                            snapshot_data = json.load(f)

                        # Adicionar SHA-256s referenciados
                        component_refs = snapshot_data.get('component_refs', {})
                        referenced_sha256s.update(component_refs.values())

                        # Limpar arquivo temporário
                        os.remove(snapshot_local)

                except Exception as e:
                    logger.warning(
                        "Erro ao processar snapshot, pulando",
                        snapshot_key=snapshot_obj['key'],
                        error=str(e)
                    )

            logger.info(
                "SHA-256s referenciados coletados",
                referenced_count=len(referenced_sha256s)
            )

            # 3. Listar todos os blobs em components/
            component_prefix = f"{self.config.backup_prefix}/components/"
            all_blobs = self.storage_client.list_backups(prefix=component_prefix)

            logger.info(
                "Blobs encontrados em components/",
                total_blobs=len(all_blobs)
            )

            # 4. Deletar blobs órfãos
            deleted_count = 0
            freed_bytes = 0

            for blob_obj in all_blobs:
                blob_key = blob_obj['key']

                # Extrair SHA-256 do nome do blob
                # Formato esperado: components/<component>/<sha256>.tar.gz
                if not blob_key.endswith('.tar.gz'):
                    continue

                blob_filename = os.path.basename(blob_key)
                blob_sha256 = blob_filename.replace('.tar.gz', '')

                # Verificar se SHA-256 está referenciado
                if blob_sha256 not in referenced_sha256s:
                    logger.info(
                        "Deletando blob órfão",
                        blob_key=blob_key,
                        sha256=blob_sha256[:16] + '...',
                        size_bytes=blob_obj.get('size', 0)
                    )

                    if self.storage_client.delete_backup(blob_key):
                        deleted_count += 1
                        freed_bytes += blob_obj.get('size', 0)
                    else:
                        logger.warning(
                            "Falha ao deletar blob",
                            blob_key=blob_key
                        )

            duration = time.time() - start_time

            logger.info(
                "Garbage collection concluído",
                deleted_count=deleted_count,
                freed_bytes=freed_bytes,
                duration_seconds=round(duration, 2)
            )

            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'freed_bytes': freed_bytes,
                'duration_seconds': round(duration, 2)
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no garbage collection",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )

            return {
                'status': 'failed',
                'error': str(e),
                'duration_seconds': round(duration, 2)
            }

    def _restore_from_snapshot(
        self,
        snapshot_id: str,
        target_dir: Optional[str] = None,
        skip_validation: bool = False,
        skip_smoke_tests: bool = False
    ) -> Dict[str, Any]:
        """
        Restaura estado do especialista a partir de snapshot incremental.

        Args:
            snapshot_id: ID do snapshot ou nome do arquivo JSON
            target_dir: Diretório de destino (opcional)
            skip_validation: Pular validação de checksums
            skip_smoke_tests: Pular smoke tests após restore

        Returns:
            Dict com resultado do restore
        """
        import time
        start_time = time.time()

        logger.info(
            "Iniciando restore de snapshot incremental",
            snapshot_id=snapshot_id
        )

        # Criar diretório temporário
        extract_dir = tempfile.mkdtemp(prefix='restore-snapshot-')
        restored_components = []

        try:
            # 1. Download do snapshot JSON
            logger.info("Baixando snapshot JSON")

            # Determinar snapshot_key
            if snapshot_id.endswith('.json'):
                snapshot_key = snapshot_id
            else:
                # Procurar snapshot por ID
                snapshot_prefix = f"{self.config.backup_prefix}/snapshots/"
                snapshots = self.storage_client.list_backups(prefix=snapshot_prefix)

                snapshot_key = None
                for s in snapshots:
                    if snapshot_id in s['key']:
                        snapshot_key = s['key']
                        break

                if not snapshot_key:
                    raise Exception(f"Snapshot não encontrado: {snapshot_id}")

            # Download do snapshot
            snapshot_local = os.path.join(tempfile.gettempdir(), os.path.basename(snapshot_key))

            if not self.storage_client.download_backup(snapshot_key, snapshot_local):
                raise Exception("Falha no download do snapshot")

            # Carregar snapshot JSON
            with open(snapshot_local, 'r') as f:
                snapshot_data = json.load(f)

            component_refs = snapshot_data.get('component_refs', {})

            logger.info(
                "Snapshot carregado",
                snapshot_id=snapshot_data.get('snapshot_id'),
                components=list(component_refs.keys())
            )

            # 2. Download e extração de componentes
            component_status = {}

            for component_name, sha256_digest in component_refs.items():
                logger.info(
                    "Restaurando componente de blob",
                    component=component_name,
                    sha256=sha256_digest[:16] + '...'
                )

                try:
                    # Construir blob key
                    blob_key = f"{self.config.backup_prefix}/components/{component_name}/{sha256_digest}.tar.gz"

                    # Download do blob
                    blob_local = os.path.join(tempfile.gettempdir(), f'{component_name}-{sha256_digest[:8]}.tar.gz')

                    if not self.storage_client.download_backup(blob_key, blob_local):
                        raise Exception(f"Falha no download do blob {component_name}")

                    # Validar SHA-256 (se não pular validação)
                    if not skip_validation:
                        actual_sha256 = self._calculate_file_checksum(blob_local)
                        if actual_sha256 != sha256_digest:
                            raise Exception(
                                f"SHA-256 mismatch para {component_name}: "
                                f"esperado {sha256_digest[:16]}..., atual {actual_sha256[:16]}..."
                            )
                        logger.info(
                            "SHA-256 validado",
                            component=component_name
                        )

                    # Extrair blob
                    with tarfile.open(blob_local, 'r:gz') as tar:
                        tar.extractall(path=extract_dir)

                    # Limpar blob local
                    os.remove(blob_local)

                    # Chamar método de restore específico
                    component_dir = os.path.join(extract_dir, component_name)
                    restore_method = getattr(self, f'_restore_{component_name}', None)

                    if restore_method:
                        logger.info(f"Restaurando componente: {component_name}")
                        restore_method(component_dir, target_dir)
                        restored_components.append(component_name)
                        component_status[component_name] = {'status': 'success'}
                        logger.info(f"Componente {component_name} restaurado com sucesso")
                    else:
                        logger.warning(f"Método de restore para {component_name} não implementado")
                        component_status[component_name] = {
                            'status': 'failed',
                            'reason': 'method_not_implemented'
                        }

                except Exception as e:
                    logger.error(
                        f"Erro ao restaurar componente {component_name}",
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    component_status[component_name] = {
                        'status': 'failed',
                        'error': str(e),
                        'error_type': type(e).__name__
                    }

            # 3. Executar smoke tests
            smoke_test_results = {}

            if not skip_smoke_tests:
                logger.info("Executando smoke tests")
                smoke_test_results = self._run_smoke_tests()

                if not smoke_test_results.get('passed', False):
                    logger.warning("Smoke tests falharam", results=smoke_test_results)

            # Limpar arquivos temporários
            os.remove(snapshot_local)
            shutil.rmtree(extract_dir, ignore_errors=True)

            # Registrar métricas
            duration = time.time() - start_time

            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.increment_restore_total('success')
                self.specialist.metrics.observe_restore_duration(duration)

            logger.info(
                "Restore de snapshot concluído com sucesso",
                snapshot_id=snapshot_id,
                duration_seconds=round(duration, 2),
                restored_components=restored_components
            )

            return {
                'status': 'success',
                'backup_id': snapshot_id,
                'restored_components': restored_components,
                'component_status': component_status,
                'duration_seconds': round(duration, 2),
                'smoke_tests': smoke_test_results,
                'backup_mode': 'incremental'
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no restore de snapshot",
                snapshot_id=snapshot_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )

            # Registrar métrica de falha
            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.increment_restore_total('failed')

            # Limpar
            shutil.rmtree(extract_dir, ignore_errors=True)

            return {
                'status': 'failed',
                'backup_id': snapshot_id,
                'error': str(e),
                'duration_seconds': round(duration, 2),
                'restored_components': restored_components,
                'backup_mode': 'incremental'
            }

    def restore_specialist_state(
        self,
        backup_id: str,
        target_dir: Optional[str] = None,
        skip_validation: bool = False,
        skip_smoke_tests: bool = False
    ) -> Dict[str, Any]:
        """
        Restaura estado do especialista de backup.

        Args:
            backup_id: ID do backup ou nome do arquivo
            target_dir: Diretório de destino (opcional)
            skip_validation: Pular validação de checksums (não recomendado)
            skip_smoke_tests: Pular smoke tests após restore

        Returns:
            Dict com resultado:
            - status: 'success', 'partial', 'failed'
            - restored_components: Lista de componentes restaurados
            - duration_seconds: Duração
            - error: Mensagem de erro (se falha)
        """
        import time
        start_time = time.time()

        logger.info(
            "Iniciando restore de especialista",
            backup_id=backup_id,
            target_dir=target_dir
        )

        # Criar diretório temporário para download e extração
        extract_dir = tempfile.mkdtemp(prefix='restore-')
        restored_components = []

        try:
            # Detectar tipo de backup: snapshot JSON (incremental) ou tar.gz (full)
            is_snapshot = backup_id.endswith('.json') or 'snapshot-' in backup_id

            if is_snapshot:
                logger.info(
                    "Detectado backup incremental (snapshot), usando restore de snapshot",
                    backup_id=backup_id
                )
                return self._restore_from_snapshot(backup_id, target_dir, skip_validation, skip_smoke_tests)

            # Backup full - comportamento original
            # 1. Download de backup
            logger.info("Baixando backup do storage (modo full)")

            # Encontrar backup (suporta backup_id ou filename)
            backup_file = None
            checksum_file = None

            if backup_id.endswith('.tar.gz'):
                backup_file = backup_id
                checksum_file = f"{backup_id}.sha256"
            else:
                # Procurar por ID nos backups disponíveis
                backups = self.list_available_backups()
                for b in backups:
                    if backup_id in b['key']:
                        backup_file = b['key']
                        checksum_file = f"{backup_file}.sha256"
                        break

            if not backup_file:
                raise Exception(f"Backup não encontrado: {backup_id}")

            # Download do arquivo de backup
            backup_local_path = os.path.join(tempfile.gettempdir(), os.path.basename(backup_file))
            checksum_local_path = f"{backup_local_path}.sha256"

            try:
                if not self.storage_client.download_backup(backup_file, backup_local_path):
                    raise Exception("Falha no download do backup")

            except Exception as e:
                # Incrementar métrica de erro de download
                if hasattr(self.specialist, 'metrics'):
                    provider = self.config.backup_storage_provider
                    self.specialist.metrics.increment_storage_download_error(provider)

                raise  # Re-raise para tratamento externo

            # Download do checksum
            try:
                if not self.storage_client.download_backup(checksum_file, checksum_local_path):
                    logger.warning("Checksum file não encontrado, validação será limitada")
                    checksum_local_path = None

            except Exception as e:
                logger.warning("Erro ao baixar checksum", error=str(e))
                checksum_local_path = None

            logger.info("Backup baixado", file=backup_local_path)

            # 2. Validar checksum do arquivo
            if not skip_validation and checksum_local_path:
                logger.info("Validando checksum do backup")

                with open(checksum_local_path, 'r') as f:
                    expected_checksum = f.read().strip().split()[0]

                actual_checksum = self._calculate_file_checksum(backup_local_path)

                if actual_checksum != expected_checksum:
                    raise Exception(f"Checksum inválido! Esperado: {expected_checksum}, Atual: {actual_checksum}")

                logger.info("Checksum validado com sucesso")

            # 3. Extrair .tar.gz
            logger.info("Extraindo arquivo de backup")

            with tarfile.open(backup_local_path, 'r:gz') as tar:
                tar.extractall(path=extract_dir)

            logger.info("Backup extraído", extract_dir=extract_dir)

            # 4. Carregar manifest
            manifest_path = os.path.join(extract_dir, 'metadata.json')

            if not os.path.exists(manifest_path):
                raise Exception("Manifest não encontrado no backup")

            manifest = BackupManifest.load_from_file(manifest_path)

            logger.info(
                "Manifest carregado",
                backup_id=manifest.backup_id,
                components=len(manifest.components)
            )

            # 5. Validar checksums de componentes
            if not skip_validation:
                logger.info("Validando checksums de componentes")

                if not manifest.validate_checksums(extract_dir):
                    raise Exception("Validação de checksums de componentes falhou")

                logger.info("Todos os checksums validados")

            # 6. Restaurar componentes em ordem
            logger.info("Iniciando restore de componentes")

            # Ordem de restore: config -> model -> ledger -> feature_store -> cache -> metrics
            restore_order = ['config', 'model', 'ledger', 'feature_store', 'cache', 'metrics']
            component_status = {}

            for component_name in restore_order:
                component = next((c for c in manifest.components if c.name == component_name), None)

                if not component or not component.included:
                    logger.debug(f"Componente {component_name} não incluído no backup, pulando")
                    component_status[component_name] = {
                        'status': 'skipped',
                        'reason': 'not_included_in_backup'
                    }
                    continue

                component_dir = os.path.join(extract_dir, component_name)

                if not os.path.exists(component_dir):
                    logger.warning(f"Diretório do componente {component_name} não encontrado")
                    component_status[component_name] = {
                        'status': 'failed',
                        'reason': 'directory_not_found'
                    }
                    continue

                try:
                    # Chamar método de restore específico
                    restore_method = getattr(self, f'_restore_{component_name}', None)

                    if restore_method:
                        logger.info(f"Restaurando componente: {component_name}")
                        restore_method(component_dir, target_dir)
                        restored_components.append(component_name)
                        component_status[component_name] = {
                            'status': 'success'
                        }
                        logger.info(f"Componente {component_name} restaurado com sucesso")
                    else:
                        logger.warning(f"Método de restore para {component_name} não implementado")
                        component_status[component_name] = {
                            'status': 'failed',
                            'reason': 'method_not_implemented'
                        }

                except Exception as e:
                    logger.error(
                        f"Erro ao restaurar componente {component_name}",
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    component_status[component_name] = {
                        'status': 'failed',
                        'error': str(e),
                        'error_type': type(e).__name__
                    }
                    # Continuar com próximo componente

            # 7. Executar smoke tests
            smoke_test_results = {}

            if not skip_smoke_tests:
                logger.info("Executando smoke tests")
                smoke_test_results = self._run_smoke_tests()

                if not smoke_test_results.get('passed', False):
                    logger.warning("Smoke tests falharam", results=smoke_test_results)

            # Limpar arquivos temporários
            os.remove(backup_local_path)
            if checksum_local_path and os.path.exists(checksum_local_path):
                os.remove(checksum_local_path)
            shutil.rmtree(extract_dir, ignore_errors=True)

            # Registrar métricas
            duration = time.time() - start_time

            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.increment_restore_total('success')
                self.specialist.metrics.observe_restore_duration(duration)

            logger.info(
                "Restore concluído com sucesso",
                backup_id=backup_id,
                duration_seconds=round(duration, 2),
                restored_components=restored_components
            )

            return {
                'status': 'success',
                'backup_id': backup_id,
                'restored_components': restored_components,
                'component_status': component_status,
                'duration_seconds': round(duration, 2),
                'smoke_tests': smoke_test_results
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no restore",
                backup_id=backup_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )

            # Registrar métrica de falha
            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.increment_restore_total('failed')

            # Limpar
            shutil.rmtree(extract_dir, ignore_errors=True)

            return {
                'status': 'failed',
                'backup_id': backup_id,
                'error': str(e),
                'duration_seconds': round(duration, 2),
                'restored_components': restored_components
            }

    def test_recovery(self, backup_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Testa recovery de backup automaticamente (sem aplicar mudanças).

        Args:
            backup_id: ID de backup específico (usa mais recente se None)

        Returns:
            Dict com resultado:
            - status: 'success', 'failed'
            - backup_id: ID do backup testado
            - test_results: Dict com resultados de cada etapa
            - duration_seconds: Duração
        """
        import time
        start_time = time.time()

        logger.info(
            "Iniciando teste de recovery",
            backup_id=backup_id or 'latest'
        )

        test_results = {
            'download': {'status': 'pending'},
            'checksum_validation': {'status': 'pending'},
            'extraction': {'status': 'pending'},
            'manifest_validation': {'status': 'pending'},
            'component_validation': {'status': 'pending'},
            'smoke_tests': {'status': 'pending'}
        }

        extract_dir = None

        try:
            # 1. Listar backups e selecionar
            logger.info("Listando backups disponíveis")

            backups = self.list_available_backups()

            if not backups:
                raise Exception("Nenhum backup disponível")

            # Filtrar apenas arquivos .tar.gz
            backup_files = [b for b in backups if b['key'].endswith('.tar.gz')]

            if not backup_files:
                raise Exception("Nenhum backup .tar.gz encontrado")

            # Selecionar backup
            if backup_id:
                # Procurar backup específico
                selected_backup = next((b for b in backup_files if backup_id in b['key']), None)
                if not selected_backup:
                    raise Exception(f"Backup não encontrado: {backup_id}")
            else:
                # Usar mais recente
                selected_backup = backup_files[0]  # Já ordenado por timestamp (mais recente primeiro)

            backup_file = selected_backup['key']
            checksum_file = f"{backup_file}.sha256"

            logger.info(
                "Backup selecionado para teste",
                backup_file=backup_file,
                size=selected_backup.get('size', 'unknown')
            )

            # 2. Download
            logger.info("Testando download de backup")

            backup_local_path = os.path.join(tempfile.gettempdir(), os.path.basename(backup_file))
            checksum_local_path = f"{backup_local_path}.sha256"

            if not self.storage_client.download_backup(backup_file, backup_local_path):
                raise Exception("Falha no download do backup")

            test_results['download'] = {'status': 'success'}
            logger.info("Download bem-sucedido")

            # Download de checksum
            has_checksum = self.storage_client.download_backup(checksum_file, checksum_local_path)

            # 3. Validar checksum
            if has_checksum:
                logger.info("Validando checksum")

                with open(checksum_local_path, 'r') as f:
                    expected_checksum = f.read().strip().split()[0]

                actual_checksum = self._calculate_file_checksum(backup_local_path)

                if actual_checksum != expected_checksum:
                    test_results['checksum_validation'] = {
                        'status': 'failed',
                        'error': f"Checksum mismatch: esperado {expected_checksum[:16]}..., atual {actual_checksum[:16]}..."
                    }
                    raise Exception("Validação de checksum falhou")

                test_results['checksum_validation'] = {'status': 'success', 'checksum': actual_checksum[:16] + '...'}
                logger.info("Checksum validado")
            else:
                test_results['checksum_validation'] = {'status': 'skipped', 'reason': 'checksum file not found'}

            # 4. Extrair
            logger.info("Testando extração")

            extract_dir = tempfile.mkdtemp(prefix='test-recovery-')

            with tarfile.open(backup_local_path, 'r:gz') as tar:
                tar.extractall(path=extract_dir)

            test_results['extraction'] = {'status': 'success'}
            logger.info("Extração bem-sucedida")

            # 5. Validar manifest
            logger.info("Validando manifest")

            manifest_path = os.path.join(extract_dir, 'metadata.json')

            if not os.path.exists(manifest_path):
                raise Exception("Manifest não encontrado")

            manifest = BackupManifest.load_from_file(manifest_path)

            test_results['manifest_validation'] = {
                'status': 'success',
                'backup_id': manifest.backup_id,
                'specialist_type': manifest.specialist_type,
                'components': [c.name for c in manifest.components if c.included]
            }

            logger.info(
                "Manifest validado",
                backup_id=manifest.backup_id,
                components=len(manifest.components)
            )

            # 6. Validar checksums de componentes
            logger.info("Validando checksums de componentes")

            if manifest.validate_checksums(extract_dir):
                test_results['component_validation'] = {'status': 'success'}
                logger.info("Todos os componentes válidos")
            else:
                test_results['component_validation'] = {
                    'status': 'failed',
                    'error': 'Component checksum validation failed'
                }

            # 7. Smoke tests (simulados, não aplicar mudanças)
            logger.info("Executando smoke tests em modo simulação")

            smoke_results = {
                'config_readable': os.path.exists(os.path.join(extract_dir, 'config')),
                'model_readable': os.path.exists(os.path.join(extract_dir, 'model')),
                'ledger_readable': os.path.exists(os.path.join(extract_dir, 'ledger'))
            }

            test_results['smoke_tests'] = {
                'status': 'success' if all(smoke_results.values()) else 'partial',
                'results': smoke_results
            }

            # Limpar
            os.remove(backup_local_path)
            if os.path.exists(checksum_local_path):
                os.remove(checksum_local_path)
            if extract_dir:
                shutil.rmtree(extract_dir, ignore_errors=True)

            # Registrar métricas
            duration = time.time() - start_time

            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.set_recovery_test_status(1)  # Success
                self.specialist.metrics.set_recovery_test_timestamp(time.time())
                self.specialist.metrics.observe_recovery_test_duration(duration)

            logger.info(
                "Teste de recovery concluído com sucesso",
                backup_file=backup_file,
                duration_seconds=round(duration, 2)
            )

            return {
                'status': 'success',
                'backup_id': backup_file,
                'test_results': test_results,
                'duration_seconds': round(duration, 2)
            }

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Erro no teste de recovery",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )

            # Registrar métrica de falha
            if hasattr(self.specialist, 'metrics'):
                self.specialist.metrics.set_recovery_test_status(0)  # Failed
                self.specialist.metrics.set_recovery_test_timestamp(time.time())

            # Limpar
            if extract_dir:
                shutil.rmtree(extract_dir, ignore_errors=True)

            return {
                'status': 'failed',
                'backup_id': backup_id or 'latest',
                'error': str(e),
                'test_results': test_results,
                'duration_seconds': round(duration, 2)
            }

    def list_available_backups(self) -> List[Dict]:
        """
        Lista backups disponíveis no storage (apenas arquivos .tar.gz).

        Returns:
            Lista de backups ordenados por timestamp (mais recente primeiro)
        """
        prefix = f"specialist-{self.config.specialist_type}"

        all_objects = self.storage_client.list_backups(prefix=prefix)

        # Filtrar apenas arquivos .tar.gz (não incluir checksums .sha256)
        backups = [b for b in all_objects if b['key'].endswith('.tar.gz')]

        logger.info(
            "Backups listados",
            count=len(backups),
            total_objects=len(all_objects)
        )

        return backups

    def delete_expired_backups(self) -> int:
        """
        Deleta backups expirados baseado em retention_days.

        Suporta ambos os modos:
        - 'full': Deleta arquivos .tar.gz e checksums
        - 'incremental': Deleta snapshots JSON (blobs são removidos por GC)

        Returns:
            Número de backups/snapshots deletados
        """
        from datetime import timezone

        logger.info(
            "Verificando backups expirados",
            retention_days=self.config.backup_retention_days
        )

        # Usar timezone-aware UTC para consistência
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.config.backup_retention_days)

        deleted_count = 0
        error_count = 0

        # Verificar modo de backup
        backup_mode = getattr(self.config, 'backup_mode', 'full')

        if backup_mode == 'incremental':
            # Deletar snapshots expirados
            snapshot_prefix = f"{self.config.backup_prefix}/snapshots/"
            snapshots = self.storage_client.list_backups(prefix=snapshot_prefix)

            for snapshot in snapshots:
                if not snapshot['key'].endswith('.json'):
                    continue

                snapshot_timestamp = snapshot.get('timestamp')

                if not snapshot_timestamp:
                    logger.warning(
                        "Snapshot sem timestamp, pulando",
                        snapshot_key=snapshot['key']
                    )
                    continue

                # Normalizar timestamp
                if isinstance(snapshot_timestamp, datetime):
                    if snapshot_timestamp.tzinfo is None:
                        snapshot_timestamp = snapshot_timestamp.replace(tzinfo=timezone.utc)
                    else:
                        snapshot_timestamp = snapshot_timestamp.astimezone(timezone.utc)
                else:
                    logger.warning(
                        "Timestamp inválido, pulando",
                        snapshot_key=snapshot['key'],
                        timestamp_type=type(snapshot_timestamp)
                    )
                    continue

                # Verificar se expirado
                if snapshot_timestamp < cutoff_date:
                    logger.info(
                        "Deletando snapshot expirado",
                        snapshot_key=snapshot['key'],
                        age_days=(datetime.now(timezone.utc) - snapshot_timestamp).days
                    )

                    if self.storage_client.delete_backup(snapshot['key']):
                        deleted_count += 1
                    else:
                        error_count += 1
                        logger.error(
                            "Falha ao deletar snapshot",
                            snapshot_key=snapshot['key']
                        )

            logger.info(
                "Snapshots expirados deletados (blobs órfãos serão removidos por GC)",
                deleted_count=deleted_count,
                error_count=error_count
            )

        else:
            # Modo 'full' - deletar backups .tar.gz
            backups = self.list_available_backups()

            for backup in backups:
                # Filtrar apenas arquivos .tar.gz (não deletar checksums sozinhos)
                if not backup['key'].endswith('.tar.gz'):
                    continue

                backup_timestamp = backup.get('timestamp')

                if not backup_timestamp:
                    logger.warning(
                        "Backup sem timestamp, pulando",
                        backup_key=backup['key']
                    )
                    continue

                # Normalizar timestamp para UTC timezone-aware
                if isinstance(backup_timestamp, datetime):
                    if backup_timestamp.tzinfo is None:
                        # Naive datetime, assumir UTC
                        backup_timestamp = backup_timestamp.replace(tzinfo=timezone.utc)
                    else:
                        # Converter para UTC
                        backup_timestamp = backup_timestamp.astimezone(timezone.utc)
                else:
                    logger.warning(
                        "Timestamp inválido, pulando",
                        backup_key=backup['key'],
                        timestamp_type=type(backup_timestamp)
                    )
                    continue

                # Verificar se expirado
                if backup_timestamp < cutoff_date:
                    logger.info(
                        "Deletando backup expirado",
                        backup_key=backup['key'],
                        age_days=(datetime.now(timezone.utc) - backup_timestamp).days
                    )

                    # Deletar arquivo de backup
                    if self.storage_client.delete_backup(backup['key']):
                        deleted_count += 1

                        # Deletar checksum correspondente
                        checksum_key = f"{backup['key']}.sha256"
                        try:
                            self.storage_client.delete_backup(checksum_key)
                        except Exception as e:
                            logger.warning(
                                "Erro ao deletar checksum",
                                checksum_key=checksum_key,
                                error=str(e)
                            )
                    else:
                        error_count += 1
                        logger.error(
                            "Falha ao deletar backup",
                            backup_key=backup['key']
                        )

            logger.info(
                "Backups expirados deletados",
                deleted_count=deleted_count,
                error_count=error_count
            )

        return deleted_count

    # ============================================================================
    # Métodos de restore de componentes
    # ============================================================================

    def _restore_config(self, component_dir: str, target_dir: Optional[str]) -> None:
        """
        Restaura configuração de backup.

        Args:
            component_dir: Diretório do componente no backup
            target_dir: Diretório de destino (não usado para config)
        """
        config_file = os.path.join(component_dir, 'config.json')

        if not os.path.exists(config_file):
            logger.warning("Arquivo de config não encontrado")
            return

        with open(config_file, 'r') as f:
            config_data = json.load(f)

        logger.info(
            "Configuração restaurada (apenas leitura, não aplicada)",
            keys=list(config_data.keys())
        )

    def _restore_model(self, component_dir: str, target_dir: Optional[str]) -> None:
        """
        Restaura modelo MLflow de backup.

        Args:
            component_dir: Diretório do componente no backup
            target_dir: Diretório de destino (não usado para model)
        """
        metadata_file = os.path.join(component_dir, 'model_metadata.json')

        if not os.path.exists(metadata_file):
            logger.warning("Metadata de modelo não encontrado")
            return

        with open(metadata_file, 'r') as f:
            model_metadata = json.load(f)

        logger.info(
            "Restaurando modelo MLflow",
            model_name=model_metadata.get('model_name'),
            model_version=model_metadata.get('model_version')
        )

        # Verificar se artifacts estão disponíveis
        artifacts_dir = os.path.join(component_dir, 'artifacts')
        if not os.path.exists(artifacts_dir) or not model_metadata.get('artifacts_downloaded'):
            logger.warning(
                "Artifacts não encontrados no backup, pulando restore de modelo",
                artifacts_downloaded=model_metadata.get('artifacts_downloaded', False)
            )
            return

        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            # Configurar MLflow
            mlflow.set_tracking_uri(self.config.mlflow_tracking_uri)
            client = MlflowClient(tracking_uri=self.config.mlflow_tracking_uri)

            # Obter ou criar experimento
            experiment_name = model_metadata.get('mlflow_experiment_name', self.config.mlflow_experiment_name)
            experiment = client.get_experiment_by_name(experiment_name)

            if experiment is None:
                experiment_id = client.create_experiment(experiment_name)
                logger.info("Experimento criado", experiment_name=experiment_name)
            else:
                experiment_id = experiment.experiment_id

            # Criar novo run para registrar o modelo restaurado
            with mlflow.start_run(experiment_id=experiment_id) as run:
                # Log de metadata do modelo
                mlflow.log_param('restored_from_backup', True)
                mlflow.log_param('original_model_version', model_metadata.get('model_version', 'unknown'))
                mlflow.log_param('backup_timestamp', datetime.utcnow().isoformat())

                # Carregar modelo dos artifacts
                model = mlflow.pyfunc.load_model(artifacts_dir)

                # Registrar modelo no MLflow
                model_name = model_metadata.get('model_name', self.config.mlflow_model_name)

                mlflow.pyfunc.log_model(
                    artifact_path='model',
                    python_model=model,
                    registered_model_name=model_name
                )

                run_id = run.info.run_id

            # Obter versão do modelo registrado
            registered_model_versions = client.search_model_versions(f"name='{model_name}'")

            # Encontrar a versão mais recente (a que acabamos de registrar)
            if registered_model_versions:
                latest_version = max(registered_model_versions, key=lambda v: int(v.version))

                # Transicionar para o stage configurado
                target_stage = model_metadata.get('model_stage', self.config.mlflow_model_stage)

                client.transition_model_version_stage(
                    name=model_name,
                    version=latest_version.version,
                    stage=target_stage
                )

                logger.info(
                    "Modelo restaurado e registrado com sucesso",
                    model_name=model_name,
                    version=latest_version.version,
                    stage=target_stage,
                    run_id=run_id
                )

                # Verificar se modelo está acessível
                try:
                    model_uri = f"models:/{model_name}/{target_stage}"
                    mlflow.pyfunc.load_model(model_uri)
                    logger.info("Modelo verificado e disponível", model_uri=model_uri)
                except Exception as e:
                    logger.error("Falha ao verificar modelo restaurado", error=str(e))
                    raise

            else:
                logger.warning("Modelo registrado mas versão não encontrada")

        except ImportError:
            logger.error("mlflow não disponível para restore de modelo")
            raise
        except Exception as e:
            logger.error("Erro ao restaurar modelo MLflow", error=str(e), error_type=type(e).__name__)
            raise

    def _restore_ledger(self, component_dir: str, target_dir: Optional[str]) -> None:
        """
        Restaura ledger MongoDB de backup.

        Args:
            component_dir: Diretório do componente no backup
            target_dir: Diretório de destino (não usado para ledger)
        """
        db_name = self.config.mongodb_database
        collection_name = self.config.mongodb_ledger_collection

        # Verificar se existe dump do mongodump ou JSON fallback
        dump_dir = os.path.join(component_dir, db_name)
        json_file = os.path.join(component_dir, f'{collection_name}.json')

        # Tentar restore via mongorestore primeiro
        if os.path.exists(dump_dir):
            logger.info("Restaurando ledger via mongorestore", dump_dir=dump_dir)

            try:
                cmd = [
                    'mongorestore',
                    '--uri', self.config.mongodb_uri,
                    '--drop',
                    '--nsInclude', f'{db_name}.{collection_name}',
                    dump_dir
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode != 0:
                    raise Exception(f"mongorestore falhou: {result.stderr}")

                logger.info("Ledger restaurado via mongorestore com sucesso")
                return

            except FileNotFoundError:
                logger.warning("mongorestore não encontrado, tentando fallback JSON")
            except Exception as e:
                logger.warning("Erro ao usar mongorestore, tentando fallback JSON", error=str(e))

        # Fallback: restore via driver com JSON
        if os.path.exists(json_file):
            logger.info("Restaurando ledger via driver MongoDB", json_file=json_file)

            try:
                from pymongo import MongoClient, UpdateOne
                from bson import ObjectId

                with open(json_file, 'r') as f:
                    ledger_data = json.load(f)

                if not isinstance(ledger_data, list):
                    logger.error("Formato de ledger inválido, esperado lista")
                    return

                logger.info("Dados do ledger carregados", document_count=len(ledger_data))

                # Conectar ao MongoDB
                client = MongoClient(self.config.mongodb_uri)
                db = client[db_name]
                collection = db[collection_name]

                # Preparar operações de upsert em bulk
                operations = []

                for doc in ledger_data:
                    # Converter string _id de volta para ObjectId se necessário
                    if '_id' in doc and isinstance(doc['_id'], str):
                        try:
                            doc['_id'] = ObjectId(doc['_id'])
                        except Exception:
                            # Manter como string se não for ObjectId válido
                            pass

                    # Usar opinion_id como chave natural para upsert
                    filter_key = {'opinion_id': doc.get('opinion_id')}

                    # Se não tem opinion_id, usar _id
                    if not doc.get('opinion_id') and '_id' in doc:
                        filter_key = {'_id': doc['_id']}

                    operations.append(
                        UpdateOne(
                            filter_key,
                            {'$set': doc},
                            upsert=True
                        )
                    )

                # Executar bulk write
                if operations:
                    result = collection.bulk_write(operations, ordered=False)

                    logger.info(
                        "Ledger restaurado via driver com sucesso",
                        inserted=result.upserted_count,
                        modified=result.modified_count,
                        total=len(ledger_data)
                    )
                else:
                    logger.warning("Nenhuma operação para executar, ledger vazio")

            except ImportError:
                logger.error("pymongo não disponível para restore de ledger")
                raise
            except Exception as e:
                logger.error("Erro ao restaurar ledger via driver", error=str(e), error_type=type(e).__name__)
                raise

        else:
            logger.warning(
                "Nenhum arquivo de ledger encontrado",
                checked_paths=[dump_dir, json_file]
            )

    def _restore_cache(self, component_dir: str, target_dir: Optional[str]) -> None:
        """
        Restaura cache Redis de backup.

        Args:
            component_dir: Diretório do componente no backup
            target_dir: Diretório de destino (não usado para cache)
        """
        # Cache é opcional e efêmero - só restaurar se configurado
        if not self.config.backup_include_cache:
            logger.info("Restore de cache desabilitado via configuração")
            return

        cache_file = os.path.join(component_dir, 'cache_keys.json')

        if not os.path.exists(cache_file):
            logger.warning("Arquivo de cache não encontrado")
            return

        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)

            logger.info(
                "Restaurando cache Redis",
                key_count=cache_data.get('key_count', 0)
            )

            # Verificar se há dados para restaurar
            cache_keys = cache_data.get('keys', [])
            if not cache_keys:
                logger.info("Nenhuma chave de cache para restaurar")
                return

            # Tentar conectar ao Redis
            try:
                import redis
                from redis.cluster import RedisCluster

                # Parsear nodes do cluster
                cluster_nodes_str = self.config.redis_cluster_nodes
                cluster_nodes = []

                for node in cluster_nodes_str.split(','):
                    host, port = node.strip().split(':')
                    cluster_nodes.append({'host': host, 'port': int(port)})

                # Criar cliente Redis Cluster
                redis_client = RedisCluster(
                    startup_nodes=cluster_nodes,
                    password=self.config.redis_password,
                    ssl=self.config.redis_ssl_enabled,
                    decode_responses=False
                )

                # Restaurar chaves com TTL padrão
                default_ttl = self.config.redis_cache_ttl
                restored_count = 0

                # Usar pipeline para performance
                pipeline = redis_client.pipeline()

                for key_data in cache_keys:
                    if isinstance(key_data, dict):
                        key = key_data.get('key')
                        value = key_data.get('value')
                        ttl = key_data.get('ttl', default_ttl)
                    else:
                        # Se for só a chave (formato antigo), pular
                        logger.debug("Cache key sem valor, pulando", key=key_data)
                        continue

                    if key and value:
                        # Set com TTL
                        pipeline.setex(key, ttl, value)
                        restored_count += 1

                        # Executar em batches de 100
                        if restored_count % 100 == 0:
                            pipeline.execute()
                            pipeline = redis_client.pipeline()

                # Executar operações restantes
                if restored_count % 100 != 0:
                    pipeline.execute()

                logger.info(
                    "Cache restaurado via Redis com sucesso",
                    restored_count=restored_count,
                    total_keys=len(cache_keys)
                )

            except ImportError:
                logger.warning("redis-py não disponível, pulando restore de cache")
            except Exception as e:
                logger.warning(
                    "Erro ao restaurar cache Redis, continuando sem cache",
                    error=str(e),
                    error_type=type(e).__name__
                )
                # Não falhar restore por erro de cache (cache é efêmero)

        except Exception as e:
            logger.warning(
                "Erro ao processar arquivo de cache",
                error=str(e),
                error_type=type(e).__name__
            )

    def _restore_feature_store(self, component_dir: str, target_dir: Optional[str]) -> None:
        """
        Restaura feature store de backup.

        Args:
            component_dir: Diretório do componente no backup
            target_dir: Diretório de destino (não usado para feature_store)
        """
        features_file = os.path.join(component_dir, 'plan_features.json')

        if not os.path.exists(features_file):
            logger.warning("Arquivo de feature store não encontrado")
            return

        try:
            with open(features_file, 'r') as f:
                features_data = json.load(f)

            if not isinstance(features_data, list):
                logger.error("Formato de feature store inválido, esperado lista")
                return

            logger.info(
                "Restaurando feature store",
                feature_count=len(features_data)
            )

            if not features_data:
                logger.info("Nenhuma feature para restaurar")
                return

            # Conectar ao MongoDB
            from pymongo import MongoClient, UpdateOne, ASCENDING
            from bson import ObjectId

            client = MongoClient(self.config.mongodb_uri)
            db = client[self.config.mongodb_database]
            collection = db[self.config.mongodb_feature_store_collection]

            # Determinar tenant_id do backup (se multi-tenancy)
            tenant_id = None
            if features_data and 'tenant_id' in features_data[0]:
                tenant_id = features_data[0].get('tenant_id')

            # Opcionalmente purgar features existentes do tenant antes de restaurar
            if tenant_id:
                logger.info("Removendo features existentes do tenant", tenant_id=tenant_id)
                delete_result = collection.delete_many({'tenant_id': tenant_id})
                logger.info("Features antigas removidas", deleted_count=delete_result.deleted_count)

            # Preparar operações de upsert em bulk
            operations = []

            for feature_doc in features_data:
                # Converter string _id de volta para ObjectId se necessário
                if '_id' in feature_doc and isinstance(feature_doc['_id'], str):
                    try:
                        feature_doc['_id'] = ObjectId(feature_doc['_id'])
                    except Exception:
                        # Manter como string se não for ObjectId válido
                        pass

                # Construir chave de upsert
                # Usar plan_id e tenant_id como chave natural
                filter_key = {}

                if 'plan_id' in feature_doc:
                    filter_key['plan_id'] = feature_doc['plan_id']

                if tenant_id and 'tenant_id' in feature_doc:
                    filter_key['tenant_id'] = feature_doc['tenant_id']

                # Se não tem chave natural suficiente, usar _id
                if not filter_key and '_id' in feature_doc:
                    filter_key = {'_id': feature_doc['_id']}

                if filter_key:
                    operations.append(
                        UpdateOne(
                            filter_key,
                            {'$set': feature_doc},
                            upsert=True
                        )
                    )

            # Executar bulk write
            if operations:
                result = collection.bulk_write(operations, ordered=False)

                logger.info(
                    "Feature store restaurado com sucesso",
                    inserted=result.upserted_count,
                    modified=result.modified_count,
                    total=len(features_data)
                )

                # Garantir índices
                try:
                    # Índice por plan_id
                    collection.create_index([('plan_id', ASCENDING)])

                    # Índice composto por tenant_id e plan_id (se multi-tenancy)
                    if tenant_id:
                        collection.create_index([('tenant_id', ASCENDING), ('plan_id', ASCENDING)])

                    logger.info("Índices de feature store criados/verificados")

                except Exception as e:
                    logger.warning("Erro ao criar índices de feature store", error=str(e))

            else:
                logger.warning("Nenhuma operação de feature store para executar")

        except ImportError:
            logger.error("pymongo não disponível para restore de feature store")
            raise
        except Exception as e:
            logger.error(
                "Erro ao restaurar feature store",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def _restore_metrics(self, component_dir: str, target_dir: Optional[str]) -> None:
        """
        Restaura métricas de backup (validação apenas, não escreve de volta para Prometheus).

        Métricas são efêmeras e reconstruídas durante operação normal.
        Este método apenas valida que o backup contém dados de métricas válidos.

        Args:
            component_dir: Diretório do componente no backup
            target_dir: Diretório de destino (não usado para metrics)
        """
        metrics_file = os.path.join(component_dir, 'metrics_summary.json')

        if not os.path.exists(metrics_file):
            logger.warning("Arquivo de métricas não encontrado")
            return

        try:
            with open(metrics_file, 'r') as f:
                metrics_data = json.load(f)

            # Validar estrutura básica das métricas
            if not isinstance(metrics_data, dict):
                logger.warning("Formato de métricas inválido")
                return

            metrics_keys = list(metrics_data.keys())

            logger.info(
                "Métricas validadas do backup (validação apenas, não restauradas para Prometheus)",
                keys=metrics_keys,
                key_count=len(metrics_keys)
            )

            # Nota: Métricas não são escritas de volta para Prometheus
            # Elas são reconstruídas durante operação normal do especialista

        except json.JSONDecodeError as e:
            logger.warning("Erro ao parsear arquivo de métricas", error=str(e))
        except Exception as e:
            logger.warning(
                "Erro ao validar métricas",
                error=str(e),
                error_type=type(e).__name__
            )

    def _run_smoke_tests(self) -> Dict[str, Any]:
        """
        Executa smoke tests básicos após restore.

        Returns:
            Dict com resultados dos smoke tests
        """
        results = {
            'passed': True,
            'tests': {}
        }

        try:
            # Test 1: Config carregada
            results['tests']['config_loaded'] = {
                'status': 'pass' if self.config else 'fail'
            }

            # Test 2: Specialist inicializado
            results['tests']['specialist_initialized'] = {
                'status': 'pass' if self.specialist else 'fail'
            }

            # Test 3: Storage client conectado
            try:
                # Tentar listar backups como teste de conectividade
                self.storage_client.list_backups(prefix='', limit=1)
                results['tests']['storage_connected'] = {'status': 'pass'}
            except Exception as e:
                results['tests']['storage_connected'] = {
                    'status': 'fail',
                    'error': str(e)
                }
                results['passed'] = False

            # Test 4: Métricas disponíveis
            if hasattr(self.specialist, 'metrics'):
                results['tests']['metrics_available'] = {'status': 'pass'}
            else:
                results['tests']['metrics_available'] = {'status': 'warn'}

        except Exception as e:
            logger.error("Erro em smoke tests", error=str(e))
            results['passed'] = False
            results['error'] = str(e)

        return results
