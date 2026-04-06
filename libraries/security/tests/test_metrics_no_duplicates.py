"""
Testes para verificar que não há métricas duplicadas no CollectorRegistry.

Este teste valida especificamente a correção do ticket SEC-008 onde a métrica
spiffe_trust_bundle_updates_total estava definida em dois locais, causando
ValueError: Duplicated timeseries in CollectorRegistry.

GitHub Issue: SEC-008
"""

from prometheus_client import REGISTRY

# Importações no topo para evitar PLC0415
from neural_hive_security.jwt.metrics import (
    jwt_verification_attempts_total,
    spiffe_trust_bundle_keys_validated_total,
    spiffe_trust_bundle_updates_total as jwt_metric_ref,
)
from neural_hive_security.spiffe_manager import (
    spiffe_svid_fetch_total,
    spiffe_trust_bundle_updates_total,
)

# =============================================================================
# Test: Validação de Métricas Duplicadas
# =============================================================================


class TestMetricsNoDuplicates:
    """Testes para garantir que não há métricas duplicadas."""

    def test_no_duplicate_metrics_in_default_registry(self):
        """
        Não deve haver métricas duplicadas no registry padrão do Prometheus.

        Este teste valida que:
        1. spiffe_manager.py e jwt/metrics.py não definem a mesma métrica
        2. O import de spiffe_trust_bundle_updates_total funciona corretamente
        """
        # Coletar todos os nomes de métricas no registry
        metric_names = set()
        duplicates = set()

        for collector in REGISTRY._collector_to_names.values():
            for metric_name in collector:
                if metric_name in metric_names:
                    duplicates.add(metric_name)
                metric_names.add(metric_name)

        # Validar que não há duplicatas
        assert len(duplicates) == 0, (
            f"Métricas duplicadas encontradas no CollectorRegistry: {duplicates}. "
            "Isso causa ValueError ao iniciar o serviço. "
            "Verifique se a mesma métrica não está definida em múltiplos módulos."
        )

    def test_spiffe_trust_bundle_metrics_unique(self):
        """
        Deve haver apenas uma definição de spiffe_trust_bundle_updates_total.

        Esta métrica específica foi a causa do bug SEC-008, onde estava
        definida tanto em spiffe_manager.py quanto em jwt/metrics.py.
        """
        # Verificar que ambas as referências apontam para a mesma métrica
        # (jwt/metrics importa de spiffe_manager)
        assert (
            spiffe_trust_bundle_updates_total is jwt_metric_ref
        ), "A métrica deve ser a mesma instância (jwt/metrics importa de spiffe_manager)."

        # Gerar alguns samples para poder coletar as métricas
        spiffe_trust_bundle_updates_total.labels(status="test").inc()
        spiffe_trust_bundle_keys_validated_total.labels(validation_status="valid").inc()

        # Coletar nomes diretamente dos descritores de métricas
        metric_names = set()
        for metric in REGISTRY.collect():
            for sample in metric.samples:
                if sample.name.startswith("spiffe_trust_bundle"):
                    metric_names.add(sample.name)

        # Verificar que existem métricas spiffe_trust_bundle
        spiffe_metrics = [name for name in metric_names if "spiffe_trust_bundle" in name]

        # Deve existir pelo menos uma métrica de trust bundle
        assert len(spiffe_metrics) > 0, "As métricas de spiffe_trust_bundle devem existir."

        # Validar que não há duplicatas - Prometheus adiciona _created e _total
        # automaticamente para Counters, então agrupamos pela métrica base
        base_metrics = set()
        for name in spiffe_metrics:
            # Remover sufixos prometheus internos
            base = (
                name.replace("_created", "")
                .replace("_total", "")
                .replace("_bucket", "")
                .replace("_count", "")
                .replace("_sum", "")
            )
            base_metrics.add(base)

        # A métrica base deve ser única (sem duplicatas reais)
        assert "spiffe_trust_bundle_updates" in base_metrics or any(
            "spiffe_trust_bundle_updates" in name for name in spiffe_metrics
        ), f"A métrica spiffe_trust_bundle_updates deve existir. Encontradas: {spiffe_metrics}"

    def test_import_metrics_from_both_modules(self):
        """
        Deve ser possível importar métricas de ambos os módulos sem conflito.

        Simula o cenário real onde o código importa de ambos spiffe_manager
        e jwt.metrics simultaneamente.
        """
        # Ambas devem ser a mesma instância (mesma referência)
        assert spiffe_trust_bundle_updates_total is jwt_metric_ref, (
            "As métricas de ambos os módulos devem ser a mesma instância "
            "para evitar duplicação no CollectorRegistry."
        )

    def test_isolated_registry_clean_import(self):
        """
        Deve ser possível importar módulos sem duplicatas no registry padrão.

        NOTA: Este teste valida que as importações funcionam corretamente
        e que as métricas são as mesmas instâncias.
        """
        # Validar que as métricas foram criadas
        assert spiffe_trust_bundle_updates_total is not None
        assert spiffe_svid_fetch_total is not None
        assert jwt_verification_attempts_total is not None
        assert spiffe_trust_bundle_keys_validated_total is not None

        # Validar que spiffe_trust_bundle_updates_total é a mesma instância
        # em ambos os módulos (importada em jwt/metrics de spiffe_manager)
        assert (
            spiffe_trust_bundle_updates_total is jwt_metric_ref
        ), "A métrica deve ser a mesma instância em ambos os módulos."
