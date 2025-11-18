#!/usr/bin/env python3
"""
Teste de Fluxo Completo End-to-End - Neural Hive Mind
Valida o fluxo completo desde o gateway até os specialists
"""

import requests
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any, List

# Configurações
GATEWAY_URL = "http://10.97.189.184:8000"
TIMEOUT = 30

# Cores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_step(step: str, message: str):
    """Imprime passo do teste"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}[{step}]{Colors.RESET} {message}")

def print_success(message: str):
    """Imprime mensagem de sucesso"""
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")

def print_error(message: str):
    """Imprime mensagem de erro"""
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")

def print_info(message: str):
    """Imprime informação"""
    print(f"{Colors.CYAN}  {message}{Colors.RESET}")

def print_json(data: Dict[Any, Any]):
    """Imprime JSON formatado"""
    print(f"{Colors.YELLOW}{json.dumps(data, indent=2, ensure_ascii=False)}{Colors.RESET}")

def test_gateway_health() -> bool:
    """Testa health check do gateway"""
    print_step("1/5", "Verificando saúde do Gateway")

    try:
        response = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Gateway está saudável: {data.get('status')}")
            print_info(f"Timestamp: {data.get('timestamp')}")
            return True
        else:
            print_error(f"Gateway retornou status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Erro ao conectar no Gateway: {e}")
        return False

def send_intent(intent_text: str, specialist_type: str = None) -> Dict[Any, Any]:
    """Envia intenção para o gateway"""
    print_step("2/5", f"Enviando intenção: '{intent_text}'")

    payload = {
        "text": intent_text,
        "context": {
            "user_id": "test-user-e2e",
            "session_id": f"test-session-{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat()
        }
    }

    if specialist_type:
        payload["specialist_type"] = specialist_type

    print_info("Payload enviado:")
    print_json(payload)

    try:
        response = requests.post(
            f"{GATEWAY_URL}/intentions",
            json=payload,
            timeout=TIMEOUT
        )

        print_info(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print_success("Intenção processada com sucesso")
            return result
        else:
            print_error(f"Falha ao processar intenção: {response.status_code}")
            print_info(f"Response: {response.text}")
            return None

    except requests.Timeout:
        print_error(f"Timeout após {TIMEOUT} segundos")
        return None
    except Exception as e:
        print_error(f"Erro ao enviar intenção: {e}")
        return None

def verify_nlu_processing(result: Dict[Any, Any]) -> bool:
    """Verifica processamento NLU"""
    print_step("3/5", "Verificando processamento NLU")

    if not result:
        print_error("Nenhum resultado para verificar")
        return False

    # Verifica campos essenciais de NLU
    nlu_fields = ["intent", "entities", "confidence"]
    missing_fields = []

    for field in nlu_fields:
        if field in result:
            print_success(f"Campo '{field}' presente")
            if field == "intent":
                print_info(f"  Intent detectado: {result[field]}")
            elif field == "confidence":
                print_info(f"  Confiança: {result[field]}")
            elif field == "entities" and result[field]:
                print_info(f"  Entidades: {result[field]}")
        else:
            missing_fields.append(field)

    if missing_fields:
        print_error(f"Campos NLU faltando: {missing_fields}")
        return False

    print_success("Processamento NLU validado")
    return True

def verify_specialist_routing(result: Dict[Any, Any], expected_specialist: str = None) -> bool:
    """Verifica roteamento para specialist"""
    print_step("4/5", "Verificando roteamento para Specialist")

    if not result:
        print_error("Nenhum resultado para verificar")
        return False

    # Verifica specialist usado
    if "specialist" in result:
        specialist = result["specialist"]
        print_success(f"Specialist identificado: {specialist}")

        if expected_specialist and specialist != expected_specialist:
            print_error(f"Expected: {expected_specialist}, Got: {specialist}")
            return False

        return True
    elif "routed_to" in result:
        specialist = result["routed_to"]
        print_success(f"Roteado para: {specialist}")
        return True
    else:
        print_error("Informação de roteamento não encontrada")
        return False

def verify_end_to_end_response(result: Dict[Any, Any]) -> bool:
    """Verifica resposta end-to-end completa"""
    print_step("5/5", "Validando resposta End-to-End")

    if not result:
        print_error("Nenhum resultado para verificar")
        return False

    print_info("Resposta completa recebida:")
    print_json(result)

    # Verifica presença de resposta
    has_response = False

    if "response" in result and result["response"]:
        print_success(f"Resposta presente: {result['response'][:100]}...")
        has_response = True
    elif "answer" in result and result["answer"]:
        print_success(f"Resposta presente: {result['answer'][:100]}...")
        has_response = True
    elif "message" in result and result["message"]:
        print_success(f"Mensagem presente: {result['message'][:100]}...")
        has_response = True

    # Verifica metadata
    if "metadata" in result:
        print_success("Metadata presente")
        metadata = result["metadata"]
        if "processing_time" in metadata:
            print_info(f"  Tempo de processamento: {metadata['processing_time']}")

    # Verifica timestamp
    if "timestamp" in result:
        print_success(f"Timestamp: {result['timestamp']}")

    return has_response

def run_test_scenario(intent_text: str, specialist_type: str = None, description: str = None):
    """Executa um cenário de teste completo"""
    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
    if description:
        print(f"{Colors.BOLD}{Colors.CYAN}CENÁRIO: {description}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")

    # 1. Health check
    if not test_gateway_health():
        print_error("Gateway não está saudável. Abortando teste.")
        return False

    time.sleep(1)

    # 2. Enviar intenção
    result = send_intent(intent_text, specialist_type)
    if not result:
        print_error("Falha ao processar intenção. Abortando teste.")
        return False

    time.sleep(1)

    # 3. Verificar NLU
    nlu_ok = verify_nlu_processing(result)

    time.sleep(1)

    # 4. Verificar roteamento
    routing_ok = verify_specialist_routing(result, specialist_type)

    time.sleep(1)

    # 5. Verificar resposta completa
    response_ok = verify_end_to_end_response(result)

    # Resultado final
    print(f"\n{Colors.BOLD}RESULTADO DO CENÁRIO:{Colors.RESET}")
    if nlu_ok and routing_ok and response_ok:
        print_success("TESTE PASSOU ✓")
        return True
    else:
        print_error("TESTE FALHOU ✗")
        print_info(f"NLU: {'✓' if nlu_ok else '✗'}")
        print_info(f"Roteamento: {'✓' if routing_ok else '✗'}")
        print_info(f"Resposta: {'✓' if response_ok else '✗'}")
        return False

def main():
    """Função principal"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}TESTE DE FLUXO COMPLETO END-TO-END - NEURAL HIVE MIND{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    # Cenários de teste
    scenarios = [
        {
            "intent": "Preciso criar uma API REST com autenticação JWT",
            "specialist": "business",
            "description": "Teste 1: Intenção de negócio (Business Specialist)"
        },
        {
            "intent": "Como otimizar performance deste algoritmo de ordenação?",
            "specialist": "technical",
            "description": "Teste 2: Questão técnica (Technical Specialist)"
        },
        {
            "intent": "Qual o melhor padrão de design para este sistema distribuído?",
            "specialist": "architecture",
            "description": "Teste 3: Arquitetura (Architecture Specialist)"
        },
        {
            "intent": "Quais são as melhores práticas para code review?",
            "specialist": "behavior",
            "description": "Teste 4: Práticas de desenvolvimento (Behavior Specialist)"
        },
        {
            "intent": "Como evoluir este microserviço mantendo compatibilidade?",
            "specialist": "evolution",
            "description": "Teste 5: Evolução de sistema (Evolution Specialist)"
        }
    ]

    results = []

    for scenario in scenarios:
        result = run_test_scenario(
            scenario["intent"],
            scenario.get("specialist"),
            scenario.get("description")
        )
        results.append({
            "scenario": scenario.get("description"),
            "passed": result
        })
        time.sleep(2)  # Pausa entre cenários

    # Relatório final
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}RELATÓRIO FINAL{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    for i, result in enumerate(results, 1):
        status = f"{Colors.GREEN}PASSOU{Colors.RESET}" if result["passed"] else f"{Colors.RED}FALHOU{Colors.RESET}"
        print(f"{i}. {result['scenario']}: {status}")

    print(f"\n{Colors.BOLD}Total: {passed}/{total} cenários passaram{Colors.RESET}")

    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ TODOS OS TESTES PASSARAM!{Colors.RESET}")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ ALGUNS TESTES FALHARAM{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
