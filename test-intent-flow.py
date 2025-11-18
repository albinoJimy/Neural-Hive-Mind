#!/usr/bin/env python3
"""
Teste de Fluxo Completo de Intent Envelope - Neural Hive-Mind Fase 1
Este script testa o fluxo completo de dados desde a criação de uma intenção
até o armazenamento em Redis e publicação no Kafka.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

def create_intent_envelope(
    text: str,
    domain: str = "BUSINESS",
    actor_id: str = "test-user-001",
    priority: str = "NORMAL"
) -> Dict[str, Any]:
    """
    Cria um Intent Envelope válido conforme schema Avro.

    Args:
        text: Texto da intenção
        domain: Domínio (BUSINESS, TECHNICAL, INFRASTRUCTURE, SECURITY)
        actor_id: ID do ator
        priority: Prioridade (LOW, NORMAL, HIGH, CRITICAL)

    Returns:
        Dict com Intent Envelope completo
    """
    now = int(datetime.now(timezone.utc).timestamp() * 1000)  # Unix timestamp em ms
    intent_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex[:32]
    span_id = uuid.uuid4().hex[:16]

    intent_envelope = {
        "id": intent_id,
        "version": "1.0.0",
        "correlationId": correlation_id,
        "traceId": trace_id,
        "spanId": span_id,
        "actor": {
            "id": actor_id,
            "actorType": "HUMAN",
            "name": "Test User"
        },
        "intent": {
            "text": text,
            "domain": domain,
            "classification": "feature-request",
            "originalLanguage": "pt-BR",
            "processedText": text,
            "entities": [],
            "keywords": text.lower().split()[:10]  # Primeiras 10 palavras
        },
        "confidence": 0.85,
        "context": {
            "sessionId": f"sess_{uuid.uuid4().hex[:16]}",
            "userId": actor_id,
            "tenantId": "neural-hive-test",
            "channel": "API",
            "userAgent": "Python Test Client 1.0",
            "clientIp": "127.0.0.1",
            "geolocation": {
                "country": "BR",
                "region": "SP",
                "city": "São Paulo",
                "timezone": "America/Sao_Paulo"
            }
        },
        "constraints": {
            "priority": priority,
            "deadline": None,
            "maxRetries": 3,
            "timeoutMs": 30000,
            "requiredCapabilities": ["semantic-translation", "risk-analysis"],
            "securityLevel": "INTERNAL"
        },
        "qos": {
            "deliveryMode": "EXACTLY_ONCE",
            "durability": "PERSISTENT",
            "consistency": "STRONG"
        },
        "timestamp": now,
        "schemaVersion": 1,
        "metadata": {
            "source": "automated-test",
            "test_id": f"test_{uuid.uuid4().hex[:8]}"
        }
    }

    return intent_envelope


def test_kafka_connection():
    """Testa conexão com Kafka."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "kafka", "kafka-broker-api-versions",
             "--bootstrap-server", "localhost:9092"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Erro testando Kafka: {e}")
        return False


def test_redis_connection():
    """Testa conexão com Redis."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "redis", "redis-cli", "ping"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() == "PONG"
    except Exception as e:
        print(f"Erro testando Redis: {e}")
        return False


def publish_to_kafka_json(topic: str, message: Dict[str, Any]):
    """
    Publica mensagem JSON no Kafka usando kafka-console-producer.

    Args:
        topic: Nome do tópico
        message: Mensagem em formato dict
    """
    import subprocess

    message_json = json.dumps(message, ensure_ascii=False)

    try:
        process = subprocess.Popen(
            ["docker", "exec", "-i", "kafka", "kafka-console-producer",
             "--bootstrap-server", "localhost:9092",
             "--topic", topic],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = process.communicate(input=message_json, timeout=10)

        if process.returncode == 0:
            return True, None
        else:
            return False, stderr
    except Exception as e:
        return False, str(e)


def store_in_redis(key: str, value: str):
    """
    Armazena valor no Redis.

    Args:
        key: Chave
        value: Valor
    """
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "exec", "redis", "redis-cli", "SET", key, value],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() == "OK"
    except Exception as e:
        print(f"Erro armazenando no Redis: {e}")
        return False


def retrieve_from_redis(key: str) -> str:
    """
    Recupera valor do Redis.

    Args:
        key: Chave

    Returns:
        Valor armazenado
    """
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "exec", "redis", "redis-cli", "GET", key],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Erro recuperando do Redis: {e}")
        return None


def main():
    """Executa teste completo de fluxo de dados."""

    print("=" * 70)
    print(" TESTE DE FLUXO COMPLETO - NEURAL HIVE-MIND FASE 1")
    print("=" * 70)
    print()

    # 1. Verificar conectividade
    print("1. Verificando conectividade dos componentes...")
    kafka_ok = test_kafka_connection()
    redis_ok = test_redis_connection()

    print(f"   Kafka: {'✓ OK' if kafka_ok else '✗ FALHOU'}")
    print(f"   Redis: {'✓ OK' if redis_ok else '✗ FALHOU'}")
    print()

    if not (kafka_ok and redis_ok):
        print("❌ Erro: Componentes não estão disponíveis. Execute:")
        print("   docker compose -f docker-compose-test.yml up -d")
        return 1

    # 2. Criar Intent Envelopes de teste
    print("2. Criando Intent Envelopes de teste...")

    test_intents = [
        ("Criar uma API REST para gerenciamento de usuários", "TECHNICAL", "HIGH"),
        ("Analisar métricas de performance do último trimestre", "BUSINESS", "NORMAL"),
        ("Implementar autenticação OAuth2 no sistema", "SECURITY", "HIGH"),
    ]

    results = []

    for text, domain, priority in test_intents:
        envelope = create_intent_envelope(text, domain, priority=priority)
        intent_id = envelope["id"]

        print(f"\n   Intent ID: {intent_id}")
        print(f"   Domain: {domain}, Priority: {priority}")
        print(f"   Text: {text[:50]}...")

        # 3. Armazenar metadata no Redis
        redis_key = f"intent:{intent_id}:metadata"
        metadata = json.dumps({
            "id": intent_id,
            "domain": domain,
            "priority": priority,
            "created_at": envelope["timestamp"],
            "status": "published"
        })

        redis_stored = store_in_redis(redis_key, metadata)
        print(f"   Redis Storage: {'✓' if redis_stored else '✗'}")

        # 4. Publicar no Kafka
        success, error = publish_to_kafka_json("intents.raw", envelope)
        print(f"   Kafka Publish: {'✓' if success else f'✗ ({error})'}")

        results.append({
            "intent_id": intent_id,
            "domain": domain,
            "redis_ok": redis_stored,
            "kafka_ok": success
        })

        time.sleep(0.5)  # Evitar sobrecarga

    # 5. Verificar armazenamento no Redis
    print("\n3. Verificando dados armazenados no Redis...")
    for result in results:
        intent_id = result["intent_id"]
        redis_key = f"intent:{intent_id}:metadata"
        stored_value = retrieve_from_redis(redis_key)

        if stored_value and stored_value != "(nil)":
            metadata = json.loads(stored_value)
            print(f"   ✓ {intent_id[:8]}... - Domain: {metadata['domain']}")
        else:
            print(f"   ✗ {intent_id[:8]}... - Não encontrado")

    # 6. Sumário final
    print("\n" + "=" * 70)
    print(" RESUMO DO TESTE")
    print("=" * 70)

    total = len(results)
    redis_success = sum(1 for r in results if r["redis_ok"])
    kafka_success = sum(1 for r in results if r["kafka_ok"])

    print(f"\nTotal de Intent Envelopes criados: {total}")
    print(f"Redis: {redis_success}/{total} sucessos ({redis_success/total*100:.0f}%)")
    print(f"Kafka: {kafka_success}/{total} sucessos ({kafka_success/total*100:.0f}%)")

    if redis_success == total and kafka_success == total:
        print("\n✅ TESTE COMPLETO: APROVADO")
        print("   Fluxo de dados funcionando corretamente!")
        return 0
    else:
        print("\n⚠️  TESTE COMPLETO: APROVADO COM RESSALVAS")
        print("   Alguns componentes falharam.")
        return 1


if __name__ == "__main__":
    exit(main())
