#!/usr/bin/env python3
"""
Script para gerar intenções de teste para coleta de feedbacks com intent_raw_text

Uso: python3 scripts/generate_test_intents.py [--count N]
"""

import argparse
import json
import uuid
import time
from datetime import datetime, timezone

# Configuração Kafka
KAFKA_BROKER = "neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
INTENT_TOPIC = "intentions.security"

# Lista de intenções de teste variadas
TEST_INTENTS = [
    {
        "text": "Create a new user account with email verification and password hashing",
        "domain": "security",
        "action": "create",
        "expected_decision": "approve"
    },
    {
        "text": "Delete all records from the users table without backup",
        "domain": "database",
        "action": "delete",
        "expected_decision": "reject"
    },
    {
        "text": "Add index to email column for improved query performance",
        "domain": "database",
        "action": "update",
        "expected_decision": "approve"
    },
    {
        "text": "Deploy the new feature to production without testing",
        "domain": "devops",
        "action": "deploy",
        "expected_decision": "reject"
    },
    {
        "text": "Run database backup before schema migration",
        "domain": "database",
        "action": "create",
        "expected_decision": "approve"
    },
    {
        "text": "Grant admin privileges to all authenticated users",
        "domain": "security",
        "action": "update",
        "expected_decision": "reject"
    },
    {
        "text": "Implement rate limiting for API endpoints to prevent abuse",
        "domain": "security",
        "action": "create",
        "expected_decision": "approve"
    },
    {
        "text": "Remove SSL certificate validation to speed up requests",
        "domain": "security",
        "action": "delete",
        "expected_decision": "reject"
    },
    {
        "text": "Create unit tests for the authentication module",
        "domain": "testing",
        "action": "create",
        "expected_decision": "approve"
    },
    {
        "text": "Drop the production database and recreate from scratch",
        "domain": "database",
        "action": "delete",
        "expected_decision": "reject"
    },
    {
        "text": "Enable two-factor authentication for all user accounts",
        "domain": "security",
        "action": "update",
        "expected_decision": "approve"
    },
    {
        "text": "Log all user passwords in plain text for debugging",
        "domain": "security",
        "action": "create",
        "expected_decision": "reject"
    },
    {
        "text": "Optimize database queries by adding appropriate indexes",
        "domain": "database",
        "action": "update",
        "expected_decision": "approve"
    },
    {
        "text": "Deploy container images with known vulnerabilities",
        "domain": "devops",
        "action": "deploy",
        "expected_decision": "reject"
    },
    {
        "text": "Set up automated security scanning in CI/CD pipeline",
        "domain": "devops",
        "action": "create",
        "expected_decision": "approve"
    },
    {
        "text": "Expose database port 27017 to public internet",
        "domain": "security",
        "action": "update",
        "expected_decision": "reject"
    },
]

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    print("Aviso: kafka-python não instalado. Usando modo simulação.")


def create_intent_envelope(test_intent):
    """Cria um IntentEnvelope a partir dos dados de teste"""
    intent_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    envelope = {
        "id": intent_id,
        "correlationId": correlation_id,
        "actor": {
            "id": "test-user-ml",
            "actor_type": "human",
            "name": "ML Test User"
        },
        "intent": {
            "text": test_intent["text"],
            "domain": test_intent["domain"].upper(),
            "classification": "request",
            "original_language": "pt-BR",
            "processed_text": test_intent["text"],
            "entities": [],
            "keywords": test_intent["text"].split()[:5]
        },
        "confidence": 0.95,
        "context": {
            "session_id": correlation_id,
            "user_id": "test-user-ml"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return envelope, intent_id, correlation_id


def send_intent_to_kafka(envelope):
    """Envia intenção para o Kafka"""
    if not KAFKA_AVAILABLE:
        print("  [SIMULAÇÃO] Intenção seria enviada ao Kafka")
        return True

    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            request_timeout_ms=10000
        )

        # Determinar tópico baseado no domínio
        topic = f"intentions.{envelope['intent']['domain'].lower()}"

        future = producer.send(topic, value=envelope)
        record_metadata = future.get(timeout=10)

        producer.flush()
        producer.close()

        print(f"  [KAFKA] Enviado para {topic} (partition: {record_metadata.partition}, offset: {record_metadata.offset})")
        return True
    except Exception as e:
        print(f"  [ERRO] Falha ao enviar para Kafka: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Gerar intenções de teste")
    parser.add_argument("--count", type=int, default=15, help="Número de intenções a gerar")
    parser.add_argument("--simulate", action="store_true", help="Simular sem enviar ao Kafka")
    args = parser.parse_args()

    print("=" * 60)
    print("GERADOR DE INTENÇÕES DE TESTE")
    print("=" * 60)
    print(f"Modo: {'SIMULAÇÃO' if args.simulate or not KAFKA_AVAILABLE else 'KAFKA REAL'}")
    print()

    count = min(args.count, len(TEST_INTENTS))
    created = []

    for i, test_intent in enumerate(TEST_INTENTS[:count]):
        print(f"{i+1}. {test_intent['text'][:60]}...")
        print(f"   Domínio: {test_intent['domain']} | Esperado: {test_intent['expected_decision']}")

        envelope, intent_id, correlation_id = create_intent_envelope(test_intent)

        if args.simulate or not KAFKA_AVAILABLE:
            print(f"   [SIMULAÇÃO] Intent ID: {intent_id}")
            created.append({
                "intent_id": intent_id,
                "correlation_id": correlation_id,
                "text": test_intent["text"],
                "expected_decision": test_intent["expected_decision"]
            })
        else:
            if send_intent_to_kafka(envelope):
                created.append({
                    "intent_id": intent_id,
                    "correlation_id": correlation_id,
                    "text": test_intent["text"],
                    "expected_decision": test_intent["expected_decision"]
                })

        time.sleep(0.5)  # Pequeno delay entre intenções
        print()

    print("=" * 60)
    print(f"CONCLUÍDO: {len(created)} intenções criadas")
    print()

    # Salvar lista para referência
    if created:
        with open("scripts/test_intents_created.json", "w") as f:
            json.dump(created, f, indent=2)
        print(f"Lista salva em: scripts/test_intents_created.json")
        print()
        print("Use este arquivo para referência ao aprovar/rejeitar planos.")
        print()
        print("Próximos passos:")
        print("1. Verifique se os planos foram criados: kubectl get planapprovals -n neural-hive")
        print("2. Aprove/rejeite os planos manualmente ou use script de aprovação")
        print("3. Verifique os feedbacks: python3 scripts/check_feedbacks.py")


if __name__ == "__main__":
    main()
