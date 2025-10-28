#!/usr/bin/env python3
"""
Script CLI para analisar resultados de A/B testing de specialists.

Este script consulta métricas de A/B testing do Prometheus e MongoDB,
calcula significância estatística e gera relatórios.

Uso:
    python3 analyze_ab_test_results.py --specialist-type technical --window-days 7
    python3 analyze_ab_test_results.py --specialist-type technical --output-format json
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import structlog

try:
    from scipy.stats import chi2_contingency
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("WARNING: scipy não disponível. Cálculo de significância estatística desabilitado.", file=sys.stderr)

try:
    from prometheus_api_client import PrometheusConnect
    PROMETHEUS_CLIENT_AVAILABLE = True
except ImportError:
    PROMETHEUS_CLIENT_AVAILABLE = False
    print("WARNING: prometheus-api-client não disponível. Métricas do Prometheus desabilitadas.", file=sys.stderr)

try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("WARNING: pymongo não disponível. Análise de business metrics desabilitada.", file=sys.stderr)

logger = structlog.get_logger(__name__)


class ABTestAnalyzer:
    """Analisador de resultados de A/B testing."""

    def __init__(
        self,
        specialist_type: str,
        prometheus_url: str = "http://localhost:9090",
        mongodb_uri: str = "mongodb://localhost:27017",
        window_days: int = 7
    ):
        """
        Inicializa o analisador.

        Args:
            specialist_type: Tipo de specialist (technical, business, etc.)
            prometheus_url: URL do Prometheus
            mongodb_uri: URI do MongoDB
            window_days: Janela de tempo em dias para análise
        """
        self.specialist_type = specialist_type
        self.window_days = window_days
        self.prom_client = None
        self.mongo_client = None

        # Conectar ao Prometheus
        if PROMETHEUS_CLIENT_AVAILABLE:
            try:
                self.prom_client = PrometheusConnect(url=prometheus_url, disable_ssl=True)
                logger.info("Conectado ao Prometheus", url=prometheus_url)
            except Exception as e:
                logger.error("Erro ao conectar ao Prometheus", error=str(e))

        # Conectar ao MongoDB
        if MONGODB_AVAILABLE:
            try:
                self.mongo_client = MongoClient(mongodb_uri)
                # Testar conexão
                self.mongo_client.admin.command('ping')
                logger.info("Conectado ao MongoDB", uri=mongodb_uri)
            except Exception as e:
                logger.error("Erro ao conectar ao MongoDB", error=str(e))

    def collect_metrics(self) -> Dict[str, Any]:
        """
        Coleta métricas de A/B testing do Prometheus.

        Returns:
            Dict com métricas de ambas variantes
        """
        metrics = {
            'model_a': {},
            'model_b': {}
        }

        if not self.prom_client:
            logger.warning("Prometheus client não disponível")
            return metrics

        # Coletar sample size
        for variant in ['model_a', 'model_b']:
            try:
                query = f'specialist_ab_test_variant_usage_total{{specialist_type="{self.specialist_type}", variant="{variant}"}}'
                result = self.prom_client.custom_query(query=query)
                if result:
                    metrics[variant]['sample_size'] = int(float(result[0]['value'][1]))
                else:
                    metrics[variant]['sample_size'] = 0
            except Exception as e:
                logger.error(f"Erro ao coletar sample_size para {variant}", error=str(e))
                metrics[variant]['sample_size'] = 0

            # Coletar confidence médio
            try:
                query = f'rate(specialist_ab_test_variant_confidence_score_sum{{specialist_type="{self.specialist_type}", variant="{variant}"}}[{self.window_days}d]) / rate(specialist_ab_test_variant_confidence_score_count{{specialist_type="{self.specialist_type}", variant="{variant}"}}[{self.window_days}d])'
                result = self.prom_client.custom_query(query=query)
                if result:
                    metrics[variant]['avg_confidence'] = float(result[0]['value'][1])
                else:
                    metrics[variant]['avg_confidence'] = 0.0
            except Exception as e:
                logger.error(f"Erro ao coletar avg_confidence para {variant}", error=str(e))
                metrics[variant]['avg_confidence'] = 0.0

            # Coletar latência média
            try:
                query = f'rate(specialist_ab_test_variant_processing_time_seconds_sum{{specialist_type="{self.specialist_type}", variant="{variant}"}}[{self.window_days}d]) / rate(specialist_ab_test_variant_processing_time_seconds_count{{specialist_type="{self.specialist_type}", variant="{variant}"}}[{self.window_days}d])'
                result = self.prom_client.custom_query(query=query)
                if result:
                    metrics[variant]['avg_latency'] = float(result[0]['value'][1])
                else:
                    metrics[variant]['avg_latency'] = 0.0
            except Exception as e:
                logger.error(f"Erro ao coletar avg_latency para {variant}", error=str(e))
                metrics[variant]['avg_latency'] = 0.0

            # Coletar agreement rate
            try:
                query = f'specialist_ab_test_variant_consensus_agreement{{specialist_type="{self.specialist_type}", variant="{variant}"}}'
                result = self.prom_client.custom_query(query=query)
                if result:
                    metrics[variant]['agreement_rate'] = float(result[0]['value'][1])
                else:
                    metrics[variant]['agreement_rate'] = 0.0
            except Exception as e:
                logger.error(f"Erro ao coletar agreement_rate para {variant}", error=str(e))
                metrics[variant]['agreement_rate'] = 0.0

            # Coletar distribuição de recomendações
            metrics[variant]['recommendation_distribution'] = {}
            for recommendation in ['approve', 'reject', 'review_required', 'conditional']:
                try:
                    query = f'specialist_ab_test_variant_recommendation_distribution{{specialist_type="{self.specialist_type}", variant="{variant}", recommendation="{recommendation}"}}'
                    result = self.prom_client.custom_query(query=query)
                    if result:
                        metrics[variant]['recommendation_distribution'][recommendation] = int(float(result[0]['value'][1]))
                except Exception as e:
                    logger.debug(f"Erro ao coletar {recommendation} para {variant}", error=str(e))

        return metrics

    def calculate_statistical_significance(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcula significância estatística entre variantes.

        Args:
            metrics: Métricas coletadas

        Returns:
            Dict com resultados de significância estatística
        """
        if not SCIPY_AVAILABLE:
            return {
                'p_value': None,
                'is_significant': False,
                'winner': None,
                'error': 'scipy não disponível'
            }

        # Verificar amostras suficientes
        sample_a = metrics['model_a'].get('sample_size', 0)
        sample_b = metrics['model_b'].get('sample_size', 0)

        if sample_a < 30 or sample_b < 30:
            return {
                'p_value': None,
                'is_significant': False,
                'winner': None,
                'error': f'amostras insuficientes (mínimo 30 por variante, tem {sample_a}/{sample_b})'
            }

        try:
            # Construir tabela de contingência usando approve vs não-approve
            approve_a = metrics['model_a']['recommendation_distribution'].get('approve', 0)
            total_a = sample_a
            reject_a = total_a - approve_a

            approve_b = metrics['model_b']['recommendation_distribution'].get('approve', 0)
            total_b = sample_b
            reject_b = total_b - approve_b

            contingency_table = [
                [approve_a, reject_a],
                [approve_b, reject_b]
            ]

            chi2, p_value, dof, expected = chi2_contingency(contingency_table)

            is_significant = p_value < 0.05

            # Determinar vencedor baseado em confidence médio
            winner = None
            if is_significant:
                conf_a = metrics['model_a'].get('avg_confidence', 0.0)
                conf_b = metrics['model_b'].get('avg_confidence', 0.0)
                winner = 'model_b' if conf_b > conf_a else 'model_a'

            return {
                'p_value': float(p_value),
                'chi2': float(chi2),
                'is_significant': is_significant,
                'winner': winner,
                'confidence_level': 0.95,
                'contingency_table': contingency_table
            }

        except Exception as e:
            logger.error("Erro ao calcular significância estatística", error=str(e))
            return {
                'p_value': None,
                'is_significant': False,
                'winner': None,
                'error': str(e)
            }

    def generate_recommendation(self, metrics: Dict[str, Any], stats: Dict[str, Any]) -> str:
        """
        Gera recomendação baseada em métricas e estatísticas.

        Args:
            metrics: Métricas coletadas
            stats: Resultados de significância estatística

        Returns:
            String com recomendação
        """
        if stats.get('error'):
            return f"insufficient_data: {stats['error']}"

        if not stats['is_significant']:
            return "continue_testing: diferença não é estatisticamente significativa"

        winner = stats['winner']
        conf_a = metrics['model_a'].get('avg_confidence', 0.0)
        conf_b = metrics['model_b'].get('avg_confidence', 0.0)
        lat_a = metrics['model_a'].get('avg_latency', 0.0)
        lat_b = metrics['model_b'].get('avg_latency', 0.0)

        # Verificar se vencedor é significativamente melhor
        conf_improvement = abs(conf_b - conf_a) / conf_a if conf_a > 0 else 0
        lat_degradation = abs(lat_b - lat_a) / lat_a if lat_a > 0 else 0

        if winner == 'model_b':
            if lat_degradation > 0.2:  # Se latência piorou >20%
                return f"deploy_{winner}_with_caution: melhoria em confidence ({conf_improvement:.1%}), mas latência aumentou ({lat_degradation:.1%})"
            else:
                return f"deploy_{winner}: melhoria significativa em confidence ({conf_improvement:.1%})"
        else:
            return f"keep_{winner}: modelo baseline ainda é melhor"

    def analyze(self) -> Dict[str, Any]:
        """
        Executa análise completa de A/B testing.

        Returns:
            Dict com resultados da análise
        """
        logger.info("Iniciando análise de A/B testing", specialist_type=self.specialist_type)

        # Coletar métricas
        metrics = self.collect_metrics()

        # Calcular significância estatística
        stats = self.calculate_statistical_significance(metrics)

        # Gerar recomendação
        recommendation = self.generate_recommendation(metrics, stats)

        result = {
            'specialist_type': self.specialist_type,
            'analysis_timestamp': datetime.utcnow().isoformat(),
            'window_days': self.window_days,
            'metrics': metrics,
            'statistical_significance': stats,
            'recommendation': recommendation
        }

        logger.info("Análise concluída", recommendation=recommendation)

        return result

    def close(self):
        """Fecha conexões."""
        if self.mongo_client:
            self.mongo_client.close()


def format_markdown(result: Dict[str, Any]) -> str:
    """
    Formata resultado em Markdown.

    Args:
        result: Resultado da análise

    Returns:
        String formatada em Markdown
    """
    md = f"""# A/B Test Analysis Report

**Specialist Type:** {result['specialist_type']}
**Analysis Date:** {result['analysis_timestamp']}
**Time Window:** {result['window_days']} days

## Metrics Summary

### Model A (Baseline)
- **Sample Size:** {result['metrics']['model_a']['sample_size']}
- **Avg Confidence:** {result['metrics']['model_a']['avg_confidence']:.3f}
- **Avg Latency:** {result['metrics']['model_a']['avg_latency']:.3f}s
- **Agreement Rate:** {result['metrics']['model_a']['agreement_rate']:.3f}
- **Recommendations:** {result['metrics']['model_a']['recommendation_distribution']}

### Model B (Challenger)
- **Sample Size:** {result['metrics']['model_b']['sample_size']}
- **Avg Confidence:** {result['metrics']['model_b']['avg_confidence']:.3f}
- **Avg Latency:** {result['metrics']['model_b']['avg_latency']:.3f}s
- **Agreement Rate:** {result['metrics']['model_b']['agreement_rate']:.3f}
- **Recommendations:** {result['metrics']['model_b']['recommendation_distribution']}

## Statistical Significance

"""

    stats = result['statistical_significance']
    if stats.get('error'):
        md += f"**Status:** {stats['error']}\n"
    else:
        md += f"""- **P-value:** {stats.get('p_value', 'N/A')}
- **Chi-squared:** {stats.get('chi2', 'N/A')}
- **Is Significant:** {stats.get('is_significant', False)}
- **Winner:** {stats.get('winner', 'None')}

"""

    md += f"""## Recommendation

**{result['recommendation']}**
"""

    return md


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Analisa resultados de A/B testing de specialists"
    )
    parser.add_argument(
        '--specialist-type',
        required=True,
        help='Tipo de specialist (technical, business, behavior, evolution)'
    )
    parser.add_argument(
        '--window-days',
        type=int,
        default=7,
        help='Janela de tempo em dias (padrão: 7)'
    )
    parser.add_argument(
        '--prometheus-url',
        default='http://localhost:9090',
        help='URL do Prometheus (padrão: http://localhost:9090)'
    )
    parser.add_argument(
        '--mongodb-uri',
        default='mongodb://localhost:27017',
        help='URI do MongoDB (padrão: mongodb://localhost:27017)'
    )
    parser.add_argument(
        '--output-format',
        choices=['json', 'markdown'],
        default='markdown',
        help='Formato de saída (padrão: markdown)'
    )
    parser.add_argument(
        '--output-file',
        help='Arquivo de saída (padrão: stdout)'
    )

    args = parser.parse_args()

    # Criar analisador
    analyzer = ABTestAnalyzer(
        specialist_type=args.specialist_type,
        prometheus_url=args.prometheus_url,
        mongodb_uri=args.mongodb_uri,
        window_days=args.window_days
    )

    try:
        # Executar análise
        result = analyzer.analyze()

        # Formatar saída
        if args.output_format == 'json':
            output = json.dumps(result, indent=2)
        else:
            output = format_markdown(result)

        # Escrever saída
        if args.output_file:
            with open(args.output_file, 'w') as f:
                f.write(output)
            print(f"Relatório salvo em: {args.output_file}")
        else:
            print(output)

        # Exit code baseado em recomendação
        if 'deploy_' in result['recommendation']:
            sys.exit(0)  # Sucesso - pode fazer deploy
        elif 'insufficient_data' in result['recommendation']:
            sys.exit(2)  # Dados insuficientes
        else:
            sys.exit(1)  # Continuar testando

    finally:
        analyzer.close()


if __name__ == '__main__':
    main()
