"""Testes do caminho real de build verificável (Task 4).

Cobre:
- Registry-prefix no image_tag (build_image_reference).
- Montagem do ghcr-secret no Kaniko (volume + volumeMount em /kaniko/.docker).
- Mapeamento digest+uri do container_image para artifact exposto no PipelineResult.
"""

from src.services.container_builder import BuilderType, ContainerBuilder
from src.services.pipeline_engine import (
    build_image_reference,
    container_image_to_artifact,
)


class TestBuildImageReference:
    """Registry-prefix determinístico no image_tag."""

    def test_with_registry(self):
        ref = build_image_reference(
            registry="ghcr.io/albinojimy/neural-hive-mind",
            artifact_name="svc",
            version="1.0.0",
        )
        assert ref == "ghcr.io/albinojimy/neural-hive-mind/svc:1.0.0"

    def test_registry_trailing_slash_stripped(self):
        ref = build_image_reference(
            registry="ghcr.io/albinojimy/neural-hive-mind/",
            artifact_name="svc",
            version="1.0.0",
        )
        assert ref == "ghcr.io/albinojimy/neural-hive-mind/svc:1.0.0"

    def test_empty_registry_keeps_legacy_behavior(self):
        ref = build_image_reference(registry="", artifact_name="svc", version="1.0.0")
        assert ref == "svc:1.0.0"


class TestContainerImageToArtifact:
    """O container_image (digest/tag/size) vira um artifact com digest+uri."""

    def test_maps_digest_and_uri(self):
        meta = {
            "digest": "sha256:abc123",
            "tag": "ghcr.io/albinojimy/neural-hive-mind/svc:1.0.0",
            "size_bytes": 12345,
        }
        artifact = container_image_to_artifact(meta)
        assert artifact["digest"] == "sha256:abc123"
        assert artifact["uri"] == "ghcr.io/albinojimy/neural-hive-mind/svc:1.0.0"
        assert artifact["registry_reference"] == "ghcr.io/albinojimy/neural-hive-mind/svc:1.0.0"
        assert artifact["type"] == "image"
        assert artifact["size_bytes"] == 12345

    def test_none_when_no_digest(self):
        assert container_image_to_artifact({"tag": "svc:1.0.0"}) is None
        assert container_image_to_artifact(None) is None


class TestKanikoGhcrSecret:
    """O secret de registry é montado em /kaniko/.docker quando configurado."""

    def test_volumes_include_docker_config_secret(self):
        builder = ContainerBuilder(
            builder_type=BuilderType.KANIKO,
            docker_config_secret="ghcr-secret",
        )
        volumes = builder._build_pod_volumes(configmap_name="cm-x")
        names = {v["name"] for v in volumes}
        assert "docker-config" in names
        secret_vol = next(v for v in volumes if v["name"] == "docker-config")
        assert secret_vol["secret"]["secretName"] == "ghcr-secret"

    def test_mounts_include_docker_config(self):
        builder = ContainerBuilder(
            builder_type=BuilderType.KANIKO,
            docker_config_secret="ghcr-secret",
        )
        mounts = builder._build_container_volume_mounts()
        paths = {m["mountPath"] for m in mounts}
        assert "/kaniko/.docker" in paths
        docker_mount = next(m for m in mounts if m["mountPath"] == "/kaniko/.docker")
        assert docker_mount["name"] == "docker-config"

    def test_no_secret_when_unconfigured(self):
        builder = ContainerBuilder(builder_type=BuilderType.KANIKO, docker_config_secret="")
        volumes = builder._build_pod_volumes(configmap_name="cm-x")
        mounts = builder._build_container_volume_mounts()
        assert "docker-config" not in {v["name"] for v in volumes}
        assert "/kaniko/.docker" not in {m["mountPath"] for m in mounts}
