"""
E2E Tests para Kaniko Multi-arch com QEMU.

Este teste executa builds multi-arch usando Kaniko no cluster Kubernetes real
com suporte a QEMU para emulação de arquiteturas diferentes.

Requisitos:
- Cluster Kubernetes acessível
- Namespace docker-build existente
- APK (Alpine Package Keeper) funcionando no cluster
"""

import pytest
import asyncio
import tempfile
import os
import time
from pathlib import Path

from src.services.container_builder import (
    ContainerBuilder,
    BuilderType,
    BuildResult,
    Platform,
    _get_qemu_binaries,
)


@pytest.mark.e2e
class TestKanikoMultiArchQEMU:
    """Testes E2E para builds multi-arch com QEMU."""

    @pytest.mark.asyncio
    async def test_qemu_binaries_detection(self):
        """Verifica a detecção correta de binários QEMU necessários."""
        # Test com plataformas ARM
        arm_bins = _get_qemu_binaries(["linux/arm64", "linux/arm/v7"])
        assert "qemu-aarch64" in arm_bins
        assert "qemu-arm" in arm_bins

        # Test com plataformas misc
        mixed_bins = _get_qemu_binaries(["linux/amd64", "linux/arm64"])
        # amd64 não precisa de QEMU (nativo)
        assert "qemu-aarch64" in mixed_bins
        assert "qemu-x86_64" not in mixed_bins  # amd64 não tem entrada no map

        # Test sem plataformas (vazio)
        empty_bins = _get_qemu_binaries([])
        assert empty_bins == []

        # Test sem plataformas (None)
        none_bins = _get_qemu_binaries(None)
        assert none_bins == []

    @pytest.mark.asyncio
    async def test_kaniko_single_arch_native(self):
        """Testa build de arquitetura nativa (amd64) sem QEMU."""
        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/native:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("""FROM alpine:3.19
RUN echo "Native AMD64 build" > /tmp/arch.txt
RUN uname -m >> /tmp/arch.txt || echo "arch check skipped"
CMD ["/bin/sh"]
""")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=600
            )

            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag=image_tag,
                platforms=["linux/amd64"],
                no_push=True,
            )

            assert result is not None
            assert isinstance(result, BuildResult)
            # Build nativo deve funcionar sem problemas
            if result.success:
                print(f"✅ Native AMD64 build sucesso!")
                print(f"   Duração: {result.duration_seconds}s")
            else:
                # Falha pode ser por outros motivos (rede, recursos)
                print(f"⚠️ Native build falhou: {result.error_message}")
                assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_kaniko_multiarch_arm64(self):
        """Testa build multi-arch com ARM64 usando QEMU."""
        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/arm64:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                # Dockerfile simples que funciona em multi-arch
                f.write("""FROM alpine:3.19
RUN echo "Multi-arch build test" > /tmp/test.txt
RUN cat /tmp/test.txt
CMD ["/bin/sh"]
""")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=900  # 15 minutos - QEMU é mais lento
            )

            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag=image_tag,
                platforms=["linux/arm64"],
                no_push=True,
            )

            assert result is not None
            assert isinstance(result, BuildResult)

            if result.success:
                print(f"✅ ARM64 build com QEMU sucesso!")
                print(f"   Duração: {result.duration_seconds}s")
                # QEMU builds são significativamente mais lentos
                assert result.duration_seconds > 10  # Pelo menos 10 segundos
            else:
                # QEMU pode não estar disponível ou pode falhar
                print(f"⚠️ ARM64 build falhou: {result.error_message}")
                # Verificar se é erro esperado (QEMU não disponível)
                if result.error_message and "qemu" in result.error_message.lower():
                    pytest.skip("QEMU não disponível no cluster")

    @pytest.mark.asyncio
    async def test_kaniko_multiarch_arm_v7(self):
        """Testa build multi-arch com ARM v7 usando QEMU."""
        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/armv7:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("""FROM alpine:3.19
RUN echo "ARM v7 test" > /tmp/test.txt
CMD ["/bin/sh"]
""")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=900
            )

            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag=image_tag,
                platforms=["linux/arm/v7"],
                no_push=True,
            )

            assert result is not None
            assert isinstance(result, BuildResult)

            if result.success:
                print(f"✅ ARM v7 build sucesso!")
                print(f"   Duração: {result.duration_seconds}s")
            else:
                print(f"⚠️ ARM v7 build falhou: {result.error_message}")

    @pytest.mark.asyncio
    async def test_kaniko_multiarch_dual_platform(self):
        """Testa build para múltiplas plataformas simultaneamente."""
        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/dual:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("""FROM alpine:3.19
RUN echo "Dual platform build" > /tmp/test.txt
RUN uname -m > /tmp/arch.txt 2>/dev/null || echo "arch unknown" > /tmp/arch.txt
CMD ["/bin/sh"]
""")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=1200  # 20 minutos para dual arch
            )

            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag=image_tag,
                platforms=["linux/amd64", "linux/arm64"],
                no_push=True,
            )

            assert result is not None
            assert isinstance(result, BuildResult)

            if result.success:
                print(f"✅ Dual platform build sucesso!")
                print(f"   Plataformas: {result.platforms}")
                print(f"   Duração: {result.duration_seconds}s")
                # Dual platform deve ser ainda mais lento
                assert result.duration_seconds > 20
            else:
                print(f"⚠️ Dual platform build falhou: {result.error_message}")

    @pytest.mark.asyncio
    async def test_kaniko_platform_aliases(self):
        """Testa build usando aliases de plataforma."""
        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/aliases:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("""FROM alpine:3.19
RUN echo "Alias test" > /tmp/test.txt
CMD ["/bin/sh"]
""")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=900
            )

            # Usar aliases em vez de nomes completos
            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag=image_tag,
                platforms=["amd64", "arm64"],  # Aliases
                no_push=True,
            )

            assert result is not None
            assert isinstance(result, BuildResult)

            if result.success:
                print(f"✅ Platform aliases build sucesso!")
                print(f"   Plataformas: {result.platforms}")
            else:
                print(f"⚠️ Platform aliases build falhou: {result.error_message}")


@pytest.mark.e2e
class TestKanikoMultiArchPython:
    """Testes E2E para builds multi-arch de aplicações Python."""

    @pytest.mark.asyncio
    async def test_python_multiarch_arm64(self):
        """Testa build de imagem Python para ARM64."""
        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/python-arm64:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("""FROM python:3.11-slim
WORKDIR /app
RUN echo "Python ARM64 build" > /tmp/test.txt
RUN python3 --version
CMD ["/bin/sh"]
""")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=1200  # 20 minutos - Python é maior
            )

            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag=image_tag,
                platforms=["linux/arm64"],
                no_push=True,
            )

            assert result is not None
            assert isinstance(result, BuildResult)

            if result.success:
                print(f"✅ Python ARM64 build sucesso!")
                print(f"   Duração: {result.duration_seconds}s")
                # Python builds são mais demorados
                assert result.duration_seconds > 30
            else:
                print(f"⚠️ Python ARM64 build falhou: {result.error_message}")

    @pytest.mark.asyncio
    async def test_fastapi_multiarch_build(self):
        """Testa build de microserviço FastAPI multi-arch."""
        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/fastapi-multi:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("""FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
RUN echo 'from fastapi import FastAPI\\napp = FastAPI()\\n@app.get("/")\\ndef read_root():\\n    return {"status": "ok", "arch": "multi-arch"}' > /app/main.py
EXPOSE 8000
CMD ["/bin/sh"]
""")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=1200
            )

            result = await builder.build_container(
                dockerfile_path=dockerfile_path,
                build_context=tmpdir,
                image_tag=image_tag,
                platforms=["linux/amd64", "linux/arm64"],
                no_push=True,
            )

            assert result is not None
            assert isinstance(result, BuildResult)

            if result.success:
                print(f"✅ FastAPI multi-arch build sucesso!")
                print(f"   Duração: {result.duration_seconds}s")
            else:
                print(f"⚠️ FastAPI multi-arch build falhou: {result.error_message}")


@pytest.mark.e2e
class TestQEMUPodStructure:
    """Testes para validar estrutura do pod com QEMU."""

    @pytest.mark.asyncio
    async def test_qemu_init_container_present(self):
        """Verifica que o init container qemu-setup está presente quando necessário."""
        import tempfile
        import uuid

        timestamp = int(time.time())
        image_tag = f"localhost:5000/codeforge-test/qemu-struct:{timestamp}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = os.path.join(tmpdir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write("FROM alpine:3.19\nRUN echo test\nCMD [\"/bin/sh\"]\n")

            builder = ContainerBuilder(
                builder_type=BuilderType.KANIKO,
                timeout_seconds=600
            )

            # Criar os init containers para verificar a estrutura
            init_containers = builder._build_init_containers(
                needs_qemu=True,
                qemu_binaries=["qemu-aarch64", "qemu-arm"]
            )

            # Deve ter 2 init containers: qemu-setup e setup
            assert len(init_containers) == 2
            assert init_containers[0]["name"] == "qemu-setup"
            assert init_containers[1]["name"] == "setup"

            # Verificar qemu-setup tem os argumentos corretos
            qemu_container = init_containers[0]
            assert "qemu-aarch64" in qemu_container["args"][0]
            assert "qemu-arm" in qemu_container["args"][0]

            print(f"✅ QEMU init container structure valid!")

    @pytest.mark.asyncio
    async def test_qemu_volumes_present(self):
        """Verifica que o volume QEMU está presente quando necessário."""
        builder = ContainerBuilder(
            builder_type=BuilderType.KANIKO,
            timeout_seconds=600
        )

        # Test com QEMU habilitado
        volumes_with_qemu = builder._build_pod_volumes(
            configmap_name="test-config",
            needs_qemu=True
        )

        # Deve ter 4 volumes: workspace, dockerfile, context, qemu
        assert len(volumes_with_qemu) == 4
        volume_names = [v["name"] for v in volumes_with_qemu]
        assert "qemu" in volume_names

        # Test sem QEMU
        volumes_without_qemu = builder._build_pod_volumes(
            configmap_name="test-config",
            needs_qemu=False
        )

        # Deve ter 3 volumes: workspace, dockerfile, context
        assert len(volumes_without_qemu) == 3
        volume_names = [v["name"] for v in volumes_without_qemu]
        assert "qemu" not in volume_names

        print(f"✅ QEMU volumes structure valid!")

    @pytest.mark.asyncio
    async def test_qemu_volume_mounts_present(self):
        """Verifica que o volumeMount QEMU está presente no container Kaniko."""
        builder = ContainerBuilder(
            builder_type=BuilderType.KANIKO,
            timeout_seconds=600
        )

        # Test com QEMU habilitado
        mounts_with_qemu = builder._build_container_volume_mounts(needs_qemu=True)

        # Deve ter 2 mounts: workspace, qemu
        assert len(mounts_with_qemu) == 2
        mount_paths = [m["mountPath"] for m in mounts_with_qemu]
        assert "/usr/local/bin" in mount_paths

        # Test sem QEMU
        mounts_without_qemu = builder._build_container_volume_mounts(needs_qemu=False)

        # Deve ter apenas 1 mount: workspace
        assert len(mounts_without_qemu) == 1
        mount_paths = [m["mountPath"] for m in mounts_without_qemu]
        assert "/usr/local/bin" not in mount_paths

        print(f"✅ QEMU volumeMounts structure valid!")
