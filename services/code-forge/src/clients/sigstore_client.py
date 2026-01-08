"""
Cliente para Sigstore (assinatura de artefatos).

Utiliza ferramentas CLI (Cosign, Syft, Rekor) via subprocess assíncrono.
"""

import asyncio
import os
import tempfile
import shutil
import time
from typing import Optional, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics
    from .s3_artifact_client import S3ArtifactClient

logger = structlog.get_logger()


class SigstoreClient:
    """Cliente para Sigstore (assinatura e verificação de artefatos)."""

    def __init__(
        self,
        fulcio_url: str,
        rekor_url: str,
        enabled: bool = True,
        cosign_path: Optional[str] = None,
        syft_path: Optional[str] = None,
        rekor_cli_path: Optional[str] = None,
        metrics: Optional['CodeForgeMetrics'] = None,
        s3_client: Optional['S3ArtifactClient'] = None
    ):
        """
        Inicializa cliente Sigstore.

        Args:
            fulcio_url: URL do servidor Fulcio
            rekor_url: URL do servidor Rekor
            enabled: Se False, operações retornam mocks
            cosign_path: Caminho para binário cosign (auto-detecta se None)
            syft_path: Caminho para binário syft (auto-detecta se None)
            rekor_cli_path: Caminho para binário rekor-cli (auto-detecta se None)
            metrics: Instância de CodeForgeMetrics para instrumentação
            s3_client: Cliente S3 para upload de SBOMs (opcional)
        """
        self.fulcio_url = fulcio_url
        self.rekor_url = rekor_url
        self.enabled = enabled
        self.cosign_path = cosign_path or shutil.which('cosign')
        self.syft_path = syft_path or shutil.which('syft')
        self.rekor_cli_path = rekor_cli_path or shutil.which('rekor-cli')
        self.metrics = metrics
        self.s3_client = s3_client

        # Verifica disponibilidade das ferramentas
        self._tools_available = {
            'cosign': self.cosign_path is not None,
            'syft': self.syft_path is not None,
            'rekor-cli': self.rekor_cli_path is not None,
        }

    async def start(self):
        """Verifica disponibilidade das ferramentas."""
        if not self.enabled:
            logger.info('sigstore_client_disabled')
            return

        missing_tools = [tool for tool, available in self._tools_available.items() if not available]
        if missing_tools:
            logger.warning(
                'sigstore_tools_not_found',
                missing=missing_tools,
                note='Operações usarão fallback com mock'
            )
        else:
            logger.info(
                'sigstore_client_started',
                fulcio_url=self.fulcio_url,
                rekor_url=self.rekor_url
            )

    async def stop(self):
        """Cleanup do cliente."""
        logger.info('sigstore_client_stopped')

    async def _run_command(
        self,
        command: list,
        timeout: int = 120,
        env: Optional[dict] = None
    ) -> tuple[int, str, str]:
        """
        Executa comando via subprocess assíncrono.

        Args:
            command: Lista de argumentos do comando
            timeout: Timeout em segundos
            env: Variáveis de ambiente adicionais

        Returns:
            Tupla (returncode, stdout, stderr)
        """
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )

            return (
                proc.returncode,
                stdout.decode('utf-8', errors='replace'),
                stderr.decode('utf-8', errors='replace')
            )

        except asyncio.TimeoutError:
            if proc:
                proc.kill()
                await proc.wait()
            logger.error('command_timeout', command=command[0], timeout=timeout)
            raise TimeoutError(f'Comando {command[0]} excedeu timeout de {timeout}s')

        except Exception as e:
            logger.error('command_execution_failed', command=command[0], error=str(e))
            raise

    async def sign_artifact(self, artifact_path: str) -> str:
        """
        Assina artefato com Cosign.

        Args:
            artifact_path: Caminho do artefato a assinar

        Returns:
            Assinatura gerada (base64)
        """
        if not self.enabled:
            logger.debug('sigstore_disabled_returning_empty')
            if self.metrics:
                self.metrics.sigstore_signatures_total.labels(status='mock').inc()
            return ''

        if not self._tools_available['cosign']:
            logger.warning('cosign_not_available_returning_mock')
            if self.metrics:
                self.metrics.sigstore_signatures_total.labels(status='mock').inc()
            return 'MOCK_SIGNATURE_COSIGN_NOT_INSTALLED'

        start_time = time.perf_counter()
        try:
            logger.info('artifact_signing_started', artifact=artifact_path)

            # cosign sign-blob --yes --output-signature - <artifact>
            command = [
                self.cosign_path,
                'sign-blob',
                '--yes',
                '--output-signature', '-',
                artifact_path
            ]

            # Adiciona URLs customizadas se não forem públicas
            if 'sigstore.dev' not in self.fulcio_url:
                command.extend(['--fulcio-url', self.fulcio_url])
            if 'sigstore.dev' not in self.rekor_url:
                command.extend(['--rekor-url', self.rekor_url])

            returncode, stdout, stderr = await self._run_command(command)

            if returncode != 0:
                logger.error(
                    'artifact_signing_failed',
                    artifact=artifact_path,
                    returncode=returncode,
                    stderr=stderr[:500]
                )
                if self.metrics:
                    self.metrics.sigstore_signatures_total.labels(status='failure').inc()
                raise RuntimeError(f'Cosign falhou: {stderr[:200]}')

            signature = stdout.strip()
            logger.info('artifact_signed', artifact=artifact_path, signature_len=len(signature))

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.sigstore_signatures_total.labels(status='success').inc()
                self.metrics.sigstore_operation_duration_seconds.labels(operation='sign').observe(duration)

            return signature

        except TimeoutError:
            if self.metrics:
                self.metrics.sigstore_signatures_total.labels(status='failure').inc()
            raise
        except Exception as e:
            if self.metrics:
                self.metrics.sigstore_signatures_total.labels(status='failure').inc()
            logger.error('artifact_signing_failed', artifact=artifact_path, error=str(e))
            raise

    async def verify_signature(self, artifact_path: str, signature: str, certificate: Optional[str] = None) -> bool:
        """
        Verifica assinatura de artefato.

        Args:
            artifact_path: Caminho do artefato
            signature: Assinatura a verificar
            certificate: Certificado usado na assinatura (opcional)

        Returns:
            True se assinatura é válida
        """
        if not self.enabled:
            logger.debug('sigstore_disabled_skipping_verification')
            return True

        if not self._tools_available['cosign']:
            logger.warning('cosign_not_available_skipping_verification')
            return True

        if signature == 'MOCK_SIGNATURE_COSIGN_NOT_INSTALLED':
            return True

        try:
            logger.info('signature_verification_started', artifact=artifact_path)

            # Cria arquivo temporário com a assinatura
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sig', delete=False) as sig_file:
                sig_file.write(signature)
                sig_path = sig_file.name

            try:
                command = [
                    self.cosign_path,
                    'verify-blob',
                    '--signature', sig_path,
                    artifact_path
                ]

                # Adiciona certificado se fornecido
                if certificate:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as cert_file:
                        cert_file.write(certificate)
                        command.extend(['--certificate', cert_file.name])

                returncode, stdout, stderr = await self._run_command(command)

                if returncode == 0:
                    logger.info('signature_verified', artifact=artifact_path)
                    return True
                else:
                    logger.warning(
                        'signature_verification_failed',
                        artifact=artifact_path,
                        stderr=stderr[:200]
                    )
                    return False

            finally:
                os.unlink(sig_path)

        except Exception as e:
            logger.error('signature_verification_error', artifact=artifact_path, error=str(e))
            return False

    async def generate_sbom(
        self,
        artifact_path: str,
        artifact_id: Optional[str] = None,
        ticket_id: Optional[str] = None,
        output_format: str = 'cyclonedx-json'
    ) -> str:
        """
        Gera Software Bill of Materials via Syft.

        Args:
            artifact_path: Caminho do artefato/diretório
            artifact_id: ID do artefato (necessário para upload S3)
            ticket_id: ID do ticket de execução (necessário para upload S3)
            output_format: Formato de saída (cyclonedx-json, spdx-json, etc)

        Returns:
            URI do SBOM gerado (s3:// se S3 configurado, file:// caso contrário)
        """
        if not self.enabled:
            logger.debug('sigstore_disabled_returning_empty_sbom')
            if self.metrics:
                self.metrics.sigstore_sbom_generations_total.labels(status='mock').inc()
            return ''

        if not self._tools_available['syft']:
            logger.warning('syft_not_available_returning_mock_sbom')
            if self.metrics:
                self.metrics.sigstore_sbom_generations_total.labels(status='mock').inc()
            return 'MOCK_SBOM_URI_SYFT_NOT_INSTALLED'

        start_time = time.perf_counter()
        sbom_path = None
        try:
            logger.info('sbom_generation_started', artifact=artifact_path, format=output_format)

            # Cria arquivo temporário para o SBOM
            sbom_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix=f'.{output_format.replace("-", ".")}',
                delete=False
            )
            sbom_path = sbom_file.name
            sbom_file.close()

            command = [
                self.syft_path,
                artifact_path,
                '-o', output_format,
                '--file', sbom_path
            ]

            returncode, stdout, stderr = await self._run_command(command, timeout=300)

            if returncode != 0:
                logger.error(
                    'sbom_generation_failed',
                    artifact=artifact_path,
                    returncode=returncode,
                    stderr=stderr[:500]
                )
                if self.metrics:
                    self.metrics.sigstore_sbom_generations_total.labels(status='failure').inc()
                raise RuntimeError(f'Syft falhou: {stderr[:200]}')

            # Upload para S3 se cliente disponível e IDs fornecidos
            sbom_uri = None
            storage_type = 'local'

            if self.s3_client and artifact_id and ticket_id:
                try:
                    sbom_uri = await self.s3_client.upload_sbom(
                        local_path=sbom_path,
                        artifact_id=artifact_id,
                        ticket_id=ticket_id
                    )
                    storage_type = 's3'
                    logger.info(
                        'sbom_uploaded_to_s3',
                        artifact=artifact_path,
                        sbom_uri=sbom_uri,
                        artifact_id=artifact_id,
                        ticket_id=ticket_id
                    )
                    # Deletar arquivo temporário local após upload
                    os.unlink(sbom_path)
                    sbom_path = None
                except Exception as upload_error:
                    logger.error(
                        'sbom_s3_upload_failed',
                        artifact=artifact_path,
                        error=str(upload_error),
                        fallback='file'
                    )
                    # Fallback para file:// se upload falhar
                    sbom_uri = f'file://{sbom_path}'
                    storage_type = 'local'
            else:
                sbom_uri = f'file://{sbom_path}'

            logger.info(
                'sbom_generated',
                artifact=artifact_path,
                sbom_uri=sbom_uri,
                storage_type=storage_type
            )

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.sigstore_sbom_generations_total.labels(status='success').inc()
                self.metrics.sigstore_operation_duration_seconds.labels(operation='sbom').observe(duration)

            return sbom_uri

        except TimeoutError:
            if self.metrics:
                self.metrics.sigstore_sbom_generations_total.labels(status='failure').inc()
            if sbom_path and os.path.exists(sbom_path):
                os.unlink(sbom_path)
            raise
        except Exception as e:
            if self.metrics:
                self.metrics.sigstore_sbom_generations_total.labels(status='failure').inc()
            if sbom_path and os.path.exists(sbom_path):
                os.unlink(sbom_path)
            logger.error('sbom_generation_failed', artifact=artifact_path, error=str(e))
            raise

    async def upload_to_rekor(self, artifact_hash: str, signature: str) -> Optional[str]:
        """
        Registra no Rekor transparency log.

        Args:
            artifact_hash: SHA256 do artefato
            signature: Assinatura do artefato

        Returns:
            UUID do registro no Rekor ou None se falhar
        """
        if not self.enabled:
            logger.debug('sigstore_disabled_skipping_rekor_upload')
            return None

        if not self._tools_available['rekor-cli']:
            logger.warning('rekor_cli_not_available_skipping_upload')
            return None

        if signature == 'MOCK_SIGNATURE_COSIGN_NOT_INSTALLED':
            return 'MOCK_REKOR_UUID'

        start_time = time.perf_counter()
        try:
            logger.info('rekor_upload_started', hash=artifact_hash[:16])

            # Cria arquivo temporário com a assinatura
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sig', delete=False) as sig_file:
                sig_file.write(signature)
                sig_path = sig_file.name

            try:
                command = [
                    self.rekor_cli_path,
                    'upload',
                    '--artifact-hash', artifact_hash,
                    '--signature', sig_path,
                    '--rekor_server', self.rekor_url
                ]

                returncode, stdout, stderr = await self._run_command(command)

                if returncode != 0:
                    logger.error(
                        'rekor_upload_failed',
                        returncode=returncode,
                        stderr=stderr[:200]
                    )
                    if self.metrics:
                        self.metrics.sigstore_rekor_uploads_total.labels(status='failure').inc()
                    return None

                # Extrai UUID do output
                # Output típico: "Created entry at index X, available at: https://rekor.../api/v1/log/entries/{uuid}"
                import re
                uuid_match = re.search(r'entries/([a-f0-9]+)', stdout)
                uuid = uuid_match.group(1) if uuid_match else None

                if uuid:
                    logger.info('rekor_upload_completed', uuid=uuid)
                else:
                    logger.warning('rekor_upload_completed_no_uuid', output=stdout[:200])

                if self.metrics:
                    duration = time.perf_counter() - start_time
                    self.metrics.sigstore_rekor_uploads_total.labels(status='success').inc()
                    self.metrics.sigstore_operation_duration_seconds.labels(operation='rekor_upload').observe(duration)

                return uuid

            finally:
                os.unlink(sig_path)

        except Exception as e:
            if self.metrics:
                self.metrics.sigstore_rekor_uploads_total.labels(status='failure').inc()
            logger.error('rekor_upload_failed', error=str(e))
            return None

    async def get_rekor_entry(self, uuid: str) -> Optional[dict]:
        """
        Recupera entrada do Rekor pelo UUID.

        Args:
            uuid: UUID da entrada no Rekor

        Returns:
            Dados da entrada ou None
        """
        if not self.enabled or not self._tools_available['rekor-cli']:
            return None

        try:
            command = [
                self.rekor_cli_path,
                'get',
                '--uuid', uuid,
                '--rekor_server', self.rekor_url,
                '--format', 'json'
            ]

            returncode, stdout, stderr = await self._run_command(command)

            if returncode != 0:
                logger.warning('rekor_get_failed', uuid=uuid, stderr=stderr[:100])
                return None

            import json
            return json.loads(stdout)

        except Exception as e:
            logger.error('rekor_get_failed', uuid=uuid, error=str(e))
            return None

    def is_available(self) -> bool:
        """Verifica se cliente está habilitado e ferramentas disponíveis."""
        return self.enabled and any(self._tools_available.values())

    async def health_check(self) -> bool:
        """
        Verifica saúde do cliente.

        Returns:
            True se pelo menos uma ferramenta está disponível ou cliente desabilitado
        """
        if not self.enabled:
            return True

        # Verifica se cosign está funcionando
        if self._tools_available['cosign']:
            start_time = time.perf_counter()
            try:
                returncode, _, _ = await self._run_command(
                    [self.cosign_path, 'version'],
                    timeout=10
                )
                is_healthy = returncode == 0
                if self.metrics:
                    duration = time.perf_counter() - start_time
                    status = 'success' if is_healthy else 'failure'
                    self.metrics.sigstore_operation_duration_seconds.labels(operation='health_check').observe(duration)
                return is_healthy
            except Exception:
                return False

        return True
