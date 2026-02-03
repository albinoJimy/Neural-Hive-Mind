"""
Exemplo de uso do EnsembleSpecialist.

Demonstra como configurar e usar um ensemble specialist para combinar
múltiplos modelos ML e obter predições mais robustas.
"""

import os
import sys

# Adicionar caminho da biblioteca
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'libraries', 'python'))

from neural_hive_specialists.ensemble_specialist import EnsembleSpecialist
from neural_hive_specialists.config import SpecialistConfig


def create_ensemble_config() -> SpecialistConfig:
    """
    Cria configuração para ensemble specialist.

    Returns:
        SpecialistConfig configurado para ensemble
    """
    config = SpecialistConfig(
        # Identificação do specialist
        specialist_type='technical',
        service_name='technical-ensemble-specialist',

        # MLflow
        mlflow_tracking_uri=os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000'),
        mlflow_experiment_name='technical-ensemble-experiment',
        mlflow_model_name='technical-ensemble',

        # MongoDB
        mongodb_uri=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'),

        # Redis
        redis_cluster_nodes=os.getenv('REDIS_CLUSTER_NODES', 'localhost:6379'),

        # Neo4j
        neo4j_uri=os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
        neo4j_password=os.getenv('NEO4J_PASSWORD', 'password'),

        # Configuração de Ensemble
        enable_ensemble=True,
        ensemble_models=['technical-rf', 'technical-gb', 'technical-lr'],
        ensemble_stages=['Production'],  # Stage único será broadcast para todos modelos
        ensemble_weights=[0.4, 0.4, 0.2],  # Pesos para cada modelo
        ensemble_aggregation_method='weighted_average',  # ou 'voting' ou 'stacking'

        # Thresholds configuráveis
        ensemble_approve_threshold=0.8,  # Confidence >= 0.8 -> approve
        ensemble_review_threshold=0.6,   # Confidence >= 0.6 -> review_required

        # Timeout de inferência
        model_inference_timeout_ms=5000,  # 5 segundos

        # Configurações opcionais
        enable_shap_explainability=True
    )

    return config


def example_basic_prediction():
    """Exemplo básico de predição com ensemble."""
    print("\n=== Exemplo 1: Predição Básica com Ensemble ===\n")

    # Criar configuração
    config = create_ensemble_config()

    # Inicializar specialist
    specialist = EnsembleSpecialist(config=config)

    # Plano cognitivo para avaliar
    cognitive_plan = {
        'plan_id': 'plan-123',
        'intent_id': 'intent-456',
        'description': 'Implementar sistema de autenticação OAuth2',
        'complexity_score': 0.7,
        'steps': [
            'Configurar provider OAuth2',
            'Implementar endpoints de callback',
            'Armazenar tokens de forma segura',
            'Implementar refresh token logic'
        ],
        'estimated_effort_hours': 16,
        'risk_factors': ['segurança', 'integração externa']
    }

    # Executar predição
    print("Executando predição com ensemble de modelos...")
    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    # Exibir resultado
    print(f"\nResultado da avaliação:")
    print(f"  Confidence Score: {result.confidence_score:.3f}")
    print(f"  Risk Score: {result.risk_score:.3f}")
    print(f"  Recommendation: {result.recommendation}")
    print(f"\nMetadata:")
    print(f"  Ensemble Models: {result.metadata.get('ensemble_models', [])}")
    print(f"  Aggregation Method: {result.metadata.get('ensemble_aggregation_method')}")

    if 'ensemble' in result.metadata:
        ens_meta = result.metadata['ensemble']
        print(f"  Prediction Variance: {ens_meta.get('prediction_variance', 0):.4f}")
        print(f"  Individual Predictions:")
        for model_pred in ens_meta.get('individual_predictions', []):
            print(f"    - {model_pred['model']}: confidence={model_pred['confidence']:.3f}")


def example_weighted_average_aggregation():
    """Exemplo de agregação por média ponderada."""
    print("\n=== Exemplo 2: Agregação por Média Ponderada ===\n")

    # Configuração com weighted average
    config = create_ensemble_config()
    config.ensemble_aggregation_method = 'weighted_average'
    config.ensemble_weights = [0.5, 0.3, 0.2]  # Maior peso para primeiro modelo

    specialist = EnsembleSpecialist(config=config)

    cognitive_plan = {
        'plan_id': 'plan-weighted-example',
        'description': 'Refatorar arquitetura de microserviços',
        'complexity_score': 0.85,
        'risk_factors': ['arquitetura', 'breaking changes']
    }

    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    print(f"Resultado com weighted average:")
    print(f"  Confidence: {result.confidence_score:.3f}")
    print(f"  Pesos usados: {config.ensemble_weights}")


def example_voting_aggregation():
    """Exemplo de agregação por votação."""
    print("\n=== Exemplo 3: Agregação por Votação ===\n")

    # Configuração com voting
    config = create_ensemble_config()
    config.ensemble_aggregation_method = 'voting'

    specialist = EnsembleSpecialist(config=config)

    cognitive_plan = {
        'plan_id': 'plan-voting-example',
        'description': 'Adicionar feature de export para CSV',
        'complexity_score': 0.3,
        'estimated_effort_hours': 4
    }

    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    print(f"Resultado com voting:")
    print(f"  Recommendation: {result.recommendation}")
    print(f"  Vote distribution:")
    if 'ensemble' in result.metadata:
        vote_dist = result.metadata['ensemble'].get('vote_distribution', {})
        for rec, count in vote_dist.items():
            print(f"    {rec}: {count} votos")


def example_with_explainability():
    """Exemplo com explainability agregada."""
    print("\n=== Exemplo 4: Ensemble com Explainability ===\n")

    # Configuração com SHAP habilitado
    config = create_ensemble_config()
    config.enable_shap_explainability = True

    specialist = EnsembleSpecialist(config=config)

    cognitive_plan = {
        'plan_id': 'plan-explainability-example',
        'description': 'Implementar cache distribuído com Redis',
        'complexity_score': 0.6,
        'steps': ['Setup Redis cluster', 'Implement caching layer', 'Add invalidation logic'],
        'risk_factors': ['performance', 'cache consistency']
    }

    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    print(f"Resultado com explainability:")
    print(f"  Confidence: {result.confidence_score:.3f}")

    if hasattr(result, 'explainability') and result.explainability:
        print(f"\nExplainability:")
        if 'ensemble' in result.explainability:
            ens_expl = result.explainability['ensemble']
            print(f"  Aggregated Feature Importances:")
            importances = ens_expl.get('aggregated_feature_importances', {})
            # Ordenar por importância
            sorted_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)
            for feature, importance in sorted_features[:5]:  # Top 5
                print(f"    {feature}: {importance:.4f}")


def example_custom_thresholds():
    """Exemplo com thresholds customizados."""
    print("\n=== Exemplo 5: Thresholds Customizados ===\n")

    # Configuração com thresholds customizados
    config = create_ensemble_config()
    config.ensemble_approve_threshold = 0.9  # Mais conservador
    config.ensemble_review_threshold = 0.7

    specialist = EnsembleSpecialist(config=config)

    cognitive_plan = {
        'plan_id': 'plan-thresholds-example',
        'description': 'Migrar banco de dados para nova versão',
        'complexity_score': 0.75,
        'risk_factors': ['data migration', 'downtime', 'rollback complexity']
    }

    result = specialist.evaluate_cognitive_plan(cognitive_plan)

    print(f"Resultado com thresholds customizados:")
    print(f"  Confidence: {result.confidence_score:.3f}")
    print(f"  Recommendation: {result.recommendation}")
    print(f"  Approve threshold: {config.ensemble_approve_threshold}")
    print(f"  Review threshold: {config.ensemble_review_threshold}")


def example_loading_weights_from_mlflow():
    """Exemplo de carregamento de pesos do MLflow."""
    print("\n=== Exemplo 6: Carregamento de Pesos do MLflow ===\n")

    config = create_ensemble_config()
    # Não especificar ensemble_weights - serão carregados do MLflow artifact
    config.ensemble_weights = None

    specialist = EnsembleSpecialist(config=config)

    # Os pesos foram carregados automaticamente do artifact ensemble_weights.json
    print(f"Pesos carregados do MLflow:")
    for model_name, weight in specialist.ensemble_weights.items():
        print(f"  {model_name}: {weight:.3f}")


def example_monitoring_metrics():
    """Exemplo de publicação de métricas."""
    print("\n=== Exemplo 7: Monitoramento de Métricas ===\n")

    config = create_ensemble_config()
    specialist = EnsembleSpecialist(config=config)

    cognitive_plan = {
        'plan_id': 'plan-metrics-example',
        'description': 'Implementar health check endpoints',
        'complexity_score': 0.2
    }

    # Executar múltiplas predições
    print("Executando 5 predições para demonstrar métricas...")
    for i in range(5):
        plan = cognitive_plan.copy()
        plan['plan_id'] = f"plan-metrics-{i}"
        result = specialist.evaluate_cognitive_plan(plan)
        print(f"  Predição {i+1}: confidence={result.confidence_score:.3f}")

    print("\nMétricas publicadas no Prometheus:")
    print("  - specialist_ensemble_model_weight{model_name}")
    print("  - specialist_ensemble_prediction_variance")
    print("  - specialist_prediction_latency_seconds")
    print("  - specialist_model_confidence_score")


def main():
    """Executa todos os exemplos."""
    print("=" * 70)
    print("EXEMPLOS DE USO DO ENSEMBLE SPECIALIST")
    print("=" * 70)

    try:
        example_basic_prediction()
        example_weighted_average_aggregation()
        example_voting_aggregation()
        example_with_explainability()
        example_custom_thresholds()
        example_loading_weights_from_mlflow()
        example_monitoring_metrics()

        print("\n" + "=" * 70)
        print("TODOS OS EXEMPLOS EXECUTADOS COM SUCESSO!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Erro ao executar exemplos: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    # Nota: Este exemplo requer MLflow, MongoDB, Redis e Neo4j rodando
    # Para rodar sem infraestrutura, use mocks apropriados
    main()
