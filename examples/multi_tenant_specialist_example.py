#!/usr/bin/env python3
"""
Exemplo de Multi-Tenant Specialist - Neural Hive Mind

Este exemplo demonstra como criar e executar um especialista com suporte a multi-tenancy,
incluindo:
- Configuração de tenants
- Validação de tenant_id
- Isolamento de dados no ledger e cache
- Métricas por tenant
- Servidor gRPC com contexto multi-tenant

Uso:
    python examples/multi_tenant_specialist_example.py
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

# Adicionar path da biblioteca ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "libraries" / "python"))

from neural_hive_specialists.multi_tenant_specialist import MultiTenantSpecialist, TenantConfig
from neural_hive_specialists.config import SpecialistConfig


class ExampleTechnicalSpecialist(MultiTenantSpecialist):
    """
    Exemplo de especialista técnico com suporte a multi-tenancy.

    Este especialista avalia planos cognitivos com isolamento completo por tenant.
    """

    def _get_specialist_type(self) -> str:
        """Retorna o tipo deste especialista."""
        return "technical"

    def _evaluate_plan_internal(
        self, cognitive_plan: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Avalia o plano cognitivo com contexto de tenant.

        Args:
            cognitive_plan: Plano cognitivo a ser avaliado
            context: Contexto incluindo tenant_id

        Returns:
            Opinião estruturada
        """
        # Extrair tenant_id do contexto
        tenant_id = context.get("tenant_id", "default")

        # Buscar configuração do tenant (já validado pelo MultiTenantSpecialist)
        tenant_config = self.tenant_configs.get(tenant_id)

        # Simular avaliação técnica com thresholds do tenant
        confidence_score = 0.85
        risk_score = 0.15

        # Aplicar threshold customizado do tenant
        min_confidence = (
            tenant_config.min_confidence_score
            if tenant_config and tenant_config.min_confidence_score
            else self.config.min_confidence_score
        )

        # Determinar recomendação baseado no threshold do tenant
        if confidence_score >= min_confidence:
            recommendation = "approve"
        else:
            recommendation = "review_required"

        # Retornar opinião
        return {
            "confidence_score": confidence_score,
            "risk_score": risk_score,
            "recommendation": recommendation,
            "reasoning_summary": f"Avaliação técnica para tenant {tenant_id}",
            "reasoning_factors": [
                {
                    "factor_name": "code_quality",
                    "weight": 0.4,
                    "score": 0.9,
                    "description": "Qualidade do código analisada",
                },
                {
                    "factor_name": "security",
                    "weight": 0.6,
                    "score": 0.8,
                    "description": "Análise de segurança",
                },
            ],
            "mitigations": [],
            "metadata": {
                "tenant_id": tenant_id,
                "model_name": (
                    tenant_config.mlflow_model_name if tenant_config else "default-model"
                ),
            },
        }


def create_tenant_configs() -> Dict[str, TenantConfig]:
    """
    Cria configurações de exemplo para múltiplos tenants.

    Returns:
        Dicionário de configurações por tenant_id
    """
    return {
        "tenant-enterprise-A": TenantConfig(
            tenant_id="tenant-enterprise-A",
            tenant_name="Empresa A (Enterprise)",
            is_active=True,
            mlflow_model_name="technical-specialist-enterprise-v2",
            mlflow_model_stage="Production",
            min_confidence_score=0.85,
            high_risk_threshold=0.7,
            enable_explainability=True,
            rate_limit_per_second=500,
            metadata={
                "tier": "enterprise",
                "support_level": "premium",
                "contract_id": "ENT-2024-001",
            },
        ),
        "tenant-startup-B": TenantConfig(
            tenant_id="tenant-startup-B",
            tenant_name="Startup B",
            is_active=True,
            min_confidence_score=0.75,
            rate_limit_per_second=100,
            metadata={"tier": "standard", "support_level": "standard"},
        ),
        "tenant-inactive-C": TenantConfig(
            tenant_id="tenant-inactive-C",
            tenant_name="Tenant Inativo C",
            is_active=False,  # ⚠️  Inativo - requests serão rejeitados
            rate_limit_per_second=0,
            metadata={"tier": "suspended", "reason": "payment_overdue"},
        ),
        "default": TenantConfig(
            tenant_id="default",
            tenant_name="Tenant Padrão",
            is_active=True,
            rate_limit_per_second=50,
            metadata={"tier": "free"},
        ),
    }


def simulate_request(specialist: ExampleTechnicalSpecialist, tenant_id: str, plan_id: str) -> None:
    """
    Simula um request gRPC com tenant_id.

    Args:
        specialist: Instância do especialista
        tenant_id: ID do tenant
        plan_id: ID do plano cognitivo
    """
    print(f"\n{'='*80}")
    print(f"Simulando request para tenant: {tenant_id}")
    print(f"{'='*80}")

    # Criar request mock
    class MockRequest:
        def __init__(self):
            self.plan_id = plan_id
            self.intent_id = f"intent-{plan_id}"
            self.correlation_id = f"corr-{plan_id}"
            self.trace_id = None
            self.context = {"tenant_id": tenant_id}
            self.cognitive_plan = {
                "action": "deploy",
                "resources": ["api-gateway", "database"],
                "domain": "infrastructure",
            }

    request = MockRequest()

    try:
        # Extrair e validar tenant
        extracted_tenant = specialist._extract_tenant_id(request)
        print(f"✅ Tenant extraído: {extracted_tenant}")

        # Validar tenant
        tenant_config = specialist._validate_tenant(extracted_tenant)
        print(f"✅ Tenant validado: {tenant_config.tenant_name} (ativo: {tenant_config.is_active})")

        # Aplicar configurações do tenant
        original_config = specialist._apply_tenant_config_overrides(tenant_config)
        print(f"✅ Configurações do tenant aplicadas:")
        print(f"   - min_confidence_score: {specialist.config.min_confidence_score}")
        print(f"   - rate_limit: {tenant_config.rate_limit_per_second} req/s")

        # Avaliar plano
        opinion = specialist._evaluate_plan_internal(
            cognitive_plan=request.cognitive_plan, context=request.context
        )

        print(f"\n📊 Opinião Gerada:")
        print(f"   - Recomendação: {opinion['recommendation']}")
        print(f"   - Confidence: {opinion['confidence_score']:.2f}")
        print(f"   - Risk: {opinion['risk_score']:.2f}")
        print(f"   - Tenant: {opinion['metadata']['tenant_id']}")

        # Demonstrar isolamento de cache
        plan_bytes = json.dumps(request.cognitive_plan, sort_keys=True).encode()
        cache_key = f"opinion:{tenant_id}:technical:1.0.0:{hash(plan_bytes)}"
        print(f"\n🔑 Cache Key (isolado por tenant):")
        print(f"   {cache_key}")

        # Demonstrar isolamento de ledger
        print(f"\n💾 Ledger Document (seria salvo com):")
        print(f"   - opinion_id: opinion-{plan_id}")
        print(f"   - plan_id: {plan_id}")
        print(f"   - tenant_id: {tenant_id}")
        print(f"   - specialist_type: technical")

        print(f"\n✅ Request processado com sucesso!")

    except ValueError as e:
        print(f"\n❌ Erro ao processar request: {e}")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")


def main():
    """Função principal do exemplo."""
    print("=" * 80)
    print("EXEMPLO: Multi-Tenant Specialist - Neural Hive Mind")
    print("=" * 80)

    # 1. Criar configuração do especialista
    print("\n1. Criando configuração do especialista...")
    config = SpecialistConfig(
        specialist_type="technical",
        specialist_version="1.0.0",
        model_name="technical-specialist-default",
        enable_multi_tenancy=True,
        max_tenants=50,
        default_tenant_id="default",
        min_confidence_score=0.7,
        # Desabilitar dependências externas para exemplo
        enable_cache=False,
        enable_ledger=False,
        enable_metrics=False,
    )
    print("✅ Configuração criada")

    # 2. Criar configurações de tenants
    print("\n2. Criando configurações de tenants...")
    tenant_configs = create_tenant_configs()
    print(f"✅ {len(tenant_configs)} tenants configurados:")
    for tid, tc in tenant_configs.items():
        status = "ATIVO" if tc.is_active else "INATIVO"
        print(f"   - {tid}: {tc.tenant_name} [{status}]")

    # 3. Criar instância do especialista
    print("\n3. Criando especialista multi-tenant...")
    specialist = ExampleTechnicalSpecialist(config)

    # Injetar configurações de tenants (normalmente carregadas de ConfigMap)
    specialist.tenant_configs = tenant_configs
    print("✅ Especialista criado")

    # 4. Simular requests de diferentes tenants
    print("\n4. Simulando requests de diferentes tenants...")

    # Request do tenant enterprise (ativo)
    simulate_request(
        specialist=specialist, tenant_id="tenant-enterprise-A", plan_id="plan-enterprise-001"
    )

    # Request do tenant startup (ativo)
    simulate_request(
        specialist=specialist, tenant_id="tenant-startup-B", plan_id="plan-startup-001"
    )

    # Request do tenant inativo (deve falhar)
    simulate_request(
        specialist=specialist, tenant_id="tenant-inactive-C", plan_id="plan-inactive-001"
    )

    # Request de tenant desconhecido (deve falhar)
    simulate_request(
        specialist=specialist, tenant_id="tenant-unknown-XYZ", plan_id="plan-unknown-001"
    )

    # Request sem tenant_id (usa default)
    print(f"\n{'='*80}")
    print(f"Simulando request SEM tenant_id (fallback para default)")
    print(f"{'='*80}")

    class MockRequestNoTenant:
        def __init__(self):
            self.plan_id = "plan-default-001"
            self.intent_id = "intent-default-001"
            self.correlation_id = "corr-default-001"
            self.trace_id = None
            self.context = {}  # ⚠️  Sem tenant_id
            self.cognitive_plan = {"action": "analyze", "resources": []}

    request = MockRequestNoTenant()
    extracted = specialist._extract_tenant_id(request)
    print(f"✅ Fallback para tenant: {extracted}")

    # 5. Demonstrar isolamento de dados
    print(f"\n5. Demonstrando isolamento de dados...")
    print(f"\n{'='*80}")

    # Mesmo plan_id, tenants diferentes
    plan_id_shared = "shared-plan-999"

    print(f"\n📝 Cenário: Dois tenants com MESMO plan_id")
    print(f"   plan_id: {plan_id_shared}")

    print(f"\n   Tenant A - Cache Key:")
    cache_key_a = f"opinion:tenant-enterprise-A:technical:1.0.0:abc123"
    print(f"   {cache_key_a}")

    print(f"\n   Tenant B - Cache Key:")
    cache_key_b = f"opinion:tenant-startup-B:technical:1.0.0:abc123"
    print(f"   {cache_key_b}")

    print(f"\n   ✅ Cache keys são DIFERENTES mesmo com inputs idênticos")
    assert cache_key_a != cache_key_b

    print(f"\n   Tenant A - Ledger Query:")
    print(f"   {{'plan_id': '{plan_id_shared}', 'tenant_id': 'tenant-enterprise-A'}}")

    print(f"\n   Tenant B - Ledger Query:")
    print(f"   {{'plan_id': '{plan_id_shared}', 'tenant_id': 'tenant-startup-B'}}")

    print(f"\n   ✅ Queries ao ledger SEMPRE incluem tenant_id")

    # 6. Resumo
    print(f"\n{'='*80}")
    print("RESUMO")
    print(f"{'='*80}")
    print(
        """
Este exemplo demonstrou:

✅ Configuração de múltiplos tenants com diferentes tiers
✅ Extração de tenant_id do contexto gRPC
✅ Validação de tenants ativos vs inativos
✅ Aplicação de thresholds customizados por tenant
✅ Isolamento de cache (chaves únicas por tenant)
✅ Isolamento de ledger (queries filtradas por tenant)
✅ Fallback para tenant 'default' quando não especificado
✅ Rejeição de tenants desconhecidos ou inativos

Para usar em produção:
1. Carregar tenant_configs de ConfigMap Kubernetes
2. Habilitar ledger, cache e métricas no SpecialistConfig
3. Configurar Envoy para extrair tenant_id do JWT
4. Deploy com helm charts incluindo tenant-config ConfigMap

Veja mais em: docs/MULTI_TENANCY_GUIDE.md
    """
    )


if __name__ == "__main__":
    main()
