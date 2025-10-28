#!/usr/bin/env python3
"""
Script para simular pipeline completo de incidentes E1-E6

Simula diferentes tipos de incidentes e mostra o fluxo completo de processamento.

Uso:
    python scripts/simulate_incident_pipeline.py [--incident-type TYPE]

Tipos de incidente:
    - unauthorized_access
    - dos_attack
    - resource_abuse
    - malicious_payload
    - data_exfiltration
"""
import asyncio
import argparse
import json
from datetime import datetime, timezone
from typing import Dict, Any

# Mock clients para simulação
class MockRedisClient:
    async def set(self, key: str, value: str, ex: int = None):
        print(f"[Redis] SET {key} (TTL: {ex}s)")

    async def get(self, key: str):
        print(f"[Redis] GET {key}")
        return None


class MockMongoDBClient:
    def __init__(self):
        self.incidents_collection = self
        self.remediation_collection = self

    async def insert_one(self, document: Dict[str, Any]):
        print(f"[MongoDB] INSERT: {document.get('incident_id', 'N/A')}")

    async def update_one(self, filter_doc, update_doc, upsert=False):
        print(f"[MongoDB] UPDATE: {filter_doc}")


class MockKubernetesClient:
    def is_healthy(self):
        return True


# Importar componentes
import sys
sys.path.insert(0, '/home/jimy/Base/Neural-Hive-Mind/services/guard-agents')

from src.services.threat_detector import ThreatDetector
from src.services.incident_classifier import IncidentClassifier
from src.services.policy_enforcer import PolicyEnforcer
from src.services.remediation_coordinator import RemediationCoordinator
from src.services.incident_orchestrator import IncidentOrchestrator


def create_incident_event(incident_type: str) -> Dict[str, Any]:
    """Cria evento baseado no tipo de incidente"""
    events = {
        "unauthorized_access": {
            "type": "authentication",
            "event_id": f"evt-{incident_type}-001",
            "user_id": "attacker-001",
            "failed_attempts": 15,
            "source_ip": "192.168.1.100",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "dos_attack": {
            "type": "request_metrics",
            "event_id": f"evt-{incident_type}-001",
            "requests_per_minute": 10000,
            "source": "external-lb",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "resource_abuse": {
            "type": "resource_metrics",
            "event_id": f"evt-{incident_type}-001",
            "metrics": {
                "cpu_usage": 0.95,
                "memory_usage": 0.92,
            },
            "resource_name": "pod-critical-001",
            "namespace": "production",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "malicious_payload": {
            "type": "request",
            "event_id": f"evt-{incident_type}-001",
            "payload": "SELECT * FROM users WHERE '1'='1' OR DROP TABLE users;",
            "source_ip": "10.0.0.1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "data_exfiltration": {
            "type": "network",
            "event_id": f"evt-{incident_type}-001",
            "data_size_mb": 500,
            "destination": "unknown-external-host",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    return events.get(incident_type, events["unauthorized_access"])


async def simulate_incident_pipeline(incident_type: str):
    """Simula pipeline completo de incidente"""
    print("=" * 80)
    print(f"SIMULAÇÃO DE INCIDENTE: {incident_type.upper()}")
    print("=" * 80)
    print()

    # Inicializar componentes com mocks
    redis_client = MockRedisClient()
    mongodb_client = MockMongoDBClient()
    k8s_client = MockKubernetesClient()

    threat_detector = ThreatDetector(redis_client=redis_client)
    incident_classifier = IncidentClassifier(mongodb_client=mongodb_client)
    policy_enforcer = PolicyEnforcer(k8s_client=k8s_client, redis_client=redis_client)
    remediation_coordinator = RemediationCoordinator(
        k8s_client=k8s_client,
        mongodb_client=mongodb_client,
        kafka_producer=None
    )

    orchestrator = IncidentOrchestrator(
        threat_detector=threat_detector,
        incident_classifier=incident_classifier,
        policy_enforcer=policy_enforcer,
        remediation_coordinator=remediation_coordinator,
        mongodb_client=mongodb_client,
        kafka_producer=None
    )

    # Criar evento
    event = create_incident_event(incident_type)
    context = {
        "environment": "production",
        "is_critical_resource": True,
    }

    print("📥 EVENTO RECEBIDO:")
    print(json.dumps(event, indent=2))
    print()

    # Processar através do fluxo E1-E6
    print("🔄 PROCESSANDO FLUXO E1-E6...")
    print()

    result = await orchestrator.process_incident_flow(event, context)

    # Exibir resultados
    print()
    print("=" * 80)
    print("📊 RESULTADO DO FLUXO COMPLETO")
    print("=" * 80)
    print()

    if result.get("incident_detected") is False:
        print("✅ NENHUM INCIDENTE DETECTADO")
        print(f"   Duração: {result['duration_ms']:.2f}ms")
        return

    # E1: Detecção
    print("🔍 E1: DETECÇÃO DE ANOMALIA")
    e1 = result.get("e1_anomaly", {})
    print(f"   Tipo de Ameaça: {e1.get('threat_type')}")
    print(f"   Severidade Base: {e1.get('severity')}")
    print(f"   Confiança: {e1.get('confidence'):.2%}")
    print()

    # E2: Classificação
    print("📋 E2: CLASSIFICAÇÃO DE SEVERIDADE")
    e2 = result.get("e2_classification", {})
    print(f"   Severidade Final: {e2.get('severity')}")
    print(f"   Runbook ID: {e2.get('runbook_id')}")
    print(f"   Prioridade: {e2.get('priority')}")
    print()

    # E3: Enforcement
    print("🛡️  E3: ENFORCEMENT DE POLÍTICAS")
    e3 = result.get("e3_enforcement", {})
    print(f"   Sucesso: {'✅' if e3.get('success') else '❌'}")
    print(f"   Ações Executadas: {e3.get('actions_count', 0)}")
    print()

    # E4: Remediação
    print("🔧 E4: REMEDIAÇÃO AUTOMATIZADA")
    e4 = result.get("e4_remediation", {})
    print(f"   Remediação ID: {e4.get('remediation_id')}")
    print(f"   Status: {e4.get('status')}")
    print()

    # E5: Validação SLA
    print("⏱️  E5: VALIDAÇÃO DE SLA")
    e5 = result.get("e5_sla_validation", {})
    recovery_time = e5.get("recovery_time_s", 0)
    mttr_target = e5.get("mttr_target_s", 90)
    sla_met = e5.get("sla_met")

    print(f"   SLA Atendido: {'✅' if sla_met else '❌'}")
    print(f"   Tempo de Recuperação: {recovery_time:.2f}s")
    print(f"   Target MTTR: {mttr_target}s")

    if not sla_met:
        print(f"   ⚠️  Issues: {', '.join(e5.get('issues', []))}")
    print()

    # E6: Lições Aprendidas
    print("📚 E6: LIÇÕES APRENDIDAS")
    e6 = result.get("e6_lessons_learned", {})
    print(f"   Resumo: {e6.get('summary')}")
    print(f"   Causa Raiz: {e6.get('root_cause')}")
    print(f"   Recomendações: {len(e6.get('recommendations', []))}")
    print()

    # Métricas Gerais
    print("📈 MÉTRICAS")
    print(f"   Incident ID: {result.get('incident_id')}")
    print(f"   Duração Total: {result['duration_ms']:.2f}ms")
    print(f"   Timestamp: {result.get('completed_at')}")
    print()

    print("=" * 80)


async def main():
    parser = argparse.ArgumentParser(
        description="Simula pipeline completo de incidentes E1-E6"
    )
    parser.add_argument(
        "--incident-type",
        type=str,
        default="unauthorized_access",
        choices=[
            "unauthorized_access",
            "dos_attack",
            "resource_abuse",
            "malicious_payload",
            "data_exfiltration",
        ],
        help="Tipo de incidente a simular"
    )

    args = parser.parse_args()

    await simulate_incident_pipeline(args.incident_type)


if __name__ == "__main__":
    asyncio.run(main())
