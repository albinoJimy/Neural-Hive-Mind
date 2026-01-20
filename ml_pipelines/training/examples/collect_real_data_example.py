#!/usr/bin/env python3
"""
Exemplo de uso do RealDataCollector.

Demonstra:
- Verificação de estatísticas antes da coleta
- Coleta de dados reais do ledger cognitivo
- Validação de distribuição de labels
- Validação de qualidade de dados
- Criação de splits temporais
- Salvamento em formato Parquet

Uso:
    python collect_real_data_example.py --specialist-type technical --days 90

Requisitos:
    - MongoDB com collections specialist_opinions e specialist_feedback
    - Mínimo de 1000 amostras com feedback por specialist
    - Variável de ambiente MONGODB_URI (opcional, default: mongodb://localhost:27017)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Adicionar paths para imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'libraries' / 'python'))

import structlog

from real_data_collector import (
    RealDataCollector,
    InsufficientDataError,
    DataQualityError,
    FeatureExtractionError
)

# Configurar logging estruturado
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description='Coleta dados reais do ledger cognitivo para treinamento ML'
    )
    parser.add_argument(
        '--specialist-type',
        type=str,
        default='technical',
        help='Tipo do especialista (technical, business, evolution, etc)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Janela de tempo em dias para buscar opiniões'
    )
    parser.add_argument(
        '--min-samples',
        type=int,
        default=1000,
        help='Mínimo de amostras necessárias'
    )
    parser.add_argument(
        '--min-rating',
        type=float,
        default=0.0,
        help='Rating mínimo de feedback para incluir'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/real',
        help='Diretório para salvar arquivos Parquet'
    )
    parser.add_argument(
        '--mongodb-uri',
        type=str,
        default=None,
        help='URI MongoDB (default: env MONGODB_URI ou localhost)'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Apenas mostrar estatísticas, sem coletar dados'
    )
    parser.add_argument(
        '--opinions-collection',
        type=str,
        default=None,
        help='Nome da collection de opiniões (default: env OPINIONS_COLLECTION ou specialist_opinions)'
    )
    parser.add_argument(
        '--feedback-collection',
        type=str,
        default=None,
        help='Nome da collection de feedback (default: env FEEDBACK_COLLECTION ou feedback)'
    )

    args = parser.parse_args()

    logger.info(
        "Iniciando coleta de dados reais",
        specialist_type=args.specialist_type,
        days=args.days,
        min_samples=args.min_samples
    )

    # Inicializar collector
    collector = RealDataCollector(
        mongodb_uri=args.mongodb_uri,
        mongodb_database='neural_hive',
        opinions_collection_name=args.opinions_collection,
        feedback_collection_name=args.feedback_collection
    )

    try:
        # 1. Verificar estatísticas primeiro
        print("\n" + "=" * 60)
        print("ESTATÍSTICAS DAS COLLECTIONS")
        print("=" * 60)

        stats = await collector.get_collection_statistics(
            specialist_type=args.specialist_type,
            days=args.days
        )

        print(f"Especialista: {stats['specialist_type']}")
        print(f"Período: últimos {stats['days']} dias")
        print(f"Total de opiniões: {stats['total_opinions']}")
        print(f"Opiniões com feedback: {stats['opinions_with_feedback']}")
        print(f"Taxa de cobertura: {stats['coverage_rate']}%")
        print(f"Suficiente para treinamento: {'Sim' if stats['sufficient_for_training'] else 'Não'}")

        if stats['rating_distribution']:
            print("\nDistribuição de ratings:")
            for rating, count in sorted(stats['rating_distribution'].items()):
                print(f"  Rating {rating}: {count} feedbacks")

        if args.stats_only:
            print("\n[--stats-only] Apenas estatísticas solicitadas, encerrando.")
            return

        if not stats['sufficient_for_training']:
            print("\n⚠️  AVISO: Dados podem ser insuficientes para treinamento!")
            print(f"   Necessário: {args.min_samples} amostras")
            print(f"   Disponível: ~{stats['opinions_with_feedback']} (estimativa)")

        # 2. Coletar dados
        print("\n" + "=" * 60)
        print("COLETANDO DADOS DE TREINAMENTO")
        print("=" * 60)

        try:
            df = await collector.collect_training_data(
                specialist_type=args.specialist_type,
                days=args.days,
                min_samples=args.min_samples,
                min_feedback_rating=args.min_rating
            )

            print(f"✓ Dados coletados: {len(df)} amostras")

        except InsufficientDataError as e:
            print(f"\n❌ ERRO: {e}")
            print("\nSugestões:")
            print("  1. Coletar mais feedback humano via Approval Service")
            print("  2. Reduzir --min-samples")
            print("  3. Aumentar --days para incluir mais opiniões")
            print("  4. Usar dados sintéticos como fallback")
            return

        except FeatureExtractionError as e:
            print(f"\n❌ ERRO DE EXTRAÇÃO: {e}")
            print("\nSugestões:")
            print("  1. Verificar se neural_hive_specialists está instalado")
            print("  2. Verificar integridade dos cognitive_plan nas opiniões")
            print("  3. Revisar FeatureExtractor para lidar com dados incompletos")
            return

        # 3. Validar distribuição de labels
        print("\n" + "=" * 60)
        print("VALIDAÇÃO DE DISTRIBUIÇÃO")
        print("=" * 60)

        dist_report = collector.validate_label_distribution(df, args.specialist_type)

        print("\nDistribuição de labels:")
        # Nota: approve_with_conditions não é aceito pelo schema de feedback atual
        label_names = {0: 'reject', 1: 'approve', 2: 'review_required'}
        for label, count in sorted(dist_report['distribution'].items()):
            pct = dist_report['percentages'].get(label, 0)
            name = label_names.get(label, f'unknown_{label}')
            print(f"  {name}: {count} ({pct:.1f}%)")

        print(f"\nBalanceado: {'Sim' if dist_report['is_balanced'] else 'Não'}")

        if dist_report['warnings']:
            print("\n⚠️  Avisos:")
            for warning in dist_report['warnings']:
                print(f"  - {warning}")

        # 4. Validar qualidade dos dados
        print("\n" + "=" * 60)
        print("VALIDAÇÃO DE QUALIDADE")
        print("=" * 60)

        quality_report = collector.validate_data_quality(df)

        print(f"Quality Score: {quality_report['quality_score']:.3f}")
        print(f"Passou: {'Sim' if quality_report['passed'] else 'Não'}")
        print(f"Features sparse (sempre zero): {quality_report['sparse_features_count']}")
        print(f"Taxa de sparsity: {quality_report['sparsity_rate']:.1f}%")

        if quality_report['warnings']:
            print("\n⚠️  Avisos de qualidade:")
            for warning in quality_report['warnings']:
                print(f"  - {warning}")

        if not quality_report['passed']:
            print("\n❌ Qualidade abaixo do threshold!")
            print("   Considere revisar o processo de coleta de feedback.")

        # 5. Criar splits temporais
        print("\n" + "=" * 60)
        print("CRIANDO SPLITS TEMPORAIS")
        print("=" * 60)

        train_df, val_df, test_df = collector.create_temporal_splits(df)

        print(f"Train: {len(train_df)} amostras (60%)")
        print(f"  Período: {train_df['created_at'].min()} até {train_df['created_at'].max()}")

        print(f"Val: {len(val_df)} amostras (20%)")
        print(f"  Período: {val_df['created_at'].min()} até {val_df['created_at'].max()}")

        print(f"Test: {len(test_df)} amostras (20%)")
        print(f"  Período: {test_df['created_at'].min()} até {test_df['created_at'].max()}")

        # 6. Salvar em Parquet
        print("\n" + "=" * 60)
        print("SALVANDO ARQUIVOS")
        print("=" * 60)

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"{args.specialist_type}"

        train_path = output_dir / f"{prefix}_train.parquet"
        val_path = output_dir / f"{prefix}_val.parquet"
        test_path = output_dir / f"{prefix}_test.parquet"

        # Remover coluna created_at antes de salvar (não é feature)
        feature_cols = [col for col in train_df.columns if col not in ['opinion_id', 'plan_id', 'specialist_type', 'created_at', 'human_rating']]

        train_df[feature_cols].to_parquet(train_path, index=False)
        val_df[feature_cols].to_parquet(val_path, index=False)
        test_df[feature_cols].to_parquet(test_path, index=False)

        print(f"✓ Salvo: {train_path}")
        print(f"✓ Salvo: {val_path}")
        print(f"✓ Salvo: {test_path}")

        # Resumo final
        print("\n" + "=" * 60)
        print("RESUMO")
        print("=" * 60)
        print(f"Especialista: {args.specialist_type}")
        print(f"Total de amostras: {len(df)}")
        print(f"Quality Score: {quality_report['quality_score']:.3f}")
        print(f"Distribuição balanceada: {'Sim' if dist_report['is_balanced'] else 'Não'}")
        print(f"Arquivos salvos em: {output_dir.absolute()}")
        print("\n✅ Coleta de dados reais concluída com sucesso!")

    finally:
        collector.close()


if __name__ == "__main__":
    asyncio.run(main())
