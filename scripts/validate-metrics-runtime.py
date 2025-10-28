#!/usr/bin/env python3
"""
Script de validação de métricas em tempo de execução
Valida se as métricas do Neural Hive-Mind estão sendo coletadas corretamente
"""

import sys
import time
import json
import argparse
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass
class MetricValidation:
    """Configuração de validação para uma métrica"""
    name: str
    expected_labels: List[str]
    min_samples: int = 1
    description: Optional[str] = None
    critical: bool = True


class MetricsValidator:
    """Validador de métricas do Prometheus"""

    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self.prometheus_url = prometheus_url
        self.session = requests.Session()
        self.session.timeout = 30

    def query_metric(self, metric_name: str) -> Dict:
        """Query uma métrica específica do Prometheus"""
        try:
            url = urljoin(self.prometheus_url, "/api/v1/query")
            params = {"query": metric_name}

            response = self.session.get(url, params=params)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            print(f"❌ Erro ao consultar métrica {metric_name}: {e}")
            return {"status": "error", "error": str(e)}

    def validate_metric(self, validation: MetricValidation) -> bool:
        """Valida uma métrica específica"""
        print(f"\n🔍 Validando métrica: {validation.name}")

        if validation.description:
            print(f"   Descrição: {validation.description}")

        # Query a métrica
        result = self.query_metric(validation.name)

        if result.get("status") != "success":
            error_msg = result.get("error", "Erro desconhecido")
            print(f"❌ Falha na query: {error_msg}")
            return not validation.critical

        data = result.get("data", {})
        result_type = data.get("resultType", "")
        results = data.get("result", [])

        if not results:
            print(f"❌ Nenhum resultado encontrado para {validation.name}")
            return not validation.critical

        print(f"✅ Encontrados {len(results)} série(s) de dados")

        # Validar número mínimo de samples
        total_samples = len(results)
        if total_samples < validation.min_samples:
            print(f"⚠️  Poucos samples: {total_samples} (mínimo: {validation.min_samples})")
            if validation.critical:
                return False

        # Validar labels esperados
        missing_labels = set()
        for result in results[:3]:  # Verificar apenas os primeiros 3 para performance
            metric_labels = set(result.get("metric", {}).keys())

            for expected_label in validation.expected_labels:
                if expected_label not in metric_labels:
                    missing_labels.add(expected_label)

        if missing_labels:
            print(f"⚠️  Labels faltando em algumas séries: {list(missing_labels)}")
            if validation.critical:
                return False

        # Mostrar exemplo de labels encontrados
        if results:
            example_labels = results[0].get("metric", {})
            print(f"   Exemplo de labels: {json.dumps(example_labels, indent=2)}")

        print(f"✅ Métrica {validation.name} validada com sucesso")
        return True

    def check_prometheus_health(self) -> bool:
        """Verifica se o Prometheus está saudável"""
        try:
            print("🏥 Verificando saúde do Prometheus...")

            health_url = urljoin(self.prometheus_url, "/-/healthy")
            response = self.session.get(health_url)
            response.raise_for_status()

            if "Prometheus is Healthy" in response.text:
                print("✅ Prometheus está saudável")
                return True
            else:
                print("❌ Prometheus não está saudável")
                return False

        except requests.RequestException as e:
            print(f"❌ Erro ao verificar saúde do Prometheus: {e}")
            return False

    def get_target_health(self) -> Dict:
        """Obtém status dos targets do Prometheus"""
        try:
            url = urljoin(self.prometheus_url, "/api/v1/targets")
            response = self.session.get(url)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            print(f"❌ Erro ao obter targets: {e}")
            return {"status": "error", "error": str(e)}

    def validate_targets(self) -> bool:
        """Valida se os targets estão sendo descobertos corretamente"""
        print("\n🎯 Validando targets do Prometheus...")

        targets_data = self.get_target_health()

        if targets_data.get("status") != "success":
            print("❌ Falha ao obter informações de targets")
            return False

        targets = targets_data.get("data", {}).get("activeTargets", [])

        if not targets:
            print("❌ Nenhum target ativo encontrado")
            return False

        print(f"✅ Encontrados {len(targets)} target(s) ativo(s)")

        # Verificar targets específicos do Neural Hive-Mind
        neural_hive_targets = [
            t for t in targets
            if any(label.get("neural_hive_component") for label in t.get("labels", {}).items())
        ]

        if neural_hive_targets:
            print(f"✅ Encontrados {len(neural_hive_targets)} target(s) do Neural Hive-Mind")
        else:
            print("⚠️  Nenhum target específico do Neural Hive-Mind encontrado")

        # Verificar targets com problemas
        unhealthy_targets = [t for t in targets if t.get("health") != "up"]
        if unhealthy_targets:
            print(f"⚠️  {len(unhealthy_targets)} target(s) com problemas:")
            for target in unhealthy_targets[:5]:  # Mostrar apenas os primeiros 5
                job = target.get("labels", {}).get("job", "unknown")
                health = target.get("health", "unknown")
                print(f"     - {job}: {health}")

        return len(unhealthy_targets) == 0


def get_neural_hive_metric_validations() -> List[MetricValidation]:
    """Retorna lista de validações para métricas do Neural Hive-Mind"""
    return [
        MetricValidation(
            name="neural_hive_requests_total",
            expected_labels=["neural_hive_component", "neural_hive_layer", "status"],
            min_samples=1,
            description="Total de requisições processadas no sistema",
            critical=True
        ),
        MetricValidation(
            name="neural_hive_captura_duration_seconds",
            expected_labels=["neural_hive_component", "neural_hive_layer"],
            min_samples=1,
            description="Duração do processo de captura de intenções",
            critical=True
        ),
        MetricValidation(
            name="up",
            expected_labels=["job", "instance"],
            min_samples=3,
            description="Status de saúde dos serviços",
            critical=False
        ),
        MetricValidation(
            name="prometheus_tsdb_samples_appended_total",
            expected_labels=["job", "instance"],
            min_samples=1,
            description="Total de samples adicionados ao Prometheus",
            critical=False
        ),
        MetricValidation(
            name="process_resident_memory_bytes",
            expected_labels=["job", "instance"],
            min_samples=1,
            description="Uso de memória dos processos",
            critical=False
        ),
    ]


def main():
    parser = argparse.ArgumentParser(description="Validar métricas do Neural Hive-Mind")
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="URL do servidor Prometheus (default: http://localhost:9090)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout para requisições em segundos (default: 30)"
    )
    parser.add_argument(
        "--skip-critical",
        action="store_true",
        help="Continuar mesmo se métricas críticas falharem"
    )

    args = parser.parse_args()

    print("=== Validação de Métricas Neural Hive-Mind ===")
    print(f"Prometheus URL: {args.prometheus_url}")
    print(f"Timeout: {args.timeout}s")
    print("")

    validator = MetricsValidator(args.prometheus_url)
    validator.session.timeout = args.timeout

    success = True

    # Verificar saúde do Prometheus
    if not validator.check_prometheus_health():
        if not args.skip_critical:
            print("❌ Parando validação devido à falha na saúde do Prometheus")
            sys.exit(1)
        success = False

    # Validar targets
    if not validator.validate_targets():
        print("⚠️  Alguns targets têm problemas, mas continuando...")

    # Validar métricas específicas
    print("\n📊 Validando métricas específicas...")
    validations = get_neural_hive_metric_validations()

    failed_validations = []

    for validation in validations:
        try:
            if not validator.validate_metric(validation):
                failed_validations.append(validation.name)
                if validation.critical and not args.skip_critical:
                    success = False
        except Exception as e:
            print(f"❌ Erro inesperado ao validar {validation.name}: {e}")
            failed_validations.append(validation.name)
            if validation.critical and not args.skip_critical:
                success = False

    # Resumo final
    print(f"\n{'='*50}")
    print("📈 RESUMO DA VALIDAÇÃO")
    print(f"{'='*50}")

    total_validations = len(validations)
    successful_validations = total_validations - len(failed_validations)

    print(f"Total de validações: {total_validations}")
    print(f"Sucessos: {successful_validations}")
    print(f"Falhas: {len(failed_validations)}")

    if failed_validations:
        print(f"\n❌ Métricas com falha: {', '.join(failed_validations)}")

    if success:
        print("\n✅ Todas as validações críticas passaram!")
        sys.exit(0)
    else:
        print("\n❌ Algumas validações críticas falharam!")
        sys.exit(1)


if __name__ == "__main__":
    main()