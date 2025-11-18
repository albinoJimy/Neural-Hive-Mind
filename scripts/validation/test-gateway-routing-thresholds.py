#!/usr/bin/env python3
"""
Script de teste de routing thresholds do Gateway de Intenções

Uso:
    python test-gateway-routing-thresholds.py --gateway-url http://gateway:8000 \
        --test-file test_intents.json \
        --output results.json
"""

import argparse
import json
import requests
import time
from collections import Counter, defaultdict
from typing import List, Dict, Tuple
import statistics

def load_test_intents(file_path: str) -> List[Dict]:
    """Carregar intents de teste de arquivo JSON"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_intent(gateway_url: str, text: str, expected_domain: str = None) -> Dict:
    """Testar uma intent e retornar resultado"""
    try:
        response = requests.post(
            f"{gateway_url}/intentions",
            json={"text": text},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        result = {
            "text": text,
            "status": data.get("status"),
            "confidence": data.get("confidence"),
            "domain": data.get("domain"),
            "classification": data.get("classification"),
            "requires_validation": data.get("requires_manual_validation"),
            "routing_thresholds": data.get("routing_thresholds"),
            "expected_domain": expected_domain,
            "correct": data.get("domain") == expected_domain if expected_domain else None
        }
        return result
    except Exception as e:
        return {
            "text": text,
            "error": str(e),
            "status": "error"
        }

def run_test_suite(gateway_url: str, test_intents: List[Dict]) -> Dict:
    """Executar suite completa de testes"""
    results = []
    status_counter = Counter()
    confidence_scores = []
    correct_classifications = 0
    total_with_expected = 0

    print(f"\nTestando {len(test_intents)} intents...")

    for i, intent_data in enumerate(test_intents, 1):
        text = intent_data["text"]
        expected_domain = intent_data.get("expected_domain")

        result = test_intent(gateway_url, text, expected_domain)
        results.append(result)

        if "error" not in result:
            status_counter[result["status"]] += 1
            confidence_scores.append(result["confidence"])

            if expected_domain:
                total_with_expected += 1
                if result["correct"]:
                    correct_classifications += 1

        # Progress
        if i % 10 == 0:
            print(f"  Processado: {i}/{len(test_intents)}")

    # Calcular estatísticas
    validation_rate = (status_counter["routed_to_validation"] / len(test_intents)) * 100
    low_confidence_rate = (status_counter.get("processed_low_confidence", 0) / len(test_intents)) * 100
    processed_rate = (status_counter.get("processed", 0) / len(test_intents)) * 100

    accuracy = (correct_classifications / total_with_expected * 100) if total_with_expected > 0 else None

    summary = {
        "total_intents": len(test_intents),
        "status_distribution": dict(status_counter),
        "validation_rate_percent": round(validation_rate, 2),
        "low_confidence_rate_percent": round(low_confidence_rate, 2),
        "processed_rate_percent": round(processed_rate, 2),
        "confidence_stats": {
            "mean": round(statistics.mean(confidence_scores), 3) if confidence_scores else 0,
            "median": round(statistics.median(confidence_scores), 3) if confidence_scores else 0,
            "stdev": round(statistics.stdev(confidence_scores), 3) if len(confidence_scores) > 1 else 0,
            "min": round(min(confidence_scores), 3) if confidence_scores else 0,
            "max": round(max(confidence_scores), 3) if confidence_scores else 0
        },
        "accuracy_percent": round(accuracy, 2) if accuracy else None,
        "correct_classifications": correct_classifications,
        "total_with_expected_domain": total_with_expected
    }

    return {
        "summary": summary,
        "results": results
    }

def print_summary(summary: Dict):
    """Imprimir resumo formatado"""
    print("\n" + "="*60)
    print("RESUMO DOS TESTES")
    print("="*60)
    print(f"\nTotal de intents testadas: {summary['total_intents']}")
    print(f"\nDistribuição de status:")
    for status, count in summary['status_distribution'].items():
        percentage = (count / summary['total_intents']) * 100
        print(f"  {status}: {count} ({percentage:.1f}%)")

    print(f"\nTaxas:")
    print(f"  Processamento normal: {summary['processed_rate_percent']}%")
    print(f"  Baixa confiança: {summary['low_confidence_rate_percent']}%")
    print(f"  Validação manual: {summary['validation_rate_percent']}%")

    print(f"\nEstatísticas de confidence:")
    stats = summary['confidence_stats']
    print(f"  Média: {stats['mean']}")
    print(f"  Mediana: {stats['median']}")
    print(f"  Desvio padrão: {stats['stdev']}")
    print(f"  Min: {stats['min']} | Max: {stats['max']}")

    if summary['accuracy_percent']:
        print(f"\nPrecisão de classificação:")
        print(f"  Corretas: {summary['correct_classifications']}/{summary['total_with_expected_domain']}")
        print(f"  Acurácia: {summary['accuracy_percent']}%")

    print("\n" + "="*60)

def main():
    parser = argparse.ArgumentParser(description="Testar routing thresholds do gateway")
    parser.add_argument("--gateway-url", required=True, help="URL do gateway")
    parser.add_argument("--test-file", required=True, help="Arquivo JSON com intents de teste")
    parser.add_argument("--output", default="results.json", help="Arquivo de saída")

    args = parser.parse_args()

    # Carregar intents de teste
    test_intents = load_test_intents(args.test_file)
    print(f"Carregadas {len(test_intents)} intents de teste")

    # Executar testes
    start_time = time.time()
    test_results = run_test_suite(args.gateway_url, test_intents)
    elapsed_time = time.time() - start_time

    test_results["metadata"] = {
        "gateway_url": args.gateway_url,
        "test_file": args.test_file,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_time_seconds": round(elapsed_time, 2)
    }

    # Imprimir resumo
    print_summary(test_results["summary"])

    # Salvar resultados
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)

    print(f"\nResultados salvos em: {args.output}")
    print(f"Tempo total: {elapsed_time:.2f}s")

    # Retornar código de saída baseado em critérios
    validation_rate = test_results["summary"]["validation_rate_percent"]
    if validation_rate > 20:
        print(f"\n⚠️  ATENÇÃO: Taxa de validação manual muito alta ({validation_rate}%)")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
