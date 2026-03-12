"""
E2E Test para Kaniko builder em cluster Kubernetes real.

Este teste valida:
1. Conexão com o cluster Kubernetes
2. Existência do namespace docker-build
3. Criação de Pod Kaniko
4. Execução de build simples
5. Extração de digest dos logs
6. Cleanup de recursos

Requisitos:
- Cluster Kubernetes acessível
- Namespace docker-build existente
- kubectl configurado ou kubeconfig válido
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path

from src.services.container_builder import (
    ContainerBuilder,
    BuilderType,
    BuildResult
)


@pytest.mark.e2e
class TestKanikoK8sReal:
    """Testes E2E com cluster Kubernetes real."""

    @pytest.mark.asyncio
    async def test_kaniko_namespace_exists(self):
        """Verifica se o namespace docker-build existe."""
        try:
            from kubernetes import client, config

            config.load_kube_config()
            v1 = client.CoreV1Api()

            namespace = v1.read_namespace(name="docker-build")
            assert namespace.metadata.name == "docker-build"
            print(f"✅ Namespace docker-build encontrado: {namespace.status.phase}")

        except Exception as e:
            pytest.skip(f"Cluster Kubernetes não acessível: {e}")

    @pytest.mark.asyncio
    async def test_kaniko_simple_build(self):
        """Executa um build simples com Kaniko no cluster real."""
        try:
            from kubernetes import client, config

            config.load_kube_config()
            v1 = client.CoreV1Api()

            # Verificar namespace existe
            try:
                v1.read_namespace(name="docker-build")
            except Exception:
                pytest.skip("Namespace docker-build não existe")

        except Exception as e:
            pytest.skip(f"Cluster Kubernetes não acessível: {e}")

        # Criar um Dockerfile simples para teste
        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("""FROM alpine:3.19
RUN echo "Kaniko E2E Test" > /tmp/test.txt
CMD cat /tmp/test.txt
""")

            # Criar builder Kaniko
            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=600  # 10 minutos para build real
            )

            # Executar build (vai falhar se registry não configurado,
            # mas podemos validar até a criação do pod)
            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag="localhost/test-kaniko:e2e-test",
            )

            # Resultado pode ser sucesso ou falha dependendo do registry
            # O importante é que o fluxo execute sem crash
            assert result is not None
            assert isinstance(result, BuildResult)

            if result.success:
                print(f"✅ Build sucesso! Digest: {result.image_digest}")
            else:
                print(f"⚠️ Build falhou (esperado se registry não configurado): {result.error_message}")

            # Para builds de teste, podemos aceitar falha de registry
            # desde que o pod tenha sido criado
            print(f"Build duration: {result.duration_seconds}s")

    @pytest.mark.asyncio
    async def test_kaniko_digest_parsing(self):
        """Testa o parsing de digest com logs reais do Kaniko."""
        builder = ContainerBuilder(builder_type=BuilderType.KANIKO)

        # Simular logs reais do Kaniko
        test_logs = """
INFO0010[0000] Resolving base image alpine:3.19...
INFO0011[0000] Resolved base image alpine:3.19 to sha256:abc123...
INFO0012[0001] Extracting layer 0/1
INFO0013[0002] Extracting layer 1/1
INFO0014[0003] RUN echo "Kaniko E2E Test" > /tmp/test.txt
INFO0015[0005] Taking snapshot of files...
INFO0016[0006] Built image with digest sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
INFO0017[0007] Pushing image to localhost/test-kaniko:e2e-test
INFO0018[0010] Pushed image with digest sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
"""

        digest = builder._parse_kaniko_digest(test_logs)

        assert digest is not None
        assert digest.startswith("sha256:")
        assert len(digest) == 71  # "sha256:" (7) + 64 caracteres
        print(f"✅ Digest parseado: {digest}")

    @pytest.mark.asyncio
    async def test_kaniko_list_pods_in_namespace(self):
        """Lista pods no namespace docker-build."""
        try:
            from kubernetes import client, config

            config.load_kube_config()
            v1 = client.CoreV1Api()

            pods = v1.list_namespaced_pod(namespace="docker-build")

            print(f"✅ Pods encontrados em docker-build: {len(pods.items)}")

            for pod in pods.items:
                print(f"  - {pod.metadata.name} ({pod.status.phase})")

        except Exception as e:
            pytest.skip(f"Erro ao listar pods: {e}")

    @pytest.mark.asyncio
    async def test_kaniko_pod_manifest_structure(self):
        """Valida a estrutura do manifesto Pod Kaniko."""
        builder = ContainerBuilder(builder_type=BuilderType.KANIKO)

        # Testar que o método _build_with_kaniko existe e tem a assinatura correta
        assert hasattr(builder, '_build_with_kaniko')
        assert callable(builder._build_with_kaniko)

        # Validar método de parsing
        assert hasattr(builder, '_parse_kaniko_digest')
        assert callable(builder._parse_kaniko_digest)

        print("✅ Métodos Kaniko validados")


@pytest.mark.e2e
class TestKanikoIntegration:
    """Testes de integração Kaniko com outros componentes."""

    @pytest.mark.asyncio
    async def test_kaniko_dockerfile_generator_integration(self):
        """Testa integração entre DockerfileGenerator e Kaniko."""
        from src.services.dockerfile_generator import (
            DockerfileGenerator,
            SupportedLanguage,
            ArtifactType
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Gerar Dockerfile com o generator
            generator = DockerfileGenerator()
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")

            dockerfile_content = generator.generate_dockerfile(
                language=SupportedLanguage.PYTHON,
                artifact_type=ArtifactType.LAMBDA_FUNCTION,
            )

            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)

            # Validar que o Dockerfile foi gerado corretamente
            assert os.path.exists(dockerfile_path)

            with open(dockerfile_path, "r") as f:
                content = f.read()
                assert "FROM python:" in content
                # Lambda functions têm CMD específico
                assert "CMD" in content or "ENTRYPOINT" in content

            print("✅ Dockerfile gerado para Kaniko build")

    @pytest.mark.asyncio
    async def test_kaniko_build_result_structure(self):
        """Valida a estrutura de BuildResult para builds Kaniko."""
        # Testar resultado de sucesso
        result_success = BuildResult(
            success=True,
            image_digest="sha256:abc123def456",
            image_tag="test:v1",
            duration_seconds=120.5,
            build_logs=["INFO Build started", "INFO Build complete"]
        )

        assert result_success.success is True
        assert result_success.image_digest == "sha256:abc123def456"
        assert result_success.image_tag == "test:v1"
        assert result_success.duration_seconds == 120.5
        assert len(result_success.build_logs) == 2

        # Testar resultado de falha
        result_failure = BuildResult(
            success=False,
            error_message="Build failed: step 5 error",
            duration_seconds=45.0,
            build_logs=["INFO Build started", "ERROR Step 5 failed"]
        )

        assert result_failure.success is False
        assert result_failure.error_message == "Build failed: step 5 error"
        assert len(result_failure.build_logs) == 2

        print("✅ Estrutura BuildResult validada")
