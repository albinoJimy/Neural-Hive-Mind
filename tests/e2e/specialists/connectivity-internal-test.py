#!/usr/bin/env python3
"""
Teste de conectividade interna entre specialists
Execute este script dentro de um pod specialist
"""
import socket
import sys
from datetime import datetime

SPECIALISTS = {
    'business': 'specialist-business.specialist-business.svc.cluster.local',
    'behavior': 'specialist-behavior.specialist-behavior.svc.cluster.local',
    'evolution': 'specialist-evolution.specialist-evolution.svc.cluster.local',
    'architecture': 'specialist-architecture.specialist-architecture.svc.cluster.local',
    'technical': 'specialist-technical.specialist-technical.svc.cluster.local',
}

PORTS = {
    'gRPC': 50051,
    'HTTP': 8000,
    'Prometheus': 8080,
}

def test_port(host, port, timeout=2):
    """Testa se uma porta está acessível"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        return False

def main():
    print("=" * 60)
    print("Teste de Conectividade Interna - Specialists")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    print()

    total_tests = 0
    passed_tests = 0

    for spec_name, spec_host in SPECIALISTS.items():
        print(f"{'='*60}")
        print(f"Testando: {spec_name}")
        print(f"Host: {spec_host}")
        print(f"{'='*60}")

        for port_name, port_num in PORTS.items():
            total_tests += 1
            if test_port(spec_host, port_num):
                print(f"  ✓ {port_name:12s} (porta {port_num}): ACESSÍVEL")
                passed_tests += 1
            else:
                print(f"  ✗ {port_name:12s} (porta {port_num}): INACESSÍVEL")

        print()

    # Resumo
    print("=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"Total de testes: {total_tests}")
    print(f"Passaram: {passed_tests}")
    print(f"Falharam: {total_tests - passed_tests}")
    print(f"Taxa de sucesso: {(passed_tests * 100 / total_tests):.1f}%")
    print()

    if passed_tests == total_tests:
        print("✓ TODOS OS TESTES PASSARAM!")
        return 0
    else:
        print("✗ ALGUNS TESTES FALHARAM")
        return 1

if __name__ == "__main__":
    sys.exit(main())
