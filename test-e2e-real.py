#!/usr/bin/env python3
"""
Teste E2E Real - Baseado na estrutura atual do gateway
"""

import sys
import json
import time
import requests
from datetime import datetime

# Configuração
GATEWAY_URL = "http://10.97.189.184:8000"
NUM_TESTS = 10

# Cores
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

# Cenários de teste
SCENARIOS = [
    {
        "name": "Business Analysis",
        "text": "Preciso analisar o ROI do projeto X e entender o impacto financeiro",
        "expected_domain": "business"
    },
    {
        "name": "Technical Implementation",
        "text": "Como implementar autenticação OAuth2 com refresh tokens",
        "expected_domain": "technical"
    },
    {
        "name": "Behavior Analysis",
        "text": "Os usuários estão abandonando o carrinho no checkout",
        "expected_domain": "behavior"
    },
    {
        "name": "Evolution & Optimization",
        "text": "Como podemos otimizar a performance do sistema de recomendações",
        "expected_domain": "evolution"
    },
    {
        "name": "Architecture Design",
        "text": "Preciso desenhar uma arquitetura microserviços escalável",
        "expected_domain": "architecture"
    }
]

def test_gateway_health():
    """Testa health check do gateway"""
    try:
        response = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"{RED}✗ Gateway health check failed: {e}{RESET}")
        return False

def send_intent(text, user_id):
    """Envia intenção para o gateway"""
    payload = {
        "text": text,
        "user_id": user_id,
        "context": {
            "source": "test_e2e",
            "timestamp": datetime.now().isoformat()
        }
    }

    start_time = time.time()
    response = requests.post(
        f"{GATEWAY_URL}/intentions",
        json=payload,
        timeout=30
    )
    latency_ms = (time.time() - start_time) * 1000

    return response, latency_ms

def analyze_response(response_data):
    """Analisa a resposta do gateway"""
    analysis = {
        "has_intent_id": "intent_id" in response_data,
        "has_correlation_id": "correlation_id" in response_data,
        "has_status": "status" in response_data,
        "has_confidence": "confidence" in response_data,
        "has_domain": "domain" in response_data,
        "has_classification": "classification" in response_data,
        "has_processing_time": "processing_time_ms" in response_data,
        "status": response_data.get("status", "unknown"),
        "domain": response_data.get("domain", "unknown"),
        "confidence": response_data.get("confidence", 0.0),
        "requires_validation": response_data.get("requires_manual_validation", False)
    }
    return analysis

def print_test_header():
    """Imprime cabeçalho do teste"""
    print(f"\n{CYAN}{BOLD}{'='*70}{RESET}")
    print(f"{CYAN}{BOLD}TESTE E2E - NEURAL HIVE MIND{RESET}")
    print(f"{CYAN}{BOLD}{'='*70}{RESET}\n")

def print_iteration_header(iteration, total):
    """Imprime cabeçalho da iteração"""
    print(f"\n{GREEN}{BOLD}{'─'*70}{RESET}")
    print(f"{GREEN}{BOLD}ITERAÇÃO {iteration}/{total}{RESET}")
    print(f"{GREEN}{BOLD}{'─'*70}{RESET}\n")

def print_summary(results):
    """Imprime resumo dos testes"""
    total = len(results)
    passed = sum(1 for r in results if r['status_code'] == 200)

    print(f"\n{CYAN}{BOLD}{'='*70}{RESET}")
    print(f"{CYAN}{BOLD}RESUMO DOS TESTES{RESET}")
    print(f"{CYAN}{BOLD}{'='*70}{RESET}\n")

    print(f"Total de testes: {total}")
    print(f"{GREEN}✓ Sucessos: {passed}{RESET}")
    print(f"{RED}✗ Falhas: {total - passed}{RESET}")
    print(f"Taxa de sucesso: {(passed/total*100):.1f}%\n")

    # Estatísticas de latência
    latencies = [r['latency_ms'] for r in results if r['status_code'] == 200]
    if latencies:
        print(f"Latências:")
        print(f"  Min: {min(latencies):.2f}ms")
        print(f"  Max: {max(latencies):.2f}ms")
        print(f"  Média: {sum(latencies)/len(latencies):.2f}ms\n")

    # Distribuição por domínio
    domains = {}
    for r in results:
        if r['status_code'] == 200:
            domain = r['analysis']['domain']
            domains[domain] = domains.get(domain, 0) + 1

    print(f"Distribuição por domínio:")
    for domain, count in sorted(domains.items()):
        print(f"  {domain}: {count}")

    # Status de validação
    needs_validation = sum(1 for r in results if r['status_code'] == 200 and r['analysis']['requires_validation'])
    print(f"\nRequerem validação manual: {needs_validation}/{passed}")

    print(f"\n{CYAN}{BOLD}{'='*70}{RESET}\n")

def main():
    """Função principal"""
    print_test_header()

    # Verifica health do gateway
    print(f"Verificando health do gateway...")
    if not test_gateway_health():
        print(f"{RED}✗ Gateway não está saudável. Abortando.{RESET}")
        return 1
    print(f"{GREEN}✓ Gateway está saudável{RESET}\n")

    results = []

    # Executa testes
    for iteration in range(1, NUM_TESTS + 1):
        print_iteration_header(iteration, NUM_TESTS)

        for scenario in SCENARIOS:
            print(f"{BOLD}Cenário: {scenario['name']}{RESET}")
            print(f"Texto: {scenario['text']}")

            try:
                response, latency_ms = send_intent(
                    scenario['text'],
                    f"test-user-{iteration}"
                )

                print(f"Latência: {YELLOW}{latency_ms:.2f}ms{RESET}")
                print(f"Status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    analysis = analyze_response(data)

                    print(f"{GREEN}✓ Resposta recebida{RESET}")
                    print(f"  Domain: {analysis['domain']}")
                    print(f"  Status: {analysis['status']}")
                    print(f"  Confidence: {analysis['confidence']:.2f}")
                    print(f"  Intent ID: {data.get('intent_id', 'N/A')[:36]}")

                    results.append({
                        "iteration": iteration,
                        "scenario": scenario['name'],
                        "status_code": response.status_code,
                        "latency_ms": latency_ms,
                        "analysis": analysis,
                        "response": data
                    })
                else:
                    print(f"{RED}✗ Erro: {response.status_code}{RESET}")
                    results.append({
                        "iteration": iteration,
                        "scenario": scenario['name'],
                        "status_code": response.status_code,
                        "latency_ms": latency_ms,
                        "error": response.text
                    })

            except Exception as e:
                print(f"{RED}✗ Exceção: {e}{RESET}")
                results.append({
                    "iteration": iteration,
                    "scenario": scenario['name'],
                    "status_code": 0,
                    "error": str(e)
                })

            print()

        # Pausa entre iterações
        if iteration < NUM_TESTS:
            time.sleep(2)

    # Imprime resumo
    print_summary(results)

    # Salva resultados
    output_file = f"e2e-test-results-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Resultados salvos em: {output_file}")

    # Retorna código de saída
    success_rate = sum(1 for r in results if r['status_code'] == 200) / len(results)
    return 0 if success_rate > 0.8 else 1

if __name__ == "__main__":
    sys.exit(main())
