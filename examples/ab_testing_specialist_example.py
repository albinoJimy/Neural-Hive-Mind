"""
Exemplo de uso do ABTestingSpecialist.

Demonstra como configurar e usar A/B testing specialist para comparar
dois modelos ML em produção de forma controlada e estatisticamente válida.
"""

import os
import sys

# Adicionar caminho da biblioteca
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "libraries", "python"))

from neural_hive_specialists.ab_testing_specialist import ABTestingSpecialist
from neural_hive_specialists.config import SpecialistConfig


def create_ab_test_config() -> SpecialistConfig:
    """
    Cria configuração para A/B testing specialist.

    Returns:
        SpecialistConfig configurado para A/B testing
    """
    config = SpecialistConfig(
        # Identificação do specialist
        specialist_type="technical",
        service_name="technical-ab-test-specialist",
        # MLflow
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        mlflow_experiment_name="technical-ab-experiment",
        mlflow_model_name="technical-baseline",  # Modelo padrão
        # MongoDB
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        # Redis
        redis_cluster_nodes=os.getenv("REDIS_CLUSTER_NODES", "localhost:6379"),
        # Neo4j
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
        # Configuração de A/B Testing
        enable_ab_testing=True,
        ab_test_model_a_name="technical-baseline",  # Modelo A (baseline)
        ab_test_model_a_stage="Production",
        ab_test_model_b_name="technical-challenger",  # Modelo B (challenger)
        ab_test_model_b_stage="Staging",
        ab_test_traffic_split=0.5,  # 50% para cada variante
        ab_test_hash_seed="production-seed-2025",  # Seed para hash determinístico
        ab_test_minimum_sample_size=30,  # Mínimo de amostras para análise estatística
        # Configurações opcionais
        enable_shap_explainability=True,
    )

    return config


def example_basic_ab_testing():
    """Exemplo básico de A/B testing."""
    print("\n=== Exemplo 1: A/B Testing Básico ===\n")

    # Criar configuração
    config = create_ab_test_config()

    # Inicializar specialist
    specialist = ABTestingSpecialist(config=config)

    # Plano cognitivo para avaliar
    cognitive_plan = {
        "plan_id": "plan-abc-123",
        "intent_id": "intent-xyz-456",
        "description": "Implementar API REST para gestão de usuários",
        "complexity_score": 0.6,
        "steps": [
            "Definir schema de dados",
            "Implementar CRUD endpoints",
            "Adicionar autenticação",
            "Escrever testes",
        ],
        "estimated_effort_hours": 12,
    }

    # Executar predição
    print("Executando predição com A/B testing...")
    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    # Exibir resultado
    print(f"\nResultado da avaliação:")
    print(f"  Confidence Score: {result.confidence_score:.3f}")
    print(f"  Risk Score: {result.risk_score:.3f}")
    print(f"  Recommendation: {result.recommendation}")
    print(f"\nA/B Test Metadata:")
    print(f"  Variant: {result.metadata.get('ab_test_variant')}")
    print(f"  Model Name: {result.metadata.get('ab_test_model_name')}")
    print(f"  Model Version: {result.metadata.get('ab_test_model_version')}")
    print(f"  Model Run ID: {result.metadata.get('ab_test_model_run_id')}")
    print(f"  Traffic Split: {result.metadata.get('ab_test_traffic_split')}")
    print(f"  Hash Value: {result.metadata.get('ab_test_hash_value'):.4f}")


def example_deterministic_assignment():
    """Exemplo de atribuição determinística de variante."""
    print("\n=== Exemplo 2: Atribuição Determinística de Variante ===\n")

    config = create_ab_test_config()
    specialist = ABTestingSpecialist(config=config)

    # Mesmo plan_id deve sempre receber mesma variante
    plan_id = "plan-deterministic-test"

    print(f"Testando determinismo com plan_id: {plan_id}")
    print("Executando 5 predições com mesmo plan_id:\n")

    variants = []
    for i in range(5):
        cognitive_plan = {
            "plan_id": plan_id,  # Mesmo ID
            "description": f"Test iteration {i+1}",
            "complexity_score": 0.5,
        }

        result = specialist.evaluate_cognitive_plan(cognitive_plan)
        variant = result.metadata.get("ab_test_variant")
        variants.append(variant)
        print(f"  Iteração {i+1}: variant={variant}")

    # Verificar que todas as variantes são iguais
    all_same = all(v == variants[0] for v in variants)
    print(
        f"\nTodas as variantes são iguais: {all_same} ✓"
        if all_same
        else "ERRO: Variantes diferentes!"
    )


def example_traffic_split_distribution():
    """Exemplo de distribuição de tráfego."""
    print("\n=== Exemplo 3: Distribuição de Tráfego ===\n")

    config = create_ab_test_config()
    config.ab_test_traffic_split = 0.3  # 30% para A, 70% para B
    specialist = ABTestingSpecialist(config=config)

    print(f"Traffic split configurado: {config.ab_test_traffic_split}")
    print("Executando 100 predições com plan_ids diferentes:\n")

    variant_counts = {"model_a": 0, "model_b": 0}

    for i in range(100):
        cognitive_plan = {
            "plan_id": f"plan-distribution-{i}",
            "description": "Test plan",
            "complexity_score": 0.5,
        }

        result = specialist.evaluate_cognitive_plan(cognitive_plan)
        variant = result.metadata.get("ab_test_variant")
        variant_counts[variant] += 1

    print(f"Distribuição observada:")
    print(f"  Model A: {variant_counts['model_a']}% ({variant_counts['model_a']} requests)")
    print(f"  Model B: {variant_counts['model_b']}% ({variant_counts['model_b']} requests)")
    print(f"\nDistribuição esperada:")
    print(f"  Model A: 30%")
    print(f"  Model B: 70%")


def example_fallback_handling():
    """Exemplo de fallback quando modelo falha."""
    print("\n=== Exemplo 4: Tratamento de Fallback ===\n")

    config = create_ab_test_config()
    specialist = ABTestingSpecialist(config=config)

    # Simular cenário onde modelo pode falhar
    cognitive_plan = {
        "plan_id": "plan-fallback-test",
        "description": "Plan that might trigger fallback",
        "complexity_score": 0.8,
    }

    print("Executando predição (com possível fallback)...")
    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    if result:
        variant = result.metadata.get("ab_test_variant")
        is_fallback = result.metadata.get("ab_test_fallback", False)

        print(f"\nResultado:")
        print(f"  Variant: {variant}")
        print(f"  Is Fallback: {is_fallback}")
        print(f"  Confidence: {result.confidence_score:.3f}")

        if is_fallback:
            print("\n⚠️  Fallback foi acionado - modelo primário falhou")
    else:
        print("\n❌ Ambos os modelos falharam")


def example_collect_statistics():
    """Exemplo de coleta de estatísticas de A/B test."""
    print("\n=== Exemplo 5: Coleta de Estatísticas ===\n")

    config = create_ab_test_config()
    specialist = ABTestingSpecialist(config=config)

    # Simular múltiplas predições
    print("Simulando 50 predições para gerar estatísticas...")
    for i in range(50):
        cognitive_plan = {
            "plan_id": f"plan-stats-{i}",
            "description": f"Test plan {i}",
            "complexity_score": 0.5 + (i % 5) * 0.1,
        }
        specialist.evaluate_cognitive_plan(cognitive_plan)

    # Coletar estatísticas
    print("\nColetando estatísticas de A/B test...")
    stats = specialist.get_ab_test_statistics()

    # Exibir estatísticas
    print(f"\n📊 Estatísticas de A/B Testing:")
    print(f"\n  Model A:")
    print(f"    Sample Size: {stats['model_a']['sample_size']}")
    print(f"    Avg Confidence: {stats['model_a']['avg_confidence']:.3f}")
    print(f"    Avg Latency: {stats['model_a']['avg_latency']:.3f}s")
    print(f"    Agreement Rate: {stats['model_a']['agreement_rate']:.3f}")
    print(f"    Recommendations: {stats['model_a']['recommendation_distribution']}")

    print(f"\n  Model B:")
    print(f"    Sample Size: {stats['model_b']['sample_size']}")
    print(f"    Avg Confidence: {stats['model_b']['avg_confidence']:.3f}")
    print(f"    Avg Latency: {stats['model_b']['avg_latency']:.3f}s")
    print(f"    Agreement Rate: {stats['model_b']['agreement_rate']:.3f}")
    print(f"    Recommendations: {stats['model_b']['recommendation_distribution']}")

    print(f"\n  Statistical Significance:")
    sig = stats["statistical_significance"]
    print(f"    P-value: {sig.get('p_value', 'N/A')}")
    print(f"    Is Significant: {sig.get('is_significant', False)}")
    print(f"    Winner: {sig.get('winner', 'None')}")

    print(f"\n  Recommendation: {stats['recommendation']}")


def example_custom_traffic_split():
    """Exemplo com traffic split customizado."""
    print("\n=== Exemplo 6: Traffic Split Customizado ===\n")

    # Teste conservador: 90% baseline, 10% challenger
    config = create_ab_test_config()
    config.ab_test_traffic_split = 0.9  # 90% para A

    specialist = ABTestingSpecialist(config=config)

    print(f"Traffic split: {config.ab_test_traffic_split}")
    print("(90% tráfego para baseline, 10% para challenger)")

    cognitive_plan = {
        "plan_id": "plan-conservative-split",
        "description": "Test with conservative split",
        "complexity_score": 0.6,
    }

    result = specialist.evaluate_cognitive_plan(cognitive_plan)
    print(f"\nVariant selecionada: {result.metadata.get('ab_test_variant')}")


def example_monitoring_metrics():
    """Exemplo de métricas publicadas."""
    print("\n=== Exemplo 7: Métricas de Monitoramento ===\n")

    config = create_ab_test_config()
    specialist = ABTestingSpecialist(config=config)

    cognitive_plan = {
        "plan_id": "plan-metrics-example",
        "description": "Test for metrics",
        "complexity_score": 0.5,
    }

    print("Executando predição e publicando métricas...")
    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    print(f"\nMétricas publicadas no Prometheus:")
    print(f"  - specialist_ab_test_traffic_split")
    print(
        f"  - specialist_ab_test_variant_usage_total{{variant=\"{result.metadata.get('ab_test_variant')}\"}}"
    )
    print(
        f"  - specialist_ab_test_variant_confidence_score{{variant=\"{result.metadata.get('ab_test_variant')}\"}}"
    )
    print(
        f"  - specialist_ab_test_variant_risk_score{{variant=\"{result.metadata.get('ab_test_variant')}\"}}"
    )
    print(
        f"  - specialist_ab_test_variant_processing_time_seconds{{variant=\"{result.metadata.get('ab_test_variant')}\"}}"
    )
    print(
        f"  - specialist_ab_test_variant_recommendation_distribution{{variant=\"{result.metadata.get('ab_test_variant')}\", recommendation=\"{result.recommendation}\"}}"
    )


def example_hash_seed():
    """Exemplo de impacto do hash seed."""
    print("\n=== Exemplo 8: Impacto do Hash Seed ===\n")

    plan_id = "plan-hash-test"

    # Testar com seed 1
    config1 = create_ab_test_config()
    config1.ab_test_hash_seed = "seed-1"
    specialist1 = ABTestingSpecialist(config=config1)

    result1 = specialist1.evaluate_cognitive_plan(
        {"plan_id": plan_id, "description": "Test", "complexity_score": 0.5}
    )

    # Testar com seed 2
    config2 = create_ab_test_config()
    config2.ab_test_hash_seed = "seed-2"
    specialist2 = ABTestingSpecialist(config=config2)

    result2 = specialist2.evaluate_cognitive_plan(
        {"plan_id": plan_id, "description": "Test", "complexity_score": 0.5}
    )

    print(f"Mesmo plan_id: {plan_id}")
    print(f"  Seed 'seed-1' -> variant: {result1.metadata.get('ab_test_variant')}")
    print(f"  Seed 'seed-2' -> variant: {result2.metadata.get('ab_test_variant')}")
    print(f"\nSeed diferente pode resultar em variante diferente para mesmo plan_id")


def main():
    """Executa todos os exemplos."""
    print("=" * 70)
    print("EXEMPLOS DE USO DO A/B TESTING SPECIALIST")
    print("=" * 70)

    try:
        example_basic_ab_testing()
        example_deterministic_assignment()
        example_traffic_split_distribution()
        example_fallback_handling()
        example_collect_statistics()
        example_custom_traffic_split()
        example_monitoring_metrics()
        example_hash_seed()

        print("\n" + "=" * 70)
        print("TODOS OS EXEMPLOS EXECUTADOS COM SUCESSO!")
        print("=" * 70)

        print("\n💡 Dicas:")
        print("  - Use traffic_split conservador (0.9) para testes iniciais")
        print("  - Aguarde pelo menos 30 amostras por variante antes de análise estatística")
        print("  - Monitore métricas no Grafana dashboard: /d/model-comparison")
        print("  - Use mesmo hash_seed em produção para consistência")
        print("  - Analise resultados com: scripts/analyze_ab_test_results.py")

    except Exception as e:
        print(f"\n❌ Erro ao executar exemplos: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Nota: Este exemplo requer MLflow, MongoDB, Redis e Neo4j rodando
    # Para rodar sem infraestrutura, use mocks apropriados
    main()
