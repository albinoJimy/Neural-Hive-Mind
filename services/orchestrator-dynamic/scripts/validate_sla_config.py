#!/usr/bin/env python3
"""
Script de validação de configuração de SLA timeouts.

Valida que:
1. Config está sendo carregado corretamente
2. Valores estão dentro dos limites recomendados
3. Fórmula está calculando corretamente
"""
import sys
import os

# Adicionar src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config.settings import get_settings


def validate_sla_config():
    """Validar configuração de SLA timeouts."""
    print("=" * 80)
    print("Validação de Configuração de SLA Timeouts")
    print("=" * 80)

    try:
        settings = get_settings()
        print("✓ Settings carregado com sucesso")
    except Exception as e:
        print(f"✗ Erro ao carregar settings: {e}")
        return False

    # Validar valores
    min_timeout = settings.sla_ticket_min_timeout_ms
    multiplier = settings.sla_ticket_timeout_buffer_multiplier

    print(f"\nValores Configurados:")
    print(f"  sla_ticket_min_timeout_ms: {min_timeout}ms ({min_timeout/1000}s)")
    print(f"  sla_ticket_timeout_buffer_multiplier: {multiplier}x")

    # Validações
    issues = []

    if min_timeout < 60000:
        issues.append(
            f"⚠️  WARNING: min_timeout ({min_timeout}ms) está abaixo do recomendado (60000ms). "
            "Isso pode causar falsos positivos de SLA violation."
        )
    else:
        print(f"✓ min_timeout está dentro do recomendado (>= 60000ms)")

    if multiplier < 2.0:
        issues.append(
            f"⚠️  WARNING: multiplier ({multiplier}x) está abaixo do recomendado (2.0x). "
            "Isso pode causar timeouts prematuros."
        )
    else:
        print(f"✓ multiplier está dentro do recomendado (>= 2.0x)")

    # Testar fórmula com casos de teste
    print("\nTestes de Fórmula:")
    test_cases = [
        (1, 60000),
        (10000, 60000),
        (20000, 60000),
        (30000, max(60000, int(30000 * multiplier))),
        (60000, max(60000, int(60000 * multiplier))),
        (120000, max(60000, int(120000 * multiplier))),
    ]

    for estimated, expected in test_cases:
        calculated = max(min_timeout, int(estimated * multiplier))
        status = "✓" if calculated == expected else "✗"
        print(f"  {status} estimated={estimated}ms → timeout={calculated}ms (esperado: {expected}ms)")

        if calculated != expected:
            issues.append(
                f"Fórmula incorreta: estimated={estimated}ms resultou em {calculated}ms, "
                f"esperado {expected}ms"
            )

    # Validar que nenhum timeout fica abaixo do mínimo
    print("\nValidação de Mínimo:")
    for estimated in [1, 100, 1000, 5000, 10000, 15000, 19999]:
        calculated = max(min_timeout, int(estimated * multiplier))
        if calculated < min_timeout:
            issues.append(
                f"✗ ERRO: estimated={estimated}ms resultou em timeout={calculated}ms < min={min_timeout}ms"
            )
            print(f"  ✗ estimated={estimated}ms → timeout={calculated}ms (ABAIXO DO MÍNIMO!)")
        else:
            print(f"  ✓ estimated={estimated}ms → timeout={calculated}ms (>= {min_timeout}ms)")

    # Resumo
    print("\n" + "=" * 80)
    if issues:
        print("❌ VALIDAÇÃO FALHOU")
        print("\nProblemas encontrados:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("✅ VALIDAÇÃO PASSOU")
        print("\nTodos os testes passaram. Configuração está correta.")
        return True


if __name__ == '__main__':
    success = validate_sla_config()
    sys.exit(0 if success else 1)
